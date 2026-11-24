from datetime import date, datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (BudgetMonth, BudgetPlan, BudgetAllocation, BudgetExpense, ExpenseRecord,
                        AssignedExpenseTask, BudgetAdjustment, BudgetAdjustmentDetail, Recommendation, MonthlyReview)
from app.modules.budgets.rules import check_unit
from app.modules.budgets.services import _write_month, BudgetConflict


class DuplicateBudgetMonthError(ValueError):
    """Raised when a user already has the requested calendar month."""


def parse_month(value):
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def list_budget_months(user_id):
    statement = (
        db.select(BudgetMonth)
        .where(BudgetMonth.user_id == user_id)
        .order_by(BudgetMonth.month_start.desc())
    )
    return list(db.session.scalars(statement))


def get_budget_month(user_id, budget_month_id):
    return db.session.scalar(
        db.select(BudgetMonth).where(
            BudgetMonth.id == budget_month_id,
            BudgetMonth.user_id == user_id,
        )
    )


def create_budget_month(user_id, month, available_vnd, tracking_start_date=None, *, planning_unit=1000):
    month_start = parse_month(month)
    if tracking_start_date is None:
        tracking_start_date = month_start
    if (
        not isinstance(tracking_start_date, date)
        or isinstance(tracking_start_date, datetime)
        or tracking_start_date.replace(day=1) != month_start
    ):
        raise ValueError("Tracking start date must be a date within the budget month.")
    if (
        not isinstance(available_vnd, int)
        or isinstance(available_vnd, bool)
        or not 0 <= available_vnd <= 9_223_372_036_854_775_807
    ):
        raise ValueError("Available funds must be a nonnegative integer VND amount.")
    if planning_unit not in (1, 1000):
        raise ValueError("Unsupported planning unit.")
    check_unit(available_vnd, planning_unit)
    budget_month = BudgetMonth(
        user_id=user_id,
        month_start=month_start,
        planning_unit=planning_unit,
        tracking_start_date=tracking_start_date,
        available_vnd=available_vnd,
    )
    db.session.add(budget_month)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if get_budget_month_for_calendar_month(user_id, month_start) is not None:
            raise DuplicateBudgetMonthError from exc
        raise

    return budget_month


def get_budget_month_for_calendar_month(user_id, month_start):
    return db.session.scalar(
        db.select(BudgetMonth).where(
            BudgetMonth.user_id == user_id,
            BudgetMonth.month_start == month_start,
        )
    )


def update_available_vnd(budget_month, available_vnd):
    with _write_month(budget_month.user_id, budget_month.id) as month:
        if month.plans:
            raise BudgetConflict("Funds are locked after generating plans.")
        check_unit(available_vnd, month.planning_unit)
        month.available_vnd = available_vnd
    return budget_month


def delete_month(user_id, month_id):
    with _write_month(user_id, month_id) as month:
        plans = db.select(BudgetPlan.id).where(BudgetPlan.budget_month_id == month.id)
        allocations = db.select(BudgetAllocation.id).where(BudgetAllocation.plan_id.in_(plans))
        tasks = db.select(AssignedExpenseTask.id).where(AssignedExpenseTask.allocation_id.in_(allocations))
        recs = db.select(Recommendation.id).where(Recommendation.budget_month_id == month.id)
        adjustments = db.select(BudgetAdjustment.id).where(BudgetAdjustment.recommendation_id.in_(recs))
        for model, condition in (
            (BudgetAdjustmentDetail, BudgetAdjustmentDetail.adjustment_id.in_(adjustments)),
            (BudgetAdjustment, BudgetAdjustment.recommendation_id.in_(recs)),
            (Recommendation, Recommendation.budget_month_id == month.id),
            (MonthlyReview, MonthlyReview.budget_month_id == month.id),
            (ExpenseRecord, ExpenseRecord.budget_month_id == month.id),
            (AssignedExpenseTask, AssignedExpenseTask.id.in_(tasks)),
            (BudgetAllocation, BudgetAllocation.plan_id.in_(plans)),
            (BudgetPlan, BudgetPlan.budget_month_id == month.id),
            (BudgetExpense, BudgetExpense.budget_month_id == month.id),
        ):
            db.session.execute(db.delete(model).where(condition).execution_options(synchronize_session=False))
        db.session.delete(month)
