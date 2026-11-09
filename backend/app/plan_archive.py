import asyncio
import calendar
import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal, get_db
from .security import Principal, require_admin, require_edit, require_plan_view
from .work_rules import business_timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/archives", tags=["archives"])
settings_router = APIRouter(prefix="/api/admin/archive-settings", tags=["archives"])
SYSTEM_ACTOR = "System (automatisch)"
MAX_CATCH_UP_PERIODS = 12

MAX_RANGE_DAYS = 366
MANAGEMENT_ROLES = {"ADMIN", "HOSPITAL_MANAGEMENT"}


class ArchiveCreate(BaseModel):
    start_date: date
    end_date: date
    department_id: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=200)


class ArchiveSummary(BaseModel):
    id: int
    created_at: datetime
    created_by: str
    start_date: date
    end_date: date
    department_id: int | None
    department_name: str
    note: str | None
    entry_count: int
    content_sha256: str


class ArchiveEntry(BaseModel):
    employee_name: str
    employee_role: str
    shift_name: str
    starts_at: datetime
    ends_at: datetime


class ArchiveDetail(ArchiveSummary):
    entries: list[ArchiveEntry]
    integrity_ok: bool


def _departments(principal: Principal) -> tuple[int, ...]:
    if principal.department_ids:
        return principal.department_ids
    return (principal.department_id,) if principal.department_id is not None else ()


def _visible(principal: Principal, archive: models.PlanArchive) -> bool:
    if principal.role_key in MANAGEMENT_ROLES:
        return True
    return archive.department_id in _departments(principal)


def _summary(archive: models.PlanArchive) -> ArchiveSummary:
    return ArchiveSummary(
        id=archive.id,
        created_at=archive.created_at,
        created_by=archive.created_by,
        start_date=archive.start_date,
        end_date=archive.end_date,
        department_id=archive.department_id,
        department_name=archive.department_name,
        note=archive.note,
        entry_count=archive.entry_count,
        content_sha256=archive.content_sha256,
    )


def _get_visible(db: Session, archive_id: int, principal: Principal) -> models.PlanArchive:
    archive = db.get(models.PlanArchive, archive_id)
    if archive is None or not _visible(principal, archive):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archive not found")
    return archive


def build_archive(
    db: Session,
    department: models.Department,
    start_date: date,
    end_date: date,
    created_by: str,
    note: str | None,
) -> models.PlanArchive:
    tz = business_timezone(db)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    assignments = db.scalars(
        select(models.Assignment)
        .join(models.ShiftType)
        .where(
            models.Assignment.starts_at < range_end,
            models.Assignment.ends_at > range_start,
            models.ShiftType.department_id == department.id,
        )
        .order_by(models.Assignment.starts_at)
    ).all()
    entries = sorted(
        (
            {
                "employee_name": item.employee.name,
                "employee_role": item.employee.role,
                "shift_name": item.shift_type.name,
                "starts_at": item.starts_at.astimezone(timezone.utc).isoformat(),
                "ends_at": item.ends_at.astimezone(timezone.utc).isoformat(),
            }
            for item in assignments
        ),
        key=lambda entry: (entry["starts_at"], entry["employee_name"]),
    )
    content = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    archive = models.PlanArchive(
        created_at=datetime.now(timezone.utc),
        created_by=created_by[:64],
        start_date=start_date,
        end_date=end_date,
        department_id=department.id,
        department_name=department.name,
        note=note,
        entry_count=len(entries),
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    db.add(archive)
    return archive


@router.post("", response_model=ArchiveSummary, status_code=status.HTTP_201_CREATED)
def create_archive(
    payload: ArchiveCreate,
    principal: Principal = Depends(require_edit),
    db: Session = Depends(get_db),
) -> ArchiveSummary:
    if payload.end_date < payload.start_date or (payload.end_date - payload.start_date).days >= MAX_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Date range must be 1–366 days")
    if payload.department_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Department is required")
    if payload.department_id not in _departments(principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    department = db.get(models.Department, payload.department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    note = (payload.note or "").strip() or None
    archive = build_archive(db, department, payload.start_date, payload.end_date, principal.username, note)
    db.commit()
    db.refresh(archive)
    return _summary(archive)


@router.get("", response_model=list[ArchiveSummary])
def list_archives(
    principal: Principal = Depends(require_plan_view),
    db: Session = Depends(get_db),
) -> list[ArchiveSummary]:
    query = select(models.PlanArchive).order_by(models.PlanArchive.created_at.desc(), models.PlanArchive.id.desc())
    if principal.role_key not in MANAGEMENT_ROLES:
        query = query.where(models.PlanArchive.department_id.in_(_departments(principal)))
    return [_summary(archive) for archive in db.scalars(query)]


def _entries(archive: models.PlanArchive) -> tuple[list[ArchiveEntry], bool]:
    integrity_ok = hashlib.sha256(archive.content.encode("utf-8")).hexdigest() == archive.content_sha256
    return [ArchiveEntry(**entry) for entry in json.loads(archive.content)], integrity_ok


@router.get("/{archive_id}", response_model=ArchiveDetail)
def read_archive(
    archive_id: int,
    principal: Principal = Depends(require_plan_view),
    db: Session = Depends(get_db),
) -> ArchiveDetail:
    archive = _get_visible(db, archive_id, principal)
    entries, integrity_ok = _entries(archive)
    return ArchiveDetail(**_summary(archive).model_dump(), entries=entries, integrity_ok=integrity_ok)


@router.get("/{archive_id}/pdf")
def download_archive_pdf(
    archive_id: int,
    principal: Principal = Depends(require_plan_view),
    db: Session = Depends(get_db),
) -> Response:
    archive = _get_visible(db, archive_id, principal)
    entries, integrity_ok = _entries(archive)
    tz = business_timezone(db)
    pdf = render_archive_pdf(archive, entries, tz, integrity_ok)
    filename = f"dienstplan-archiv-{archive.id}-{archive.start_date}_{archive.end_date}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


def _pdf_text(value: str) -> bytes:
    encoded = value.encode("cp1252", errors="replace")
    return encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_archive_pdf(
    archive: models.PlanArchive,
    entries: list[ArchiveEntry],
    tz: ZoneInfo,
    integrity_ok: bool,
) -> bytes:
    page_width, page_height = 842, 595
    margin = 40
    line_height = 15
    columns = [(margin, "Datum"), (110, "Beginn"), (160, "Ende"), (215, "Mitarbeitende"), (400, "Funktion"), (560, "Dienst")]
    limits = [10, 5, 5, 34, 28, 38]
    created_local = archive.created_at.astimezone(tz)

    def header(page_no: int) -> list[bytes]:
        lines: list[tuple[int, float, str, str, int]] = [
            (margin, page_height - 45, "F2", f"Dienstplan-Archiv #{archive.id} – {archive.department_name}", 15),
            (
                margin,
                page_height - 64,
                "F1",
                f"Zeitraum {archive.start_date:%d.%m.%Y} – {archive.end_date:%d.%m.%Y} · archiviert am "
                f"{created_local:%d.%m.%Y %H:%M} von {archive.created_by} · {archive.entry_count} Dienste",
                9,
            ),
            (
                margin,
                page_height - 77,
                "F1",
                f"SHA-256: {archive.content_sha256}" + ("" if integrity_ok else "  –  PRÜFSUMME STIMMT NICHT ÜBEREIN"),
                7,
            ),
        ]
        if archive.note:
            lines.append((margin, page_height - 90, "F1", f"Notiz: {_clip(archive.note, 140)}", 8))
        out = [
            b"BT /%s %d Tf %d %.1f Td (%s) Tj ET" % (font.encode(), size, x, y, _pdf_text(text))
            for x, y, font, text, size in lines
        ]
        out.append(b"BT /F1 8 Tf %d 25 Td (%s) Tj ET" % (margin, _pdf_text(f"Seite {page_no}")))
        return out

    def row(y: float, cells: list[str], font: str) -> bytes:
        return b" ".join(
            b"BT /%s 9 Tf %d %.1f Td (%s) Tj ET" % (font.encode(), x, y, _pdf_text(_clip(cell, limit)))
            for (x, _), cell, limit in zip(columns, cells, limits)
        )

    top = page_height - 115
    rows_per_page = int((top - 50) // line_height)
    chunks = [entries[i : i + rows_per_page] for i in range(0, len(entries), rows_per_page)] or [[]]
    streams: list[bytes] = []
    for page_no, chunk in enumerate(chunks, start=1):
        parts = header(page_no)
        parts.append(row(top, [label for _, label in columns], "F2"))
        y = top - line_height
        for entry in chunk:
            start = entry.starts_at.astimezone(tz)
            end = entry.ends_at.astimezone(tz)
            parts.append(row(y, [
                f"{start:%d.%m.%Y}", f"{start:%H:%M}", f"{end:%H:%M}",
                entry.employee_name, entry.employee_role, entry.shift_name,
            ], "F1"))
            y -= line_height
        if not chunk:
            parts.append(row(y, ["Keine Dienste im Zeitraum", "", "", "", "", ""], "F1"))
        streams.append(b"\n".join(parts))

    objects: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    page_ids = []
    for stream in streams:
        content_id = len(objects) + 1
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page_ids.append(len(objects) + 1)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            b"/Contents %d 0 R >>" % (page_width, page_height, content_id)
        )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = b" ".join(b"%d 0 R" % page_id for page_id in page_ids)
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        output += b"%010d 00000 n \n" % offset
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(output)


class ArchiveSettingsWrite(BaseModel):
    auto_enabled: bool
    period: Literal["monthly", "weekly"]


class ArchiveSettingsRead(ArchiveSettingsWrite):
    last_period_end: date | None


def _settings(db: Session) -> models.ArchiveSettings:
    settings = db.get(models.ArchiveSettings, 1)
    if settings is None:
        settings = models.ArchiveSettings(id=1)
        db.add(settings)
    return settings


def _settings_read(settings: models.ArchiveSettings) -> ArchiveSettingsRead:
    return ArchiveSettingsRead(
        auto_enabled=bool(settings.auto_enabled),
        period=settings.period or "monthly",
        last_period_end=settings.last_period_end,
    )


def period_end(start: date, period: str) -> date:
    if period == "weekly":
        return start + timedelta(days=6)
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def last_completed_period_end(today: date, period: str) -> date:
    if period == "weekly":
        return today - timedelta(days=today.weekday() + 1)
    return today.replace(day=1) - timedelta(days=1)


@settings_router.get("", response_model=ArchiveSettingsRead)
def read_archive_settings(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> ArchiveSettingsRead:
    settings = _settings(db)
    db.commit()
    return _settings_read(settings)


@settings_router.put("", response_model=ArchiveSettingsRead)
def update_archive_settings(
    changes: ArchiveSettingsWrite,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ArchiveSettingsRead:
    db.info["audit_actor"] = principal.username
    settings = _settings(db)
    if (changes.auto_enabled, changes.period) != (bool(settings.auto_enabled), settings.period):
        # Nur künftig abgeschlossene Zeiträume archivieren, keine rückwirkende Flut beim Einschalten.
        today = datetime.now(business_timezone(db)).date()
        settings.last_period_end = last_completed_period_end(today, changes.period)
    settings.auto_enabled = changes.auto_enabled
    settings.period = changes.period
    db.commit()
    return _settings_read(settings)


def run_due_archive(db: Session, now: datetime | None = None) -> list[models.PlanArchive]:
    settings = db.get(models.ArchiveSettings, 1)
    if settings is None or not settings.auto_enabled or settings.last_period_end is None:
        return []
    today = (now or datetime.now(timezone.utc)).astimezone(business_timezone(db)).date()
    completed_end = last_completed_period_end(today, settings.period)
    created: list[models.PlanArchive] = []
    departments = db.scalars(select(models.Department).order_by(models.Department.id)).all()
    for _ in range(MAX_CATCH_UP_PERIODS):
        if settings.last_period_end >= completed_end:
            break
        start = settings.last_period_end + timedelta(days=1)
        end = period_end(start, settings.period)
        for department in departments:
            created.append(build_archive(db, department, start, end, SYSTEM_ACTOR, "Automatische Archivierung"))
        settings.last_period_end = end
        db.commit()
    return created


def _scheduled_worker() -> None:
    with SessionLocal() as db:
        db.info["audit_actor"] = SYSTEM_ACTOR
        run_due_archive(db)


async def archive_scheduler() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_scheduled_worker)
        except Exception:
            logger.exception("Scheduled archive check failed")
