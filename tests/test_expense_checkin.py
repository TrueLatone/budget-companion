from datetime import date
import uuid

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
from app.modules.expenses.validators import ValidationError

USER = "test-user"


def create_test_task(
    user_id: str,
    assigned_date: date,
    amount: int = 100000,
    title: str = "Tiền nhà",
    task_status: str = "PENDING",
    payment_due_date: date | None = None,
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
            available_vnd=10000000,
        )
        db.session.add(month)
        db.session.flush()

    category = ExpenseCategory.query.filter_by(
        user_id=user_uuid, category_name="Nhà ở"
    ).first()
    if not category:
        category = ExpenseCategory(user_id=user_uuid, category_name="Nhà ở")
        db.session.add(category)
        db.session.flush()

    expense = BudgetExpense.query.filter_by(
        budget_month_id=month.id, expense_name=title
    ).first()
    if not expense:
        expense = BudgetExpense(
            budget_month=month,
            category=category,
            expense_name=title,
            priority="P1",
            allocation_frequency="MONTHLY",
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
        period_end=assigned_date,
        original_limit=amount,
        current_limit=amount,
        task_status=task_status,
        payment_due_date=payment_due_date,
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_checkin_planned_then_actual_updates_single_record(app):
    task = create_test_task(USER, date(2099, 1, 5), amount=100000)

    services.checkin_task(USER, task.id, action="planned")
    db.session.refresh(task)
    record = services.list_records(USER, date(2099, 1, 5), date(2099, 1, 5))[0]

    assert services.get_task_status(task) == services.STATUS_WITHIN_BUDGET
    assert task.task_status == "RECORDED"
    assert record.amount == 100000
    assert record.actual_amount_source == services.RECORD_PLANNED
    assert record.title == "Tiền nhà"

    # A repeated planned check-in updates the same planned record.
    services.checkin_task(USER, task.id, action="planned")
    assert len(services.list_records(USER, date(2099, 1, 5), date(2099, 1, 5))) == 1

    services.checkin_task(
        USER,
        task.id,
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
    assert records[0].category.category_name == "Nhà ở"
    assert services.get_task_status(task) == services.STATUS_OVER_BUDGET
    assert task.task_status == "RECORDED"


def test_no_expense_rejected_when_record_exists_then_allowed_after_delete(app):
    task = create_test_task(USER, date(2099, 1, 6), amount=100000)
    services.checkin_task(USER, task.id, action="planned")
    record = services.list_records(USER, date(2099, 1, 6), date(2099, 1, 6))[0]

    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.id, action="no_expense")

    services.delete_record(USER, record.record_id)
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_PENDING
    assert task.task_status == services.STATUS_PENDING

    services.checkin_task(USER, task.id, action="no_expense")
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_NO_EXPENSE
    assert task.task_status == services.STATUS_NO_EXPENSE
    assert services.list_records(USER, date(2099, 1, 6), date(2099, 1, 6)) == []


def test_no_expense_does_not_create_zero_record(app):
    task = create_test_task(USER, date(2099, 1, 7))
    services.checkin_task(USER, task.id, action="no_expense")

    assert services.list_records(USER, date(2099, 1, 7), date(2099, 1, 7)) == []


def test_actual_requires_positive_integer(app):
    task = create_test_task(USER, date(2099, 1, 8))
    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.id, action="actual", amount_raw="0")
    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.id, action="actual", amount_raw="abc")
    with pytest.raises(ValidationError):
        services.checkin_task(USER, task.id, action="actual", amount_raw="")


def test_overdue_pending_task_becomes_unrecorded_idempotently(app):
    task = create_test_task(USER, date(2020, 1, 5))

    assert services.refresh_unrecorded(USER) == 1
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_UNRECORDED
    assert task.task_status == services.STATUS_PENDING
    assert services.refresh_unrecorded(USER) == 1


def test_limit_change_recalculates_status(app):
    task = create_test_task(USER, date(2099, 1, 9), amount=100000)
    services.checkin_task(USER, task.id, action="actual", amount_raw="120000")
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_OVER_BUDGET

    # When task limit is increased to 150000, status derives to WITHIN_BUDGET
    task.current_limit = 150000
    db.session.commit()
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_WITHIN_BUDGET


def test_payment_status_lifecycle_and_manual_update(app):
    task = create_test_task(
        USER, date(2099, 1, 10), amount=200000, payment_due_date=date(2099, 1, 15)
    )
    assert task.payment_status is None

    # Check-in records the expense; payment_status remains independent (None)
    services.checkin_task(USER, task.id, action="planned")
    db.session.refresh(task)
    assert task.payment_status is None

    # User explicitly reports payment status as PAID
    services.set_payment_status(USER, task.id, "PAID")
    db.session.refresh(task)
    assert task.payment_status == "PAID"

    # User explicitly toggles status to UNPAID
    services.set_payment_status(USER, task.id, "UNPAID")
    db.session.refresh(task)
    assert task.payment_status == "UNPAID"

    # User clears payment status
    services.set_payment_status(USER, task.id, None)
    db.session.refresh(task)
    assert task.payment_status is None


def test_multiple_planned_records_aggregate_against_current_limit(app):
    task = create_test_task(USER, date(2099, 1, 11), amount=100000)

    # First checkin
    services.checkin_task(USER, task.id, action="actual", amount_raw="40000")
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_WITHIN_BUDGET

    # Add a second planned record directly linked to this task
    month = task.allocation.plan.budget_month
    rec2 = ExpenseRecord(
        id=uuid.uuid4(),
        budget_month_id=month.id,
        task_id=task.id,
        category_id=task.allocation.budget_expense.category_id,
        amount=70000,
        expense_date=date(2099, 1, 11),
        record_type="PLANNED",
    )
    db.session.add(rec2)
    db.session.commit()

    # 40000 + 70000 = 110000 > 100000 -> OVER_BUDGET
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_OVER_BUDGET

    # When current_limit is adjusted to 120000 by budget -> WITHIN_BUDGET
    task.current_limit = 120000
    db.session.commit()
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_WITHIN_BUDGET


def test_user_ownership_isolation(app):
    task = create_test_task(USER, date(2099, 1, 12), amount=50000)
    other_user = "other-user-999"

    # Other user cannot read or check in user's task
    with pytest.raises(services.NotFoundError):
        services.checkin_task(other_user, task.id, action="planned")

    services.checkin_task(USER, task.id, action="planned")
    record = services.list_records(USER, date(2099, 1, 12), date(2099, 1, 12))[0]

    # Other user cannot edit or delete user's record
    with pytest.raises(services.NotFoundError):
        services.update_record(other_user, record.record_id, {"amount": "60000", "expense_date": "2099-01-12"})

    with pytest.raises(services.NotFoundError):
        services.delete_record(other_user, record.record_id)


def test_built_in_category_reused_and_other_user_category_isolated(app):
    user_uuid = services.to_uuid(USER)
    other_uuid = services.to_uuid("other-user-888")
    services._ensure_user(user_uuid)
    services._ensure_user(other_uuid)

    # Built-in category (user_id is None)
    builtin = ExpenseCategory(id=uuid.uuid4(), user_id=None, category_name="Y tế")
    # Category owned by other user
    other_cat = ExpenseCategory(id=uuid.uuid4(), user_id=other_uuid, category_name="Bí mật")
    db.session.add_all([builtin, other_cat])
    db.session.commit()

    # When USER references "Y tế", the built-in category is reused
    resolved_builtin = services._find_or_create_category(user_uuid, "Y tế")
    assert resolved_builtin.id == builtin.id
    assert resolved_builtin.user_id is None

    # When USER references "Bí mật", other user's category is NEVER reused;
    # a new category owned by user_uuid is created
    resolved_other = services._find_or_create_category(user_uuid, "Bí mật")
    assert resolved_other.id != other_cat.id
    assert resolved_other.user_id == user_uuid
