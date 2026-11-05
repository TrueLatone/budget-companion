"""Compatible navigation cases retained from KAN-8 c382f6c."""
from datetime import date
import pytest
from app.modules.expenses import services


def test_year_period_and_navigation_boundaries(app):
    period = services.resolve_period("year", "2026-10-21")
    assert period.start == date(2026, 1, 1)
    assert period.end == date(2026, 12, 31)
    assert period.label == "Year 2026"

    navigation = services.build_navigation(period)
    assert navigation["prev"].year == 2025
    assert navigation["next"].year == 2027
    assert navigation["prev_month"] == date(2026, 9, 21)

    month = services.resolve_period("month", "2026-01-31")
    navigation = services.build_navigation(month)
    assert navigation["next"] == date(2026, 2, 28)
    assert navigation["prev"] == date(2025, 12, 31)


def test_week_navigation_moves_by_seven_days():
    period = services.resolve_period("week", "2026-10-07")
    assert period.start == date(2026, 10, 5)
    assert period.end == date(2026, 10, 11)

    navigation = services.build_navigation(period)
    assert navigation["prev"] == date(2026, 9, 30)
    assert navigation["next"] == date(2026, 10, 14)

    previous_week = services.resolve_period(
        "week", navigation["prev"].isoformat()
    )
    next_week = services.resolve_period("week", navigation["next"].isoformat())
    assert (previous_week.start, previous_week.end) == (
        date(2026, 9, 28),
        date(2026, 10, 4),
    )
    assert (next_week.start, next_week.end) == (
        date(2026, 10, 12),
        date(2026, 10, 18),
    )


@pytest.mark.parametrize("value", ["0001-01-01", "9999-12-31"])
@pytest.mark.parametrize("view", ["day", "week", "month", "year"])
def test_navigation_at_supported_date_boundaries(view, value):
    period = services.resolve_period(view, value)
    navigation = services.build_navigation(period)
    assert period.start <= period.end
    assert all(date.min <= point <= date.max for point in navigation.values())
