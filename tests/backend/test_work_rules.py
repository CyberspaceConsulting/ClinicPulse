from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.work_rules import _replacement_rest_days, _uncovered_event


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
