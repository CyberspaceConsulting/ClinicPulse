import asyncio
import base64
import binascii
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .backup_core import (
    BackupError,
    backup_filename,
    create_backup,
    generate_recovery_key,
    is_backup_filename,
    load_recovery_key,
    parse_public_key,
    restore_backup,
)
from .backup_targets import KINDS, mask_config, open_target, parse_config, validate_config
from .database import SessionLocal, get_db
from .security import Principal, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/backup", tags=["backup"])

MAX_RESTORE_BYTES = 256 * 1024 * 1024
RESTORE_CONFIRMATION = "WIEDERHERSTELLEN"
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class TargetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["local", "sftp", "webdav", "s3"]
    config: dict[str, object] = {}
    enabled: bool = True
    retention_count: int = Field(default=10, ge=0, le=1000)


class TargetRead(BaseModel):
    id: int
    name: str
    kind: str
    config: dict[str, object]
    enabled: bool
    retention_count: int


class SettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schedule_enabled: bool
    frequency: Literal["daily", "weekly"]
    weekday: int = Field(ge=0, le=6)
    time_of_day: str = Field(pattern=TIME_PATTERN.pattern)


class SettingsRead(BaseModel):
    schedule_enabled: bool
    frequency: str
    weekday: int
    time_of_day: str
    recipient_count: int
    last_slot: datetime | None
    timezone: str


class RunRead(BaseModel):
    id: int
    started_at: datetime
    trigger: str
    target_name: str
    filename: str | None
    size_bytes: int | None
    status: str
    error: str | None


class RemoteFileRead(BaseModel):
    name: str
    size: int
    modified: datetime | None


class DownloadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Encrypt for exactly this key (e.g. a new instance) instead of all stored recipients.
    public_key: str | None = Field(default=None, max_length=100)


class RecipientWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    public_key: str = Field(max_length=100)


class RecipientRead(BaseModel):
    id: int
    name: str
    public_key: str
    created_at: datetime


class RecoveryKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Diese Instanz", min_length=1, max_length=80)
    passphrase: str = Field(max_length=200)
    add_as_recipient: bool = True


class TargetRestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(max_length=120)
    recovery_key: str = Field(max_length=4000)
    key_passphrase: str = Field(max_length=200)
    confirm: str


def _settings(db: Session) -> models.BackupSettings:
    settings = db.get(models.BackupSettings, 1)
    if settings is None:
        settings = models.BackupSettings(id=1)
        db.add(settings)
        db.flush()
    return settings


def _recipient_keys(db: Session) -> list[str]:
    return list(db.scalars(select(models.BackupRecipient.public_key).order_by(models.BackupRecipient.id)))


def _recipient_count(db: Session) -> int:
    return len(_recipient_keys(db))


def _timezone_name(db: Session) -> str:
    configuration = db.get(models.BusinessConfiguration, 1)
    return configuration.timezone if configuration else "Europe/Berlin"


def _zone(db: Session) -> ZoneInfo:
    try:
        return ZoneInfo(_timezone_name(db))
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Berlin")


def latest_slot(now: datetime, frequency: str, weekday: int, time_of_day: str) -> datetime:
    hour, minute = (int(part) for part in time_of_day.split(":"))
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if frequency == "weekly":
        slot -= timedelta(days=(now.weekday() - weekday) % 7)
        if slot > now:
            slot -= timedelta(days=7)
    elif slot > now:
        slot -= timedelta(days=1)
    return slot


def _target_read(target: models.BackupTarget) -> TargetRead:
    return TargetRead(
        id=target.id, name=target.name, kind=target.kind, config=mask_config(parse_config(target.config)),
        enabled=target.enabled, retention_count=target.retention_count,
    )


def _settings_read(db: Session, settings: models.BackupSettings) -> SettingsRead:
    return SettingsRead(
        schedule_enabled=settings.schedule_enabled, frequency=settings.frequency, weekday=settings.weekday,
        time_of_day=settings.time_of_day, recipient_count=_recipient_count(db),
        last_slot=settings.last_slot, timezone=_timezone_name(db),
    )


def _get_target(db: Session, target_id: int) -> models.BackupTarget:
    target = db.get(models.BackupTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Backup-Ziel nicht gefunden")
    return target


def _fail(exc: Exception, code: int = 422) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


def apply_retention(target: models.BackupTarget) -> None:
    if target.retention_count <= 0:
        return
    remote = open_target(target.kind, parse_config(target.config))
    files = sorted((item.name for item in remote.list()), reverse=True)
    for name in files[target.retention_count:]:
        remote.delete(name)


def run_backup(db: Session, target: models.BackupTarget, trigger: str) -> models.BackupRun:
    run = models.BackupRun(
        started_at=datetime.now(timezone.utc), trigger=trigger, target_name=target.name, status="failed",
    )
    try:
        data = create_backup(db, _recipient_keys(db))
        name = backup_filename()
        remote = open_target(target.kind, parse_config(target.config))
        remote.upload(name, data)
        run.filename, run.size_bytes, run.status = name, len(data), "success"
        try:
            apply_retention(target)
        except BackupError as exc:
            run.error = f"Backup gespeichert, Aufräumen fehlgeschlagen: {exc}"[:300]
    except BackupError as exc:
        run.error = str(exc)[:300]
    except Exception as exc:  # never let one target break the scheduler loop
        logger.exception("Backup failed")
        run.error = f"Unerwarteter Fehler: {type(exc).__name__}"
    db.add(run)
    db.commit()
    return run


def run_due_backup(db: Session, now: datetime | None = None) -> list[models.BackupRun]:
    settings = db.get(models.BackupSettings, 1)
    if settings is None or not settings.schedule_enabled:
        return []
    zone = _zone(db)
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    slot = latest_slot(current, settings.frequency, settings.weekday, settings.time_of_day)
    if settings.last_slot is not None and settings.last_slot.astimezone(zone) >= slot:
        return []
    settings.last_slot = slot
    db.commit()
    targets = db.scalars(select(models.BackupTarget).where(models.BackupTarget.enabled.is_(True)).order_by(models.BackupTarget.id)).all()
    if not targets:
        db.add(models.BackupRun(
            started_at=datetime.now(timezone.utc), trigger="scheduled", target_name="–", status="failed",
            error="Kein aktives Backup-Ziel konfiguriert",
        ))
        db.commit()
        return []
    return [run_backup(db, target, "scheduled") for target in targets]


def _scheduled_worker() -> None:
    with SessionLocal() as db:
        run_due_backup(db)


async def backup_scheduler() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_scheduled_worker)
        except Exception:
            logger.exception("Scheduled backup check failed")


@router.get("/settings")
def get_settings(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> SettingsRead:
    return _settings_read(db, _settings(db))


@router.put("/settings")
def update_settings(changes: SettingsWrite, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> SettingsRead:
    db.info["audit_actor"] = principal.username
    settings = _settings(db)
    if changes.schedule_enabled and not _recipient_count(db):
        raise HTTPException(status_code=422, detail="Für automatische Backups wird mindestens ein Empfänger-Schlüssel benötigt (zuerst Wiederherstellungsschlüssel erzeugen)")
    schedule_changed = (
        changes.schedule_enabled != settings.schedule_enabled
        or (changes.frequency, changes.weekday, changes.time_of_day) != (settings.frequency, settings.weekday, settings.time_of_day)
    )
    settings.schedule_enabled = changes.schedule_enabled
    settings.frequency, settings.weekday, settings.time_of_day = changes.frequency, changes.weekday, changes.time_of_day
    if schedule_changed:
        # Do not fire immediately for a slot that already passed before the schedule was saved.
        settings.last_slot = latest_slot(datetime.now(_zone(db)), changes.frequency, changes.weekday, changes.time_of_day)
    db.commit()
    return _settings_read(db, settings)


def _recipient_read(item: models.BackupRecipient) -> RecipientRead:
    return RecipientRead(id=item.id, name=item.name, public_key=item.public_key, created_at=item.created_at)


def _add_recipient(db: Session, name: str, public_key: str) -> models.BackupRecipient:
    public_key = public_key.strip()
    try:
        parse_public_key(public_key)
    except BackupError as exc:
        raise _fail(exc) from exc
    if db.scalar(select(models.BackupRecipient.id).where((models.BackupRecipient.name == name.strip()) | (models.BackupRecipient.public_key == public_key))):
        raise HTTPException(status_code=409, detail="Name oder Schlüssel ist bereits als Empfänger hinterlegt")
    item = models.BackupRecipient(name=name.strip(), public_key=public_key, created_at=datetime.now(timezone.utc))
    db.add(item)
    return item


@router.get("/recipients")
def list_recipients(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[RecipientRead]:
    return [_recipient_read(item) for item in db.scalars(select(models.BackupRecipient).order_by(models.BackupRecipient.id))]


@router.post("/recipients", status_code=status.HTTP_201_CREATED)
def create_recipient(body: RecipientWrite, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> RecipientRead:
    item = _add_recipient(db, body.name, body.public_key)
    db.commit()
    return _recipient_read(item)


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipient(recipient_id: int, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    item = db.get(models.BackupRecipient, recipient_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Empfänger nicht gefunden")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/recovery-key")
def create_recovery_key(body: RecoveryKeyBody, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    """Generate a key pair. Only the public half is stored; the private key is returned once, passphrase-protected."""
    try:
        public_key, key_file = generate_recovery_key(body.passphrase)
    except BackupError as exc:
        raise _fail(exc) from exc
    if body.add_as_recipient:
        _add_recipient(db, body.name, public_key)
        db.commit()
    return Response(
        content=key_file, media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="clinicpulse-recovery-key.cpkey"',
            "X-Public-Key": public_key,
            "Cache-Control": "no-store",
        },
    )


@router.get("/targets")
def list_targets(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[TargetRead]:
    return [_target_read(item) for item in db.scalars(select(models.BackupTarget).order_by(models.BackupTarget.id))]


def _store_target(db: Session, target: models.BackupTarget, body: TargetWrite) -> None:
    previous = parse_config(target.config) if target.config and target.kind == body.kind else None
    try:
        config = validate_config(body.kind, dict(body.config), previous)
    except BackupError as exc:
        raise _fail(exc) from exc
    duplicate = db.scalar(select(models.BackupTarget.id).where(models.BackupTarget.name == body.name, models.BackupTarget.id != (target.id or 0)))
    if duplicate:
        raise HTTPException(status_code=409, detail="Ein Backup-Ziel mit diesem Namen existiert bereits")
    target.name, target.kind, target.enabled, target.retention_count = body.name.strip(), body.kind, body.enabled, body.retention_count
    target.config = json.dumps(config)


@router.post("/targets", status_code=status.HTTP_201_CREATED)
def create_target(body: TargetWrite, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> TargetRead:
    db.info["audit_actor"] = principal.username
    target = models.BackupTarget(config="")
    _store_target(db, target, body)
    db.add(target)
    db.commit()
    return _target_read(target)


@router.put("/targets/{target_id}")
def update_target(target_id: int, body: TargetWrite, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> TargetRead:
    db.info["audit_actor"] = principal.username
    target = _get_target(db, target_id)
    _store_target(db, target, body)
    db.commit()
    return _target_read(target)


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: int, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    db.info["audit_actor"] = principal.username
    db.delete(_get_target(db, target_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/targets/{target_id}/test")
def test_target(target_id: int, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    target = _get_target(db, target_id)
    try:
        open_target(target.kind, parse_config(target.config)).test()
    except BackupError as exc:
        raise _fail(exc) from exc
    return {"status": "ok"}


@router.post("/targets/{target_id}/run")
def run_target(target_id: int, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> RunRead:
    target = _get_target(db, target_id)
    run = run_backup(db, target, "manual")
    return RunRead.model_validate(run, from_attributes=True)


@router.get("/targets/{target_id}/files")
def list_target_files(target_id: int, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[RemoteFileRead]:
    target = _get_target(db, target_id)
    try:
        files = open_target(target.kind, parse_config(target.config)).list()
    except BackupError as exc:
        raise _fail(exc) from exc
    files.sort(key=lambda item: item.name, reverse=True)
    return [RemoteFileRead(name=item.name, size=item.size, modified=item.modified) for item in files]


@router.post("/targets/{target_id}/restore")
def restore_from_target(target_id: int, body: TargetRestoreBody, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, object]:
    if body.confirm != RESTORE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Bitte „{RESTORE_CONFIRMATION}“ zur Bestätigung eingeben")
    if not is_backup_filename(body.filename):
        raise HTTPException(status_code=422, detail="Ungültiger Dateiname")
    target = _get_target(db, target_id)
    try:
        private_key = load_recovery_key(body.recovery_key, body.key_passphrase)
        data = open_target(target.kind, parse_config(target.config)).download(body.filename)
        counts = restore_backup(db, data, private_key, principal.username)
    except BackupError as exc:
        raise _fail(exc) from exc
    return {"status": "restored", "rows": sum(counts.values())}


@router.post("/download")
def download_backup(body: DownloadBody, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    keys = [body.public_key.strip()] if body.public_key else _recipient_keys(db)
    try:
        data = create_backup(db, keys)
    except BackupError as exc:
        raise _fail(exc) from exc
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{backup_filename()}"', "Cache-Control": "no-store"},
    )


@router.post("/restore")
async def restore_upload(
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
    x_recovery_key: str = Header(default=""),
    x_key_passphrase: str = Header(default=""),
    x_restore_confirm: str = Header(default=""),
) -> dict[str, object]:
    if x_restore_confirm != RESTORE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Bitte „{RESTORE_CONFIRMATION}“ zur Bestätigung eingeben")
    if int(request.headers.get("content-length", "0") or 0) > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail="Backup-Datei ist zu groß")
    data = await request.body()
    if len(data) > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail="Backup-Datei ist zu groß")
    try:
        key_file = base64.b64decode(x_recovery_key, validate=True).decode("utf-8")
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Wiederherstellungsschlüssel fehlt oder ist ungültig") from exc
    try:
        counts = restore_backup(db, data, load_recovery_key(key_file, x_key_passphrase), principal.username)
    except BackupError as exc:
        raise _fail(exc) from exc
    return {"status": "restored", "rows": sum(counts.values())}


@router.get("/runs")
def list_runs(limit: int = 20, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[RunRead]:
    rows = db.scalars(select(models.BackupRun).order_by(models.BackupRun.id.desc()).limit(max(1, min(limit, 100))))
    return [RunRead.model_validate(row, from_attributes=True) for row in rows]


@router.get("/kinds")
def list_kinds(_: Principal = Depends(require_admin)) -> list[str]:
    return list(KINDS)
