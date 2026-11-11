from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import models
from .absences import employee_is_absent
from .work_rules import (
    business_timezone,
    load_work_rules,
    work_rule_violation,
)

MAX_OPEN_SLOTS = 150
MAX_CANDIDATE_VARIABLES = 5_000
SOLVER_TIME_LIMIT_SECONDS = 3.0


class OptimizationTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class SuggestedAssignment:
    employee_id: int
    employee_name: str
    employee_role: str
    shift_type_id: int
    shift_name: str
    position: str
    role_match: bool
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class OpenSlot:
    shift_type_id: int
    shift_name: str
    position: str


@dataclass(frozen=True)
class OptimizationPreview:
    suggestions: tuple[SuggestedAssignment, ...]
    unfilled_slots: tuple[OpenSlot, ...]
    status: str


@dataclass(frozen=True)
class _Candidate:
    slot_index: int
    employee: models.Employee
    shift: models.ShiftType
    position: str
    starts_at: datetime
    ends_at: datetime
    role_match: bool


def _shift_interval(target_date: date, shift: models.ShiftType, business_tz: ZoneInfo) -> tuple[datetime, datetime]:
    local_start = datetime.combine(target_date, shift.start_time, tzinfo=business_tz)
    local_end_date = target_date + timedelta(days=shift.end_time <= shift.start_time)
    local_end = datetime.combine(local_end_date, shift.end_time, tzinfo=business_tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _has_rest_between(
    first: _Candidate, second: _Candidate, rest_hours: int
) -> bool:
    if first.starts_at <= second.starts_at:
        earlier, later = first, second
    else:
        earlier, later = second, first
    return later.starts_at - earlier.ends_at >= timedelta(hours=rest_hours)


def _slot_dates(candidate: _Candidate, business_tz: ZoneInfo) -> set[date]:
    first = candidate.starts_at.astimezone(business_tz).date()
    last = (candidate.ends_at - timedelta(microseconds=1)).astimezone(business_tz).date()
    dates: set[date] = set()
    while first <= last:
        dates.add(first)
        first += timedelta(days=1)
    return dates


def _work_minutes_in_window(
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    break_start_minutes: int,
    window_start: datetime,
    window_end: datetime,
) -> int:
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)
    else:
        starts_at = starts_at.astimezone(timezone.utc)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    else:
        ends_at = ends_at.astimezone(timezone.utc)
    overlap_start = max(starts_at, window_start)
    overlap_end = min(ends_at, window_end)
    if overlap_end <= overlap_start:
        return 0
    worked_minutes = (overlap_end - overlap_start).total_seconds() / 60
    if break_minutes:
        break_start = starts_at + timedelta(minutes=break_start_minutes)
        break_end = break_start + timedelta(minutes=break_minutes)
        break_overlap = max(
            0,
            (min(break_end, window_end) - max(break_start, window_start)).total_seconds() / 60,
        )
        worked_minutes -= break_overlap
    return max(0, round(worked_minutes))


def optimize_day(
    db: Session,
    target_date: date,
    department_ids: tuple[int, ...] | None = None,
    *,
    target_vacancies: dict[tuple[int, str], int] | None = None,
) -> OptimizationPreview:
    business_tz = business_timezone(db)
    rules = load_work_rules(db)
    shift_query = select(models.ShiftType).options(
        selectinload(models.ShiftType.staffing_requirements)
    ).order_by(models.ShiftType.id)
    employee_query = select(models.Employee).order_by(models.Employee.id)
    if department_ids is not None:
        shift_query = shift_query.where(models.ShiftType.department_id.in_(department_ids))
        employee_query = employee_query.where(models.Employee.department_id.in_(department_ids))
    if target_vacancies is not None:
        shift_query = shift_query.where(
            models.ShiftType.id.in_({shift_id for shift_id, _ in target_vacancies})
        )
    shifts = list(db.scalars(shift_query))
    employees = list(db.scalars(employee_query))
    employees_by_department: dict[int | None, list[models.Employee]] = {}
    for employee in employees:
        employees_by_department.setdefault(employee.department_id, []).append(employee)

    local_day_start = datetime.combine(target_date, time.min, tzinfo=business_tz)
    local_day_end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=business_tz)
    day_start = local_day_start.astimezone(timezone.utc)
    day_end = local_day_end.astimezone(timezone.utc)
    existing_assignments = list(db.scalars(
        select(models.Assignment)
        .options(
            selectinload(models.Assignment.shift_type).selectinload(models.ShiftType.staffing_requirements),
        )
        .where(
            models.Assignment.starts_at >= day_start,
            models.Assignment.starts_at < day_end,
        )
    ))
    existing_counts: dict[tuple[int, str], int] = {}
    existing_counts_by_shift: dict[int, int] = {}
    for assignment in existing_assignments:
        shift = assignment.shift_type
        employee_role = assignment.employee.role.strip().casefold()
        requirements = shift.staffing_requirements or [
            models.ShiftStaffingRequirement(
                position=shift.position,
                required_staff=shift.required_staff,
            )
        ]
        for requirement in requirements:
            if requirement.position.strip().casefold() == employee_role:
                key = (shift.id, requirement.position.strip().casefold())
                existing_counts[key] = existing_counts.get(key, 0) + 1
        existing_counts_by_shift[shift.id] = existing_counts_by_shift.get(shift.id, 0) + 1

    slots: list[tuple[models.ShiftType, str, datetime, datetime]] = []
    for shift in shifts:
        starts_at, ends_at = _shift_interval(target_date, shift, business_tz)
        requirements = shift.staffing_requirements or [
            models.ShiftStaffingRequirement(
                position=shift.position,
                required_staff=shift.required_staff,
            )
        ]
        for requirement in requirements:
            qualification_required = (
                len(requirements) > 1
                or requirement.position.strip().casefold() == "oberarzt"
            )
            existing_count = (
                existing_counts.get((shift.id, requirement.position.strip().casefold()), 0)
                if qualification_required
                else existing_counts_by_shift.get(shift.id, 0)
            )
            vacancies = (
                target_vacancies.get((shift.id, requirement.position.strip().casefold()), 0)
                if target_vacancies is not None
                else max(0, requirement.required_staff - existing_count)
            )
            slots.extend((shift, requirement.position, starts_at, ends_at) for _ in range(vacancies))
    if not slots:
        return OptimizationPreview((), (), "OPTIMAL")
    if len(slots) > MAX_OPEN_SLOTS:
        raise OptimizationTooLarge("Limit optimization to a maximum of 150 open positions per day")
    possible_combinations = sum(
        len(employees_by_department.get(shift.department_id, ()))
        for shift, _position, _starts_at, _ends_at in slots
    )
    if possible_combinations > MAX_CANDIDATE_VARIABLES:
        raise OptimizationTooLarge("Select a smaller department for day optimization")

    candidate_cache: dict[tuple[int, int], bool] = {}
    candidates: list[_Candidate] = []
    for slot_index, (shift, position, starts_at, ends_at) in enumerate(slots):
        for employee in employees_by_department.get(shift.department_id, ()):
            if (
                (len(shift.staffing_requirements) > 1 or position.strip().casefold() == "oberarzt")
                and employee.role.strip().casefold() != position.strip().casefold()
            ):
                continue
            cache_key = (employee.id, shift.id)
            eligible = candidate_cache.get(cache_key)
            if eligible is None:
                eligible = (
                    not employee_is_absent(db, employee.id, starts_at, ends_at)
                    and work_rule_violation(
                        db,
                        employee.id,
                        starts_at,
                        ends_at,
                        shift.break_minutes,
                        shift.break_start_minutes,
                        rules,
                    ) is None
                )
                candidate_cache[cache_key] = eligible
            if eligible:
                candidates.append(_Candidate(
                    slot_index=slot_index,
                    employee=employee,
                    shift=shift,
                    position=position,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    role_match=employee.role.strip().casefold() == position.strip().casefold(),
                ))
    if len(candidates) > MAX_CANDIDATE_VARIABLES:
        raise OptimizationTooLarge("Optimization has too many eligible employee-position combinations")

    model = cp_model.CpModel()
    candidate_variables = [
        model.NewBoolVar(f"assign_{candidate.slot_index}_{candidate.employee.id}")
        for candidate in candidates
    ]
    unfilled_variables = [
        model.NewBoolVar(f"unfilled_{index}") for index in range(len(slots))
    ]
    variables_by_slot: dict[int, list[int]] = {index: [] for index in range(len(slots))}
    variables_by_employee: dict[int, list[int]] = {}
    for index, candidate in enumerate(candidates):
        variables_by_slot[candidate.slot_index].append(index)
        variables_by_employee.setdefault(candidate.employee.id, []).append(index)
    for slot_index, variable_indices in variables_by_slot.items():
        model.AddExactlyOne(
            [candidate_variables[index] for index in variable_indices]
            + [unfilled_variables[slot_index]]
        )

    for variable_indices in variables_by_employee.values():
        model.AddAtMostOne(candidate_variables[index] for index in variable_indices)
        for offset, first_index in enumerate(variable_indices):
            for second_index in variable_indices[offset + 1:]:
                first = candidates[first_index]
                second = candidates[second_index]
                if not _has_rest_between(first, second, rules.rest_hours):
                    model.Add(
                        candidate_variables[first_index] + candidate_variables[second_index] <= 1
                    )

    employee_day_candidates: dict[tuple[int, date], list[tuple[int, int]]] = {}
    for index, candidate in enumerate(candidates):
        for work_date in _slot_dates(candidate, business_tz):
            local_start = datetime.combine(work_date, time.min, tzinfo=business_tz)
            local_end = datetime.combine(work_date + timedelta(days=1), time.min, tzinfo=business_tz)
            minutes = _work_minutes_in_window(
                candidate.starts_at,
                candidate.ends_at,
                candidate.shift.break_minutes,
                candidate.shift.break_start_minutes,
                local_start.astimezone(timezone.utc),
                local_end.astimezone(timezone.utc),
            )
            employee_day_candidates.setdefault(
                (candidate.employee.id, work_date), []
            ).append((index, minutes))

    for (employee_id, work_date), day_candidates in employee_day_candidates.items():
        local_start = datetime.combine(work_date, time.min, tzinfo=business_tz)
        local_end = datetime.combine(work_date + timedelta(days=1), time.min, tzinfo=business_tz)
        window_start = local_start.astimezone(timezone.utc)
        window_end = local_end.astimezone(timezone.utc)
        existing_minutes = 0
        rows = db.execute(
            select(
                models.Assignment.starts_at,
                models.Assignment.ends_at,
                models.ShiftType.break_minutes,
                models.ShiftType.break_start_minutes,
            )
            .join(models.ShiftType)
            .where(
                models.Assignment.employee_id == employee_id,
                models.Assignment.starts_at < window_end,
                models.Assignment.ends_at > window_start,
            )
        )
        for starts_at, ends_at, break_minutes, break_start_minutes in rows:
            existing_minutes += _work_minutes_in_window(
                starts_at, ends_at, break_minutes, break_start_minutes,
                window_start, window_end,
            )
        model.Add(
            existing_minutes + sum(
                candidate_variables[index] * minutes
                for index, minutes in day_candidates
            ) <= rules.max_daily_hours * 60
        )

    eligible_employee_ids = set(variables_by_employee)
    week_start_date = target_date - timedelta(days=target_date.weekday())
    week_start = datetime.combine(week_start_date, time.min, tzinfo=business_tz)
    week_end = datetime.combine(week_start_date + timedelta(days=7), time.min, tzinfo=business_tz)
    week_start_utc = week_start.astimezone(timezone.utc)
    week_end_utc = week_end.astimezone(timezone.utc)
    weekly_existing_minutes = {employee_id: 0 for employee_id in eligible_employee_ids}
    for employee_id, starts_at, ends_at, break_minutes, break_start_minutes in db.execute(
        select(
            models.Assignment.employee_id,
            models.Assignment.starts_at,
            models.Assignment.ends_at,
            models.ShiftType.break_minutes,
            models.ShiftType.break_start_minutes,
        )
        .join(models.ShiftType)
        .where(
            models.Assignment.employee_id.in_(eligible_employee_ids),
            models.Assignment.starts_at < week_end_utc,
            models.Assignment.ends_at > week_start_utc,
        )
    ):
        weekly_existing_minutes[employee_id] += _work_minutes_in_window(
            starts_at, ends_at, break_minutes, break_start_minutes,
            week_start_utc, week_end_utc,
        )

    weekly_loads = []
    for employee_id, variable_indices in variables_by_employee.items():
        added_minutes = [
            (
                index,
                _work_minutes_in_window(
                    candidates[index].starts_at,
                    candidates[index].ends_at,
                    candidates[index].shift.break_minutes,
                    candidates[index].shift.break_start_minutes,
                    week_start_utc,
                    week_end_utc,
                ),
            )
            for index in variable_indices
        ]
        weekly_loads.append(
            weekly_existing_minutes[employee_id]
            + sum(candidate_variables[index] * minutes for index, minutes in added_minutes)
        )
    maximum_weekly_load = model.NewIntVar(0, 100_000, "maximum_weekly_work_minutes")
    if weekly_loads:
        model.AddMaxEquality(maximum_weekly_load, weekly_loads)
    else:
        model.Add(maximum_weekly_load == 0)

    total_unfilled = sum(unfilled_variables)
    role_mismatches = sum(
        candidate_variables[index]
        for index, candidate in enumerate(candidates)
        if not candidate.role_match
    )
    model.Minimize(total_unfilled * 20_000_000 + role_mismatches * 20_000 + maximum_weekly_load)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    solver.parameters.num_search_workers = 1
    solver.parameters.log_search_progress = False
    status_code = solver.Solve(model)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return OptimizationPreview((), tuple(
            OpenSlot(shift.id, shift.name, position)
            for shift, position, _starts_at, _ends_at in slots
        ), "UNKNOWN")

    suggestions = tuple(
        SuggestedAssignment(
            employee_id=candidate.employee.id,
            employee_name=candidate.employee.name,
            employee_role=candidate.employee.role,
            shift_type_id=candidate.shift.id,
            shift_name=candidate.shift.name,
            position=candidate.position,
            role_match=candidate.role_match,
            starts_at=candidate.starts_at,
            ends_at=candidate.ends_at,
        )
        for index, candidate in enumerate(candidates)
        if solver.Value(candidate_variables[index])
    )
    unfilled = tuple(
        OpenSlot(slots[index][0].id, slots[index][0].name, slots[index][1])
        for index, variable in enumerate(unfilled_variables)
        if solver.Value(variable)
    )
    result_status = "OPTIMAL" if status_code == cp_model.OPTIMAL else "FEASIBLE"
    return OptimizationPreview(suggestions, unfilled, result_status)


@dataclass(frozen=True)
class PlannedDay:
    target_date: date
    preview: OptimizationPreview


def optimize_period(
    db: Session,
    start_date: date,
    end_date: date,
    department_ids: tuple[int, ...] | None = None,
) -> list[PlannedDay]:
    """Fill only open positions day by day without moving stored assignments.

    Each day's suggestions are flushed temporarily so later days are checked
    against them (rest time, weekly averages, Sunday rules). Everything is
    rolled back before returning; nothing is persisted.
    """
    days: list[PlannedDay] = []
    try:
        current = start_date
        while current <= end_date:
            preview = optimize_day(db, current, department_ids)
            for suggestion in preview.suggestions:
                db.add(models.Assignment(
                    employee_id=suggestion.employee_id,
                    shift_type_id=suggestion.shift_type_id,
                    starts_at=suggestion.starts_at,
                    ends_at=suggestion.ends_at,
                ))
            db.flush()
            days.append(PlannedDay(current, preview))
            current += timedelta(days=1)
    finally:
        db.rollback()
    return days
