"""Authorized persistence for budget setup, generated plans and confirmation."""

from contextlib import contextmanager
import hashlib
import json
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAllocation, BudgetExpense, BudgetMonth,
    BudgetPlan, ExpenseCategory,
)
from app.modules.budgets.rules import BudgetError, ExpenseInput, generate_plans, money, validate_allocations
from app.modules.budgets.suggestions import SUGGESTED_EXPENSES
from app.modules.budgets.ai_service import recommend_weights


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


def get_confirmed_allocations(user_id, month_id):
    """Expense handoff: authorized monthly allocations, excluding all drafts.

    Amounts are monthly totals, not per-task amounts. This read-only function
    does not generate schedules or modify confirmed allocations.
    """
    month = get_month(user_id, month_id)
    plan_id = db.session.scalar(db.select(BudgetPlan.id).where(
        BudgetPlan.budget_month_id == month.id, BudgetPlan.status == "CONFIRMED",
    ))
    if plan_id is None:
        return []
    plan = get_plan(user_id, month.id, plan_id)
    return sorted(plan.allocations, key=lambda allocation: (allocation.budget_expense.expense_name, allocation.id))


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
        expense = _save_expense(month, data, expense_id=expense_id)
    return expense


def _save_expense(month, data, *, expense_id=None):
    """Shared validation/write path; caller owns the locked month transaction."""
    user_id = month.user_id
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
    # Keep explicit category choices for F03 and the shared KAN-19 model.
    # Inline custom expenses may omit category information entirely; for those
    # new entries the expense name is a safe fallback, not an override.
    category_id = data.get("category_id")
    category_name = str(data.get("category_name") or "").strip()
    if category_id or category_name:
        category = _category(user_id, {
            "category_id": category_id,
            "category_name": category_name,
        })
    elif expense is not None:
        # Editing the amount/frequency must not silently reclassify an expense.
        category = expense.category
    else:
        category = _category(user_id, {"category_name": name})
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


def apply_suggested_expenses(user_id, month_id, selected_keys, values=None):
    """Atomically add selected hints through the normal Budget write path.

    Idempotency is semantic: an existing case-insensitive expense name in this
    month always wins, including user edits and explicit zero/unknown values.
    No submitted amount, priority or identity can overwrite an existing row.
    """
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        known = {item.key: item for item in SUGGESTED_EXPENSES}
        if (not isinstance(selected_keys, (list, tuple)) or not selected_keys
                or any(not isinstance(key, str) or key not in known for key in selected_keys)
                or len(set(selected_keys)) != len(selected_keys)):
            raise BudgetError("Select at least one valid suggested expense, once each.")
        if values is not None and not isinstance(values, dict):
            raise BudgetError("Invalid suggested expense values.")
        values = values or {}
        existing = {e.expense_name.strip().casefold() for e in list_expenses(user_id, month.id)}
        created = []
        for key in selected_keys:
            suggestion = known[key]
            if suggestion.name.casefold() in existing:
                continue
            fields = values.get(key, {})
            if not isinstance(fields, dict):
                raise BudgetError("Invalid suggested expense fields.")
            created.append(_save_expense(month, {
                "expense_name": suggestion.name, "priority": suggestion.priority,
                "category_name": suggestion.category,
                "estimated_amount": fields.get("estimated_amount"),
                "minimum_amount": fields.get("minimum_amount"),
                "allocation_frequency": fields.get("allocation_frequency", suggestion.frequency),
                "due_day": fields.get("due_day"),
            }))
            existing.add(suggestion.name.casefold())
    return created


def plan_breakdown(user_id, month_id, plan_id):
    """Compute display totals from saved allocations, never mutable month funds."""
    plan = get_plan(user_id, month_id, plan_id)
    totals = {"P0": 0, "P1": 0, "P2": 0, "Savings": plan.planned_savings}
    for allocation in plan.allocations:
        totals[allocation.budget_expense.priority] += allocation.allocated_amount
    return totals


def _inputs(user_id, month_id):
    expenses = list_expenses(user_id, month_id)
    return [ExpenseInput(e.id, e.expense_name, e.priority, e.estimated_amount, e.minimum_amount) for e in expenses]


def generate_budget_plans(user_id, month_id, *, use_ai=False, return_source=False, return_details=False):
    # Optional network call takes place BEFORE the DB write lock. Recheck the
    # inputs under the lock so stale AI weights cannot affect a changed setup.
    weights = {}
    source = "Rule-based fallback"
    explanations = {}
    snapshot = None
    if use_ai:
        month_before = get_month(user_id, month_id)
        _assert_editable(month_before)
        inputs_before = _inputs(user_id, month_before.id)
        from app.modules.budgets.rules import validate_setup
        validate_setup(month_before.available_vnd, inputs_before)
        snapshot = (month_before.available_vnd, tuple(inputs_before))
        weights, source, explanations = recommend_weights(inputs_before, include_explanations=True)
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        current_inputs = _inputs(user_id, month.id)
        if snapshot is not None and snapshot != (month.available_vnd, tuple(current_inputs)):
            raise BudgetConflict("Budget setup changed while AI suggestions were prepared. Reload and generate again.")
        proposals = generate_plans(month.available_vnd, current_inputs, weights_by_style=weights)
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
    return (plans, source, explanations) if return_details else (plans, source) if return_source else plans



def generate_budget_plans_from_setup(user_id, month_id, selected_keys, suggested_values,
                                     custom_expenses, *, use_ai=False):
    """Save suggested/custom expenses AND three drafts in one DB transaction.

    An invalid custom row, insufficient funds or a failing generation rolls back
    everything, including any new ExpenseCategory and replaced draft. No
    separate form POST can discard the unsaved inputs on the Budget page.
    """
    known = {entry.key: entry for entry in SUGGESTED_EXPENSES}
    if (not isinstance(selected_keys, (list, tuple)) or
            len(selected_keys) != len(set(selected_keys)) or
            any(key not in known for key in selected_keys)):
        raise BudgetError("Invalid suggested expense selection.")
    if not isinstance(suggested_values, dict) or not isinstance(custom_expenses, list):
        raise BudgetError("Invalid expense input.")
    if len(custom_expenses) > 40:
        raise BudgetError("Too many additional expenses (maximum 40).")
    source = "Rule-based fallback"
    explanations = {}
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        existing = {e.expense_name.strip().casefold() for e in list_expenses(user_id, month.id)}
        for key in selected_keys:
            suggestion = known[key]
            if suggestion.name.casefold() in existing:
                continue
            values = suggested_values.get(key, {})
            if not isinstance(values, dict):
                raise BudgetError("Invalid suggested expense details.")
            _save_expense(month, {
                "expense_name": suggestion.name,
                "priority": suggestion.priority,
                "category_name": suggestion.category,
                "allocation_frequency": values.get("allocation_frequency", suggestion.frequency),
                "estimated_amount": values.get("estimated_amount"),
                "minimum_amount": values.get("minimum_amount"),
                "due_day": values.get("due_day"),
                "is_recurring": values.get("is_recurring", False),
            })
            existing.add(suggestion.name.casefold())
        for data in custom_expenses:
            if not isinstance(data, dict):
                raise BudgetError("Invalid additional expense.")
            _save_expense(month, data)
        current_inputs = _inputs(user_id, month.id)
        # KAN-11's Gemini hint only supplies relative weights. All financial
        # calculations remain inside generate_plans/validate_allocations.
        weights = {}
        if use_ai:
            from app.modules.budgets.rules import validate_setup
            validate_setup(month.available_vnd, current_inputs)
            weights, source, explanations = recommend_weights(
                current_inputs, include_explanations=True)
        proposals = generate_plans(month.available_vnd, current_inputs,
                                   weights_by_style=weights)
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
                    plan_id=plan.id, budget_expense_id=expense_id,
                    allocated_amount=amount,
                ))
            plans.append(plan)
        db.session.flush()
    return plans, source, explanations

def plan_draft_fingerprint(plan):
    """Stable, non-secret version token for an editable saved plan.

    KAN-19 does not need a version column. This hashes one saved plan's
    allocation content; ``customization_fingerprint`` combines the selected
    source, current MANUAL draft, and monthly funds for a safe form token.
    """
    content = {
        "id": str(plan.id),
        "status": plan.status,
        "type": plan.plan_type,
        "savings": plan.planned_savings,
        "allocations": sorted(
            [(str(a.budget_expense_id), a.allocated_amount) for a in plan.allocations],
            key=lambda part: part[0],
        ),
    }
    payload = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()



def customization_fingerprint(user_id, month_id, source_plan_id):
    """Optimistic lock token for the *whole* editable manual-plan workflow.

    A generated source plan stays unchanged when a MANUAL draft is saved.
    Consequently fingerprinting the source alone cannot detect two browser tabs
    overwriting the same MANUAL draft. Include the latest MANUAL candidate,
    current available funds and source before accepting a save.

    The caller must check this value again inside ``_write_month``. Tokens are
    not authentication credentials: month ownership/CSRF are verified separately.
    """
    month = get_month(user_id, month_id)
    source = get_plan(user_id, month.id, source_plan_id)
    manual_plans = list(db.session.scalars(db.select(BudgetPlan).where(
        BudgetPlan.budget_month_id == month.id,
        BudgetPlan.plan_type == "MANUAL", BudgetPlan.status == "GENERATED",
    )))
    if len(manual_plans) > 1:
        raise BudgetConflict("Multiple manual drafts exist. Resolve the duplicate before saving.")
    payload = {
        "month": str(month.id),
        "funds": month.available_vnd,
        "source": plan_draft_fingerprint(source),
        "manual": plan_draft_fingerprint(manual_plans[0]) if manual_plans else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def save_manual_plan(user_id, month_id, source_plan_id, editable_amounts, savings=None, *, expected_fingerprint, auto_savings=False):
    """Save a separate MANUAL candidate; keep all three generated strategies.

    The caller supplies exactly one P1/P2 amount per included expense; P0 is
    taken solely from the saved source plan. Existing KAN-19 allocations and
    confirmation rules remain authoritative. No scheduled/confirmed data edits.
    """
    if not isinstance(editable_amounts, dict):
        raise BudgetError("Invalid allocation changes.")
    with _write_month(user_id, month_id) as month:
        _assert_editable(month)
        source = get_plan(user_id, month.id, source_plan_id)
        if source.status != "GENERATED" or source.plan_type not in {"SAVING", "BALANCED", "LIFESTYLE", "MANUAL"}:
            raise BudgetConflict("Only a generated budget option can be customized.")
        # Require the token on *every* write; an omitted hidden field must not
        # bypass concurrency protection. Recheck under the owned-month lock.
        if (not isinstance(expected_fingerprint, str) or
                len(expected_fingerprint) != 64 or
                customization_fingerprint(user_id, month.id, source.id) != expected_fingerprint):
            raise BudgetConflict("The plan was changed in another tab. Reload before customizing.")
        inputs = _inputs(user_id, month.id)
        original = list(source.allocations)
        validate_allocations(month.available_vnd, inputs,
                             [(a.budget_expense_id, a.allocated_amount) for a in original],
                             source.planned_savings)
        if any(a.tasks for a in original):
            raise BudgetConflict("A scheduled plan cannot be customized.")
        editable = {str(a.budget_expense_id) for a in original
                    if a.budget_expense.priority in ("P1", "P2")}
        if set(editable_amounts) != editable:
            raise BudgetError("Submit exactly one amount for each P1 and P2 expense.")
        values = {str(key): money(value, "Allocation", positive=True)
                  for key, value in editable_amounts.items()}
        allocations = [(a.budget_expense_id,
                        a.allocated_amount if a.budget_expense.priority == "P0"
                        else values[str(a.budget_expense_id)]) for a in original]
        if auto_savings:
            # The posted UI does not control savings. Derive the only balancing
            # value under the month lock, so browser edits cannot bypass rules.
            saved_savings = month.available_vnd - sum(amount for _, amount in allocations)
            if saved_savings < 0:
                raise BudgetError("Allocations exceed available funds.")
        else:
            saved_savings = money(savings, "Planned savings")
        validate_allocations(month.available_vnd, inputs, allocations, saved_savings)

        manual_candidates = list(db.session.scalars(db.select(BudgetPlan).where(
            BudgetPlan.budget_month_id == month.id, BudgetPlan.plan_type == "MANUAL",
            BudgetPlan.status == "GENERATED",
        )))
        if len(manual_candidates) > 1:
            raise BudgetConflict("Multiple manual drafts exist. Resolve the duplicate before saving.")
        manual = manual_candidates[0] if manual_candidates else None
        if manual is None:
            manual = BudgetPlan(budget_month_id=month.id, plan_type="MANUAL",
                                status="GENERATED", planned_savings=saved_savings)
            db.session.add(manual)
            db.session.flush()
        else:
            if any(a.tasks for a in manual.allocations):
                raise BudgetConflict("A scheduled customized plan cannot be overwritten.")
            manual.planned_savings = saved_savings
        by_expense = {item.budget_expense_id: item for item in manual.allocations}
        if len(by_expense) != len(manual.allocations):
            raise BudgetError("Stored customized allocations are inconsistent.")
        expected = {exp_id for exp_id, _ in allocations}
        if set(by_expense) - expected:
            raise BudgetConflict("Customized plan contains outdated expenses. Regenerate plans.")
        for expense_id, amount in allocations:
            if expense_id in by_expense:
                by_expense[expense_id].allocated_amount = amount
            else:
                db.session.add(BudgetAllocation(
                    plan_id=manual.id, budget_expense_id=expense_id, allocated_amount=amount,
                ))
        db.session.flush()
    return manual


def confirm_plan(user_id, month_id, plan_id, *, expected_fingerprint=None):
    with _write_month(user_id, month_id) as month:
        plan = get_plan(user_id, month.id, plan_id)
        if plan.status == "CONFIRMED":
            return plan  # A retry never rewrites the original confirmed snapshot.
        _assert_editable(month)
        if plan.status != "GENERATED":
            raise BudgetConflict("Only a generated plan can be confirmed.")
        # A MANUAL draft can be edited in a second tab while its confirmation
        # page stays open. The route requires a token only for MANUAL plans;
        # generated-strategy confirmation retains its existing API contract.
        if (plan.plan_type == "MANUAL" and expected_fingerprint is not None and
                plan_draft_fingerprint(plan) != expected_fingerprint):
            raise BudgetConflict("The manual plan changed in another tab. Review the latest amounts before confirming.")
        validate_allocations(
            month.available_vnd, _inputs(user_id, month.id),
            [(a.budget_expense_id, a.allocated_amount) for a in plan.allocations],
            plan.planned_savings,
        )
        if any(a.tasks for a in plan.allocations):
            raise BudgetConflict("Tasks must be scheduled after confirmation.")
        plan.status = "CONFIRMED"
    return plan
