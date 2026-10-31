"""KAN-11 budgeting rules adapted to UUIDs and exact integer VND arithmetic.

The prototype's strategy targets apply after P0 reservation. P1 minimums and
positive included P1/P2 allocations take precedence over those targets.
"""

from dataclasses import dataclass
from uuid import UUID


MAX_VND = 9_223_372_036_854_775_807
PLAN_RATIOS = {"SAVING": (70, 5), "BALANCED": (65, 15), "LIFESTYLE": (60, 30)}
REQUIRED_P0 = {"rent", "electricity", "water"}


class BudgetError(ValueError):
    """The expense setup or allocation violates a budgeting rule."""


@dataclass(frozen=True)
class ExpenseInput:
    id: UUID
    name: str
    priority: str
    estimated_amount: int | None
    minimum_amount: int | None


def money(value, label, *, optional=False, positive=False):
    if optional and (value is None or value == ""):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or not value.isascii() or not value.isdigit():
            raise BudgetError(f"{label} must be an integer VND amount.")
        # Reject oversized input before converting an arbitrarily long integer.
        value = value.lstrip("0") or "0"
        if len(value) > 19:
            raise BudgetError(f"{label} exceeds the VND limit.")
        value = int(value)
    if type(value) is not int or not (1 if positive else 0) <= value <= MAX_VND:
        raise BudgetError(f"{label} must be {'positive' if positive else 'nonnegative'} integer VND, at most {MAX_VND}.")
    return value


def validate_setup(funds, expenses):
    money(funds, "Available funds")
    names = [expense.name.strip().casefold() for expense in expenses]
    if len(set(names)) != len(names):
        raise BudgetError("Expense names must be unique within the month.")
    present = {e.name.strip().casefold() for e in expenses if e.priority == "P0"}
    missing = REQUIRED_P0 - present
    if missing:
        raise BudgetError("Required P0 expenses are missing: " + ", ".join(sorted(missing)) + ".")
    for expense in expenses:
        if expense.priority not in {"P0", "P1", "P2"}:
            raise BudgetError("Every expense needs a P0/P1/P2 priority.")
        money(expense.estimated_amount, "Estimated amount", optional=True)
        money(expense.minimum_amount, "Minimum amount", optional=True, positive=True)
        if expense.name.strip().casefold() == "internet" and expense.priority != "P0":
            raise BudgetError("Internet, when included, must be P0.")
        if expense.priority == "P0":
            money(expense.estimated_amount, f"P0 {expense.name} amount", positive=True)
        if expense.priority != "P1" and expense.minimum_amount is not None:
            raise BudgetError("Only P1 expenses may specify a minimum.")
    required = sum(
        e.estimated_amount if e.priority == "P0" else (e.minimum_amount or 1)
        for e in expenses
    )
    if required > funds:
        raise BudgetError(f"Budget shortfall: P0, P1 minimums and positive included expenses need {required - funds} more VND.")


def split_integer(total, weights):
    """Largest-remainder split, using integer products even at BIGINT limits."""
    if not weights:
        return []
    denominator = sum(weights)
    pieces = [total * weight // denominator for weight in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % denominator), i))
    for index in order[:total - sum(pieces)]:
        pieces[index] += 1
    return pieces


def validate_allocations(funds, expenses, allocations, savings):
    validate_setup(funds, expenses)
    money(savings, "Planned savings")
    expected = {e.id: e for e in expenses}
    seen = set()
    total = savings
    for expense_id, amount in allocations:
        if expense_id not in expected or expense_id in seen:
            raise BudgetError("Allocations must reference each expense in this month exactly once.")
        seen.add(expense_id)
        money(amount, "Allocation", positive=True)
        expense = expected[expense_id]
        if expense.priority == "P0" and amount != expense.estimated_amount:
            raise BudgetError(f"P0 {expense.name} must receive its exact required amount.")
        if expense.priority == "P1" and expense.minimum_amount is not None and amount < expense.minimum_amount:
            raise BudgetError(f"{expense.name} allocation is below its P1 minimum.")
        total += amount
    if seen != set(expected):
        raise BudgetError("Every included expense requires an allocation.")
    if total != funds:
        raise BudgetError("Allocations plus planned savings must exactly equal available funds; generate plans again.")


def generate_plans(funds, expenses):
    validate_setup(funds, expenses)
    p0 = [e for e in expenses if e.priority == "P0"]
    p1 = [e for e in expenses if e.priority == "P1"]
    p2 = [e for e in expenses if e.priority == "P2"]
    remaining = funds - sum(e.estimated_amount for e in p0)
    p1_floor = sum(e.minimum_amount or 1 for e in p1)
    p2_floor = len(p2)
    plans = []
    for plan_type, (p1_ratio, p2_ratio) in PLAN_RATIOS.items():
        p1_pool = remaining * p1_ratio // 100 if p1 else 0
        p2_pool = remaining * p2_ratio // 100 if p2 else 0
        savings = remaining - p1_pool - p2_pool
        # Reserve floors first; take discretionary surplus before savings.
        if p1_pool < p1_floor:
            needed = p1_floor - p1_pool
            transfer = min(needed, max(0, p2_pool - p2_floor))
            p2_pool -= transfer
            savings -= needed - transfer
            p1_pool = p1_floor
        if p2_pool < p2_floor:
            needed = p2_floor - p2_pool
            transfer = min(needed, max(0, p1_pool - p1_floor))
            p1_pool -= transfer
            savings -= needed - transfer
            p2_pool = p2_floor
        allocations = [(e.id, e.estimated_amount) for e in p0]
        for items, pool in ((p1, p1_pool), (p2, p2_pool)):
            bases = [e.minimum_amount or 1 for e in items]
            # Scale KAN-11 fallback weights 3 / 1.5 / 1 to integers 6 / 3 / 2.
            weights = [6 if e.name.casefold() == "food" else 3 if e.name.casefold() == "transportation" else 2 for e in items]
            extras = split_integer(pool - sum(bases), weights)
            allocations.extend((e.id, base + extra) for e, base, extra in zip(items, bases, extras))
        validate_allocations(funds, expenses, allocations, savings)
        plans.append({"plan_type": plan_type, "allocations": allocations, "planned_savings": savings})
    return plans
