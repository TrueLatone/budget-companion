"""Authorized persistence for budget setup, generated plans and confirmation."""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAllocation, BudgetExpense, BudgetMonth,
    BudgetPlan, ExpenseCategory,
)
from app.modules.budgets.rules import BudgetError, ExpenseInput, generate_plans, money, validate_allocations


class BudgetNotFound(LookupError):
    """An identifier is invalid, absent or outside the authenticated owner."""


class BudgetConflict(BudgetError):
    """The current saved state cannot be changed by this operation."""


def _uuid(value):
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise BudgetNotFound("Budget resource not found.") from None


def get_month(user_id, month_id, *, lock=False):
    statement = db.select(BudgetMonth).where(
        BudgetMonth.id == _uuid(month_id), BudgetMonth.user_id == _uuid(user_id),
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    month = db.session.scalar(statement)
    if month is None:
        raise BudgetNotFound("Budget month not found.")
    return month


@contextmanager
def _write_month(user_id, month_id):
    # Serialize setup edits and confirmation on PostgreSQL. The existing partial
    # unique index is the final guard against concurrent confirmations on SQLite.
    try:
        yield get_month(user_id, month_id, lock=True)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise BudgetConflict("The budget changed concurrently or violates a saved constraint. Reload and try again.") from exc
    except Exception:
        db.session.rollback()
        raise


def list_categories(user_id):
    return list(db.session.scalars(db.select(ExpenseCategory).where(
        db.or_(ExpenseCategory.user_id == _uuid(user_id), ExpenseCategory.user_id.is_(None)),
    ).order_by(ExpenseCategory.category_name, ExpenseCategory.id)))


def list_expenses(user_id, month_id):
    month = get_month(user_id, month_id)
    expenses = list(db.session.scalars(db.select(BudgetExpense).where(
        BudgetExpense.budget_month_id == month.id,
    ).order_by(BudgetExpense.expense_name, BudgetExpense.id)))
    _check_categories(month.user_id, expenses)
    return expenses


def list_plans(user_id, month_id):
    month = get_month(user_id, month_id)
    return list(db.session.scalars(db.select(BudgetPlan).where(
        BudgetPlan.budget_month_id == month.id,
    ).order_by(BudgetPlan.plan_type, BudgetPlan.id)))


def get_plan(user_id, month_id, plan_id):
    month = get_month(user_id, month_id)
    plan = db.session.scalar(db.select(BudgetPlan).where(
        BudgetPlan.id == _uuid(plan_id), BudgetPlan.budget_month_id == month.id,
    ))
    if plan is None:
        raise BudgetNotFound("Budget plan not found.")
    expenses = [allocation.budget_expense for allocation in plan.allocations]
    if any(expense is None or expense.budget_month_id != month.id for expense in expenses):
        raise BudgetError("The saved plan references an expense outside its month.")
    _check_categories(month.user_id, expenses)
    return plan


def get_expense(user_id, month_id, expense_id):
    month = get_month(user_id, month_id)
    expense = db.session.scalar(db.select(BudgetExpense).where(
        BudgetExpense.id == _uuid(expense_id), BudgetExpense.budget_month_id == month.id,
    ))
    if expense is None:
        raise BudgetNotFound("Budget expense not found.")
    _check_categories(month.user_id, [expense])
    return expense


def _check_categories(user_id, expenses):
    for expense in expenses:
        if expense.category is None or expense.category.user_id not in (None, user_id):
            raise BudgetError("An expense references an unauthorized category.")


def _assert_editable(month):
    if db.session.scalar(db.select(BudgetPlan.id).where(
        BudgetPlan.budget_month_id == month.id, BudgetPlan.status == "CONFIRMED",
    )) is not None:
        raise BudgetConflict("This month's confirmed plan and expense setup are locked.")


def _discard_drafts(month):
    plans = list(db.session.scalars(db.select(BudgetPlan).where(
        BudgetPlan.budget_month_id == month.id, BudgetPlan.status == "GENERATED",
    )))
    for plan in plans:
        for allocation in plan.allocations:
            if db.session.scalar(db.select(AssignedExpenseTask.id).where(
                AssignedExpenseTask.allocation_id == allocation.id,
            ).limit(1)) is not None:
                raise BudgetConflict("A draft plan has scheduled tasks; it cannot be replaced.")
            db.session.delete(allocation)
    db.session.flush()
    for plan in plans:
        db.session.delete(plan)
    db.session.flush()


def _category(user_id, data):
    category_id = data.get("category_id")
    name = str(data.get("category_name") or "").strip()
    if category_id and name:
        raise BudgetError("Choose an existing category or enter a new category, not both.")
    if category_id:
        category = db.session.scalar(db.select(ExpenseCategory).where(
            ExpenseCategory.id == _uuid(category_id),
            db.or_(ExpenseCategory.user_id == user_id, ExpenseCategory.user_id.is_(None)),
        ))
        if category is None:
            raise BudgetNotFound("Category not found.")
        return category
    if not name or len(name) > 100:
        raise BudgetError("Enter a category name of 1 to 100 characters.")
    category = db.session.scalar(db.select(ExpenseCategory).where(
        ExpenseCategory.user_id == user_id,
        db.func.lower(db.func.trim(ExpenseCategory.category_name)) == name.lower(),
    ))
    if category is None:
        category = ExpenseCategory(user_id=user_id, category_name=name)
        db.session.add(category)
        db.session.flush()
    return category


def save_expense(user_id, month_id, data, *, expense_id=None):
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        expense = get_expense(user_id, month.id, expense_id) if expense_id else None
        name = str(data.get("expense_name") or "").strip()
        priority = data.get("priority")
        frequency = data.get("allocation_frequency")
        if not name or len(name) > 120:
            raise BudgetError("Enter an expense name of 1 to 120 characters.")
        if priority not in {"P0", "P1", "P2"} or frequency not in {"DAILY", "WEEKLY", "MONTHLY"}:
            raise BudgetError("Choose a valid priority and allocation frequency.")
        for existing in list_expenses(user_id, month.id):
            if existing.id != (expense.id if expense else None) and existing.expense_name.casefold() == name.casefold():
                raise BudgetError("Expense names must be unique within the month.")
        estimate = money(data.get("estimated_amount"), "Estimated amount", optional=True)
        minimum = money(data.get("minimum_amount"), "Minimum amount", optional=True, positive=True)
        if minimum is not None and priority != "P1":
            raise BudgetError("Only P1 expenses may specify a minimum.")
        due_day = data.get("due_day")
        if due_day in (None, ""):
            due_day = None
        else:
            try:
                due_day = money(due_day, "Due day", positive=True)
            except BudgetError:
                raise BudgetError("Due day must be an integer from 1 to 31.") from None
            if due_day > 31 or frequency != "MONTHLY":
                raise BudgetError("Due day must be 1 to 31 and only applies to monthly expenses.")
        recurring = data.get("is_recurring", False)
        if type(recurring) is not bool:
            raise BudgetError("Recurring must be a boolean.")
        category = _category(month.user_id, data)
        _discard_drafts(month)
        if expense is None:
            expense = BudgetExpense(budget_month_id=month.id)
            db.session.add(expense)
        expense.expense_name = name
        expense.category_id = category.id
        expense.priority = priority
        expense.estimated_amount = estimate
        expense.minimum_amount = minimum
        expense.allocation_frequency = frequency
        expense.is_recurring = recurring
        expense.due_day = due_day
    return expense


def delete_expense(user_id, month_id, expense_id):
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        expense = get_expense(user_id, month.id, expense_id)
        _discard_drafts(month)
        db.session.delete(expense)


def _inputs(user_id, month_id):
    expenses = list_expenses(user_id, month_id)
    return [ExpenseInput(e.id, e.expense_name, e.priority, e.estimated_amount, e.minimum_amount) for e in expenses]


def generate_budget_plans(user_id, month_id):
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        proposals = generate_plans(month.available_vnd, _inputs(user_id, month.id))
        _discard_drafts(month)
        plans = []
        for proposal in proposals:
            plan = BudgetPlan(
                budget_month_id=month.id, plan_type=proposal["plan_type"],
                planned_savings=proposal["planned_savings"], status="GENERATED",
            )
            db.session.add(plan)
            db.session.flush()
            for expense_id, amount in proposal["allocations"]:
                db.session.add(BudgetAllocation(
                    plan_id=plan.id, budget_expense_id=expense_id, allocated_amount=amount,
                ))
            plans.append(plan)
    return plans


def confirm_plan(user_id, month_id, plan_id):
    with _write_month(user_id, month_id) as month:
        plan = get_plan(user_id, month.id, plan_id)
        if plan.status == "CONFIRMED":
            return plan  # A retry never rewrites the original confirmed snapshot.
        _assert_editable(month)
        if plan.status != "GENERATED":
            raise BudgetConflict("Only a generated plan can be confirmed.")
        validate_allocations(
            month.available_vnd, _inputs(user_id, month.id),
            [(a.budget_expense_id, a.allocated_amount) for a in plan.allocations],
            plan.planned_savings,
        )
        if any(a.tasks for a in plan.allocations):
            raise BudgetConflict("Tasks must be scheduled after confirmation.")
        plan.status = "CONFIRMED"
    return plan
