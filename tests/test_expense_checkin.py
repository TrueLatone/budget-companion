from datetime import date

import pytest

from app.extensions import db
from app.modules.expenses import services
from app.modules.expenses.validators import ValidationError


USER = "test-user"


def _create_and_generate(assigned_date: date, amount: str = "100000"):
    services.create_plan_item(
        USER,
        {
            "title": "Tiền nhà",
            "planned_amount": amount,
            "amount_source": "USER_ENTERED",
            "priority": "P1",
            "schedule_tag": "DATE",
            "specific_date": assigned_date.isoformat(),
            "is_active": "1",
        },
    )
    services.generate_tasks(USER, assigned_date, assigned_date)
    return services.list_tasks(USER, assigned_date, assigned_date)[0]


def test_checkin_planned_then_actual_updates_single_record(app):
    task = _create_and_generate(date(2099, 1, 5))

    services.checkin_task(USER, task.task_id, action="planned")
    db.session.refresh(task)
    record = services.list_records(USER, date(2099, 1, 5), date(2099, 1, 5))[0]

    assert task.task_status == services.STATUS_WITHIN_BUDGET
    assert task.checked_at is not None
    assert record.amount == 100000
    assert record.actual_amount_source == services.RECORD_PLANNED
    assert record.title == "Tiền nhà"

    # A repeated planned check-in updates the same planned record.
    services.checkin_task(USER, task.task_id, action="planned")
    assert len(services.list_records(USER, date(2099, 1, 5), date(2099, 1, 5))) == 1

    services.checkin_task(
        USER,
        task.task_id,
        action="actual",
        amount_raw="120000",
        expense_date_raw="2099-01-05",
        category="Nhà ở",
        note="Tăng giá",
    )
    db.session.refresh(task)
    records = services.list_records(USER, date(2099, 1, 5), date(2099, 1, 5))

    assert len(records) == 1
    assert records[0].record_id == record.record_id
    assert records[0].amount == 120000
    assert records[0].actual_amount_source == "USER_ENTERED"
    assert records[0].category == "Nhà ở"
    assert task.task_status == services.STATUS_OVER_BUDGET
    assert task.checked_at is not None


def test_no_expense_rejected_when_record_exists_then_allowed_after_delete(app):
    task = _create_and_generate(date(2099, 1, 6))
    services.checkin_task(USER, task.task_id, action="planned")
    record = services.list_records(USER, date(2099, 1, 6), date(2099, 1, 6))[0]

    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.task_id, action="no_expense")

    services.delete_record(USER, record.record_id)
    db.session.refresh(task)
    assert task.task_status == services.STATUS_PENDING
    assert task.checked_at is None

    services.checkin_task(USER, task.task_id, action="no_expense")
    db.session.refresh(task)
    assert task.task_status == services.STATUS_NO_EXPENSE
    assert services.list_records(USER, date(2099, 1, 6), date(2099, 1, 6)) == []


def test_no_expense_does_not_create_zero_record(app):
    task = _create_and_generate(date(2099, 1, 7))
    services.checkin_task(USER, task.task_id, action="no_expense")

    assert services.list_records(USER, date(2099, 1, 7), date(2099, 1, 7)) == []


def test_actual_requires_positive_integer(app):
    task = _create_and_generate(date(2099, 1, 8))
    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.task_id, action="actual", amount_raw="0")
    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.task_id, action="actual", amount_raw="abc")
    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.task_id, action="actual", amount_raw="")


def test_overdue_pending_task_becomes_unrecorded_idempotently(app):
    task = _create_and_generate(date(2020, 1, 5))

    assert services.refresh_unrecorded(USER) == 1
    db.session.refresh(task)
    assert task.task_status == services.STATUS_UNRECORDED
    assert services.refresh_unrecorded(USER) == 0


def test_plan_amount_change_does_not_rewrite_confirmed_history(app):
    task = _create_and_generate(date(2099, 1, 9), amount="100000")
    services.checkin_task(USER, task.task_id, action="actual", amount_raw="120000")
    db.session.refresh(task)
    assert task.task_status == services.STATUS_OVER_BUDGET

    item = db.session.get(services.ExpensePlanItem, task.plan_item_id)
    services.update_plan_item(
        USER,
        item.plan_item_id,
        {
            "title": item.title,
            "planned_amount": "150000",
            "amount_source": item.amount_source,
            "priority": "P0",
            "schedule_tag": item.schedule_tag,
            "specific_date": item.specific_date.isoformat(),
            "is_active": "1",
        },
    )
    db.session.refresh(task)
    assert task.planned_amount == 100000
    assert task.priority == "P1"
    assert task.task_status == services.STATUS_OVER_BUDGET
    assert services.list_records(USER, date(2099, 1, 9), date(2099, 1, 9))[
        0
    ].amount == 120000


def test_plan_amount_change_updates_unconfirmed_tasks(app):
    task = _create_and_generate(date(2099, 1, 10), amount="100000")
    item = db.session.get(services.ExpensePlanItem, task.plan_item_id)
    services.update_plan_item(
        USER,
        item.plan_item_id,
        {
            "title": item.title,
            "planned_amount": "150000",
            "amount_source": item.amount_source,
            "priority": "P0",
            "schedule_tag": item.schedule_tag,
            "specific_date": item.specific_date.isoformat(),
            "is_active": "1",
        },
    )
    db.session.refresh(task)
    assert task.planned_amount == 150000
    assert task.priority == "P0"
    assert task.task_status == services.STATUS_PENDING


def test_plan_amount_change_keeps_unrecorded_history(app):
    task = _create_and_generate(date(2020, 1, 9), amount="100000")
    services.refresh_unrecorded(USER)
    db.session.refresh(task)
    assert task.task_status == services.STATUS_UNRECORDED

    item = db.session.get(services.ExpensePlanItem, task.plan_item_id)
    services.update_plan_item(
        USER,
        item.plan_item_id,
        {
            "title": item.title,
            "planned_amount": "150000",
            "amount_source": item.amount_source,
            "priority": "P0",
            "schedule_tag": item.schedule_tag,
            "specific_date": item.specific_date.isoformat(),
            "is_active": "1",
        },
    )
    db.session.refresh(task)
    assert task.planned_amount == 100000
    assert task.priority == "P1"
    assert task.task_status == services.STATUS_UNRECORDED


def test_plan_amount_change_skips_pending_task_past_deadline(app):
    task = _create_and_generate(date(2020, 1, 10), amount="100000")
    item = db.session.get(services.ExpensePlanItem, task.plan_item_id)
    services.update_plan_item(
        USER,
        item.plan_item_id,
        {
            "title": item.title,
            "planned_amount": "150000",
            "amount_source": item.amount_source,
            "priority": "P0",
            "schedule_tag": item.schedule_tag,
            "specific_date": item.specific_date.isoformat(),
            "is_active": "1",
        },
    )
    db.session.refresh(task)
    assert task.planned_amount == 100000
    assert task.priority == "P1"
    # The page-level refresh is what normally marks this task UNRECORDED.
    assert task.task_status == services.STATUS_PENDING
    services.refresh_unrecorded(USER)
    db.session.refresh(task)
    assert task.task_status == services.STATUS_UNRECORDED
