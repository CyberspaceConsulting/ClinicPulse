from datetime import date, datetime, time

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .encrypted import EncryptedText


user_department_access = Table(
    "user_department_access",
    Base.metadata,
    Column("user_id", ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")
    shift_types: Mapped[list["ShiftType"]] = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText(), index=False)
    first_name: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    last_name: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    role: Mapped[str] = mapped_column(String(80), default="Employee")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="employee")
    department: Mapped[Department | None] = relationship(back_populates="employees")


class ShiftType(Base):
    __tablename__ = "shift_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    position: Mapped[str] = mapped_column(String(80), default="Pflegefachkraft")
    required_staff: Mapped[int] = mapped_column(Integer, default=1)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    break_start_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="shift_type")
    department: Mapped[Department | None] = relationship(back_populates="shift_types")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    shift_type_id: Mapped[int] = mapped_column(ForeignKey("shift_types.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee] = relationship(back_populates="assignments")
    shift_type: Mapped[ShiftType] = relationship(back_populates="assignments")


class AdminAccount(Base):
    __tablename__ = "admin_account"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    username: Mapped[str] = mapped_column(EncryptedText())
    username_lookup: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_salt: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(128))
    signing_key: Mapped[str] = mapped_column(EncryptedText())
    license_token: Mapped[str] = mapped_column(EncryptedText(), default="")
    profile_image_data: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    profile_photo_visibility: Mapped[str] = mapped_column(String(16), default="private")
    token_version: Mapped[int] = mapped_column(Integer, default=0)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(EncryptedText())
    username_lookup: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_salt: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(128))
    role_key: Mapped[str] = mapped_column(String(32))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    can_view: Mapped[bool] = mapped_column(default=True)
    can_edit: Mapped[bool] = mapped_column(default=False)
    can_approve: Mapped[bool] = mapped_column(default=False)
    email: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    first_name: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    last_name: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    birth_date: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    invitation_status: Mapped[str] = mapped_column(String(24), default="active", server_default="active")
    profile_image_data: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    profile_photo_visibility: Mapped[str] = mapped_column(String(16), default="private")
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(default=False)

    department: Mapped[Department | None] = relationship()
    departments: Mapped[list[Department]] = relationship(
        secondary=user_department_access,
        order_by=Department.id,
        lazy="selectin",
    )

    @property
    def department_ids(self) -> list[int]:
        return [department.id for department in self.departments]


class AccountInvitation(Base):
    __tablename__ = "account_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), unique=True, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(24), default="pending")


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    update_channel: Mapped[str] = mapped_column(String(16), default="stable")
    rest_hours: Mapped[int] = mapped_column(Integer, default=11, server_default="11")
    max_daily_hours: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    max_weekly_hours: Mapped[int] = mapped_column(Integer, default=48, server_default="48")
    idle_timeout_minutes: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    mail_public_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    mail_smtp_host: Mapped[str] = mapped_column(String(255), default="", server_default="")
    mail_smtp_port: Mapped[int] = mapped_column(Integer, default=587, server_default="587")
    mail_smtp_username: Mapped[str] = mapped_column(String(255), default="", server_default="")
    mail_smtp_password: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    mail_from_address: Mapped[str] = mapped_column(String(255), default="", server_default="")
    mail_use_ssl: Mapped[bool] = mapped_column(default=False, server_default="false")
    mail_use_starttls: Mapped[bool] = mapped_column(default=True, server_default="true")


class BusinessConfiguration(Base):
    __tablename__ = "business_configuration"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    federal_state: Mapped[str] = mapped_column(String(32))
    operational_profile: Mapped[str] = mapped_column(String(32))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    sunday_work_authorized: Mapped[bool] = mapped_column(default=False, server_default="false")


class LicenseState(Base):
    __tablename__ = "license_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    installation_id: Mapped[str] = mapped_column(String(36), unique=True)
    signed_status_token: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    last_successful_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_last_seen", "last_seen"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[float] = mapped_column(Float)
    blocked_until: Mapped[float] = mapped_column(Float, default=0)
    last_seen: Mapped[float] = mapped_column(Float)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_actor_created_at", "actor_username", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor_username: Mapped[str] = mapped_column(EncryptedText())
    action: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))


class Absence(Base):
    __tablename__ = "absences"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    note: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship()


class PlanArchive(Base):
    __tablename__ = "plan_archives"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    department_name: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entry_count: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(EncryptedText())
    content_sha256: Mapped[str] = mapped_column(String(64))


class ArchiveSettings(Base):
    __tablename__ = "archive_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    auto_enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    period: Mapped[str] = mapped_column(String(8), default="monthly", server_default="monthly")
    last_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)


class BackupTarget(Base):
    __tablename__ = "backup_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    config: Mapped[str] = mapped_column(EncryptedText())
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true")
    retention_count: Mapped[int] = mapped_column(Integer, default=10, server_default="10")


class BackupSettings(Base):
    __tablename__ = "backup_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    schedule_enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    frequency: Mapped[str] = mapped_column(String(8), default="weekly", server_default="weekly")
    weekday: Mapped[int] = mapped_column(Integer, default=6, server_default="6")
    time_of_day: Mapped[str] = mapped_column(String(5), default="03:00", server_default="03:00")
    last_slot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trigger: Mapped[str] = mapped_column(String(12))
    target_name: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class BackupRecipient(Base):
    __tablename__ = "backup_recipients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    public_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
