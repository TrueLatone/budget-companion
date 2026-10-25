from datetime import date

import pytest

from app.extensions import db
from app.modules.expenses import services


USER = "test-user"


def _seed_october():
    services.create_plan_item(
        USER,
        {
            "title": "Tiền ăn",
            "planned_amount": "100000",
            "amount_source": "USER_ENTERED",
            "priority": "P1",
            "schedule_tag": "WEEKLY",
            "day_of_week": "1",
            "is_active": "1",
        },
    )
    services.generate_tasks(USER, date(2026, 10, 1), date(2026, 10, 31))
    tasks = services.list_tasks(USER, date(2026, 10, 1), date(2026, 10, 31))
    assert len(tasks) == 4

    services.checkin_task(USER, tasks[0].task_id, action="planned")
    services.checkin_task(
        USER,
        tasks[1].task_id,
        action="actual",
        amount_raw="120000",
        expense_date_raw="2026-10-12",
    )
    services.checkin_task(USER, tasks[2].task_id, action="no_expense")

    services.create_unexpected_record(
        USER,
        {
            "title": "Sửa xe",
            "amount": "50000",
            "expense_date": "2026-10-10",
            "category": "Di chuyển",
            "note": "Bất ngờ",
        },
    )
    services.create_unexpected_record(
        USER,
        {
            "title": "Ngoài kỳ",
            "amount": "999000",
            "expense_date": "2026-09-30",
        },
    )
    return tasks


def test_month_summary_counts_plan_actual_and_statuses(app):
    _seed_october()
    period = services.resolve_period("month", "2026-10-15")
    summary = services.build_summary(USER, period)

    assert summary["plan_total"] == 400000
    assert summary["actual_total"] == 270000
    assert summary["difference"] == 130000
    assert summary["counts"] == {
        "pending": 1,
        "unrecorded": 0,
        "no_expense": 1,
        "within": 1,
        "over": 1,
    }
    assert summary["unconfirmed"] == 1
    assert summary["confirmed"] == 3
    assert len(summary["unexpected_records"]) == 1
    assert summary["unexpected_records"][0].title == "Sửa xe"
    assert len(summary["planned_by_task"]) == 2


def test_day_and_week_views_use_correct_boundaries(app):
    _seed_october()

    day = services.build_summary(
        USER, services.resolve_period("day", "2026-10-05")
    )
    assert day["plan_total"] == 100000
    assert day["actual_total"] == 100000

    week = services.build_summary(
        USER, services.resolve_period("week", "2026-10-07")
    )
    assert week["period"].start == date(2026, 10, 5)
    assert week["period"].end == date(2026, 10, 11)
    assert week["plan_total"] == 100000
    assert week["actual_total"] == 150000


def test_pending_tasks_are_not_counted_as_zero_spending(app):
    services.create_plan_item(
        USER,
        {
            "title": "Chưa check-in",
            "planned_amount": "250000",
            "amount_source": "USER_ENTERED",
            "priority": "P1",
            "schedule_tag": "DATE",
            "specific_date": "2026-11-01",
            "is_active": "1",
        },
    )
    services.generate_tasks(USER, date(2026, 11, 1), date(2026, 11, 1))

    summary = services.build_summary(
        USER, services.resolve_period("month", "2026-11-15")
    )
    assert summary["plan_total"] == 250000
    assert summary["actual_total"] == 0
    assert summary["unconfirmed"] == 1


def test_record_outside_period_is_not_counted(app):
    _seed_october()
    summary = services.build_summary(
        USER, services.resolve_period("month", "2026-10-15")
    )
    assert all(
        record.expense_date.month == 10 for record in summary["records"]
    )
    assert all(
        record.title != "Ngoài kỳ" for record in summary["records"]
    )


def test_record_edit_and_delete_update_task_status(app):
    _seed_october()

    tasks = services.list_tasks(USER, date(2026, 10, 1), date(2026, 10, 31))
    record = services.list_records(USER, date(2026, 10, 12), date(2026, 10, 12))[0]
    services.update_record(
        USER,
        record.record_id,
        {
            "amount": "90000",
            "expense_date": "2026-10-12",
            "category": "Ăn uống",
            "note": "Giảm giá",
        },
    )
    db.session.refresh(tasks[1])
    assert tasks[1].task_status == services.STATUS_WITHIN_BUDGET

    services.delete_record(USER, record.record_id)
    db.session.refresh(tasks[1])
    assert tasks[1].task_status == services.STATUS_UNRECORDED
    assert tasks[1].checked_at is None


def test_demo_queries_do_not_mix_official_rows(app):
    from app.models.expense_planning import AssignedExpenseTask, ExpensePlanItem, ExpenseRecord
    from app.modules.expenses.idgen import new_id

    item = ExpensePlanItem(
        plan_item_id=new_id(),
        user_id=USER,
        title="Dữ liệu chính thức",
        amount_source="USER_ENTERED",
        planned_amount=500000,
        priority="P0",
        schedule_tag="DATE",
        specific_date=date(2099, 2, 1),
        is_active=True,
        is_demo=False,
    )
    task = AssignedExpenseTask(
        task_id=new_id(),
        plan_item_id=item.plan_item_id,
        user_id=USER,
        assigned_date=date(2099, 2, 1),
        planned_amount=500000,
        priority="P0",
        checkin_deadline_at=services.deadline_for(date(2099, 2, 1)),
        task_status=services.STATUS_PENDING,
        is_demo=False,
    )
    record = ExpenseRecord(
        record_id=new_id(),
        user_id=USER,
        task_id=task.task_id,
        record_type=services.RECORD_PLANNED,
        amount=500000,
        expense_date=date(2099, 2, 1),
        actual_amount_source="USER_ENTERED",
        is_demo=False,
    )
    db.session.add_all([item, task, record])
    db.session.commit()

    summary = services.build_summary(
        USER, services.resolve_period("month", "2099-02-01")
    )
    assert summary["tasks"] == []
    assert summary["records"] == []
    assert summary["plan_total"] == 0
    assert summary["actual_total"] == 0
    assert len(services.list_tasks(
        USER, date(2099, 2, 1), date(2099, 2, 1), demo_only=False
    )) == 1

    with pytest.raises(services.NotFoundError):
        services.set_plan_item_active(USER, item.plan_item_id, False)
