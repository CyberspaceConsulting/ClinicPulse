from contextlib import asynccontextmanager
import asyncio
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
import platform
import secrets
import smtplib
import time as time_module
import urllib.error
import urllib.request

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit as _audit
from . import models
from .invitations import (
    MailConfiguration,
    environment_mail_configuration,
    send_invitation,
    send_test_email,
)
from .plan_archive import archive_scheduler, router as archive_router, settings_router as archive_settings_router
from .database import Base, SessionLocal, engine, get_db
from .encrypted import username_lookup_digest
from .role_catalog import access_role_allowed, catalog_for
from .schemas import (
    SecuritySettings,
    AssignmentCreate,
    AssignmentRead,
    BusinessConfigurationRead,
    BusinessConfigurationUpdate,
    DepartmentCreate,
    DepartmentLeaderUpdate,
    DepartmentRead,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeOnboardCreate,
    EmployeeRead,
    EmployeeUpdate,
    InvitationAccept,
    LoginRequest,
    MailMode,
    MailSettingsRead,
    MailSettingsUpdate,
    MailTestRequest,
    ProfileResponse,
    ProfileUpdate,
    SessionResponse,
    SettingsUpdate,
    UserLockRequest,
    SetupRequest,
    ShiftTypeCreate,
    ShiftTypeRead,
    ShiftStaffingRequirementCreate,
    UserCreate,
    UserRead,
    UserUpdate,
    WorkRulesRead,
    WorkRulesUpdate,
    TeamProfileRead,
    UpdateChannelUpdate,
    PasswordCheck,
    PasswordCheckResponse,
    LicenseTokenUpdate,
    OptimizationPreviewRequest,
    PlanningApproval,
    PlanningRequest,
    SickCoverageApproval,
    SickCoveragePreviewRequest,
)
from .security import (
    idle_timeout_minutes,
    Principal,
    authenticate,
    create_token_response,
    get_account,
    hash_password,
    require_admin,
    require_approve,
    require_edit,
    require_plan_view,
    require_license_writable,
    require_manage,
    require_department_manage,
    require_employee_manage,
    require_team_manage,
    require_principal,
    require_view,
    set_session_cookie,
    verify_password,
)
from .licensing import LicenseConfigurationError, LicenseTokenError
from .license_manager import (
    DEFAULT_API_URL,
    LicenseServerUnavailable,
    activate_license,
    check_license,
    check_retry_delay,
    decode_license_claims,
    get_installation_id,
    license_is_read_only,
    managed_federal_state,
    managed_institution,
    status_claims,
)
from .absences import employee_is_absent, router as absences_router
from .login_throttle import LoginThrottle
from .work_rules import (
    business_timezone,
    default_break_start_minutes,
    gross_duration,
    load_work_rules,
    required_break_minutes,
    work_rule_violation,
)
from .optimizer import OptimizationTooLarge, _shift_interval, optimize_day, optimize_period
from .backup_api import backup_scheduler, router as backup_router
from .update_checker import APP_VERSION, default_update_channel, update_checker

logger = logging.getLogger(__name__)

login_throttle = LoginThrottle()


def _migrate_encrypted_columns() -> None:
    with engine.begin() as connection:
        dialect = connection.dialect.name
        if dialect == "postgresql":
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS clinicpulse_schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        if connection.execute(
            text("SELECT 1 FROM clinicpulse_schema_migrations WHERE version = 1")
        ).first():
            return

        for table in ("admin_account", "user_accounts"):
            existing_columns = {
                column["name"] for column in inspect(connection).get_columns(table)
            }
            if "username_lookup" not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN username_lookup VARCHAR(64)"
                )

        encrypted_columns = {
            "admin_account": ("username", "signing_key", "license_token", "profile_image_data"),
            "user_accounts": ("username", "profile_image_data"),
            "employees": ("name",),
            "audit_events": ("actor_username",),
            "license_state": ("signed_status_token",),
        }
        if dialect == "postgresql":
            for table, columns in encrypted_columns.items():
                for column in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT USING {column}::TEXT"
                    )

        for table in ("admin_account", "user_accounts"):
            for record_id, username in connection.execute(
                text(f"SELECT id, username FROM {table}")
            ):
                connection.execute(
                    text(f"""
                        UPDATE {table}
                        SET username_lookup = :lookup,
                            username = encode(
                                pgp_sym_encrypt(username, current_setting('clinicpulse.data_encryption_key')),
                                'base64'
                            )
                        WHERE id = :record_id
                    """),
                    {
                        "lookup": username_lookup_digest(username),
                        "record_id": record_id,
                    },
                )

        for table, columns in encrypted_columns.items():
            for column in columns:
                if column == "username":
                    continue
                connection.exec_driver_sql(
                    f"""
                        UPDATE {table}
                        SET {column} = encode(
                            pgp_sym_encrypt({column}, current_setting('clinicpulse.data_encryption_key')),
                            'base64'
                        )
                        WHERE {column} IS NOT NULL
                    """
                )

        if dialect == "postgresql":
            connection.exec_driver_sql(
                "ALTER TABLE admin_account ALTER COLUMN username_lookup SET NOT NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE user_accounts ALTER COLUMN username_lookup SET NOT NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE admin_account DROP CONSTRAINT IF EXISTS admin_account_username_key"
            )
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_admin_account_username")
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_user_accounts_username")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_admin_account_username_lookup "
            "ON admin_account (username_lookup)"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_accounts_username_lookup "
            "ON user_accounts (username_lookup)"
        )
        connection.execute(
            text("INSERT INTO clinicpulse_schema_migrations (version) VALUES (1)")
        )


def migrate_existing_database() -> None:
    account_columns = {column["name"] for column in inspect(engine).get_columns("admin_account")}
    with engine.begin() as connection:
        if "license_token" not in account_columns:
            connection.exec_driver_sql(
                "ALTER TABLE admin_account ADD COLUMN license_token VARCHAR(4096) NOT NULL DEFAULT ''"
            )
        if "profile_image_data" not in account_columns:
            connection.exec_driver_sql("ALTER TABLE admin_account ADD COLUMN profile_image_data TEXT")
        if "profile_photo_visibility" not in account_columns:
            connection.exec_driver_sql(
                "ALTER TABLE admin_account ADD COLUMN profile_photo_visibility VARCHAR(16) NOT NULL DEFAULT 'private'"
            )
        if "first_name" not in account_columns:
            connection.exec_driver_sql("ALTER TABLE admin_account ADD COLUMN first_name TEXT")
        if "last_name" not in account_columns:
            connection.exec_driver_sql("ALTER TABLE admin_account ADD COLUMN last_name TEXT")
        user_columns = {column["name"] for column in inspect(engine).get_columns("user_accounts")}
        if "email" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE user_accounts ADD COLUMN email TEXT")
        if "invitation_status" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE user_accounts ADD COLUMN invitation_status VARCHAR(24) NOT NULL DEFAULT 'active'"
            )
        if "must_change_password" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE user_accounts ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE"
            )
        if "can_manage_department" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE user_accounts ADD COLUMN can_manage_department BOOLEAN NOT NULL DEFAULT FALSE"
            )
        if "profile_image_data" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE user_accounts ADD COLUMN profile_image_data TEXT")
        if "profile_photo_visibility" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE user_accounts ADD COLUMN profile_photo_visibility VARCHAR(16) NOT NULL DEFAULT 'private'"
            )
        absence_columns = {column["name"] for column in inspect(engine).get_columns("absences")}
        if "requested_by" not in absence_columns:
            connection.exec_driver_sql("ALTER TABLE absences ADD COLUMN requested_by VARCHAR(64)")
        settings_columns = {column["name"] for column in inspect(engine).get_columns("application_settings")}
        connection.exec_driver_sql(
            "UPDATE application_settings SET update_channel = CASE update_channel "
            "WHEN 'stable' THEN 'main' WHEN 'nightly' THEN 'test' ELSE update_channel END "
            "WHERE update_channel IN ('stable', 'nightly')"
        )
        if "idle_timeout_minutes" not in settings_columns:
            connection.exec_driver_sql(
                "ALTER TABLE application_settings ADD COLUMN idle_timeout_minutes INTEGER NOT NULL DEFAULT 5"
            )
        mail_columns = (
            ("mail_public_url", "VARCHAR(500) NOT NULL DEFAULT ''"),
            ("mail_smtp_host", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("mail_smtp_port", "INTEGER NOT NULL DEFAULT 587"),
            ("mail_smtp_username", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("mail_smtp_password", "TEXT"),
            ("mail_from_address", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("mail_use_ssl", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("mail_use_starttls", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("mail_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
        )
        for column, definition in mail_columns:
            if column not in settings_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE application_settings ADD COLUMN {column} {definition}"
                )
        if "is_locked" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE user_accounts ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT FALSE")
    _migrate_encrypted_columns()
    columns = {column["name"] for column in inspect(engine).get_columns("shift_types")}
    with engine.begin() as connection:
        if "position" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE shift_types ADD COLUMN position VARCHAR(80) NOT NULL DEFAULT 'Pflegefachkraft'"
            )
        if "required_staff" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE shift_types ADD COLUMN required_staff INTEGER NOT NULL DEFAULT 1"
            )
        if "department_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE shift_types ADD COLUMN department_id INTEGER")
    user_columns = {column["name"] for column in inspect(engine).get_columns("user_accounts")}
    if "employee_id" not in user_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE user_accounts ADD COLUMN employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL"
            )
    department_columns = {column["name"] for column in inspect(engine).get_columns("departments")}
    if "manager_user_id" not in department_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE departments ADD COLUMN manager_user_id INTEGER "
                "REFERENCES user_accounts(id) ON DELETE SET NULL"
            )
    department_columns = {column["name"] for column in inspect(engine).get_columns("departments")}
    if "deputy_user_id" not in department_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE departments ADD COLUMN deputy_user_id INTEGER "
                "REFERENCES user_accounts(id) ON DELETE SET NULL"
            )
    for table, names in (
        ("user_accounts", ("first_name", "last_name", "birth_date", "address", "phone")),
        ("employees", ("first_name", "last_name")),
    ):
        existing = {column["name"] for column in inspect(engine).get_columns(table)}
        with engine.begin() as connection:
            for name in names:
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} TEXT")
    shift_columns = {column["name"] for column in inspect(engine).get_columns("shift_types")}
    if "break_minutes" not in shift_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE shift_types ADD COLUMN break_minutes INTEGER NOT NULL DEFAULT 0")
        with SessionLocal() as db:
            for shift in db.scalars(select(models.ShiftType)):
                shift.break_minutes = required_break_minutes(gross_duration(shift.start_time, shift.end_time))
            db.commit()
    shift_columns = {column["name"] for column in inspect(engine).get_columns("shift_types")}
    if "break_start_minutes" not in shift_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE shift_types ADD COLUMN break_start_minutes INTEGER NOT NULL DEFAULT 0"
            )
        with SessionLocal() as db:
            for shift in db.scalars(select(models.ShiftType)):
                shift.break_start_minutes = default_break_start_minutes(
                    gross_duration(shift.start_time, shift.end_time), shift.break_minutes
                )
            db.commit()
    with SessionLocal() as db:
        for shift in db.scalars(select(models.ShiftType)):
            if not shift.staffing_requirements:
                shift.staffing_requirements.append(models.ShiftStaffingRequirement(
                    position=shift.position,
                    required_staff=shift.required_staff,
                ))
        db.commit()
    setting_columns = {column["name"] for column in inspect(engine).get_columns("application_settings")}
    for column, default in (("rest_hours", 11), ("max_daily_hours", 10), ("max_weekly_hours", 48)):
        if column not in setting_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    f"ALTER TABLE application_settings ADD COLUMN {column} INTEGER NOT NULL DEFAULT {default}"
                )
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE application_settings SET rest_hours = 11 WHERE rest_hours < 11")
        connection.exec_driver_sql("UPDATE application_settings SET max_weekly_hours = 48 WHERE max_weekly_hours > 48")
    business_columns = {column["name"] for column in inspect(engine).get_columns("business_configuration")}
    if "sunday_work_authorized" not in business_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE business_configuration ADD COLUMN sunday_work_authorized BOOLEAN NOT NULL DEFAULT FALSE"
            )
    employee_columns = {column["name"] for column in inspect(engine).get_columns("employees")}
    if "department_id" not in employee_columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE employees ADD COLUMN department_id INTEGER")
    with SessionLocal() as db:
        if db.get(models.AdminAccount, 1) is not None and db.get(models.BusinessConfiguration, 1) is None:
            db.add(models.BusinessConfiguration(
                id=1,
                federal_state="Nordrhein-Westfalen",
                operational_profile="hospital",
                timezone="Europe/Berlin",
            ))
        for user in db.scalars(select(models.UserAccount)):
            if user.department_id is not None and all(
                department.id != user.department_id for department in user.departments
            ):
                department = db.get(models.Department, user.department_id)
                if department is not None:
                    user.departments.append(department)
        unassigned_employees = db.scalar(
            select(models.Employee.id).where(models.Employee.department_id.is_(None)).limit(1)
        )
        unassigned_shifts = db.scalar(
            select(models.ShiftType.id).where(models.ShiftType.department_id.is_(None)).limit(1)
        )
        if unassigned_employees is not None or unassigned_shifts is not None:
            department = db.scalar(
                select(models.Department).where(models.Department.name == "Allgemein")
            )
            if department is None:
                department = models.Department(name="Allgemein")
                db.add(department)
                db.flush()
            db.execute(
                update(models.Employee)
                .where(models.Employee.department_id.is_(None))
                .values(department_id=department.id)
            )
            db.execute(
                update(models.ShiftType)
                .where(models.ShiftType.department_id.is_(None))
                .values(department_id=department.id)
            )
            db.commit()
        else:
            db.commit()
        for department in db.scalars(select(models.Department)):
            roles_by_name = {
                qualification.name.casefold(): qualification
                for qualification in department.qualifications
            }
            employees = list(db.scalars(
                select(models.Employee).where(models.Employee.department_id == department.id)
            ))
            positions = {
                employee.role for employee in employees
            }
            for shift in db.scalars(
                select(models.ShiftType).where(models.ShiftType.department_id == department.id)
            ):
                requirements = shift.staffing_requirements or [
                    models.ShiftStaffingRequirement(position=shift.position, required_staff=shift.required_staff)
                ]
                positions.update(item.position for item in requirements)
            for position in positions:
                if position.casefold() not in roles_by_name:
                    qualification = models.DepartmentQualification(
                        department_id=department.id,
                        name=position,
                        leadership_eligible=position.strip().casefold() == "oberarzt",
                    )
                    db.add(qualification)
                    db.flush()
                    roles_by_name[position.casefold()] = qualification
            for employee in employees:
                if not employee.qualifications:
                    employee.qualifications = [roles_by_name[employee.role.casefold()]]
        db.commit()


def _sync_managed_profile(db: Session, verified_claims: dict[str, object], license_token: str) -> None:
    license_claims = decode_license_claims(license_token)
    _, profile = managed_institution(verified_claims, license_claims)
    federal_state = managed_federal_state(verified_claims, license_claims)
    configuration = db.get(models.BusinessConfiguration, 1)
    if configuration is None:
        return
    if profile:
        configuration.operational_profile = str(profile)
    if federal_state:
        configuration.federal_state = str(federal_state)


def _stored_managed_values(db: Session) -> tuple[str | None, str | None]:
    state = db.get(models.LicenseState, 1)
    account = get_account(db)
    if account is None or not account.license_token:
        return None, None
    try:
        claims = (
            status_claims(state.signed_status_token, account.license_token, state.installation_id)
            if state and state.signed_status_token
            else {}
        )
        license_claims = decode_license_claims(account.license_token)
        return (
            managed_institution(claims, license_claims)[1],
            managed_federal_state(claims, license_claims),
        )
    except (LicenseConfigurationError, LicenseTokenError):
        return None, None


def _record_license_failure(db: Session, state: models.LicenseState, error: Exception) -> None:
    state.consecutive_failures += 1
    state.last_error = str(error)[:300]
    state.next_check_at = datetime.now(timezone.utc) + check_retry_delay(state.consecutive_failures)
    db.commit()


def _license_release_channel(settings: models.ApplicationSetting | None) -> str:
    channel = settings.update_channel if settings is not None else default_update_channel()
    return "nightly" if channel in {"nightly", "test"} else "stable"


def _check_license_state(db: Session, force: bool = False) -> None:
    account = get_account(db)
    if account is None or not account.license_token:
        return
    state = db.get(models.LicenseState, 1)
    if state is None:
        state = models.LicenseState(id=1, installation_id=get_installation_id())
        db.add(state)
        db.flush()
    now = datetime.now(timezone.utc)
    if not force and state.next_check_at is not None:
        next_check = state.next_check_at
        if next_check.tzinfo is None:
            next_check = next_check.replace(tzinfo=timezone.utc)
        if next_check > now:
            return
    settings = db.get(models.ApplicationSetting, 1)
    release_channel = _license_release_channel(settings)
    try:
        if state.signed_status_token is None:
            verified = activate_license(
                account.license_token,
                state.installation_id,
                APP_VERSION,
                release_channel,
            )
        else:
            verified = check_license(
                account.license_token,
                state.installation_id,
                APP_VERSION,
                release_channel,
            )
    except (LicenseServerUnavailable, LicenseTokenError, LicenseConfigurationError) as exc:
        _record_license_failure(db, state, exc)
        return
    state.signed_status_token = verified.token
    state.last_successful_check_at = now
    state.next_check_at = now + timedelta(hours=24)
    state.last_error = None
    state.consecutive_failures = 0
    _sync_managed_profile(db, verified.claims, account.license_token)
    db.commit()


def _license_check_worker(force: bool = False) -> None:
    with SessionLocal() as db:
        _check_license_state(db, force=force)


async def _license_check_scheduler() -> None:
    while True:
        await asyncio.sleep(60)
        await asyncio.to_thread(_license_check_worker)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_existing_database()
    await asyncio.to_thread(_license_check_worker, True)
    schedulers = [asyncio.create_task(_license_check_scheduler()), asyncio.create_task(backup_scheduler()), asyncio.create_task(archive_scheduler())]
    try:
        yield
    finally:
        for scheduler in schedulers:
            scheduler.cancel()
        for scheduler in schedulers:
            try:
                await scheduler
            except asyncio.CancelledError:
                pass


ARCHITECTURE = {"x86_64": "X86", "amd64": "X86", "aarch64": "ARM", "arm64": "ARM"}.get(
    platform.machine().lower(), platform.machine()
)
app = FastAPI(title="ClinicPulse API", version=APP_VERSION, docs_url="/api/docs", lifespan=lifespan)
app.include_router(absences_router)
app.include_router(archive_router)
app.include_router(archive_settings_router)
app.include_router(backup_router)


def has_core_feature(features: object) -> bool:
    return isinstance(features, list) and ("core_scheduling" in features or "all" in features)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "date": date.today().isoformat(), "version": APP_VERSION, "architecture": ARCHITECTURE, "display_version": f"{APP_VERSION}-{ARCHITECTURE}"}


@app.post("/api/password/check", response_model=PasswordCheckResponse)
def check_password_breach(check: PasswordCheck) -> PasswordCheckResponse:
    digest = hashlib.sha1(check.password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    request = urllib.request.Request(
        f"https://api.pwnedpasswords.com/range/{prefix}",
        headers={"Add-Padding": "true", "User-Agent": "ClinicPulse/PasswordCheck"},
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            if response.status != 200:
                raise HTTPException(status_code=503, detail="Have I Been Pwned konnte nicht erreicht werden")
            payload = response.read(1_000_001)
            if len(payload) > 1_000_000:
                raise HTTPException(status_code=502, detail="Antwort des Passwort-Prüfdienstes ist zu groß")
            ranges = payload.decode("ascii")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Passwortprüfung momentan nicht verfügbar",
        ) from exc
    for entry in ranges.splitlines():
        returned_suffix, separator, count = entry.partition(":")
        if (
            not separator
            or len(returned_suffix) != 35
            or any(character not in "0123456789ABCDEFabcdef" for character in returned_suffix)
            or not count.isdigit()
        ):
            raise HTTPException(status_code=502, detail="Ungültige Antwort des Passwort-Prüfdienstes")
        if returned_suffix.upper() == suffix:
            return PasswordCheckResponse(compromised_count=int(count))
    return PasswordCheckResponse(compromised_count=0)


@app.get("/api/admin/updates")
def check_for_updates(
    refresh: bool = Query(default=False),
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    settings = db.get(models.ApplicationSetting, 1)
    channel = settings.update_channel if settings is not None else default_update_channel()
    return update_checker.check(channel=channel, force=refresh)


@app.get("/api/admin/work-rules", response_model=WorkRulesRead)
def get_work_rules(_: Principal = Depends(require_manage), db: Session = Depends(get_db)) -> WorkRulesRead:
    rules = load_work_rules(db)
    return WorkRulesRead(
        rest_hours=rules.rest_hours, max_daily_hours=rules.max_daily_hours, max_weekly_hours=rules.max_weekly_hours
    )


@app.get("/api/admin/business-configuration", response_model=BusinessConfigurationRead)
def get_business_configuration(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BusinessConfigurationRead:
    configuration = db.get(models.BusinessConfiguration, 1)
    if configuration is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Business configuration is missing")
    managed_profile, managed_state = _stored_managed_values(db)
    return BusinessConfigurationRead(
        federal_state=managed_state or configuration.federal_state,
        federal_state_managed=managed_state is not None,
        operational_profile=managed_profile or configuration.operational_profile,
        operational_profile_managed=managed_profile is not None,
        timezone=configuration.timezone,
        sunday_work_authorized=configuration.sunday_work_authorized,
    )


@app.put("/api/admin/business-configuration", response_model=BusinessConfigurationRead)
def set_business_configuration(
    changes: BusinessConfigurationUpdate,
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BusinessConfigurationRead:
    configuration = db.get(models.BusinessConfiguration, 1)
    if configuration is None:
        configuration = models.BusinessConfiguration(id=1, timezone="Europe/Berlin")
        db.add(configuration)
    managed_profile, managed_state = _stored_managed_values(db)
    requested_state = managed_state or changes.federal_state or configuration.federal_state
    if not requested_state:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bundesland fehlt")
    configuration.federal_state = requested_state
    requested_profile = managed_profile or changes.operational_profile or configuration.operational_profile
    if requested_profile is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Einrichtungsart fehlt")
    configuration.operational_profile = requested_profile
    configuration.timezone = "Europe/Berlin"
    configuration.sunday_work_authorized = changes.sunday_work_authorized
    db.commit()
    return BusinessConfigurationRead(
        federal_state=configuration.federal_state,
        federal_state_managed=managed_state is not None,
        operational_profile=configuration.operational_profile,
        operational_profile_managed=managed_profile is not None,
        timezone=configuration.timezone,
        sunday_work_authorized=configuration.sunday_work_authorized,
    )


@app.put("/api/admin/work-rules", response_model=WorkRulesRead)
def set_work_rules(
    changes: WorkRulesUpdate,
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkRulesRead:
    settings = db.get(models.ApplicationSetting, 1)
    if settings is None:
        settings = models.ApplicationSetting(id=1)
        db.add(settings)
    settings.rest_hours = changes.rest_hours
    settings.max_daily_hours = changes.max_daily_hours
    settings.max_weekly_hours = changes.max_weekly_hours
    db.commit()
    return WorkRulesRead(**changes.model_dump())


@app.get("/api/admin/security-settings", response_model=SecuritySettings)
def get_security_settings(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> SecuritySettings:
    return SecuritySettings(idle_timeout_minutes=idle_timeout_minutes(db))


@app.put("/api/admin/security-settings", response_model=SecuritySettings)
def set_security_settings(
    changes: SecuritySettings,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SecuritySettings:
    db.info["audit_actor"] = principal.username
    settings = db.get(models.ApplicationSetting, 1)
    if settings is None:
        settings = models.ApplicationSetting(id=1)
        db.add(settings)
    settings.idle_timeout_minutes = changes.idle_timeout_minutes
    db.commit()
    return changes


def _mail_configuration(db: Session) -> MailConfiguration:
    settings = db.get(models.ApplicationSetting, 1)
    if settings is not None and settings.mail_smtp_host:
        return MailConfiguration(
            public_url=settings.mail_public_url,
            smtp_host=settings.mail_smtp_host,
            smtp_port=settings.mail_smtp_port,
            smtp_username=settings.mail_smtp_username,
            smtp_password=settings.mail_smtp_password or "",
            from_address=settings.mail_from_address,
            use_ssl=settings.mail_use_ssl,
            use_starttls=settings.mail_use_starttls,
        )
    return environment_mail_configuration()


def _mail_enabled(db: Session) -> bool:
    settings = db.get(models.ApplicationSetting, 1)
    return settings.mail_enabled if settings is not None else True


@app.get("/api/account-creation/mail-mode", response_model=MailMode)
def get_mail_mode(_: Principal = Depends(require_team_manage), db: Session = Depends(get_db)) -> MailMode:
    return MailMode(enabled=_mail_enabled(db))


@app.put("/api/admin/mail-mode", response_model=MailMode)
def set_mail_mode(
    changes: MailMode,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MailMode:
    db.info["audit_actor"] = principal.username
    settings = db.get(models.ApplicationSetting, 1)
    if settings is None:
        settings = models.ApplicationSetting(id=1)
        db.add(settings)
    settings.mail_enabled = changes.enabled
    db.commit()
    return changes


def _mail_settings_response(configuration: MailConfiguration) -> MailSettingsRead:
    return MailSettingsRead(
        public_url=configuration.public_url,
        smtp_host=configuration.smtp_host,
        smtp_port=configuration.smtp_port,
        smtp_username=configuration.smtp_username,
        smtp_password_configured=bool(configuration.smtp_password),
        from_address=configuration.from_address,
        use_ssl=configuration.use_ssl,
        use_starttls=configuration.use_starttls,
    )


@app.get("/api/admin/mail-settings", response_model=MailSettingsRead)
def get_mail_settings(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MailSettingsRead:
    return _mail_settings_response(_mail_configuration(db))


@app.put("/api/admin/mail-settings", response_model=MailSettingsRead)
def set_mail_settings(
    changes: MailSettingsUpdate,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MailSettingsRead:
    db.info["audit_actor"] = principal.username
    settings = db.get(models.ApplicationSetting, 1)
    if settings is None:
        settings = models.ApplicationSetting(id=1)
        db.add(settings)
    effective_password = (
        None
        if changes.clear_smtp_password
        else changes.smtp_password or settings.mail_smtp_password
    )
    if changes.smtp_username and effective_password and not (changes.use_ssl or changes.use_starttls):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="SMTP authentication requires TLS",
        )
    settings.mail_public_url = changes.public_url
    settings.mail_smtp_host = changes.smtp_host.strip()
    settings.mail_smtp_port = changes.smtp_port
    settings.mail_smtp_username = changes.smtp_username.strip()
    if changes.clear_smtp_password:
        settings.mail_smtp_password = None
    elif changes.smtp_password:
        settings.mail_smtp_password = changes.smtp_password
    settings.mail_from_address = changes.from_address.strip()
    settings.mail_use_ssl = changes.use_ssl
    settings.mail_use_starttls = changes.use_starttls
    db.commit()
    return _mail_settings_response(_mail_configuration(db))


@app.post("/api/admin/mail-settings/test")
def test_mail_settings(
    request: MailTestRequest,
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not _mail_enabled(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email delivery is disabled")
    try:
        send_test_email(request.recipient, _mail_configuration(db))
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        logger.warning("SMTP test delivery failed (error=%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Testmail konnte nicht versendet werden. SMTP-Host, Zugangsdaten und TLS-Einstellungen prüfen.",
        ) from exc
    return {"status": "sent"}


@app.put("/api/admin/update-channel")
def set_update_channel(
    changes: UpdateChannelUpdate,
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = db.get(models.ApplicationSetting, 1)
    if settings is None:
        settings = models.ApplicationSetting(id=1, update_channel=changes.channel)
        db.add(settings)
    else:
        settings.update_channel = changes.channel
    db.commit()
    update_status = update_checker.check(channel=changes.channel, force=True)
    return {"channel": changes.channel, "status": str(update_status["status"])}


def license_snapshot(db: Session) -> dict[str, object]:
    state = db.get(models.LicenseState, 1)
    account = get_account(db)
    license_claims = decode_license_claims(account.license_token) if account and account.license_token else {}
    try:
        claims = (
            status_claims(state.signed_status_token, account.license_token, state.installation_id)
            if state and state.signed_status_token and account and account.license_token
            else {}
        )
    except (LicenseConfigurationError, LicenseTokenError):
        claims = {}
    read_only, reason = license_is_read_only(
        state.signed_status_token if state else None,
        state.last_successful_check_at if state else None,
        license_token=account.license_token if account else None,
        installation_id=state.installation_id if state else None,
    )
    grace_until = claims.get("grace_until")
    expires_at = claims.get("license_expires_at")
    institution_name, operational_profile = managed_institution(claims, license_claims)
    federal_state = managed_federal_state(claims, license_claims)
    return {
        "status": claims.get("license_status", "UNVERIFIED"),
        "checked_at": state.last_successful_check_at.isoformat() if state and state.last_successful_check_at else None,
        "license_expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat()
        if isinstance(expires_at, (int, float)) and not isinstance(expires_at, bool) else None,
        "grace_until": datetime.fromtimestamp(grace_until, timezone.utc).isoformat()
        if isinstance(grace_until, (int, float)) and not isinstance(grace_until, bool) else None,
        "read_only": read_only,
        "message": reason or ("Kulanzzeitraum aktiv" if claims.get("license_status") == "GRACE_PERIOD" else None),
        "vip": claims.get("vip", False),
        "suppress_warnings": claims.get("suppress_warnings", False),
        "last_error": state.last_error if state else "Lizenz noch nicht online aktiviert",
        "next_check_at": state.next_check_at.isoformat() if state and state.next_check_at else None,
        "max_users": license_claims.get("max_users"),
        "features": license_claims.get("features", []),
        "institution_name": institution_name,
        "operational_profile": operational_profile,
        "federal_state": federal_state,
    }


@app.get("/api/admin/license")
def get_license_status(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return license_snapshot(db)


@app.get("/api/admin/audit")
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None, pattern="^(logins|accounts|backups)$"),
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(models.AuditEvent)
    if category == "logins":
        query = query.where(models.AuditEvent.action.in_(["login", "login_failed", "locked", "unlocked"]))
    elif category == "accounts":
        query = query.where(models.AuditEvent.entity_type.in_(["UserAccount", "AdminAccount"]))
    elif category == "backups":
        query = query.where(models.AuditEvent.entity_type.like("Backup%"))
    events = db.scalars(
        query
        .order_by(models.AuditEvent.created_at.desc(), models.AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": entry.id,
                "created_at": entry.created_at.isoformat(),
                "actor_username": entry.actor_username,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
            }
            for entry in events
        ],
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/license/status")
def get_current_license_status(
    _: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return license_snapshot(db)


@app.post("/api/admin/license/check")
def force_license_check(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _check_license_state(db, force=True)
    return license_snapshot(db)


@app.put("/api/admin/license/token")
def replace_license_token(
    changes: LicenseTokenUpdate,
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    account = get_account(db)
    state = db.get(models.LicenseState, 1)
    if account is None or state is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="License installation is not initialized")
    settings = db.get(models.ApplicationSetting, 1)
    release_channel = _license_release_channel(settings)
    license_claims = decode_license_claims(changes.license_token)
    if "features" in license_claims and not has_core_feature(license_claims["features"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lizenz enthält kein ClinicPulse-Kernfeature")
    try:
        verified = activate_license(
            changes.license_token,
            state.installation_id,
            APP_VERSION,
            release_channel,
        )
    except LicenseConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Lizenzprüfung ist nicht verfügbar") from exc
    except LicenseTokenError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Lizenz-Token oder Status ungültig") from exc
    except LicenseServerUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Lizenzserver ist momentan nicht erreichbar") from exc
    account.license_token = changes.license_token
    state.signed_status_token = verified.token
    state.last_successful_check_at = datetime.now(timezone.utc)
    state.next_check_at = datetime.now(timezone.utc) + timedelta(hours=24)
    state.consecutive_failures = 0
    state.last_error = None
    _sync_managed_profile(db, verified.claims, changes.license_token)
    db.commit()
    return license_snapshot(db)


@app.get("/api/setup/status")
def setup_status(db: Session = Depends(get_db)) -> dict[str, object]:
    account = get_account(db)
    institution_name = None
    if account is not None and account.license_token:
        try:
            state = db.get(models.LicenseState, 1)
            claims = (
                status_claims(state.signed_status_token, account.license_token, state.installation_id)
                if state and state.signed_status_token
                else {}
            )
            institution_name = managed_institution(claims, decode_license_claims(account.license_token))[0]
        except (LicenseConfigurationError, LicenseTokenError):
            logger.exception("Unable to read institution name from stored license")
    return {
        "setup_required": account is None,
        "institution_name": institution_name,
    }


@app.post("/api/setup", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def setup_admin(
    setup: SetupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse:
    if get_account(db) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Initial setup is already complete")
    installation_id = get_installation_id()
    try:
        verified_status = activate_license(
            setup.license_token,
            installation_id,
            APP_VERSION,
            "stable",
        )
    except LicenseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lizenzprüfung ist nicht konfiguriert",
        ) from exc
    except LicenseTokenError as exc:
        logger.warning("Initial license activation rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lizenz-Token oder signierter Lizenzstatus ist ungültig",
        ) from exc
    except LicenseServerUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lizenzserver ist momentan nicht erreichbar",
        ) from exc
    if verified_status.claims["license_status"] == "BLOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Diese Lizenz ist gesperrt")
    read_only, reason = license_is_read_only(
        verified_status.token,
        datetime.now(timezone.utc),
        license_token=setup.license_token,
        installation_id=installation_id,
    )
    if read_only:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Diese Lizenz ist nicht aktiv: {reason}")
    license_claims = decode_license_claims(setup.license_token)
    if "features" in license_claims and not has_core_feature(license_claims["features"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lizenz enthält kein ClinicPulse-Kernfeature")
    _, managed_profile = managed_institution(verified_status.claims, license_claims)
    operational_profile = managed_profile or setup.operational_profile
    federal_state = managed_federal_state(verified_status.claims, license_claims) or setup.federal_state
    if federal_state is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Die Lizenz enthält kein Bundesland. Bitte im License Manager beim Kunden hinterlegen und Token neu ausstellen.",
        )
    if operational_profile is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Die Lizenz enthält keine Einrichtungsart. Bitte im License Manager beim Kunden hinterlegen und Token neu ausstellen.",
        )
    salt, password_hash = hash_password(setup.password)
    account = models.AdminAccount(
        id=1,
        username=setup.username,
        first_name=setup.first_name,
        last_name=setup.last_name,
        password_salt=salt,
        password_hash=password_hash,
        signing_key=secrets.token_urlsafe(48),
        license_token=setup.license_token,
        token_version=0,
    )
    db.info["audit_actor"] = setup.username
    db.add(account)
    db.add(models.BusinessConfiguration(
        id=1,
        federal_state=federal_state,
        operational_profile=operational_profile,
        timezone="Europe/Berlin",
        sunday_work_authorized=setup.sunday_work_authorized,
    ))
    db.add(models.LicenseState(
        id=1,
        installation_id=installation_id,
        signed_status_token=verified_status.token,
        last_successful_check_at=datetime.now(timezone.utc),
        next_check_at=datetime.now(timezone.utc) + timedelta(hours=24),
        consecutive_failures=0,
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Initial setup is already complete") from exc
    db.refresh(account)
    set_session_cookie(response, account.signing_key, request, "a:1", account.token_version)
    return SessionResponse(**create_token_response(account.username))


@app.post("/api/auth/login", response_model=SessionResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse:
    client_ip = request.headers.get("x-real-ip") or (
        request.client.host if request.client is not None else "unknown"
    )
    root = get_account(db)
    if root is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    retry_after = login_throttle.retry_after(
        db,
        client_ip,
        credentials.username,
        root.signing_key,
    )
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zu viele Anmeldeversuche. Bitte in {retry_after} Sekunden erneut versuchen.",
            headers={"Retry-After": str(retry_after)},
        )
    account = authenticate(db, credentials.username, credentials.password)
    if account is None:
        db.add(models.AuditEvent(
            created_at=datetime.now(timezone.utc),
            actor_username="anonymous",
            action="login_failed",
            entity_type="Authentication",
            entity_id="login",
        ))
        delay = login_throttle.record_failure(
            db,
            client_ip,
            credentials.username,
            root.signing_key,
        )
        time_module.sleep(delay)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    root, principal, subject, version = account
    if credentials.stay_signed_in and principal.role_key in {"ADMIN", "HOSPITAL_MANAGEMENT"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Angemeldet bleiben ist für Administrationskonten nicht verfügbar",
        )
    login_throttle.record_success(
        db,
        client_ip,
        credentials.username,
        root.signing_key,
    )
    db.info["audit_actor"] = principal.username
    db.add(models.AuditEvent(
        created_at=datetime.now(timezone.utc),
        actor_username=principal.username,
        action="login",
        entity_type="Authentication",
        entity_id=principal.role_key,
    ))
    db.commit()
    remember_me = credentials.stay_signed_in or principal.role_key == "KIOSK"
    set_session_cookie(response, root.signing_key, request, subject, version, remember_me)
    return SessionResponse(employee_id=principal.employee_id, must_change_password=principal.must_change_password, **create_token_response(
        principal.username,
        principal.role_key,
        principal.department_id,
        principal.can_view,
        principal.can_edit,
        principal.can_approve,
        remember_me,
        principal.can_manage_department,
    ))


@app.get("/api/auth/session", response_model=SessionResponse)
def current_session(principal: Principal = Depends(require_principal), db: Session = Depends(get_db)) -> SessionResponse:
    return SessionResponse(employee_id=principal.employee_id, idle_timeout_minutes=idle_timeout_minutes(db), must_change_password=principal.must_change_password, **create_token_response(
        principal.username,
        principal.role_key,
        principal.department_id,
        principal.can_view,
        principal.can_edit,
        principal.can_approve,
        principal.remember_me,
        principal.can_manage_department,
    ))


def profile_response(principal: Principal, db: Session) -> ProfileResponse:
    if principal.user_account_id is None:
        account = get_account(db)
        if account is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
        return ProfileResponse(
            username=account.username,
            role_key="ADMIN",
            department_id=None,
            profile_image_data=account.profile_image_data,
            profile_photo_visibility=account.profile_photo_visibility,
            first_name=account.first_name,
            last_name=account.last_name,
            remember_me=False,
        )
    user = db.get(models.UserAccount, principal.user_account_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return ProfileResponse(
        username=user.username,
        role_key=user.role_key,
        department_id=user.department_id,
        profile_image_data=user.profile_image_data,
        profile_photo_visibility=user.profile_photo_visibility,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date,
        address=user.address,
        phone=user.phone,
        remember_me=principal.remember_me,
    )


@app.get("/api/profile/me", response_model=ProfileResponse)
def get_my_profile(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    return profile_response(principal, db)


@app.put("/api/profile/me", response_model=ProfileResponse)
def update_my_profile(
    changes: ProfileUpdate,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    account = get_account(db) if principal.user_account_id is None else db.get(
        models.UserAccount, principal.user_account_id
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    if changes.profile_photo_visibility == "department" and principal.department_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dieses Konto ist keiner Abteilung zugeordnet")
    account.profile_image_data = changes.profile_image_data
    account.profile_photo_visibility = changes.profile_photo_visibility
    if principal.user_account_id is not None:
        provided = changes.model_fields_set
        if "first_name" in provided and changes.first_name:
            account.first_name = changes.first_name
        if "last_name" in provided and changes.last_name:
            account.last_name = changes.last_name
        if "birth_date" in provided:
            account.birth_date = changes.birth_date.isoformat() if changes.birth_date else None
        if "address" in provided:
            account.address = changes.address
        if "phone" in provided:
            account.phone = changes.phone
        linked = db.get(models.Employee, account.employee_id) if account.employee_id is not None else None
        if linked is not None and account.first_name and account.last_name:
            linked.first_name, linked.last_name = account.first_name, account.last_name
            linked.name = f"{account.first_name} {account.last_name}"
    else:
        if changes.first_name:
            account.first_name = changes.first_name
        if changes.last_name:
            account.last_name = changes.last_name
    db.commit()
    db.refresh(account)
    return profile_response(principal, db)


@app.get("/api/profile/department", response_model=list[TeamProfileRead])
def list_department_profiles(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[TeamProfileRead]:
    if principal.role_key == "ADMIN" or principal.department_id is None:
        return []
    users = list(db.scalars(
        select(models.UserAccount)
        .where(
            models.UserAccount.department_id == principal.department_id,
            models.UserAccount.profile_photo_visibility == "department",
            models.UserAccount.profile_image_data.is_not(None),
            models.UserAccount.id != db.scalar(
                select(models.UserAccount.id).where(
                    models.UserAccount.username_lookup == username_lookup_digest(principal.username)
                )
            ),
        )
        .order_by(models.UserAccount.id)
    ))
    users.sort(key=lambda user: user.username.casefold())
    return [
        TeamProfileRead(
            username=user.username,
            role_key=user.role_key,
            profile_image_data=user.profile_image_data,
            department_id=user.department_id,
        )
        for user in users
    ]


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    result = Response(status_code=status.HTTP_204_NO_CONTENT)
    result.delete_cookie(
        "clinicpulse_session",
        path="/",
        httponly=True,
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        samesite="strict",
    )
    result.headers["Cache-Control"] = "no-store"
    return result


@app.put("/api/settings/account", response_model=SessionResponse)
def update_account_settings(
    changes: SettingsUpdate,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> SessionResponse:
    root = get_account(db)
    user = None
    if principal.user_account_id is None:
        account = root
        subject = "a:1"
    else:
        account = None
        user = db.scalar(select(models.UserAccount).where(
            models.UserAccount.username_lookup == username_lookup_digest(principal.username)
        ))
        subject = f"u:{user.id}" if user is not None else ""
    if account is None and user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    salt = account.password_salt if account is not None else user.password_salt
    password_hash = account.password_hash if account is not None else user.password_hash
    if not verify_password(salt, password_hash, changes.current_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    if principal.must_change_password:
        if not changes.new_password or verify_password(salt, password_hash, changes.new_password):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A different new password is required")
        if changes.username != principal.username:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username cannot be changed during the required password change")
    duplicate_root = root is not None and root.username == changes.username and principal.user_account_id is not None
    duplicate_user = db.scalar(select(models.UserAccount.id).where(
        models.UserAccount.username_lookup == username_lookup_digest(changes.username),
        models.UserAccount.username_lookup != username_lookup_digest(principal.username),
    ))
    duplicate_admin = account is not None and account.username != changes.username and db.scalar(
        select(models.UserAccount.id).where(
            models.UserAccount.username_lookup == username_lookup_digest(changes.username)
        )
    ) is not None
    if duplicate_root or duplicate_user is not None or duplicate_admin:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use")
    if account is not None:
        account.username = changes.username
        if changes.new_password:
            account.password_salt, account.password_hash = hash_password(changes.new_password)
        account.token_version += 1
        account.signing_key = secrets.token_urlsafe(48)
        signing_key = account.signing_key
        token_version = account.token_version
        response_principal = create_token_response(account.username)
    else:
        user.username = changes.username
        if changes.new_password:
            user.password_salt, user.password_hash = hash_password(changes.new_password)
            user.must_change_password = False
        user.token_version += 1
        token_version = user.token_version
        signing_key = root.signing_key
        response_principal = create_token_response(
            user.username, user.role_key, user.department_id,
            user.can_view, user.can_edit, user.can_approve, principal.remember_me,
            user.can_manage_department,
        )
    db.commit()
    db.refresh(account or user)
    set_session_cookie(response, signing_key, request, subject, token_version, principal.remember_me)
    return SessionResponse(employee_id=principal.employee_id, **response_principal)


def verify_department(db: Session, department_id: int | None) -> None:
    if department_id is not None and db.get(models.Department, department_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")


def scoped_to_department(principal: Principal) -> bool:
    return principal.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL"}


def accessible_department_ids(principal: Principal) -> tuple[int, ...]:
    if principal.department_ids:
        return principal.department_ids
    return (principal.department_id,) if principal.department_id is not None else ()


def can_access_department(principal: Principal, department_id: int | None) -> bool:
    return not scoped_to_department(principal) or department_id in accessible_department_ids(principal)


def require_department_scope(principal: Principal, department_id: int | None) -> None:
    if principal.can_manage_department and department_id not in principal.managed_department_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only manage your own department")


def require_user_department_scope(principal: Principal, department_id: int | None) -> None:
    if principal.can_manage_department and department_id not in principal.managed_department_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only manage accounts in your department")


def require_user_scope(principal: Principal, user: models.UserAccount) -> None:
    if principal.role_key == "PERSONNEL" and user.role_key != "EMPLOYEE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Personnel users can manage employee accounts only")
    if principal.can_manage_department and (
        user.role_key != "EMPLOYEE" or user.department_id not in principal.managed_department_ids
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only manage employee accounts in your department")


@app.get("/api/departments", response_model=list[DepartmentRead])
def list_departments(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[models.Department]:
    if principal.role_key == "PERSONNEL" or principal.can_manage_department:
        require_team_manage(principal)
    else:
        require_view(principal)
    query = select(models.Department).order_by(models.Department.name)
    if scoped_to_department(principal):
        query = query.where(models.Department.id.in_(accessible_department_ids(principal)))
    return list(db.scalars(query))


@app.post("/api/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
def create_department(
    department: DepartmentCreate,
    _: Principal = Depends(require_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> models.Department:
    record = models.Department(name=department.name.strip())
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department already exists") from exc
    db.refresh(record)
    return record


@app.put("/api/departments/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: int,
    changes: DepartmentUpdate,
    principal: Principal = Depends(require_department_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> models.Department:
    department = db.get(models.Department, department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    require_department_scope(principal, department.id)
    department.name = changes.name.strip()
    if changes.qualifications is not None:
        requested = {item.name.casefold(): item for item in changes.qualifications}
        if len(requested) != len(changes.qualifications):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Qualification names must be unique")
        existing = {item.name.casefold(): item for item in department.qualifications}
        for key, current in existing.items():
            replacement = requested.get(key)
            if replacement is None:
                used_by_employee = db.scalar(
                    select(models.employee_qualification_access.c.employee_id)
                    .where(models.employee_qualification_access.c.qualification_id == current.id)
                    .limit(1)
                )
                used_by_shift = db.scalar(
                    select(models.ShiftStaffingRequirement.id)
                    .join(models.ShiftType)
                    .where(
                        models.ShiftType.department_id == department.id,
                        func.lower(models.ShiftStaffingRequirement.position) == current.name.casefold(),
                    )
                    .limit(1)
                )
                if used_by_employee is not None or used_by_shift is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Qualification {current.name} is still in use",
                    )
                department.qualifications.remove(current)
            else:
                current.leadership_eligible = replacement.leadership_eligible
                requested.pop(key)
        for qualification in requested.values():
            department.qualifications.append(models.DepartmentQualification(
                name=qualification.name.strip(),
                leadership_eligible=qualification.leadership_eligible,
            ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department name already exists") from exc
    db.refresh(department)
    return department


@app.delete("/api/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    department_id: int,
    principal: Principal = Depends(require_department_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> Response:
    department = db.get(models.Department, department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    require_department_scope(principal, department.id)
    used_by_user = db.scalar(
        select(models.user_department_access.c.user_id)
        .where(models.user_department_access.c.department_id == department_id)
        .limit(1)
    )
    if used_by_user is None:
        used_by_user = db.scalar(
            select(models.UserAccount.id).where(models.UserAccount.department_id == department_id).limit(1)
        )
    if department.employees or department.shift_types or used_by_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department is still in use")
    db.delete(department)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/api/departments/{department_id}/leader", response_model=DepartmentRead)
def set_department_leader(
    department_id: int,
    changes: DepartmentLeaderUpdate,
    principal: Principal = Depends(require_department_manage),
    db: Session = Depends(get_db),
) -> models.Department:
    department = db.get(models.Department, department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    require_department_scope(principal, department.id)

    def eligible_leader(user_id: int | None) -> models.UserAccount | None:
        user = db.get(models.UserAccount, user_id) if user_id is not None else None
        if user is None:
            return None
        accessible = set(user.department_ids or ([user.department_id] if user.department_id else []))
        if department_id not in accessible:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Department leader must have access to this department")
        if user.employee_id is not None:
            employee = db.get(models.Employee, user.employee_id)
            eligible = employee is not None and employee.department_id == department_id and any(
                qualification.leadership_eligible for qualification in employee.qualifications
            )
        else:
            senior_qualification = next(
                (qualification for qualification in department.qualifications
                 if qualification.name.strip().casefold() == "oberarzt"),
                None,
            )
            if user.role_key == "OBERARZT" and senior_qualification is None:
                senior_qualification = models.DepartmentQualification(
                    department_id=department_id,
                    name="Oberarzt",
                    leadership_eligible=True,
                )
                db.add(senior_qualification)
                db.flush()
            eligible = (
                user.role_key == "OBERARZT"
                and senior_qualification is not None
                and senior_qualification.leadership_eligible
            )
        if not eligible:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Department leaders must have an eligible department qualification",
            )
        return user

    if "manager_user_id" in changes.model_fields_set:
        manager = eligible_leader(changes.manager_user_id)
        department.manager_user_id = manager.id if manager is not None else None
    if "deputy_user_id" in changes.model_fields_set:
        deputy = eligible_leader(changes.deputy_user_id)
        if deputy is not None and deputy.id == department.manager_user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Leader and deputy must be different users")
        department.deputy_user_id = deputy.id if deputy is not None else None
    db.commit()
    db.refresh(department)
    return department


def linked_employee_id(
    db: Session, role_key: str, employee_id: int | None, department_ids: list[int], user_id: int | None = None,
) -> int | None:
    if employee_id is None and role_key != "EMPLOYEE":
        return None
    employee = db.get(models.Employee, employee_id) if employee_id is not None else None
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if role_key in {"EMPLOYEE", "OBERARZT", "CHEFARZT"} and employee.department_id not in department_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Employee must belong to the account's department")
    query = select(models.UserAccount.id).where(models.UserAccount.employee_id == employee.id)
    if user_id is not None:
        query = query.where(models.UserAccount.id != user_id)
    taken = db.scalar(query.limit(1))
    if taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee already has an account")
    return employee.id


def _create_invitation(db: Session, user: models.UserAccount, email: str) -> tuple[models.AccountInvitation, str]:
    invitation = db.scalar(
        select(models.AccountInvitation).where(models.AccountInvitation.user_id == user.id)
    )
    if invitation is None:
        invitation = models.AccountInvitation(
            user_id=user.id,
            token_digest="",
            expires_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            delivery_status="pending",
        )
        db.add(invitation)
    token = secrets.token_urlsafe(32)
    invitation.token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    invitation.created_at = datetime.now(timezone.utc)
    invitation.accepted_at = None
    invitation.revoked_at = None
    invitation.delivery_status = "pending"
    user.email = email
    user.invitation_status = "pending"
    user.is_locked = True
    user.token_version += 1
    return invitation, token


def _deliver_invitation(
    db: Session,
    user: models.UserAccount,
    invitation: models.AccountInvitation,
    token: str,
) -> None:
    try:
        if not user.email:
            raise RuntimeError("Account invitation has no recipient email")
        send_invitation(user.email, user.username, token, _mail_configuration(db))
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        logger.warning("Account invitation delivery failed (user_id=%s, error=%s)", user.id, type(exc).__name__)
        invitation.delivery_status = "delivery_failed"
        user.invitation_status = "delivery_failed"
    else:
        invitation.delivery_status = "sent"
        user.invitation_status = "pending"
    db.commit()
    db.refresh(user)


def _verify_user_limit(db: Session) -> None:
    license_claims = decode_license_claims(get_account(db).license_token)
    user_limit = license_claims.get("max_users")
    if user_limit is not None:
        existing_users = db.scalar(select(func.count()).select_from(models.UserAccount)) or 0
        if existing_users + 2 > user_limit:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Licensed user limit reached")


def facility_profile(db: Session) -> str | None:
    configuration = db.get(models.BusinessConfiguration, 1)
    return configuration.operational_profile if configuration is not None else None


def require_role_for_facility(db: Session, role_key: str, current_role_key: str | None = None) -> None:
    if role_key != "ADMIN" and role_key != current_role_key and not access_role_allowed(facility_profile(db), role_key):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role is not available for this facility type")


@app.get("/api/role-catalog")
def role_catalog(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return catalog_for(facility_profile(db))


@app.get("/api/roles")
def list_roles(principal: Principal = Depends(require_team_manage), db: Session = Depends(get_db)) -> list[dict[str, str]]:
    roles = [role for role in catalog_for(facility_profile(db))["access_roles"] if role["key"] != "KIOSK"]  # type: ignore[union-attr]
    if principal.role_key == "PERSONNEL" or principal.can_manage_department:
        return [role for role in roles if role["key"] == "EMPLOYEE"]
    if principal.role_key == "ADMIN":
        return [{"key": "ADMIN", "label": "Administrator"}, *roles]
    return roles


@app.get("/api/users", response_model=list[UserRead])
def list_users(
    principal: Principal = Depends(require_team_manage),
    db: Session = Depends(get_db),
) -> list[models.UserAccount]:
    query = select(models.UserAccount).order_by(models.UserAccount.id)
    if principal.role_key == "PERSONNEL":
        query = query.where(models.UserAccount.role_key == "EMPLOYEE")
    elif principal.can_manage_department:
        query = query.where(
            models.UserAccount.role_key == "EMPLOYEE",
            models.UserAccount.department_id.in_(principal.managed_department_ids),
        )
    users = list(db.scalars(query))
    return sorted(users, key=lambda user: user.username.casefold())


@app.post("/api/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user: UserCreate,
    principal: Principal = Depends(require_team_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> models.UserAccount:
    require_role_for_facility(db, user.role_key)
    if principal.role_key == "PERSONNEL" and user.role_key != "EMPLOYEE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Personnel users can create employee accounts only")
    if user.role_key == "ADMIN" and principal.role_key != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can create administrator accounts")
    if principal.can_manage_department and user.role_key != "EMPLOYEE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Senior physicians can create employee accounts only")
    if user.role_key == "HOSPITAL_MANAGEMENT" and principal.role_key != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the administrator can add hospital managers")
    if user.role_key == "PERSONNEL" and principal.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only management can add personnel users")
    if user.role_key in {"OBERARZT", "CHEFARZT"} and user.department_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A department is required for this role")
    _verify_user_limit(db)
    for department_id in user.department_ids:
        verify_department(db, department_id)
        require_user_department_scope(principal, department_id)
    employee_id = linked_employee_id(db, user.role_key, user.employee_id, user.department_ids)
    root = get_account(db)
    if root is not None and user.username == root.username:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use")
    if user.email is None and user.password is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A password or invitation email is required")
    mail_enabled = _mail_enabled(db)
    if not mail_enabled and user.password is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="An initial password is required when email delivery is disabled")
    invite = mail_enabled and user.email is not None
    salt, password_hash = hash_password(user.password or secrets.token_urlsafe(32))
    record = models.UserAccount(
        username=user.username,
        password_salt=salt,
        password_hash=password_hash,
        role_key=user.role_key,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date.isoformat() if user.birth_date else None,
        address=user.address,
        phone=user.phone,
        invitation_status="pending" if invite else "active",
        must_change_password=not mail_enabled,
        employee_id=employee_id,
        department_id=user.department_id if user.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL"} else None,
        departments=list(db.scalars(
            select(models.Department).where(models.Department.id.in_(user.department_ids))
        )) if user.department_ids and user.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL"} else [],
        can_view=False if user.role_key == "PERSONNEL" else user.can_view,
        can_edit=False if user.role_key in {"HOSPITAL_MANAGEMENT", "PERSONNEL"} else user.can_edit,
        can_approve=False if user.role_key in {"HOSPITAL_MANAGEMENT", "PERSONNEL"} else user.can_approve,
        is_locked=invite,
        token_version=0,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use") from exc
    db.refresh(record)
    if invite and user.email is not None:
        invitation, token = _create_invitation(db, record, user.email)
        db.commit()
        _deliver_invitation(db, record, invitation, token)
    return record


@app.put("/api/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    changes: UserUpdate,
    principal: Principal = Depends(require_team_manage),
    db: Session = Depends(get_db),
) -> models.UserAccount:
    user = db.get(models.UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    require_role_for_facility(db, changes.role_key, user.role_key)
    if principal.role_key != "ADMIN" and (
        user.role_key in {"ADMIN", "HOSPITAL_MANAGEMENT"}
        or changes.role_key in {"ADMIN", "HOSPITAL_MANAGEMENT"}
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can manage privileged accounts")
    if principal.role_key == "PERSONNEL" and (
        user.role_key != "EMPLOYEE" or changes.role_key != "EMPLOYEE"
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Personnel users can manage employee accounts only")
    if principal.role_key == "OBERARZT" or principal.can_manage_department:
        require_user_scope(principal, user)
        if changes.role_key != "EMPLOYEE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Senior physicians can manage employee accounts only")
    if changes.role_key == "PERSONNEL" and principal.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only management can assign the personnel role")
    if changes.role_key in {"OBERARZT", "CHEFARZT"} and not changes.department_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A department is required for this role")
    for department_id in changes.department_ids:
        verify_department(db, department_id)
        require_user_department_scope(principal, department_id)
    employee_id = linked_employee_id(db, changes.role_key, changes.employee_id, changes.department_ids, user.id)
    root = get_account(db)
    if root is not None and changes.username == root.username:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use")
    duplicate = db.scalar(
        select(models.UserAccount.id).where(
            models.UserAccount.username_lookup == username_lookup_digest(changes.username),
            models.UserAccount.id != user.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use")
    user.username = changes.username
    user.role_key = changes.role_key
    user.employee_id = employee_id
    user.department_id = changes.department_id if changes.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL"} else None
    user.departments = list(db.scalars(
        select(models.Department).where(models.Department.id.in_(changes.department_ids))
    )) if changes.department_ids and changes.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL"} else []
    for department in db.scalars(select(models.Department).where(
        (models.Department.manager_user_id == user.id) | (models.Department.deputy_user_id == user.id)
    )):
        employee = db.get(models.Employee, employee_id) if employee_id is not None else None
        eligible = employee is not None and employee.department_id == department.id and any(
            qualification.leadership_eligible for qualification in employee.qualifications
        )
        legacy_eligible = employee is None and changes.role_key == "OBERARZT" and any(
            qualification.leadership_eligible and qualification.name.strip().casefold() == "oberarzt"
            for qualification in department.qualifications
        )
        remains_assigned = department.id in changes.department_ids and (eligible or legacy_eligible)
        if not remains_assigned:
            if department.manager_user_id == user.id:
                department.manager_user_id = None
            if department.deputy_user_id == user.id:
                department.deputy_user_id = None
    user.can_manage_department = db.scalar(
        select(models.Department.id).where(
            (models.Department.manager_user_id == user.id) | (models.Department.deputy_user_id == user.id)
        ).limit(1)
    ) is not None
    user.can_view = False if changes.role_key == "PERSONNEL" else changes.can_view
    user.can_edit = False if changes.role_key == "HOSPITAL_MANAGEMENT" else changes.can_edit
    user.can_approve = False if changes.role_key == "HOSPITAL_MANAGEMENT" else changes.can_approve
    if changes.role_key != "OBERARZT":
        for department in db.scalars(
            select(models.Department).where(models.Department.manager_user_id == user.id)
        ):
            department.manager_user_id = None
        user.can_manage_department = False
    if changes.role_key == "PERSONNEL":
        user.can_view = user.can_edit = user.can_approve = False
    user.first_name = changes.first_name
    user.last_name = changes.last_name
    user.birth_date = changes.birth_date.isoformat() if changes.birth_date else None
    user.address = changes.address
    user.phone = changes.phone
    invitation: models.AccountInvitation | None = None
    token: str | None = None
    if changes.email and changes.email != user.email:
        if _mail_enabled(db):
            invitation, token = _create_invitation(db, user, changes.email)
        else:
            user.email = changes.email
    if changes.new_password:
        user.password_salt, user.password_hash = hash_password(changes.new_password)
        if not _mail_enabled(db):
            user.must_change_password = True
            if user.invitation_status in {"pending", "delivery_failed", "revoked"}:
                old_invitation = db.scalar(select(models.AccountInvitation).where(models.AccountInvitation.user_id == user.id))
                if old_invitation is not None:
                    old_invitation.revoked_at = datetime.now(timezone.utc)
                user.invitation_status = "active"
                user.is_locked = False
    user.token_version += 1
    db.commit()
    db.refresh(user)
    if invitation is not None and token is not None:
        _deliver_invitation(db, user, invitation, token)
    return user


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    principal: Principal = Depends(require_team_manage),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(models.UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if principal.role_key != "ADMIN" and user.role_key in {"ADMIN", "HOSPITAL_MANAGEMENT"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can manage privileged accounts")
    require_user_scope(principal, user)
    for department in db.scalars(
        select(models.Department).where(
            (models.Department.manager_user_id == user.id) | (models.Department.deputy_user_id == user.id)
        )
    ):
        if department.manager_user_id == user.id:
            department.manager_user_id = None
        if department.deputy_user_id == user.id:
            department.deputy_user_id = None
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/api/users/{user_id}/lock", response_model=UserRead)
def set_user_lock(
    user_id: int,
    body: UserLockRequest,
    principal: Principal = Depends(require_team_manage),
    db: Session = Depends(get_db),
) -> models.UserAccount:
    user = db.get(models.UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if principal.role_key != "ADMIN" and user.role_key in {"ADMIN", "HOSPITAL_MANAGEMENT"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can manage privileged accounts")
    require_user_scope(principal, user)
    if not body.locked and user.invitation_status in {"pending", "delivery_failed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An invited account must accept its invitation before it can be unlocked")
    user.is_locked = body.locked
    user.token_version += 1
    db.add(models.AuditEvent(
        created_at=datetime.now(timezone.utc),
        actor_username=principal.username,
        action="locked" if body.locked else "unlocked",
        entity_type="UserAccount",
        entity_id=str(user.id),
    ))
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/users/{user_id}/invitation", response_model=UserRead)
def resend_user_invitation(
    user_id: int,
    principal: Principal = Depends(require_team_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> models.UserAccount:
    if not _mail_enabled(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email delivery is disabled")
    user = db.get(models.UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    require_user_scope(principal, user)
    if not user.email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No invitation email address is stored")
    invitation, token = _create_invitation(db, user, user.email)
    db.commit()
    _deliver_invitation(db, user, invitation, token)
    return user


@app.delete("/api/users/{user_id}/invitation", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_invitation(
    user_id: int,
    principal: Principal = Depends(require_team_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(models.UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    require_user_scope(principal, user)
    invitation = db.scalar(
        select(models.AccountInvitation).where(models.AccountInvitation.user_id == user.id)
    )
    if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active invitation exists")
    now = datetime.now(timezone.utc)
    invitation.revoked_at = now
    user.invitation_status = "revoked"
    user.is_locked = True
    user.token_version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/auth/accept-invitation", status_code=status.HTTP_204_NO_CONTENT)
def accept_invitation(
    body: InvitationAccept,
    db: Session = Depends(get_db),
) -> Response:
    digest = hashlib.sha256(body.token.encode("ascii")).hexdigest()
    invitation = db.scalar(
        select(models.AccountInvitation).where(models.AccountInvitation.token_digest == digest)
    )
    now = datetime.now(timezone.utc)
    if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or expired")
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    user = db.get(models.UserAccount, invitation.user_id)
    if user is None or expires_at <= now or user.invitation_status not in {"pending", "delivery_failed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or expired")
    user.password_salt, user.password_hash = hash_password(body.password)
    user.must_change_password = False
    user.is_locked = False
    user.invitation_status = "active"
    user.token_version += 1
    invitation.accepted_at = now
    db.add(models.AuditEvent(
        created_at=now,
        actor_username=user.username,
        action="invitation_accepted",
        entity_type="UserAccount",
        entity_id=str(user.id),
    ))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _visible_employee_photos(db: Session, principal: Principal, employee_ids: list[int]) -> dict[int, str]:
    if not employee_ids:
        return {}
    users = db.scalars(select(models.UserAccount).where(
        models.UserAccount.employee_id.in_(employee_ids),
        models.UserAccount.profile_image_data.is_not(None),
    ))
    return {
        user.employee_id: user.profile_image_data
        for user in users
        if user.employee_id is not None and user.profile_image_data
        and (user.profile_photo_visibility == "department" or user.username == principal.username)
    }


@app.get("/api/employees", response_model=list[EmployeeRead])
def list_employees(
    principal: Principal = Depends(require_principal), db: Session = Depends(get_db)
) -> list[models.Employee]:
    if principal.role_key == "PERSONNEL" or principal.can_manage_department:
        require_team_manage(principal)
    else:
        require_view(principal)
    query = select(models.Employee).order_by(models.Employee.name)
    if scoped_to_department(principal):
        query = query.where(models.Employee.department_id.in_(accessible_department_ids(principal)))
    employees = list(db.scalars(query))
    photos = _visible_employee_photos(db, principal, [employee.id for employee in employees])
    result = []
    for employee in employees:
        item = EmployeeRead.model_validate(employee)
        item.profile_image_data = photos.get(employee.id)
        result.append(item)
    return result


def _resolve_employee_qualifications(
    db: Session,
    department_id: int,
    qualification_ids: list[int],
    legacy_role: str,
) -> list[models.DepartmentQualification]:
    if qualification_ids:
        if len(set(qualification_ids)) != len(qualification_ids):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Duplicate qualifications are not allowed")
        qualifications = list(db.scalars(
            select(models.DepartmentQualification).where(
                models.DepartmentQualification.id.in_(qualification_ids),
                models.DepartmentQualification.department_id == department_id,
            )
        ))
        if len(qualifications) != len(qualification_ids):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Qualifications must belong to the selected department")
        return qualifications

    qualification = db.scalar(
        select(models.DepartmentQualification).where(
            models.DepartmentQualification.department_id == department_id,
            func.lower(models.DepartmentQualification.name) == legacy_role.strip().casefold(),
        )
    )
    if qualification is None:
        qualification = models.DepartmentQualification(
            department_id=department_id,
            name=legacy_role.strip(),
            leadership_eligible=legacy_role.strip().casefold() == "oberarzt",
        )
        db.add(qualification)
        db.flush()
    return [qualification]


def _ensure_shift_qualifications(
    db: Session,
    department_id: int | None,
    requirements: list[ShiftStaffingRequirementCreate],
) -> None:
    if department_id is None:
        return
    for requirement in requirements:
        qualification = db.scalar(
            select(models.DepartmentQualification).where(
                models.DepartmentQualification.department_id == department_id,
                func.lower(models.DepartmentQualification.name) == requirement.position.strip().casefold(),
            )
        )
        if qualification is None:
            db.add(models.DepartmentQualification(
                department_id=department_id,
                name=requirement.position.strip(),
                leadership_eligible=requirement.position.strip().casefold() == "oberarzt",
            ))


@app.post("/api/employees", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def create_employee(
    employee: EmployeeCreate,
    principal: Principal = Depends(require_employee_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> models.Employee:
    verify_department(db, employee.department_id)
    require_department_scope(principal, employee.department_id)
    qualifications = _resolve_employee_qualifications(
        db, employee.department_id, employee.qualification_ids, employee.role
    )
    record = models.Employee(
        name=f"{employee.first_name} {employee.last_name}",
        first_name=employee.first_name,
        last_name=employee.last_name,
        role=qualifications[0].name,
        department_id=employee.department_id,
        qualifications=qualifications,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.put("/api/employees/{employee_id}", response_model=EmployeeRead)
def update_employee(
    employee_id: int,
    changes: EmployeeUpdate,
    principal: Principal = Depends(require_employee_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> models.Employee:
    employee = db.get(models.Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    require_department_scope(principal, employee.department_id)
    verify_department(db, changes.department_id)
    require_department_scope(principal, changes.department_id)
    if employee.department_id != changes.department_id and employee.assignments:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department cannot be changed while the employee has scheduled shifts",
        )
    employee.name = f"{changes.first_name} {changes.last_name}"
    employee.first_name = changes.first_name
    employee.last_name = changes.last_name
    employee.department_id = changes.department_id
    employee.qualifications = _resolve_employee_qualifications(
        db, changes.department_id, changes.qualification_ids, changes.role
    )
    employee.role = employee.qualifications[0].name
    linked_user = db.scalar(
        select(models.UserAccount).where(models.UserAccount.employee_id == employee.id)
    )
    if linked_user is not None:
        linked_user.first_name = changes.first_name
        linked_user.last_name = changes.last_name
        if linked_user.role_key == "EMPLOYEE":
            linked_user.department_id = changes.department_id
            linked_user.departments = [db.get(models.Department, changes.department_id)]
        elif linked_user.role_key in {"OBERARZT", "CHEFARZT"} and changes.department_id not in linked_user.department_ids:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee must belong to the account's department")
    db.commit()
    db.refresh(employee)
    return employee


@app.post("/api/employees/onboard", status_code=status.HTTP_201_CREATED)
def onboard_employee(
    employee: EmployeeOnboardCreate,
    principal: Principal = Depends(require_employee_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    verify_department(db, employee.department_id)
    require_department_scope(principal, employee.department_id)
    qualifications = _resolve_employee_qualifications(
        db, employee.department_id, employee.qualification_ids, employee.role
    )
    record = models.Employee(
        name=f"{employee.first_name} {employee.last_name}",
        first_name=employee.first_name,
        last_name=employee.last_name,
        role=qualifications[0].name,
        department_id=employee.department_id,
        qualifications=qualifications,
    )
    db.add(record)
    invitation_status = None
    invitation: models.AccountInvitation | None = None
    token: str | None = None
    try:
        db.flush()
        if employee.create_account:
            username = employee.username
            email = employee.email
            mail_enabled = _mail_enabled(db)
            if not username or (mail_enabled and not email):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username and email are required")
            if not mail_enabled and not employee.password:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="An initial password is required when email delivery is disabled")
            existing = db.scalar(
                select(models.UserAccount.id).where(
                    models.UserAccount.username_lookup == username_lookup_digest(username)
                )
            )
            root = get_account(db)
            if existing is not None or (root is not None and root.username == username):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use")
            taken = db.scalar(
                select(models.UserAccount.id).where(models.UserAccount.employee_id == record.id)
            )
            if taken is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee already has an account")
            _verify_user_limit(db)
            salt, password_hash = hash_password(employee.password if not mail_enabled and employee.password else secrets.token_urlsafe(32))
            account = models.UserAccount(
                username=username,
                username_lookup=username_lookup_digest(username),
                password_salt=salt,
                password_hash=password_hash,
                role_key="EMPLOYEE",
                department_id=record.department_id,
                employee_id=record.id,
                departments=[db.get(models.Department, record.department_id)],
                can_view=True,
                can_edit=False,
                can_approve=False,
                email=email,
                first_name=employee.first_name,
                last_name=employee.last_name,
                invitation_status="pending" if mail_enabled else "active",
                must_change_password=not mail_enabled,
                is_locked=mail_enabled,
                token_version=0,
            )
            db.add(account)
            db.flush()
            if mail_enabled and email:
                invitation, token = _create_invitation(db, account, email)
                invitation_status = "pending"
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use") from exc
    db.refresh(record)
    if invitation is not None and token is not None:
        account = db.get(models.UserAccount, invitation.user_id)
        if account is not None:
            _deliver_invitation(db, account, invitation, token)
            invitation_status = account.invitation_status
    return {
        "employee": EmployeeRead.model_validate(record),
        "invitation_status": invitation_status,
    }


@app.delete("/api/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    employee_id: int,
    principal: Principal = Depends(require_employee_manage),
    __: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> Response:
    employee = db.get(models.Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    require_department_scope(principal, employee.department_id)
    if employee.assignments:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee has scheduled shifts")
    linked_user = db.scalar(
        select(models.UserAccount.id).where(models.UserAccount.employee_id == employee.id)
    )
    if linked_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee has a linked login account")
    db.delete(employee)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/shift-types", response_model=list[ShiftTypeRead])
def list_shift_types(
    principal: Principal = Depends(require_plan_view), db: Session = Depends(get_db)
) -> list[models.ShiftType]:
    query = select(models.ShiftType).order_by(models.ShiftType.start_time)
    if scoped_to_department(principal):
        query = query.where(models.ShiftType.department_id.in_(accessible_department_ids(principal)))
    return list(db.scalars(query))


@app.post("/api/shift-types", response_model=ShiftTypeRead, status_code=status.HTTP_201_CREATED)
def create_shift_type(
    shift_type: ShiftTypeCreate,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> models.ShiftType:
    department_id = shift_type.department_id
    if principal.role_key == "OBERARZT" or principal.can_manage_department:
        if department_id is None:
            department_id = (
                principal.department_id
                if principal.role_key == "OBERARZT" or principal.department_id in principal.managed_department_ids
                else principal.managed_department_ids[0]
            )
        if not can_access_department(principal, department_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only plan your own department")
    verify_department(db, department_id)
    gross = gross_duration(shift_type.start_time, shift_type.end_time)
    break_minutes = (
        shift_type.break_minutes
        if shift_type.break_minutes is not None
        else required_break_minutes(gross)
    )
    required_break = required_break_minutes(gross, break_minutes)
    break_start_minutes = (
        shift_type.break_start_minutes
        if shift_type.break_start_minutes is not None
        else default_break_start_minutes(gross, break_minutes)
    )
    if break_minutes < required_break:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At least {required_break} minutes of break are required for this shift length (ArbZG §4)",
        )
    gross_minutes = int(gross.total_seconds() // 60)
    if break_minutes and (
        break_start_minutes > 360
        or break_start_minutes + break_minutes > gross_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The scheduled break must fit within the shift and start within the first six hours (ArbZG §4)",
        )
    requirements = shift_type.staffing_requirements or [
        ShiftStaffingRequirementCreate(position=shift_type.position, required_staff=shift_type.required_staff)
    ]
    _ensure_shift_qualifications(db, department_id, requirements)
    record = models.ShiftType(
        **shift_type.model_dump(exclude={
            "break_minutes", "break_start_minutes", "position", "required_staff", "staffing_requirements",
        })
    )
    record.position = requirements[0].position
    record.required_staff = sum(item.required_staff for item in requirements)
    record.staffing_requirements = [
        models.ShiftStaffingRequirement(
            position=item.position,
            required_staff=item.required_staff,
        )
        for item in requirements
    ]
    record.break_minutes = break_minutes
    record.break_start_minutes = break_start_minutes
    record.department_id = department_id
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift type name already exists") from exc
    db.refresh(record)
    return record


@app.put("/api/shift-types/{shift_type_id}", response_model=ShiftTypeRead)
def update_shift_type(
    shift_type_id: int,
    shift_type: ShiftTypeCreate,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> models.ShiftType:
    record = db.get(models.ShiftType, shift_type_id)
    if record is None or not can_access_department(principal, record.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift type not found")
    department_id = shift_type.department_id
    if principal.role_key == "OBERARZT" or principal.can_manage_department:
        if department_id is None:
            department_id = record.department_id or (
                principal.department_id
                if principal.role_key == "OBERARZT" or principal.department_id in principal.managed_department_ids
                else principal.managed_department_ids[0]
            )
        if not can_access_department(principal, department_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only plan your own department")
    verify_department(db, department_id)
    gross = gross_duration(shift_type.start_time, shift_type.end_time)
    break_minutes = (
        shift_type.break_minutes
        if shift_type.break_minutes is not None
        else required_break_minutes(gross)
    )
    required_break = required_break_minutes(gross, break_minutes)
    break_start_minutes = (
        shift_type.break_start_minutes
        if shift_type.break_start_minutes is not None
        else default_break_start_minutes(gross, break_minutes)
    )
    if break_minutes < required_break:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At least {required_break} minutes of break are required for this shift length (ArbZG §4)",
        )
    gross_minutes = int(gross.total_seconds() // 60)
    if break_minutes and (
        break_start_minutes > 360
        or break_start_minutes + break_minutes > gross_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The scheduled break must fit within the shift and start within the first six hours (ArbZG §4)",
        )
    requirements = shift_type.staffing_requirements or [
        ShiftStaffingRequirementCreate(position=shift_type.position, required_staff=shift_type.required_staff)
    ]
    _ensure_shift_qualifications(db, department_id, requirements)
    values = shift_type.model_dump(exclude={
        "break_minutes", "break_start_minutes", "position", "required_staff", "staffing_requirements",
    })
    for field, value in values.items():
        setattr(record, field, value)
    record.position = requirements[0].position
    record.required_staff = sum(item.required_staff for item in requirements)
    record.staffing_requirements = [
        models.ShiftStaffingRequirement(position=item.position, required_staff=item.required_staff)
        for item in requirements
    ]
    record.break_minutes = break_minutes
    record.break_start_minutes = break_start_minutes
    record.department_id = department_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift type name already exists") from exc
    db.refresh(record)
    return record


@app.delete("/api/shift-types/{shift_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift_type(
    shift_type_id: int, principal: Principal = Depends(require_edit), db: Session = Depends(get_db)
) -> Response:
    shift_type = db.get(models.ShiftType, shift_type_id)
    if shift_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift type not found")
    if not can_access_department(principal, shift_type.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift type not found")
    if shift_type.assignments:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift type is in use")
    db.delete(shift_type)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/assignments", response_model=list[AssignmentRead])
def list_assignments(
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    timezone_offset_minutes: int = Query(default=0, ge=-840, le=840),
    principal: Principal = Depends(require_plan_view),
    db: Session = Depends(get_db),
) -> list[AssignmentRead]:
    if end < start or (end - start).days > 62:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Date range must be 1–63 days")
    local_offset = timedelta(minutes=timezone_offset_minutes)
    range_start = datetime.combine(start, time.min, tzinfo=timezone.utc) - local_offset
    range_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc) - local_offset
    query = (
        select(models.Assignment)
        .join(models.ShiftType)
        .where(models.Assignment.starts_at < range_end, models.Assignment.ends_at > range_start)
        .order_by(models.Assignment.starts_at)
    )
    if scoped_to_department(principal):
        query = query.where(models.ShiftType.department_id.in_(accessible_department_ids(principal)))
    if principal.role_key == "EMPLOYEE":
        query = query.where(models.Assignment.employee_id == principal.employee_id)
    assignments = db.scalars(query)
    return [
        AssignmentRead(
            id=assignment.id,
            employee_id=assignment.employee_id,
            shift_type_id=assignment.shift_type_id,
            starts_at=assignment.starts_at,
            ends_at=assignment.ends_at,
            employee_name=assignment.employee.name,
            shift_name=assignment.shift_type.name,
        )
        for assignment in assignments
    ]


@app.post("/api/assignments", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(
    assignment: AssignmentCreate,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> AssignmentRead:
    employee = db.scalar(
        select(models.Employee)
        .where(models.Employee.id == assignment.employee_id)
        .with_for_update()
    )
    shift_type = db.get(models.ShiftType, assignment.shift_type_id)
    if employee is None or shift_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee or shift type not found")
    if scoped_to_department(principal) and (
        not can_access_department(principal, shift_type.department_id)
        or not can_access_department(principal, employee.department_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only plan your own department")
    if shift_type.department_id != employee.department_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee and shift must belong to the same department")

    return save_assignment(assignment, employee, shift_type, db)


@app.post("/api/optimization/preview")
def preview_optimized_day(
    request: OptimizationPreviewRequest,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if request.department_id is not None:
        if not can_access_department(principal, request.department_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        department_ids = (request.department_id,)
    elif scoped_to_department(principal):
        department_ids = accessible_department_ids(principal)
        if not department_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No department access is configured")
    else:
        department_ids = None
    try:
        preview = optimize_day(db, request.target_date, department_ids)
    except OptimizationTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "target_date": request.target_date,
        "status": preview.status,
        "suggestions": [
            {
                "employee_id": item.employee_id,
                "employee_name": item.employee_name,
                "employee_role": item.employee_role,
                "shift_type_id": item.shift_type_id,
                "shift_name": item.shift_name,
                "position": item.position,
                "role_match": item.role_match,
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
            }
            for item in preview.suggestions
        ],
        "unfilled_slots": [
            {
                "shift_type_id": item.shift_type_id,
                "shift_name": item.shift_name,
                "position": item.position,
            }
            for item in preview.unfilled_slots
        ],
    }


def resolve_planning_departments(
    principal: Principal, department_id: int | None
) -> tuple[int, ...] | None:
    if department_id is not None:
        if not can_access_department(principal, department_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return (department_id,)
    if scoped_to_department(principal):
        department_ids = accessible_department_ids(principal)
        if not department_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No department access is configured")
        return tuple(department_ids)
    return None


@app.post("/api/planning/preview")
def preview_planning_period(
    request: PlanningRequest,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    department_ids = resolve_planning_departments(principal, request.department_id)
    try:
        days = optimize_period(db, request.start_date, request.end_date, department_ids)
    except OptimizationTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "start_date": request.start_date,
        "end_date": request.end_date,
        "days": [
            {
                "target_date": day.target_date,
                "status": day.preview.status,
                "suggestions": [
                    {
                        "employee_id": item.employee_id,
                        "employee_name": item.employee_name,
                        "employee_role": item.employee_role,
                        "shift_type_id": item.shift_type_id,
                        "shift_name": item.shift_name,
                        "position": item.position,
                        "role_match": item.role_match,
                        "starts_at": item.starts_at,
                        "ends_at": item.ends_at,
                    }
                    for item in day.preview.suggestions
                ],
                "unfilled_slots": [
                    {
                        "shift_type_id": item.shift_type_id,
                        "shift_name": item.shift_name,
                        "position": item.position,
                    }
                    for item in day.preview.unfilled_slots
                ],
            }
            for day in days
        ],
    }


@app.post("/api/planning/sick-cover/preview")
def preview_sick_coverage(
    request: SickCoveragePreviewRequest,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    absence = db.get(models.Absence, request.absence_id)
    if absence is None or absence.kind != "sick" or absence.status != "approved":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sick absence not found")
    employee = db.get(models.Employee, absence.employee_id)
    if employee is None or not can_access_department(principal, employee.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sick absence not found")

    business_tz = business_timezone(db)
    range_start = datetime.combine(absence.start_date, time.min, tzinfo=business_tz).astimezone(timezone.utc)
    range_end = datetime.combine(absence.end_date + timedelta(days=1), time.min, tzinfo=business_tz).astimezone(timezone.utc)
    affected = list(db.scalars(
        select(models.Assignment)
        .join(models.ShiftType)
        .where(
            models.Assignment.employee_id == employee.id,
            models.Assignment.starts_at < range_end,
            models.Assignment.ends_at > range_start,
        )
        .order_by(models.Assignment.starts_at, models.Assignment.id)
    ))
    if scoped_to_department(principal):
        affected = [
            item for item in affected
            if can_access_department(principal, item.shift_type.department_id)
        ]

    grouped: dict[date, list[models.Assignment]] = {}
    position_by_assignment: dict[int, str] = {}
    for assignment in affected:
        starts_at = assignment.starts_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        target_date = starts_at.astimezone(business_tz).date()
        grouped.setdefault(target_date, []).append(assignment)
        requirements = assignment.shift_type.staffing_requirements or [
            models.ShiftStaffingRequirement(
                position=assignment.shift_type.position,
                required_staff=assignment.shift_type.required_staff,
            )
        ]
        qualifications = {assignment.employee.role.strip().casefold()}
        position_by_assignment[assignment.id] = next(
            (
                requirement.position.strip()
                for requirement in requirements
                if requirement.position.strip().casefold() in qualifications
            ),
            requirements[0].position.strip(),
        )

    suggestions_by_assignment: dict[int, list[dict[str, object]]] = {
        assignment.id: [] for assignment in affected
    }
    for target_date, assignments_for_day in grouped.items():
        target_vacancies: dict[tuple[int, str], int] = {}
        slot_assignments: dict[tuple[int, str], list[models.Assignment]] = {}
        for assignment in assignments_for_day:
            position = position_by_assignment[assignment.id]
            key = (assignment.shift_type_id, position.casefold())
            target_vacancies[key] = target_vacancies.get(key, 0) + 1
            slot_assignments.setdefault(key, []).append(assignment)

        try:
            preview = optimize_day(
                db,
                target_date,
                (employee.department_id,) if employee.department_id is not None else None,
                target_vacancies=target_vacancies,
            )
        except OptimizationTooLarge as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        suggestions_by_slot: dict[tuple[int, str], list[dict[str, object]]] = {}
        for item in preview.suggestions:
            key = (item.shift_type_id, item.position.strip().casefold())
            suggestions_by_slot.setdefault(key, []).append({
                "employee_id": item.employee_id,
                "employee_name": item.employee_name,
                "employee_role": item.employee_role,
                "role_match": item.role_match,
            })
        for key, assignments_for_slot in slot_assignments.items():
            available = suggestions_by_slot.get(key, [])
            for assignment in assignments_for_slot:
                if available:
                    suggestions_by_assignment[assignment.id].append(available.pop(0))

    return {
        "absence_id": absence.id,
        "employee_name": employee.name,
        "start_date": absence.start_date,
        "end_date": absence.end_date,
        "assignments": [
            {
                "assignment_id": assignment.id,
                "shift_type_id": assignment.shift_type_id,
                "shift_name": assignment.shift_type.name,
                "position": position_by_assignment[assignment.id],
                "starts_at": assignment.starts_at,
                "ends_at": assignment.ends_at,
                "suggestions": suggestions_by_assignment[assignment.id],
            }
            for assignment in affected
        ],
    }


@app.post("/api/planning/sick-cover/approve", status_code=status.HTTP_201_CREATED)
def approve_sick_coverage(
    request: SickCoverageApproval,
    absence_id: int = Query(gt=0),
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    absence = db.get(models.Absence, absence_id)
    if absence is None or absence.kind != "sick" or absence.status != "approved":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sick absence not found")
    absent_employee = db.get(models.Employee, absence.employee_id)
    if absent_employee is None or not can_access_department(principal, absent_employee.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sick absence not found")
    assignment_ids = [item.assignment_id for item in request.replacements]
    if len(set(assignment_ids)) != len(assignment_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A sick shift can only be replaced once")

    business_tz = business_timezone(db)
    range_start = datetime.combine(absence.start_date, time.min, tzinfo=business_tz).astimezone(timezone.utc)
    range_end = datetime.combine(absence.end_date + timedelta(days=1), time.min, tzinfo=business_tz).astimezone(timezone.utc)
    originals = list(db.scalars(
        select(models.Assignment)
        .join(models.ShiftType)
        .where(
            models.Assignment.id.in_(assignment_ids),
            models.Assignment.employee_id == absent_employee.id,
            models.Assignment.starts_at < range_end,
            models.Assignment.ends_at > range_start,
        )
    ))
    original_by_id = {assignment.id: assignment for assignment in originals}
    if len(original_by_id) != len(assignment_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A sick shift changed; regenerate the suggestions")
    for assignment in originals:
        if not can_access_department(principal, assignment.shift_type.department_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sick absence not found")

    try:
        replacements: list[tuple[models.Assignment, models.Employee]] = []
        for item in request.replacements:
            original = original_by_id[item.assignment_id]
            replacement = db.get(models.Employee, item.employee_id)
            if replacement is None or replacement.department_id != original.shift_type.department_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Replacement employee is no longer available")
            requirements = original.shift_type.staffing_requirements or [
                models.ShiftStaffingRequirement(
                    position=original.shift_type.position,
                    required_staff=original.shift_type.required_staff,
                )
            ]
            original_qualifications = {absent_employee.role.strip().casefold()}
            position = next(
                (
                    requirement.position.strip()
                    for requirement in requirements
                    if requirement.position.strip().casefold() in original_qualifications
                ),
                requirements[0].position.strip(),
            )
            if position.casefold() != replacement.role.strip().casefold():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Replacement employee lacks the required qualification")
            replacements.append((original, replacement))

        for original, _replacement in replacements:
            db.delete(original)
        db.flush()
        for original, replacement in replacements:
            starts_at = original.starts_at
            ends_at = original.ends_at
            if starts_at.tzinfo is None:
                starts_at = starts_at.replace(tzinfo=timezone.utc)
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            proposed = AssignmentCreate(
                employee_id=replacement.id,
                shift_type_id=original.shift_type_id,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            check_assignment_allowed(proposed, replacement, original.shift_type, db)
            db.add(models.Assignment(**proposed.model_dump()))
            db.flush()
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return {"created": len(replacements)}


@app.post("/api/planning/approve", status_code=status.HTTP_201_CREATED)
def approve_planning(
    request: PlanningApproval,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    business_tz = business_timezone(db)
    created = 0
    try:
        for item in sorted(request.items, key=lambda entry: entry.target_date):
            employee = db.get(models.Employee, item.employee_id)
            shift_type = db.get(models.ShiftType, item.shift_type_id)
            if employee is None or shift_type is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee or shift type not found")
            if not can_access_department(principal, shift_type.department_id) or not can_access_department(principal, employee.department_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only plan your own department")
            if shift_type.department_id != employee.department_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee and shift must belong to the same department")
            starts_at, ends_at = _shift_interval(item.target_date, shift_type, business_tz)
            staffed = db.scalar(
                select(func.count(models.Assignment.id)).where(
                    models.Assignment.shift_type_id == shift_type.id,
                    models.Assignment.starts_at >= starts_at,
                    models.Assignment.starts_at < starts_at + timedelta(minutes=1),
                )
            ) or 0
            if staffed >= shift_type.required_staff:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{shift_type.name} on {item.target_date} is already fully staffed")
            assignment = AssignmentCreate(
                employee_id=employee.id,
                shift_type_id=shift_type.id,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            check_assignment_allowed(assignment, employee, shift_type, db)
            db.add(models.Assignment(**assignment.model_dump()))
            db.flush()
            created += 1
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return {"created": created}


def check_assignment_allowed(
    assignment: AssignmentCreate,
    employee: models.Employee,
    shift_type: models.ShiftType,
    db: Session,
) -> None:
    requirements = shift_type.staffing_requirements or [
        models.ShiftStaffingRequirement(
            position=shift_type.position,
            required_staff=shift_type.required_staff,
        )
    ]
    qualification_required = len(requirements) > 1 or any(
        item.position.strip().casefold() == "oberarzt" for item in requirements
    )
    employee_qualifications = {name.strip().casefold() for name in employee.qualification_names}
    if qualification_required and not employee_qualifications.intersection(
        item.position.strip().casefold() for item in requirements
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee role is not required for this shift",
        )
    matching_requirement = next(
        (
            item for item in requirements
            if item.position.strip().casefold() in employee_qualifications
        ),
        None,
    )
    if qualification_required and matching_requirement is not None:
        staffed_for_position = db.scalar(
            select(func.count(func.distinct(models.Assignment.id)))
            .join(models.Employee)
            .join(
                models.employee_qualification_access,
                models.employee_qualification_access.c.employee_id == models.Employee.id,
            )
            .join(
                models.DepartmentQualification,
                models.DepartmentQualification.id == models.employee_qualification_access.c.qualification_id,
            )
            .where(
                models.Assignment.shift_type_id == shift_type.id,
                models.Assignment.starts_at == assignment.starts_at,
                func.lower(models.DepartmentQualification.name) == matching_requirement.position.casefold(),
            )
        ) or 0
        if staffed_for_position >= matching_requirement.required_staff:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{matching_requirement.position} positions are already fully staffed",
            )
    overlaps = db.scalar(
        select(models.Assignment.id).where(
            models.Assignment.employee_id == assignment.employee_id,
            models.Assignment.starts_at < assignment.ends_at,
            models.Assignment.ends_at > assignment.starts_at,
        ).limit(1)
    )
    if overlaps is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee already has an overlapping shift")
    if employee_is_absent(db, employee.id, assignment.starts_at, assignment.ends_at):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee is absent during this shift")
    violation = work_rule_violation(
        db,
        employee.id,
        assignment.starts_at,
        assignment.ends_at,
        shift_type.break_minutes,
        shift_type.break_start_minutes,
    )
    if violation is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=violation)


def save_assignment(
    assignment: AssignmentCreate,
    employee: models.Employee,
    shift_type: models.ShiftType,
    db: Session,
) -> AssignmentRead:
    check_assignment_allowed(assignment, employee, shift_type, db)
    record = models.Assignment(**assignment.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return AssignmentRead(
        id=record.id,
        employee_id=record.employee_id,
        shift_type_id=record.shift_type_id,
        starts_at=record.starts_at,
        ends_at=record.ends_at,
        employee_name=employee.name,
        shift_name=shift_type.name,
    )


@app.get("/api/smart-selection")
def smart_selection(
    shift_type_id: int = Query(gt=0),
    starts_at: datetime = Query(),
    ends_at: datetime = Query(),
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid timezone-aware interval is required")
    shift_type = db.get(models.ShiftType, shift_type_id)
    if shift_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift type not found")
    if not can_access_department(principal, shift_type.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift type not found")
    employee_query = select(models.Employee).order_by(models.Employee.name)
    if scoped_to_department(principal):
        employee_query = employee_query.where(models.Employee.department_id.in_(accessible_department_ids(principal)))
    employees = list(db.scalars(employee_query))
    candidates: list[dict[str, object]] = []
    rules = load_work_rules(db)
    for employee in employees:
        conflicts = db.scalar(
            select(models.Assignment.id).where(
                models.Assignment.employee_id == employee.id,
                models.Assignment.starts_at < ends_at,
                models.Assignment.ends_at > starts_at,
            ).limit(1)
        )
        if (
            conflicts is not None
            or employee_is_absent(db, employee.id, starts_at, ends_at)
            or work_rule_violation(
                db,
                employee.id,
                starts_at,
                ends_at,
                shift_type.break_minutes,
                shift_type.break_start_minutes,
                rules,
            ) is not None
        ):
            continue
        employee_qualifications = {name.strip().casefold() for name in employee.qualification_names}
        role_match = shift_type.position.strip().casefold() in employee_qualifications
        requirements = shift_type.staffing_requirements or [
            models.ShiftStaffingRequirement(
                position=shift_type.position,
                required_staff=shift_type.required_staff,
            )
        ]
        qualification_required = len(requirements) > 1 or any(
            item.position.strip().casefold() == "oberarzt" for item in requirements
        )
        if qualification_required and not any(
            item.position.strip().casefold() in employee_qualifications
            for item in requirements
        ):
            continue
        week_start = starts_at.replace(hour=0, minute=0, second=0, microsecond=0)
        planned_assignments = len(list(db.scalars(
            select(models.Assignment.id).where(
                models.Assignment.employee_id == employee.id,
                models.Assignment.starts_at >= week_start,
                models.Assignment.starts_at < week_start + timedelta(days=7),
            )
        )))
        candidates.append({
            "employee_id": employee.id,
            "employee_name": employee.name,
            "role": employee.role,
            "role_match": role_match,
            "planned_assignments": planned_assignments,
        })
    candidates.sort(key=lambda item: (not item["role_match"], item["planned_assignments"], item["employee_name"]))
    return {"position": shift_type.position, "candidates": candidates}


@app.post("/api/smart-selection/approve", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def approve_smart_assignment(
    assignment: AssignmentCreate,
    principal: Principal = Depends(require_approve),
    db: Session = Depends(get_db),
) -> AssignmentRead:
    employee = db.get(models.Employee, assignment.employee_id)
    shift_type = db.get(models.ShiftType, assignment.shift_type_id)
    if employee is None or shift_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee or shift type not found")
    if scoped_to_department(principal) and (
        not can_access_department(principal, shift_type.department_id)
        or not can_access_department(principal, employee.department_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only approve for your own department")
    if shift_type.department_id != employee.department_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee and shift must belong to the same department")
    return save_assignment(assignment, employee, shift_type, db)


@app.delete("/api/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int, principal: Principal = Depends(require_edit), db: Session = Depends(get_db)
) -> Response:
    assignment = db.get(models.Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if not can_access_department(principal, assignment.shift_type.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    db.delete(assignment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
