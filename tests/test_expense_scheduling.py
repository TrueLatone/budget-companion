from datetime import date

import pytest

from app.modules.expenses import services
from app.modules.expenses.idgen import ID_RE, creation_date, new_id


def test_weekly_schedule_is_inclusive():
    dates = services.occurrence_dates(
        "WEEKLY", date(2026, 1, 1), date(2026, 1, 31), day_of_week=1
    )
    assert len(dates) == 4
    assert dates == [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
    ]


def test_monthly_schedule_uses_last_day_and_handles_leap_year():
    feb_2026 = services.occurrence_dates(
        "MONTHLY", date(2026, 2, 1), date(2026, 2, 28)
    )
    assert feb_2026 == [date(2026, 2, 28)]

    feb_2028 = services.occurrence_dates(
        "MONTHLY", date(2028, 2, 1), date(2028, 2, 29)
    )
    assert feb_2028 == [date(2028, 2, 29)]


def test_day_of_month_is_clamped_and_specific_date_is_respected():
    feb = services.occurrence_dates(
        "DAY_OF_MONTH", date(2026, 2, 1), date(2026, 2, 28), day_of_month=31
    )
    assert feb == [date(2026, 2, 28)]

    outside = services.occurrence_dates(
        "DATE",
        date(2026, 2, 1),
        date(2026, 2, 28),
        specific_date=date(2026, 3, 15),
    )
    assert outside == []

    inside = services.occurrence_dates(
        "DATE",
        date(2026, 3, 1),
        date(2026, 3, 31),
        specific_date=date(2026, 3, 15),
    )
    assert inside == [date(2026, 3, 15)]


def test_daily_schedule_includes_both_boundaries():
    dates = services.occurrence_dates(
        "DAILY", date(2026, 4, 1), date(2026, 4, 3)
    )
    assert dates == [
        date(2026, 4, 1),
        date(2026, 4, 2),
        date(2026, 4, 3),
    ]


def test_reversed_period_returns_empty():
    dates = services.occurrence_dates(
        "DAILY", date(2026, 4, 3), date(2026, 4, 1)
    )
    assert dates == []


def test_invalid_scheduling_inputs_raise_validation_error():
    with pytest.raises(services.ValidationError):
        services.occurrence_dates("WEEKLY", date(2026, 1, 1), date(2026, 1, 31), day_of_week=8)

    with pytest.raises(services.ValidationError):
        services.occurrence_dates("DAY_OF_MONTH", date(2026, 1, 1), date(2026, 1, 31), day_of_month=32)

    with pytest.raises(services.ValidationError):
        services.occurrence_dates("DATE", date(2026, 1, 1), date(2026, 1, 31), specific_date=None)

    with pytest.raises(services.ValidationError):
        services.occurrence_dates("INVALID_TAG", date(2026, 1, 1), date(2026, 1, 31))


def test_new_id_format_and_encoded_date():
    value = new_id()
    assert len(value) == 21
    assert ID_RE.fullmatch(value)
    assert creation_date(value) is not None
