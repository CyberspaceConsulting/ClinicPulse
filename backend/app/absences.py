from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .schemas import AbsenceCreate, AbsenceDecision, AbsenceRead
from .security import Principal, require_approve, require_license_writable, require_principal

router = APIRouter(prefix="/api/absences", tags=["absences"])

ACTIVE_STATUSES = ("pending", "approved")
READ_ALL_ROLES = {"ADMIN", "HOSPITAL_MANAGEMENT"}


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


def employee_is_absent(db: Session, employee_id: int, starts_at: datetime, ends_at: datetime) -> bool:
    return db.scalar(
        select(models.Absence.id).where(
            models.Absence.employee_id == employee_id,
            models.Absence.status == "approved",
            models.Absence.start_date <= ends_at.date(),
            models.Absence.end_date >= starts_at.date(),
        ).limit(1)
    ) is not None


def _departments(principal: Principal) -> tuple[int, ...]:
    if principal.department_ids:
        return principal.department_ids
    return (principal.department_id,) if principal.department_id is not None else ()


def _in_scope(principal: Principal, employee: models.Employee) -> bool:
    if principal.role_key in READ_ALL_ROLES:
        return True
    if principal.role_key == "EMPLOYEE":
        return principal.employee_id == employee.id
    return employee.department_id in _departments(principal)


def _read(absence: models.Absence) -> AbsenceRead:
    return AbsenceRead(
        id=absence.id,
        employee_id=absence.employee_id,
        employee_name=absence.employee.name,
        kind=absence.kind,
        start_date=absence.start_date,
        end_date=absence.end_date,
        status=absence.status,
        note=absence.note,
        requested_by=absence.requested_by,
        created_at=absence.created_at,
        decided_by=absence.decided_by,
        decided_at=absence.decided_at,
    )


def _has_assignments(db: Session, absence: models.Absence) -> bool:
    range_start, range_end = _day_bounds(absence.start_date, absence.end_date)
    return db.scalar(
        select(models.Assignment.id).where(
            models.Assignment.employee_id == absence.employee_id,
            models.Assignment.starts_at < range_end,
            models.Assignment.ends_at > range_start,
        ).limit(1)
    ) is not None


def _require_planner(principal: Principal) -> None:
    if principal.role_key != "OBERARZT" or not principal.can_edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Absence management permission required")


@router.get("", response_model=list[AbsenceRead])
def list_absences(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|approved|rejected)$"),
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[AbsenceRead]:
    if principal.role_key == "KIOSK":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Absences are not available for kiosk accounts")
    query = select(models.Absence).join(models.Employee).order_by(models.Absence.start_date.desc())
    if status_filter:
        query = query.where(models.Absence.status == status_filter)
    if principal.role_key == "EMPLOYEE":
        query = query.where(models.Absence.employee_id == principal.employee_id)
    elif principal.role_key not in READ_ALL_ROLES:
        query = query.where(models.Employee.department_id.in_(_departments(principal)))
    return [_read(absence) for absence in db.scalars(query)]


@router.post("", response_model=AbsenceRead, status_code=status.HTTP_201_CREATED)
def create_absence(
    payload: AbsenceCreate,
    principal: Principal = Depends(require_principal),
    _: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> AbsenceRead:
    if principal.role_key == "EMPLOYEE":
        employee_id = principal.employee_id
        if payload.employee_id not in (None, employee_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only request your own absences")
        decision = "pending" if payload.kind != "sick" else "approved"
    else:
        _require_planner(principal)
        employee_id = payload.employee_id
        decision = "approved"
    employee = db.get(models.Employee, employee_id) if employee_id is not None else None
    if employee is None or not _in_scope(principal, employee):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    overlap = db.scalar(
        select(models.Absence.id).where(
            models.Absence.employee_id == employee.id,
            models.Absence.status.in_(ACTIVE_STATUSES),
            models.Absence.start_date <= payload.end_date,
            models.Absence.end_date >= payload.start_date,
        ).limit(1)
    )
    if overlap is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An absence already exists in this period")
    record = models.Absence(
        employee_id=employee.id,
        kind=payload.kind,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=decision,
        note=payload.note or None,
        created_at=datetime.now(timezone.utc),
        requested_by=principal.username,
        decided_by=principal.username if decision == "approved" and payload.kind != "sick" else None,
        decided_at=datetime.now(timezone.utc) if decision == "approved" else None,
    )
    # Krankmeldungen brauchen keine Genehmigung und dürfen nicht an bestehenden Diensten scheitern.
    if decision == "approved" and payload.kind != "sick" and _has_assignments(db, record):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee has scheduled shifts in this period")
    db.add(record)
    db.commit()
    db.refresh(record)
    return _read(record)


@router.post("/{absence_id}/decision", response_model=AbsenceRead)
def decide_absence(
    absence_id: int,
    payload: AbsenceDecision,
    principal: Principal = Depends(require_approve),
    db: Session = Depends(get_db),
) -> AbsenceRead:
    absence = db.get(models.Absence, absence_id)
    if absence is None or not _in_scope(principal, absence.employee):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Absence not found")
    if absence.kind == "sick":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sick leave does not require approval")
    if absence.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Absence was already decided")
    if payload.decision == "approved" and _has_assignments(db, absence):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee has scheduled shifts in this period")
    absence.status = payload.decision
    absence.decided_by = principal.username
    absence.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(absence)
    return _read(absence)


@router.delete("/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_absence(
    absence_id: int,
    principal: Principal = Depends(require_principal),
    _: None = Depends(require_license_writable),
    db: Session = Depends(get_db),
) -> Response:
    absence = db.get(models.Absence, absence_id)
    if absence is None or not _in_scope(principal, absence.employee):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Absence not found")
    if principal.role_key == "EMPLOYEE":
        if absence.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending requests can be withdrawn")
    else:
        _require_planner(principal)
    db.delete(absence)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
