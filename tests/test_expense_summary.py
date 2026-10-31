from datetime import date

import pytest

from app.extensions import db
from app.models import (
    AssignedExpenseTask,
    BudgetAllocation,
    BudgetExpense,
    BudgetMonth,
    BudgetPlan,
    ExpenseCategory,
    ExpenseRecord,
    User,
)
from app.modules.expenses import services

USER = services.DEMO_USER_ID


def _seed_canonical_task(
    user_id: str,
    assigned_date: date,
    amount: int = 100000,
    title: str = "Tiền ăn",
    schedule_tag: str = "WEEKLY",
    payment_due_date: date | None = None,
    period_end: date | None = None,
    task_status: str = "PENDING",
) -> AssignedExpenseTask:
    user_uuid = services.to_uuid(user_id)
    user = db.session.get(User, user_uuid)
    if not user:
        user = User(
            id=user_uuid,
            email=f"{user_id}@example.com",
            password_hash="fake-hash",
        )
        db.session.add(user)
        db.session.flush()

    month_start = date(assigned_date.year, assigned_date.month, 1)
    month = BudgetMonth.query.filter_by(
        user_id=user_uuid, month_start=month_start
    ).first()
    if not month:
        month = BudgetMonth(
            user_id=user_uuid,
            month_start=month_start,
            tracking_start_date=month_start,
            available_vnd=50000000,
        )
        db.session.add(month)
        db.session.flush()

    category = ExpenseCategory.query.filter_by(
        user_id=user_uuid, category_name="Ăn uống"
    ).first()
    if not category:
        category = ExpenseCategory(user_id=user_uuid, category_name="Ăn uống")
        db.session.add(category)
        db.session.flush()

    alloc_freq = "DAILY"
    is_recurring = True
    due_day = None
    if schedule_tag == "DAILY":
        alloc_freq = "DAILY"
    elif schedule_tag == "WEEKLY":
        alloc_freq = "WEEKLY"
    elif schedule_tag == "MONTHLY":
        alloc_freq = "MONTHLY"
    elif schedule_tag == "DAY_OF_MONTH":
        alloc_freq = "MONTHLY"
        due_day = 15
    elif schedule_tag == "DATE":
        alloc_freq = "MONTHLY"
        is_recurring = False

    expense = BudgetExpense.query.filter_by(
        budget_month_id=month.id, expense_name=title
    ).first()
    if not expense:
        expense = BudgetExpense(
            budget_month=month,
            category=category,
            expense_name=title,
            priority="P1",
            allocation_frequency=alloc_freq,
            is_recurring=is_recurring,
            due_day=due_day,
        )
        db.session.add(expense)
        db.session.flush()

    plan = BudgetPlan.query.filter_by(
        budget_month_id=month.id, status="CONFIRMED"
    ).first()
    if not plan:
        plan = BudgetPlan(
            budget_month=month, plan_type="BALANCED", status="CONFIRMED"
        )
        db.session.add(plan)
        db.session.flush()

    allocation = BudgetAllocation.query.filter_by(
        plan_id=plan.id, budget_expense_id=expense.id
    ).first()
    if not allocation:
        allocation = BudgetAllocation(
            plan=plan, budget_expense=expense, allocated_amount=amount
        )
        db.session.add(allocation)
        db.session.flush()

    task = AssignedExpenseTask(
        allocation=allocation,
        assigned_date=assigned_date,
        period_end=period_end or assigned_date,
        original_limit=amount,
        current_limit=amount,
        task_status=task_status,
        payment_due_date=payment_due_date,
    )
    db.session.add(task)
    db.session.commit()
    return task


def _seed_october():
    t1 = _seed_canonical_task(USER, date(2026, 10, 5), amount=100000, title="Tiền ăn")
    t2 = _seed_canonical_task(USER, date(2026, 10, 12), amount=100000, title="Tiền ăn")
    t3 = _seed_canonical_task(USER, date(2026, 10, 19), amount=100000, title="Tiền ăn")
    t4 = _seed_canonical_task(USER, date(2099, 10, 26), amount=100000, title="Tiền ăn")  # Future date for PENDING
    # Actually for October 2026 tests, we need assigned_date in Oct 2026:
    # To keep t4 as PENDING (not UNRECORDED), we give it a future period_end:
    t4.assigned_date = date(2026, 10, 26)
    t4.period_end = date(2099, 10, 26)
    db.session.commit()

    tasks = [t1, t2, t3, t4]

    services.checkin_task(USER, tasks[0].id, action="planned")
    services.checkin_task(
        USER,
        tasks[1].id,
        action="actual",
        amount_raw="120000",
        expense_date_raw="2026-10-12",
    )
    services.checkin_task(USER, tasks[2].id, action="no_expense")

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
    _seed_canonical_task(
        USER,
        date(2026, 11, 1),
        amount=250000,
        title="Chưa check-in",
        schedule_tag="DATE",
        period_end=date(2099, 11, 1),
    )

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
    tasks = _seed_october()

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
    assert services.get_task_status(tasks[1]) == services.STATUS_WITHIN_BUDGET

    services.delete_record(USER, record.record_id)
    db.session.refresh(tasks[1])
    assert services.get_task_status(tasks[1]) == services.STATUS_UNRECORDED
    assert tasks[1].task_status == services.STATUS_PENDING


def test_demo_queries_do_not_mix_official_rows(app):
    other_user = "00000000-0000-0000-0000-000000000002"
    _seed_canonical_task(
        other_user,
        date(2099, 2, 1),
        amount=500000,
        title="Dữ liệu chính thức",
        schedule_tag="DATE",
    )

    summary = services.build_summary(
        USER, services.resolve_period("month", "2099-02-01")
    )
    assert summary["tasks"] == []
    assert summary["records"] == []
    assert summary["plan_total"] == 0
    assert summary["actual_total"] == 0
    assert len(services.list_tasks(
        other_user, date(2099, 2, 1), date(2099, 2, 1)
    )) == 1
