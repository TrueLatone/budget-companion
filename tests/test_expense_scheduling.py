from datetime import date

import pytest

from app.extensions import db
from app.modules.expenses import services
from app.modules.expenses.idgen import new_id


USER = "test-user"


def _create_plan(**overrides):
    payload = {
        "title": "Khoản chi thử nghiệm",
        "planned_amount": "100000",
        "amount_source": "USER_ENTERED",
        "priority": "P1",
        "schedule_tag": "MONTHLY",
        "is_active": "1",
    }
    payload.update(overrides)
    return services.create_plan_item(USER, payload)


def test_weekly_schedule_is_inclusive_and_idempotent(app):
    item = _create_plan(schedule_tag="WEEKLY", day_of_week="1")

    created = services.generate_tasks(USER, date(2026, 1, 1), date(2026, 1, 31))
    tasks = services.list_tasks(USER, date(2026, 1, 1), date(2026, 1, 31))

    assert created == 4
    assert [task.assigned_date for task in tasks] == [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
    ]
    assert all(task.plan_item_id == item.plan_item_id for task in tasks)

    assert services.generate_tasks(USER, date(2026, 1, 1), date(2026, 1, 31)) == 0


def test_monthly_schedule_uses_last_day_and_handles_leap_year(app):
    _create_plan(schedule_tag="MONTHLY")

    services.generate_tasks(USER, date(2026, 2, 1), date(2026, 2, 28))
    feb_2026 = services.list_tasks(USER, date(2026, 2, 1), date(2026, 2, 28))
    assert [task.assigned_date for task in feb_2026] == [date(2026, 2, 28)]

    services.generate_tasks(USER, date(2028, 2, 1), date(2028, 2, 29))
    feb_2028 = services.list_tasks(USER, date(2028, 2, 1), date(2028, 2, 29))
    assert [task.assigned_date for task in feb_2028] == [date(2028, 2, 29)]


def test_day_of_month_is_clamped_and_specific_date_is_respected(app):
    _create_plan(schedule_tag="DAY_OF_MONTH", day_of_month="31")
    services.generate_tasks(USER, date(2026, 2, 1), date(2026, 2, 28))
    feb = services.list_tasks(USER, date(2026, 2, 1), date(2026, 2, 28))
    assert [task.assigned_date for task in feb] == [date(2026, 2, 28)]

    _create_plan(
        title="Một lần",
        schedule_tag="DATE",
        specific_date="2026-03-15",
    )
    assert services.generate_tasks(USER, date(2026, 2, 1), date(2026, 2, 28)) == 0
    assert services.generate_tasks(USER, date(2026, 3, 1), date(2026, 3, 31)) == 2
    march = services.list_tasks(USER, date(2026, 3, 1), date(2026, 3, 31))
    assert [task.assigned_date for task in march] == [
        date(2026, 3, 15),
        date(2026, 3, 31),
    ]


def test_daily_schedule_includes_both_boundaries(app):
    _create_plan(schedule_tag="DAILY")
    created = services.generate_tasks(USER, date(2026, 4, 1), date(2026, 4, 3))
    tasks = services.list_tasks(USER, date(2026, 4, 1), date(2026, 4, 3))
    assert created == 3
    assert [task.assigned_date for task in tasks] == [
        date(2026, 4, 1),
        date(2026, 4, 2),
        date(2026, 4, 3),
    ]


def test_irrelevant_schedule_fields_are_normalized_to_null(app):
    item = _create_plan(
        schedule_tag="DAILY",
        day_of_week="1",
        day_of_month="31",
        specific_date="2026-01-01",
    )
    assert item.day_of_week is None
    assert item.day_of_month is None
    assert item.specific_date is None


def test_generate_rejects_reversed_period(app):
    _create_plan()
    with pytest.raises(services.ValidationError):
        services.generate_tasks(USER, date(2026, 4, 3), date(2026, 4, 1))


def test_new_id_format_and_encoded_date():
    value = new_id()
    assert len(value) == 21
    from app.modules.expenses.idgen import ID_RE, creation_date

    assert ID_RE.fullmatch(value)
    assert creation_date(value) is not None


def test_schedule_change_is_rejected_after_tasks_exist(app):
    item = _create_plan(schedule_tag="MONTHLY")
    services.generate_tasks(USER, date(2026, 5, 1), date(2026, 5, 31))

    with pytest.raises(services.ValidationError):
        services.update_plan_item(
            USER,
            item.plan_item_id,
            {
                "title": item.title,
                "planned_amount": str(item.planned_amount),
                "amount_source": item.amount_source,
                "priority": item.priority,
                "schedule_tag": "WEEKLY",
                "day_of_week": "1",
                "is_active": "1",
            },
        )


def test_plan_update_keeps_internal_and_external_ids(app):
    item = _create_plan()
    item.source_expense_id = "M1-EXTERNAL-001"
    db.session.commit()

    updated = services.update_plan_item(
        USER,
        item.plan_item_id,
        {
            "title": "Tên mới",
            "planned_amount": "200000",
            "amount_source": "USER_ENTERED",
            "priority": "P0",
            "schedule_tag": "MONTHLY",
            "is_active": "1",
        },
    )

    assert updated.plan_item_id == item.plan_item_id
    assert updated.source_expense_id == "M1-EXTERNAL-001"
    assert updated.title == "Tên mới"
