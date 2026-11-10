from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.work_rules import (
    _hours_in_window,
    _replacement_rest_days,
    _uncovered_event,
    _worked_calendar_days,
)


def test_replacement_rest_day_period_includes_the_work_day():
    business_tz = ZoneInfo("Europe/Berlin")
    event_date = date(2030, 3, 10)
    starts_at = datetime(2030, 3, 10, 16, tzinfo=timezone.utc)
    ends_at = datetime(2030, 3, 10, 22, tzinfo=timezone.utc)

    rest_days = _replacement_rest_days(
        event_date, 14, [(starts_at, ends_at)], business_tz
    )

    assert date(2030, 3, 9) in rest_days


def test_one_rest_day_cannot_cover_two_work_events():
    first_event = date(2030, 3, 10)
    second_event = date(2030, 3, 17)
    shared_rest_day = date(2030, 3, 16)

    uncovered = _uncovered_event({
        first_event: {date(2030, 3, 9), shared_rest_day},
        second_event: {shared_rest_day},
    })

    assert uncovered is None
    assert _uncovered_event({
        first_event: {shared_rest_day},
        second_event: {shared_rest_day},
    }) is not None


@pytest.mark.parametrize(
    ("business_day", "expected_elapsed_hours"),
    [(date(2030, 3, 31), 23), (date(2030, 10, 27), 25)],
)
def test_business_day_window_uses_real_duration_across_daylight_saving(
    business_day, expected_elapsed_hours
):
    business_tz = ZoneInfo("Europe/Berlin")
    next_day = business_day + timedelta(days=1)
    window_start = datetime.combine(
        business_day, time.min, tzinfo=business_tz
    ).astimezone(timezone.utc)
    window_end = datetime.combine(
        next_day, time.min, tzinfo=business_tz
    ).astimezone(timezone.utc)
    elapsed_hours = (window_end - window_start).total_seconds() / 3600

    assert elapsed_hours == expected_elapsed_hours
    assert _hours_in_window(
        window_start, window_end, 0, 0, window_start, window_end
    ) == expected_elapsed_hours
    assert _worked_calendar_days(
        ((window_start, window_end),), business_tz
    ) == {business_day}
