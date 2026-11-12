from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ortools.sat.python import cp_model
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from . import models
from .absences import employee_is_absent
from .staffing import qualified_requirements, shift_requirements
from .work_rules import (
    business_timezone,
    has_overlapping_assignment,
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
    positions: tuple[str, ...] = ()


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
class _Need:
    shift: models.ShiftType
    position: str
    vacancies: int
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class _Candidate:
    employee: models.Employee
    shift: models.ShiftType
    starts_at: datetime
    ends_at: datetime
    need_indices: tuple[int, ...]


def _shift_interval(target_date: date, shift: models.ShiftType, business_tz: ZoneInfo) -> tuple[datetime, datetime]:
    local_start = datetime.combine(target_date, shift.start_time, tzinfo=business_tz)
    local_end_date = target_date + timedelta(days=shift.end_time <= shift.start_time)
    local_end = datetime.combine(local_end_date, shift.end_time, tzinfo=business_tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


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
    shift_query = select(models.ShiftType).where(
        or_(
            models.ShiftType.vehicle_id.is_(None),
            models.ShiftType.vehicle_id.in_(select(models.Vehicle.id).where(models.Vehicle.is_active.is_(True))),
        )
    ).order_by(models.ShiftType.id)
    employee_query = select(models.Employee).options(
        selectinload(models.Employee.qualifications),
        selectinload(models.Employee.additional_departments),
    ).order_by(models.Employee.id)
    if department_ids is not None:
        shift_query = shift_query.where(models.ShiftType.department_id.in_(department_ids))
        employee_query = employee_query.where(models.employee_in_departments(department_ids))
    if target_vacancies is not None:
        shift_query = shift_query.where(
            models.ShiftType.id.in_({shift_id for shift_id, _ in target_vacancies})
        )
    shifts = list(db.scalars(shift_query))
    employees = list(db.scalars(employee_query))
    employees_by_department: dict[int | None, list[models.Employee]] = {}
    for employee in employees:
        for member_department_id in employee.department_ids:
            employees_by_department.setdefault(member_department_id, []).append(employee)

    local_day_start = datetime.combine(target_date, time.min, tzinfo=business_tz)
    local_day_end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=business_tz)
    day_start = local_day_start.astimezone(timezone.utc)
    day_end = local_day_end.astimezone(timezone.utc)
    existing_assignments = list(db.scalars(
        select(models.Assignment)
        .options(
            selectinload(models.Assignment.employee).selectinload(models.Employee.qualifications),
            selectinload(models.Assignment.shift_type).selectinload(models.ShiftType.staffing_requirements),
        )
        .where(
            models.Assignment.starts_at >= day_start,
            models.Assignment.starts_at < day_end,
        )
    ))
    # Existing staff counts for every requirement they qualify for, so one person
    # holding several qualifications can cover several requirements of a shift.
    existing_counts: dict[tuple[int, str], int] = {}
    for assignment in existing_assignments:
        for requirement in qualified_requirements(assignment.employee, assignment.shift_type):
            key = (assignment.shift_type.id, requirement.position.strip().casefold())
            existing_counts[key] = existing_counts.get(key, 0) + 1

    needs: list[_Need] = []
    for shift in shifts:
        starts_at, ends_at = _shift_interval(target_date, shift, business_tz)
        for requirement in shift_requirements(shift):
            key = (shift.id, requirement.position.strip().casefold())
            vacancies = (
                target_vacancies.get(key, 0)
                if target_vacancies is not None
                else max(0, requirement.required_staff - existing_counts.get(key, 0))
            )
            if vacancies:
                needs.append(_Need(shift, requirement.position, vacancies, starts_at, ends_at))
    if not needs:
        return OptimizationPreview((), (), "OPTIMAL")
    if sum(need.vacancies for need in needs) > MAX_OPEN_SLOTS:
        raise OptimizationTooLarge("Limit optimization to a maximum of 150 open positions per day")
    possible_combinations = sum(
        len(employees_by_department.get(need.shift.department_id, ()))
        for need in needs
    )
    if possible_combinations > MAX_CANDIDATE_VARIABLES:
        raise OptimizationTooLarge("Select a smaller department for day optimization")

    needs_by_shift: dict[int, list[int]] = {}
    for need_index, need in enumerate(needs):
        needs_by_shift.setdefault(need.shift.id, []).append(need_index)
    shifts_with_needs = {need.shift.id: need.shift for need in needs}

    candidate_cache: dict[tuple[int, int], bool] = {}
    candidates: list[_Candidate] = []
    for shift_id, shift in shifts_with_needs.items():
        need_positions = {
            needs[need_index].position.strip().casefold(): need_index
            for need_index in needs_by_shift[shift_id]
        }
        starts_at = needs[needs_by_shift[shift_id][0]].starts_at
        ends_at = needs[needs_by_shift[shift_id][0]].ends_at
        for employee in employees_by_department.get(shift.department_id, ()):
            covered = tuple(
                need_positions[requirement.position.strip().casefold()]
                for requirement in qualified_requirements(employee, shift)
                if requirement.position.strip().casefold() in need_positions
            )
            if not covered:
                continue
            cache_key = (employee.id, shift.id)
            eligible = candidate_cache.get(cache_key)
            if eligible is None:
                eligible = (
                    not has_overlapping_assignment(db, employee.id, starts_at, ends_at)
                    and not employee_is_absent(db, employee.id, starts_at, ends_at)
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
                    employee=employee,
                    shift=shift,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    need_indices=covered,
                ))
    if len(candidates) > MAX_CANDIDATE_VARIABLES:
        raise OptimizationTooLarge("Optimization has too many eligible employee-position combinations")

    model = cp_model.CpModel()
    candidate_variables = [
        model.NewBoolVar(f"assign_{candidate.shift.id}_{candidate.employee.id}")
        for candidate in candidates
    ]
    shortage_variables = [
        model.NewIntVar(0, need.vacancies, f"shortage_{index}")
        for index, need in enumerate(needs)
    ]
    variables_by_employee: dict[int, list[int]] = {}
    for index, candidate in enumerate(candidates):
        variables_by_employee.setdefault(candidate.employee.id, []).append(index)

    fill_variables: dict[tuple[int, int], cp_model.IntVar] = {}
    if target_vacancies is not None:
        # Every absent person needs an individual replacement for their own position.
        for index, candidate in enumerate(candidates):
            for need_index in candidate.need_indices:
                fill_variables[(index, need_index)] = model.NewBoolVar(f"fill_{index}_{need_index}")
            model.Add(
                candidate_variables[index]
                == sum(fill_variables[(index, need_index)] for need_index in candidate.need_indices)
            )
        for need_index, need in enumerate(needs):
            model.Add(
                sum(
                    variable for (_index, filled), variable in fill_variables.items()
                    if filled == need_index
                ) + shortage_variables[need_index] == need.vacancies
            )
    else:
        for need_index, need in enumerate(needs):
            model.Add(
                sum(
                    candidate_variables[index]
                    for index, candidate in enumerate(candidates)
                    if need_index in candidate.need_indices
                ) + shortage_variables[need_index] >= need.vacancies
            )

    # One person can work at most one of the candidate shifts of the day, whichever
    # department it belongs to.
    for variable_indices in variables_by_employee.values():
        model.AddAtMostOne(candidate_variables[index] for index in variable_indices)

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

    total_shortage = sum(shortage_variables)
    assigned_people = sum(candidate_variables)
    # Open positions come first; fewer people is next so nobody is scheduled beyond the
    # requirement, then the workload is balanced.
    model.Minimize(total_shortage * 20_000_000 + assigned_people * 200_000 + maximum_weekly_load)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    solver.parameters.num_search_workers = 1
    solver.parameters.log_search_progress = False
    status_code = solver.Solve(model)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return OptimizationPreview((), tuple(
            OpenSlot(need.shift.id, need.shift.name, need.position)
            for need in needs
            for _ in range(need.vacancies)
        ), "UNKNOWN")

    suggestion_list: list[SuggestedAssignment] = []
    for index, candidate in enumerate(candidates):
        if not solver.Value(candidate_variables[index]):
            continue
        covered = [needs[need_index].position for need_index in candidate.need_indices]
        if target_vacancies is not None:
            covered = [
                needs[need_index].position for need_index in candidate.need_indices
                if solver.Value(fill_variables[(index, need_index)])
            ]
        suggestion_list.append(SuggestedAssignment(
            employee_id=candidate.employee.id,
            employee_name=candidate.employee.name,
            employee_role=candidate.employee.role,
            shift_type_id=candidate.shift.id,
            shift_name=candidate.shift.name,
            position=covered[0],
            role_match=True,
            starts_at=candidate.starts_at,
            ends_at=candidate.ends_at,
            positions=tuple(covered),
        ))
    suggestions = tuple(suggestion_list)
    unfilled = tuple(
        OpenSlot(need.shift.id, need.shift.name, need.position)
        for need_index, need in enumerate(needs)
        for _ in range(solver.Value(shortage_variables[need_index]))
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
