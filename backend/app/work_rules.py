from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .regional_calendar import german_public_holidays

@dataclass(frozen=True)
class WorkRules:
    # The weekly value is the average limit over 24 weeks, not a per-week cap.
    rest_hours: int = 11
    max_daily_hours: int = 10
    max_weekly_hours: int = 48


def load_work_rules(db: Session) -> WorkRules:
    settings = db.get(models.ApplicationSetting, 1)
    if settings is None:
        return WorkRules()
    return WorkRules(settings.rest_hours, settings.max_daily_hours, settings.max_weekly_hours)


def business_timezone(db: Session) -> ZoneInfo:
    configuration = db.get(models.BusinessConfiguration, 1)
    return ZoneInfo(configuration.timezone if configuration is not None else "Europe/Berlin")


def has_overlapping_assignment(
    db: Session, employee_id: int, starts_at: datetime, ends_at: datetime
) -> bool:
    return db.scalar(
        select(models.Assignment.id).where(
            models.Assignment.employee_id == employee_id,
            models.Assignment.starts_at < ends_at,
            models.Assignment.ends_at > starts_at,
        ).limit(1)
    ) is not None


def gross_duration(start: time, end: time) -> timedelta:
    start_delta = timedelta(hours=start.hour, minutes=start.minute)
    end_delta = timedelta(hours=end.hour, minutes=end.minute)
    return end_delta - start_delta if end_delta > start_delta else end_delta + timedelta(days=1) - start_delta


def required_break_minutes(gross: timedelta, planned_break_minutes: int | None = None) -> int:
    if planned_break_minutes is None:
        planned_break_minutes = 30 if gross > timedelta(hours=6) else 0
        if gross - timedelta(minutes=planned_break_minutes) > timedelta(hours=9):
            return 45
        return planned_break_minutes
    working_time = gross - timedelta(minutes=planned_break_minutes)
    if working_time > timedelta(hours=9):
        return 45
    if working_time > timedelta(hours=6):
        return 30
    return 0


def default_break_start_minutes(gross: timedelta, break_minutes: int) -> int:
    return max(0, min(360, int(gross.total_seconds() // 60) - break_minutes))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _work_segments(
    starts_at: datetime, ends_at: datetime, break_minutes: int, break_start_minutes: int
) -> tuple[tuple[datetime, datetime], ...]:
    starts_at = _utc(starts_at)
    ends_at = _utc(ends_at)
    if break_minutes <= 0:
        return ((starts_at, ends_at),)
    break_start = starts_at + timedelta(minutes=break_start_minutes)
    break_end = break_start + timedelta(minutes=break_minutes)
    return tuple(
        (segment_start, segment_end)
        for segment_start, segment_end in ((starts_at, break_start), (break_end, ends_at))
        if segment_end > segment_start
    )


def _hours_in_window(
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    break_start_minutes: int,
    window_start: datetime,
    window_end: datetime,
) -> float:
    seconds = 0.0
    for segment_start, segment_end in _work_segments(
        starts_at, ends_at, break_minutes, break_start_minutes
    ):
        overlap_start = max(segment_start, window_start)
        overlap_end = min(segment_end, window_end)
        if overlap_end > overlap_start:
            seconds += (overlap_end - overlap_start).total_seconds()
    return seconds / 3600


def _worked_calendar_days(
    segments: tuple[tuple[datetime, datetime], ...], business_tz: ZoneInfo
) -> set[date]:
    days: set[date] = set()
    for segment_start, segment_end in segments:
        local_date = segment_start.astimezone(business_tz).date()
        final_date = (segment_end - timedelta(microseconds=1)).astimezone(business_tz).date()
        while local_date <= final_date:
            day_start = datetime.combine(local_date, time.min, tzinfo=business_tz).astimezone(timezone.utc)
            day_end = datetime.combine(
                local_date + timedelta(days=1), time.min, tzinfo=business_tz
            ).astimezone(timezone.utc)
            if segment_start < day_end and segment_end > day_start:
                days.add(local_date)
            local_date += timedelta(days=1)
    return days


def _replacement_rest_days(
    event_date: date,
    deadline_days: int,
    segments: list[tuple[datetime, datetime]],
    business_tz: ZoneInfo,
) -> set[date]:
    required_rest = timedelta(hours=11)
    rest_days: set[date] = set()
    for offset in range(1 - deadline_days, deadline_days):
        if offset == 0:
            continue
        rest_date = event_date + timedelta(days=offset)
        day_start = datetime.combine(rest_date, time.min, tzinfo=business_tz).astimezone(timezone.utc)
        day_end = day_start + timedelta(hours=24)
        if any(start < day_end and end > day_start for start, end in segments):
            continue
        previous_end = max((end for _start, end in segments if end <= day_start), default=None)
        next_start = min((start for start, _end in segments if start >= day_end), default=None)
        before_rest = previous_end is None or day_start - previous_end >= required_rest
        after_rest = next_start is None or next_start - day_end >= required_rest
        if before_rest or after_rest:
            rest_days.add(rest_date)
    return rest_days


def _uncovered_event(
    rest_options: dict[date, set[date]],
) -> date | None:
    assigned_rest_days: dict[date, date] = {}

    def assign_rest_day(event_date: date, visited: set[date]) -> bool:
        for rest_date in sorted(
            rest_options[event_date],
            key=lambda day: (abs((day - event_date).days), day > event_date, day),
        ):
            if rest_date in visited:
                continue
            visited.add(rest_date)
            previous_event = assigned_rest_days.get(rest_date)
            if previous_event is None or assign_rest_day(previous_event, visited):
                assigned_rest_days[rest_date] = event_date
                return True
        return False

    for event_date in sorted(rest_options, key=lambda day: len(rest_options[day])):
        if not assign_rest_day(event_date, set()):
            return event_date
    return None


def calendar_rule_violation(
    db: Session,
    employee_id: int,
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    break_start_minutes: int,
) -> str | None:
    configuration = db.get(models.BusinessConfiguration, 1)
    if configuration is None:
        return "Business configuration is required before scheduling"
    business_tz = business_timezone(db)
    candidate_segments = _work_segments(starts_at, ends_at, break_minutes, break_start_minutes)
    candidate_days = _worked_calendar_days(candidate_segments, business_tz)
    candidate_years = {day.year for day in candidate_days}
    holiday_calendar = german_public_holidays(configuration.federal_state, candidate_years)
    candidate_sundays = {day for day in candidate_days if day.weekday() == 6}
    candidate_holidays = candidate_days.intersection(holiday_calendar)
    if (candidate_sundays or candidate_holidays) and not configuration.sunday_work_authorized:
        return "Work on Sundays or public holidays is disabled for this facility (ArbZG §§9–10)"

    candidate_first = min(candidate_days)
    candidate_last = max(candidate_days)
    calendar_start_date = min(
        [date(day.year, 1, 1) for day in candidate_days]
        + [candidate_first - timedelta(days=110)]
    )
    calendar_end_date = max(
        [date(day.year + 1, 1, 1) for day in candidate_days]
        + [candidate_last + timedelta(days=111)]
    )
    calendar_start = datetime.combine(
        calendar_start_date, time.min, tzinfo=business_tz
    ).astimezone(timezone.utc)
    calendar_end = datetime.combine(
        calendar_end_date, time.min, tzinfo=business_tz
    ).astimezone(timezone.utc)
    schedule_rows = list(db.execute(
        select(
            models.Assignment.starts_at,
            models.Assignment.ends_at,
            models.ShiftType.break_minutes,
            models.ShiftType.break_start_minutes,
        )
        .join(models.ShiftType)
        .where(
            models.Assignment.employee_id == employee_id,
            models.Assignment.starts_at < calendar_end,
            models.Assignment.ends_at > calendar_start,
        )
    ))
    schedule_segments: list[tuple[datetime, datetime]] = list(candidate_segments)
    worked_days = set(candidate_days)
    for shift_start, shift_end, shift_break, shift_break_start in schedule_rows:
        segments = _work_segments(shift_start, shift_end, shift_break, shift_break_start)
        schedule_segments.extend(segments)
        worked_days.update(_worked_calendar_days(segments, business_tz))

    if candidate_sundays:
        for year in candidate_years:
            sundays_worked = {
                day for day in worked_days if day.year == year and day.weekday() == 6
            }
            if len(sundays_worked) > 37:
                return "At least 15 Sundays per calendar year must remain free of work (ArbZG §11)"

    all_years = {day.year for day in worked_days}
    all_holidays = german_public_holidays(configuration.federal_state, all_years)
    event_days = {
        day for day in worked_days
        if day.weekday() == 6 or day in all_holidays
    }
    if event_days:
        check_from = candidate_first - timedelta(days=55)
        check_until = candidate_last + timedelta(days=55)
        today = datetime.now(business_tz).date()
        relevant_events = sorted(
            day for day in event_days
            if check_from <= day <= check_until
        )
        active_events = [
            (event_date, 14 if event_date.weekday() == 6 else 56)
            for event_date in relevant_events
            if event_date + timedelta(
                days=(14 if event_date.weekday() == 6 else 56) - 1
            ) >= today
        ]
        rest_options = {
            event_date: _replacement_rest_days(
                event_date, deadline_days, schedule_segments, business_tz
            )
            for event_date, deadline_days in active_events
        }
        uncovered_event = _uncovered_event(rest_options)
        if uncovered_event is not None:
            deadline_days = 14 if uncovered_event.weekday() == 6 else 56
            return (
                f"A distinct replacement rest day is required within a "
                f"{deadline_days}-day period including {uncovered_event.isoformat()} "
                f"(ArbZG §11)"
            )
    return None


def work_rule_violation(
    db: Session,
    employee_id: int,
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    break_start_minutes: int,
    rules: WorkRules | None = None,
) -> str | None:
    rules = rules or load_work_rules(db)
    starts_at = _utc(starts_at)
    ends_at = _utc(ends_at)
    if break_minutes < required_break_minutes(ends_at - starts_at, break_minutes):
        return "Shift does not include the legally required break (ArbZG §4)"
    if break_minutes and (
        break_start_minutes > 360
        or break_start_minutes + break_minutes > (ends_at - starts_at).total_seconds() / 60
    ):
        return "Scheduled break does not fit within the shift or starts after six hours (ArbZG §4)"
    if break_minutes and (
        break_start_minutes > 360
        or (ends_at - starts_at).total_seconds() / 60 - break_start_minutes - break_minutes > 360
    ):
        return "A work period longer than six hours without a break would violate ArbZG §4"
    calendar_violation = calendar_rule_violation(
        db, employee_id, starts_at, ends_at, break_minutes, break_start_minutes
    )
    if calendar_violation is not None:
        return calendar_violation

    rest = timedelta(hours=rules.rest_hours)
    before = db.scalar(
        select(models.Assignment.id).where(
            models.Assignment.employee_id == employee_id,
            models.Assignment.ends_at <= starts_at,
            models.Assignment.ends_at > starts_at - rest,
        ).limit(1)
    )
    after = db.scalar(
        select(models.Assignment.id).where(
            models.Assignment.employee_id == employee_id,
            models.Assignment.starts_at >= ends_at,
            models.Assignment.starts_at < ends_at + rest,
        ).limit(1)
    )
    if before is not None or after is not None:
        return f"Minimum rest period of {rules.rest_hours} hours between shifts would be violated"

    business_tz = business_timezone(db)
    local_start = starts_at.astimezone(business_tz)
    local_end = ends_at.astimezone(business_tz)
    local_date = local_start.date()
    while local_date <= local_end.date():
        local_day_start = datetime.combine(local_date, time.min, tzinfo=business_tz)
        local_day_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=business_tz)
        day_start = local_day_start.astimezone(timezone.utc)
        day_end = local_day_end.astimezone(timezone.utc)
        daily_shifts = list(db.execute(
            select(
                models.Assignment.starts_at,
                models.Assignment.ends_at,
                models.ShiftType.break_minutes,
                models.ShiftType.break_start_minutes,
            )
            .join(models.ShiftType)
            .where(
                models.Assignment.employee_id == employee_id,
                models.Assignment.starts_at < day_end,
                models.Assignment.ends_at > day_start,
            )
        ))
        daily = _hours_in_window(
            starts_at, ends_at, break_minutes, break_start_minutes, day_start, day_end
        )
        for other_start, other_end, other_break, other_break_start in daily_shifts:
            daily += _hours_in_window(
                other_start, other_end, other_break, other_break_start, day_start, day_end
            )
        if daily > rules.max_daily_hours:
            return f"Daily working time would exceed {rules.max_daily_hours} hours (ArbZG §3)"
        local_date += timedelta(days=1)

    period = timedelta(weeks=24)
    local_starts_at = starts_at.astimezone(business_tz)
    local_ends_at = ends_at.astimezone(business_tz)
    first_window = local_starts_at - period
    last_window = local_ends_at
    query_start = first_window.astimezone(timezone.utc)
    query_end = (last_window + period).astimezone(timezone.utc)
    assignments = list(db.execute(
        select(
            models.Assignment.starts_at,
            models.Assignment.ends_at,
            models.ShiftType.break_minutes,
            models.ShiftType.break_start_minutes,
        )
        .join(models.ShiftType)
        .where(
            models.Assignment.employee_id == employee_id,
            models.Assignment.starts_at < query_end,
            models.Assignment.ends_at > query_start,
        )
    ))
    candidate_segments = _work_segments(starts_at, ends_at, break_minutes, break_start_minutes)
    window_starts = {first_window, local_starts_at}
    for segment_start, segment_end in candidate_segments:
        for point_utc in (segment_start, segment_end):
            point = point_utc.astimezone(business_tz)
            for boundary in (point, point - period):
                if first_window < boundary < last_window:
                    window_starts.add(boundary)
    for other_start, other_end, _break, _break_start in assignments:
        other_start = _utc(other_start)
        other_end = _utc(other_end)
        segments = _work_segments(other_start, other_end, _break, _break_start)
        for segment_start, segment_end in segments:
            for point_utc in (segment_start, segment_end):
                point = point_utc.astimezone(business_tz)
                for boundary in (point, point - period):
                    if first_window < boundary < last_window:
                        window_starts.add(boundary)
    allowed_hours = rules.max_weekly_hours * 24
    for window_start in window_starts:
        window_start_utc = window_start.astimezone(timezone.utc)
        window_end_utc = (window_start + period).astimezone(timezone.utc)
        worked_hours = sum(
            _hours_in_window(
                other_start,
                other_end,
                other_break,
                other_break_start,
                window_start_utc,
                window_end_utc,
            )
            for other_start, other_end, other_break, other_break_start in assignments
        )
        worked_hours += sum(
            max((min(segment_end, window_end_utc) - max(segment_start, window_start_utc)).total_seconds(), 0)
            / 3600
            for segment_start, segment_end in candidate_segments
        )
        if worked_hours > allowed_hours:
            return (
                f"Average working time would exceed {rules.max_weekly_hours} hours per week "
                "over the 24-week reference period (ArbZG §3)"
            )
    return None
