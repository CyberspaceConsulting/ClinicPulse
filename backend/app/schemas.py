from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_required_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("Name must not be empty")
    return value


class PersonName(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_required_name(value)


class PersonalDetails(BaseModel):
    birth_date: date | None = None
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is not None and not (date(1900, 1, 1) <= value <= date.today()):
            raise ValueError("Birth date is not plausible")
        return value

    @field_validator("address", "phone")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class EmployeeCreate(PersonName):
    role: str = Field(default="Employee", min_length=1, max_length=80)
    department_id: int = Field(gt=0)
    qualification_ids: list[int] = Field(default_factory=list)


class EmployeeUpdate(EmployeeCreate):
    pass


class EmployeeOnboardCreate(EmployeeCreate):
    create_account: bool = False
    username: str | None = Field(default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(default=None, min_length=3, max_length=254)
    password: str | None = Field(default=None, min_length=8, max_length=256)

    @model_validator(mode="after")
    def require_invitation_details(self) -> "EmployeeOnboardCreate":
        if self.create_account and (not self.username or (not self.email and not self.password)):
            raise ValueError("Username and email or password are required when creating an account")
        if self.email is not None:
            self.email = self.email.strip()
            if "@" not in self.email:
                raise ValueError("A valid email address is required")
        return self


class DepartmentQualificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    leadership_eligible: bool = False

    @field_validator("name")
    @classmethod
    def clean_qualification_name(cls, value: str) -> str:
        return _clean_required_name(value)


class DepartmentQualificationRead(DepartmentQualificationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    department_id: int | None
    qualifications: list[DepartmentQualificationRead] = Field(default_factory=list)
    profile_image_data: str | None = None


class ShiftStaffingRequirementCreate(BaseModel):
    position: str = Field(min_length=1, max_length=80)
    required_staff: int = Field(ge=1, le=100)

    @field_validator("position")
    @classmethod
    def clean_position(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Position must not be empty")
        return value


class ShiftStaffingRequirementRead(ShiftStaffingRequirementCreate):
    model_config = ConfigDict(from_attributes=True)


class ShiftTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start_time: time
    end_time: time
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    position: str = Field(default="Pflegefachkraft", min_length=1, max_length=80)
    required_staff: int = Field(default=1, ge=1, le=100)
    department_id: int | None = Field(default=None, gt=0)
    break_minutes: int | None = Field(default=None, ge=0, le=240)
    break_start_minutes: int | None = Field(default=None, ge=0, le=360)
    staffing_requirements: list[ShiftStaffingRequirementCreate] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_staffing_requirements(self) -> "ShiftTypeCreate":
        if self.staffing_requirements is not None:
            positions = [item.position.casefold() for item in self.staffing_requirements]
            if len(positions) != len(set(positions)):
                raise ValueError("Each position can only be listed once")
            if sum(item.required_staff for item in self.staffing_requirements) > 100:
                raise ValueError("Total required staff must not exceed 100")
        return self


class ShiftTypeRead(ShiftTypeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    break_minutes: int
    break_start_minutes: int
    staffing_requirements: list[ShiftStaffingRequirementRead]


class WorkRulesRead(BaseModel):
    rest_hours: int
    max_daily_hours: int
    max_weekly_hours: int


class WorkRulesUpdate(BaseModel):
    rest_hours: int = Field(ge=11, le=24)
    max_daily_hours: int = Field(ge=1, le=10)
    max_weekly_hours: int = Field(ge=1, le=48)


class BusinessConfigurationRead(BaseModel):
    federal_state: str
    operational_profile: str
    operational_profile_managed: bool = False
    federal_state_managed: bool = False
    timezone: str
    sunday_work_authorized: bool


class BusinessConfigurationUpdate(BaseModel):
    federal_state: Literal[
        "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
        "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz",
        "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
    ] | None = None
    operational_profile: Literal["hospital", "rescue_service", "ils", "care_facility", "other"] | None = None
    sunday_work_authorized: bool = False


class AssignmentCreate(BaseModel):
    employee_id: int = Field(gt=0)
    shift_type_id: int = Field(gt=0)
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> "AssignmentCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("Shift end must be after shift start")
        return self


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    shift_type_id: int
    starts_at: datetime
    ends_at: datetime
    employee_name: str
    shift_name: str


class OptimizationPreviewRequest(BaseModel):
    target_date: date
    department_id: int | None = Field(default=None, gt=0)


class PlanningRequest(BaseModel):
    start_date: date
    end_date: date
    department_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_period(self) -> "PlanningRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days >= 31:
            raise ValueError("Planning period is limited to 31 days")
        return self


class PlanningItem(BaseModel):
    employee_id: int = Field(gt=0)
    shift_type_id: int = Field(gt=0)
    target_date: date


class PlanningApproval(BaseModel):
    items: list[PlanningItem] = Field(min_length=1, max_length=500)


class SickCoveragePreviewRequest(BaseModel):
    absence_id: int = Field(gt=0)


class SickCoverageReplacement(BaseModel):
    assignment_id: int = Field(gt=0)
    employee_id: int = Field(gt=0)


class SickCoverageApproval(BaseModel):
    replacements: list[SickCoverageReplacement] = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    stay_signed_in: bool = False


class SetupRequest(PersonName):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)
    license_token: str = Field(min_length=1, max_length=4096)
    federal_state: Literal[
        "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
        "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz",
        "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
    ] | None = None
    operational_profile: Literal["hospital", "rescue_service", "ils", "care_facility", "other"] | None = None
    sunday_work_authorized: bool = False

    @field_validator("license_token")
    @classmethod
    def require_nonempty_license_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("License token must not be empty")
        return token


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DepartmentUpdate(DepartmentCreate):
    qualifications: list[DepartmentQualificationCreate] | None = None


class DepartmentRead(DepartmentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    manager_user_id: int | None = None
    deputy_user_id: int | None = None
    qualifications: list[DepartmentQualificationRead] = Field(default_factory=list)


class DepartmentLeaderUpdate(BaseModel):
    manager_user_id: int | None = Field(default=None, gt=0)
    deputy_user_id: int | None = Field(default=None, gt=0)


AccessRole = Literal["ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL", "OBERARZT", "CHEFARZT", "KIOSK", "EMPLOYEE"]


class UserCreate(PersonName, PersonalDetails):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str | None = Field(default=None, min_length=8, max_length=256)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    role_key: AccessRole
    department_id: int | None = Field(default=None, gt=0)
    department_ids: list[int] = Field(default_factory=list)
    employee_id: int | None = Field(default=None, gt=0)
    can_view: bool = True
    can_edit: bool = False
    can_approve: bool = False

    @model_validator(mode="after")
    def require_view_for_planning_access(self) -> "UserCreate":
        if self.role_key == "HOSPITAL_MANAGEMENT" and "can_view" not in self.model_fields_set:
            self.can_view = False
        if self.email is not None:
            self.email = self.email.strip()
            if "@" not in self.email:
                raise ValueError("A valid email address is required")
        if self.password is None and self.email is None:
            raise ValueError("An email address is required when no password is supplied")
        if not self.department_ids and self.department_id is not None:
            self.department_ids = [self.department_id]
        self.department_ids = list(dict.fromkeys(self.department_ids))
        if self.department_ids and self.department_id is None:
            self.department_id = self.department_ids[0]
        if self.role_key != "HOSPITAL_MANAGEMENT" and (self.can_edit or self.can_approve) and not self.can_view:
            raise ValueError("Planning permissions require schedule view access")
        if self.role_key == "KIOSK" and (not self.can_view or self.can_edit or self.can_approve):
            raise ValueError("Kiosk accounts must be read-only and have schedule view access")
        if self.role_key in {"OBERARZT", "CHEFARZT"} and not self.department_ids:
            raise ValueError("At least one department is required for this role")
        if self.role_key == "EMPLOYEE":
            if self.employee_id is None:
                raise ValueError("Employee accounts must be linked to an employee")
            if not self.can_view:
                raise ValueError("Employee accounts must have schedule view access")
        elif self.role_key in {"ADMIN", "KIOSK"} and self.employee_id is not None:
            raise ValueError("Administrator and kiosk accounts cannot be linked to an employee")
        return self


class UserUpdate(PersonName, PersonalDetails):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    role_key: AccessRole
    department_id: int | None = Field(default=None, gt=0)
    can_view: bool = True
    can_edit: bool = False
    can_approve: bool = False
    department_ids: list[int] = Field(default_factory=list)
    employee_id: int | None = Field(default=None, gt=0)
    new_password: str | None = Field(default=None, min_length=8, max_length=256)
    email: str | None = Field(default=None, min_length=3, max_length=254)

    @model_validator(mode="after")
    def require_view_for_planning_access(self) -> "UserUpdate":
        if self.role_key == "HOSPITAL_MANAGEMENT" and "can_view" not in self.model_fields_set:
            self.can_view = False
        if self.email is not None:
            self.email = self.email.strip()
            if "@" not in self.email:
                raise ValueError("A valid email address is required")
        if not self.department_ids and self.department_id is not None:
            self.department_ids = [self.department_id]
        self.department_ids = list(dict.fromkeys(self.department_ids))
        if self.department_ids and self.department_id is None:
            self.department_id = self.department_ids[0]
        if self.role_key != "HOSPITAL_MANAGEMENT" and (self.can_edit or self.can_approve) and not self.can_view:
            raise ValueError("Planning permissions require schedule view access")
        if self.role_key == "KIOSK" and (not self.can_view or self.can_edit or self.can_approve):
            raise ValueError("Kiosk accounts must be read-only and have schedule view access")
        if self.role_key in {"OBERARZT", "CHEFARZT"} and not self.department_ids:
            raise ValueError("At least one department is required for this role")
        if self.role_key == "EMPLOYEE":
            if self.employee_id is None:
                raise ValueError("Employee accounts must be linked to an employee")
            if not self.can_view:
                raise ValueError("Employee accounts must have schedule view access")
        elif self.role_key in {"ADMIN", "KIOSK"} and self.employee_id is not None:
            raise ValueError("Administrator and kiosk accounts cannot be linked to an employee")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role_key: str
    department_id: int | None
    department_ids: list[int]
    employee_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    birth_date: date | None = None
    address: str | None = None
    phone: str | None = None
    can_view: bool
    can_edit: bool
    can_approve: bool
    can_manage_department: bool = False
    is_locked: bool = False
    email: str | None = None
    invitation_status: str = "active"


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=8, max_length=256)


class UserLockRequest(BaseModel):
    locked: bool


class SettingsUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    new_password: str | None = Field(default=None, min_length=8, max_length=256)


class PasswordCheck(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class PasswordCheckResponse(BaseModel):
    compromised_count: int


class SessionResponse(BaseModel):
    username: str
    role_key: str = "ADMIN"
    department_id: int | None = None
    employee_id: int | None = None
    can_view: bool = True
    can_edit: bool = True
    can_approve: bool = True
    can_manage: bool = True
    can_manage_department: bool = False
    remember_me: bool = False
    idle_timeout_minutes: int | None = None
    must_change_password: bool = False


class MailMode(BaseModel):
    enabled: bool


class SecuritySettings(BaseModel):
    idle_timeout_minutes: int = Field(ge=1, le=120)


class MailSettingsUpdate(BaseModel):
    public_url: str = Field(min_length=8, max_length=500)
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_username: str = Field(default="", max_length=255)
    smtp_password: str | None = Field(default=None, max_length=512)
    clear_smtp_password: bool = False
    from_address: str = Field(min_length=3, max_length=255)
    use_ssl: bool = False
    use_starttls: bool = True

    @model_validator(mode="after")
    def validate_password_change(self) -> "MailSettingsUpdate":
        if self.clear_smtp_password and self.smtp_password:
            raise ValueError("Choose either a new SMTP password or clearing the saved password")
        if self.use_ssl and self.use_starttls:
            raise ValueError("Implicit TLS and STARTTLS cannot be enabled together")
        if self.smtp_username and self.smtp_password and not (self.use_ssl or self.use_starttls):
            raise ValueError("SMTP authentication requires TLS")
        return self

    @field_validator("public_url")
    @classmethod
    def require_safe_instance_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        local_http_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and parsed.hostname not in local_http_hosts)
        ):
            raise ValueError("The public instance URL must use HTTPS")
        return normalized


class MailSettingsRead(BaseModel):
    public_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password_configured: bool
    from_address: str
    use_ssl: bool
    use_starttls: bool


class MailTestRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=254)

    @field_validator("recipient")
    @classmethod
    def require_email_address(cls, value: str) -> str:
        normalized = value.strip()
        if "@" not in normalized:
            raise ValueError("A valid email address is required")
        return normalized


class ProfileUpdate(PersonalDetails):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    profile_image_data: str | None = Field(default=None, max_length=400_000)
    profile_photo_visibility: Literal["private", "department"]

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_required_name(value)

    @field_validator("profile_image_data")
    @classmethod
    def validate_profile_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        import base64
        import binascii

        if not value.startswith("data:image/"):
            raise ValueError("Profile image must be a PNG, JPEG, or WebP data URL")
        mime, separator, encoded = value.partition(",")
        if not separator or mime not in {
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/webp;base64",
        }:
            raise ValueError("Profile image must be a PNG, JPEG, or WebP data URL")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Profile image data is invalid") from exc
        if not decoded or len(decoded) > 256_000:
            raise ValueError("Profile image must be between 1 byte and 256 KB")
        if mime == "data:image/png;base64" and not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Profile image does not match its declared format")
        if mime == "data:image/jpeg;base64" and not decoded.startswith(b"\xff\xd8\xff"):
            raise ValueError("Profile image does not match its declared format")
        if mime == "data:image/webp;base64" and not (
            decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP"
        ):
            raise ValueError("Profile image does not match its declared format")
        return value


class ProfileResponse(BaseModel):
    username: str
    role_key: str
    department_id: int | None
    profile_image_data: str | None
    profile_photo_visibility: Literal["private", "department"]
    first_name: str | None = None
    last_name: str | None = None
    birth_date: date | None = None
    address: str | None = None
    phone: str | None = None
    remember_me: bool = False


class TeamProfileRead(BaseModel):
    username: str
    role_key: str
    profile_image_data: str | None
    department_id: int | None


class UpdateChannelUpdate(BaseModel):
    channel: Literal["main", "test"]


class LicenseTokenUpdate(BaseModel):
    license_token: str = Field(min_length=1, max_length=4096)

    @field_validator("license_token")
    @classmethod
    def trim_license_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("License token must not be empty")
        return token


class HealthResponse(BaseModel):
    status: str
    date: date


AbsenceKind = Literal["vacation", "sick", "other"]


class AbsenceCreate(BaseModel):
    employee_id: int | None = Field(default=None, gt=0)
    kind: AbsenceKind
    start_date: date
    end_date: date
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_range(self) -> "AbsenceCreate":
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 365:
            raise ValueError("Absence must span 1-366 days")
        return self


class AbsenceDecision(BaseModel):
    decision: Literal["approved", "rejected"]


class AbsenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str
    kind: str
    start_date: date
    end_date: date
    status: str
    note: str | None
    requested_by: str | None = None
    created_at: datetime | None = None
    decided_by: str | None
    decided_at: datetime | None = None
