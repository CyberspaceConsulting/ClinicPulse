from datetime import datetime, timezone

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from . import models
from .encrypted import username_lookup_digest

AUDITED_MODELS = (
    models.AdminAccount,
    models.UserAccount,
    models.Department,
    models.Employee,
    models.ShiftType,
    models.Assignment,
    models.ApplicationSetting,
    models.BusinessConfiguration,
    models.Absence,
    models.PlanArchive,
    models.ArchiveSettings,
    models.BackupTarget,
    models.BackupSettings,
    models.BackupRecipient,
)


@event.listens_for(Session, "before_flush")
def record_audit_events(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    actor = session.info.get("audit_actor")
    if not isinstance(actor, str) or not actor:
        return

    pending = session.info.setdefault("pending_audit_events", [])
    pending.extend(
        (record, "created")
        for record in session.new
        if isinstance(record, AUDITED_MODELS)
    )
    pending.extend(
        (record, "deleted")
        for record in session.deleted
        if isinstance(record, AUDITED_MODELS)
    )
    pending.extend(
        (record, "updated")
        for record in session.dirty
        if record not in session.deleted
        and isinstance(record, AUDITED_MODELS)
        and inspect(record).modified
    )


@event.listens_for(Session, "before_flush")
def update_username_lookup_digests(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    for record in session.new.union(session.dirty):
        if isinstance(record, (models.AdminAccount, models.UserAccount)):
            record.username_lookup = username_lookup_digest(record.username)


@event.listens_for(Session, "after_flush_postexec")
def persist_audit_events(session: Session, _flush_context: object) -> None:
    for record, action in session.info.pop("pending_audit_events", []):
        identity = inspect(record).identity
        entity_id = identity[0] if identity else getattr(record, "id", None)
        session.add(models.AuditEvent(
            created_at=datetime.now(timezone.utc),
            actor_username=str(session.info["audit_actor"])[:64],
            action=action,
            entity_type=type(record).__name__,
            entity_id=str(entity_id) if entity_id is not None else "pending",
        ))
