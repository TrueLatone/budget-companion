"""Budget Companion: predictable financial rules and calendar scheduling.

All amounts are integer VND. AI output never determines financial totals.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from math import floor, isfinite


PLAN_RATIOS = {
    "Saving": {"P1": 70, "P2": 5, "Savings": 25},
    "Balanced": {"P1": 65, "P2": 15, "Savings": 20},
    "Lifestyle": {"P1": 60, "P2": 30, "Savings": 10},
}
REQUIRED_P0 = ("rent", "electricity", "water")
VALID_PRIORITIES = {"P0", "P1", "P2"}
VALID_FREQUENCIES = {"daily", "weekly", "monthly"}
MAX_VND = 1_000_000_000_000

# Demo-only default, not a researched Vietnamese spending average.
MEAL_WEIGHTS = {"Breakfast": 30, "Lunch": 40, "Dinner": 30}


class BudgetError(ValueError):
    """Raised when user input or a proposed plan violates budgeting rules."""


def _money(value, label, *, allow_none=False):
    if allow_none and value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise BudgetError(f"{label} must be a whole number of VND.")
    try:
        amount = int(value)
    except (ValueError, TypeError):
        raise BudgetError(f"{label} must be a whole number of VND.") from None
    if isinstance(value, str) and str(amount) != value.strip():
        raise BudgetError(f"{label} must be a whole number of VND (without commas).")
    if amount < 0 or amount > MAX_VND:
        raise BudgetError(f"{label} must be between 0 and {MAX_VND:,} VND.")
    return amount


def validate_setup(data):
    """Validate initial input and return a normalized, safe dictionary."""
    if not isinstance(data, dict):
        raise BudgetError("Invalid request data.")
    month = str(data.get("month", ""))
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise BudgetError("Select a valid budget month (YYYY-MM).")
    year, month_number = map(int, month.split("-"))
    if not 2000 <= year <= 2100 or not 1 <= month_number <= 12:
        raise BudgetError("Select a valid budget month.")

    funds = _money(data.get("available_funds"), "Available funds")
    if funds <= 0:
        raise BudgetError("Available funds must be positive.")

    original_expenses = data.get("expenses")
    if not isinstance(original_expenses, list) or len(original_expenses) > 40:
        raise BudgetError("Provide up to 40 expenses.")
    expenses = []
    seen_ids = set()
    seen_names = set()
    for item in original_expenses:
        if not isinstance(item, dict):
            raise BudgetError("An expense has invalid fields.")
        expense_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        priority = str(item.get("priority", "")).strip()
        frequency = str(item.get("frequency", "")).strip().lower()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", expense_id):
            raise BudgetError("Expense IDs must contain only letters, numbers, _ or -.")
        if not name or len(name) > 60:
            raise BudgetError("Every expense needs a name (up to 60 characters).")
        if expense_id in seen_ids or name.casefold() in seen_names:
            raise BudgetError(f"Duplicate expense: {name}.")
        if priority not in VALID_PRIORITIES:
            raise BudgetError(f"Select or confirm a P0/P1/P2 priority for {name}.")
        if frequency not in VALID_FREQUENCIES:
            raise BudgetError(f"Select a valid tracking frequency for {name}.")
        seen_ids.add(expense_id)
        seen_names.add(name.casefold())

        due_day = item.get("due_day")
        if due_day in (None, ""):
            due_day = None
        else:
            try:
                due_day = int(due_day)
            except (ValueError, TypeError):
                raise BudgetError(f"Due day for {name} must be 1–31.") from None
            if not 1 <= due_day <= 31:
                raise BudgetError(f"Due day for {name} must be 1–31.")
        if frequency != "monthly":
            due_day = None

        expense = {
            "id": expense_id,
            "name": name,
            "priority": priority,
            "frequency": frequency,
            "due_day": due_day,
            "amount": None,
            "minimum": None,
        }
        if priority == "P0":
            amount = _money(item.get("amount"), f"{name} amount")
            if amount <= 0:
                raise BudgetError(f"P0 expense {name} must have a positive amount.")
            expense["amount"] = amount
        elif priority == "P1":
            minimum = _money(item.get("minimum"), f"{name} minimum", allow_none=True)
            if minimum is not None and minimum <= 0:
                raise BudgetError(f"{name}: a specified P1 minimum must be positive.")
            expense["minimum"] = minimum
        expenses.append(expense)

    present = {e["name"].casefold() for e in expenses if e["priority"] == "P0"}
    for name in REQUIRED_P0:
        if name not in present:
            raise BudgetError(f"Required P0 expense is missing: {name.title()}.")

    p0_total = sum(e["amount"] for e in expenses if e["priority"] == "P0")
    minimum_total = sum(e["minimum"] or 0 for e in expenses if e["priority"] == "P1")
    if p0_total + minimum_total > funds:
        shortage = p0_total + minimum_total - funds
        raise BudgetError(f"Budget shortfall: P0 + P1 minimums exceed available funds by {shortage:,} VND.")

    return {
        "month": month,
        "available_funds": funds,
        "expenses": expenses,
        "p0_total": p0_total,
        "p1_minimum_total": minimum_total,
        "remaining_after_p0": funds - p0_total,
    }


def _split_integer(total, weights):
    """Integer VND proportional split; remainder distributed deterministically."""
    if not weights:
        if total != 0:
            raise BudgetError("No expenses available for this allocation.")
        return []
    normalized = [float(weight) for weight in weights]
    if any(not isfinite(x) or x <= 0 for x in normalized):
        raise BudgetError("AI weights must be positive finite numbers.")
    weight_total = sum(normalized)
    raw = [total * x / weight_total for x in normalized]
    values = [floor(x) for x in raw]
    missing = total - sum(values)
    order = sorted(range(len(values)), key=lambda i: (-(raw[i] - values[i]), i))
    for i in order[:missing]:
        values[i] += 1
    return values


def _expense_allocation(pool, items, weights, *, respect_minimums):
    if not items:
        if pool:
            raise BudgetError("Unused category funds must be reallocated.")
        return []
    bases = []
    for item in items:
        required = item["minimum"] if respect_minimums else None
        bases.append(required if required is not None else 1)
    if sum(bases) > pool:
        raise BudgetError("Too little money to allocate a positive amount to every expense.")
    extras = _split_integer(pool - sum(bases), weights)
    return [{"expense_id": e["id"], "name": e["name"], "priority": e["priority"],
             "frequency": e["frequency"], "due_day": e["due_day"],
             "amount": minimum + extra}
            for e, minimum, extra in zip(items, bases, extras)]


def generate_three_plans(setup, weights_by_plan=None, explanations=None):
    """Apply P1/P2/Savings percentages after reserving P0.

    If a percentage conflicts with P1 minimums, reduce P2 *surplus* first,
    then savings. Original ratios remain visible as strategy targets.
    """
    weights_by_plan = weights_by_plan or {}
    explanations = explanations or {}
    p0 = [e for e in setup["expenses"] if e["priority"] == "P0"]
    p1 = [e for e in setup["expenses"] if e["priority"] == "P1"]
    p2 = [e for e in setup["expenses"] if e["priority"] == "P2"]
    remaining = setup["remaining_after_p0"]
    p1_floor = sum(e["minimum"] if e["minimum"] is not None else 1 for e in p1)
    p2_floor = len(p2)  # each included P2 expense needs at least 1 VND
    if p1_floor + p2_floor > remaining:
        raise BudgetError("Not enough funds for positive P1/P2 allocations after P0 and P1 minimums.")

    plans = []
    for style, ratios in PLAN_RATIOS.items():
        p1_pool = remaining * ratios["P1"] // 100
        p2_pool = remaining * ratios["P2"] // 100
        savings = remaining - p1_pool - p2_pool
        adjustments = []

        # A percentage group with no expenses is moved into savings.
        if not p1:
            savings += p1_pool
            p1_pool = 0
            adjustments.append("No P1 expenses selected: unused P1 share moved to savings.")
        if not p2:
            savings += p2_pool
            p2_pool = 0
            adjustments.append("No P2 expenses selected: unused P2 share moved to savings.")

        # Make room for positive amounts for included P2 expenses.
        if p2_pool < p2_floor:
            transfer = p2_floor - p2_pool
            if transfer > savings:
                raise BudgetError(f"{style}: insufficient funds for all included P2 expenses.")
            p2_pool += transfer
            savings -= transfer
            adjustments.append("Small adjustment to give every included P2 expense a positive amount.")

        # Protect any user-defined P1 minimums; preserve P2 floor and reduce
        # discretionary P2 share before savings if the P1 target is too low.
        if p1_pool < p1_floor:
            needed = p1_floor - p1_pool
            from_p2 = min(needed, max(0, p2_pool - p2_floor))
            p2_pool -= from_p2
            needed -= from_p2
            if needed > savings:
                raise BudgetError(f"{style}: P1 minimums cannot be covered.")
            savings -= needed
            p1_pool = p1_floor
            adjustments.append("Adjusted the strategy ratio to protect P1 minimums.")

        hints = weights_by_plan.get(style, {})
        def choose_weights(group, items):
            values = hints.get(group, {})
            if (not isinstance(values, dict) or set(values) != {item["id"] for item in items}
                    or any(not isinstance(x, (int, float)) or isinstance(x, bool) or
                           not isfinite(x) or x <= 0 for x in values.values())):
                # Simple, deterministic fallback priorities, not survey statistics.
                return [3 if e["name"].casefold() == "food" else
                        1.5 if e["name"].casefold() == "transportation" else 1
                        for e in items]
            return [values[e["id"]] for e in items]

        allocations = [
            {"expense_id": e["id"], "name": e["name"], "priority": "P0",
             "frequency": e["frequency"], "due_day": e["due_day"], "amount": e["amount"]}
            for e in p0
        ]
        allocations += _expense_allocation(p1_pool, p1, choose_weights("P1", p1), respect_minimums=True)
        allocations += _expense_allocation(p2_pool, p2, choose_weights("P2", p2), respect_minimums=False)

        if sum(a["amount"] for a in allocations) + savings != setup["available_funds"]:
            raise BudgetError("Internal validation failed: budget totals do not balance.")
        plans.append({
            "name": style,
            "ratios": ratios,
            "totals": {"P0": setup["p0_total"], "P1": p1_pool, "P2": p2_pool,
                       "Savings": savings},
            "allocations": allocations,
            "adjustments": adjustments,
            "explanation": str(explanations.get(style, ""))[:260],
        })
    return plans


def generate_schedule(plan, month):
    """Generate dates for a full calendar month and preserve every VND.

    Weeks are Monday-Sunday. Partial weeks receive proportional shares based
    on their number of days inside the selected month.
    """
    year, month_number = map(int, month.split("-"))
    last_day = calendar.monthrange(year, month_number)[1]
    first_date = date(year, month_number, 1)
    last_date = date(year, month_number, last_day)
    days = [first_date + timedelta(days=offset) for offset in range(last_day)]

    weeks = []
    cursor = first_date
    while cursor <= last_date:
        end = min(cursor + timedelta(days=6 - cursor.weekday()), last_date)
        weeks.append((cursor, end, (end - cursor).days + 1))
        cursor = end + timedelta(days=1)

    schedule = {"daily": [], "weekly": [], "monthly": []}
    for expense in plan["allocations"]:
        total = expense["amount"]
        basic = {"expense_id": expense["expense_id"], "expense": expense["name"],
                 "priority": expense["priority"]}
        if expense["frequency"] == "daily":
            amounts = _split_integer(total, [1] * last_day)
            for day, amount in zip(days, amounts):
                entry = {**basic, "date": day.isoformat(), "amount": amount}
                # Only daily Food is split into meals; this does not add new
                # expenses or change the total Food allocation.
                if expense["name"].casefold() == "food":
                    meal_parts = _split_integer(amount, list(MEAL_WEIGHTS.values()))
                    entry["meals"] = dict(zip(MEAL_WEIGHTS, meal_parts))
                schedule["daily"].append(entry)
        elif expense["frequency"] == "weekly":
            amounts = _split_integer(total, [week[2] for week in weeks])
            for (start, end, _), amount in zip(weeks, amounts):
                schedule["weekly"].append({**basic, "start": start.isoformat(),
                                           "end": end.isoformat(), "amount": amount})
        else:
            due_day = expense.get("due_day")
            due_date = (date(year, month_number, min(due_day, last_day)).isoformat()
                        if due_day else None)
            schedule["monthly"].append({**basic, "month": month,
                                        "due_date": due_date, "amount": total})
    return schedule



def apply_manual_adjustments(setup, proposed_plan, edited_allocations, savings):
    """Build an edited confirmation snapshot without changing the generated proposal.

    P0 is never editable. Every included P1/P2 expense remains positive,
    P1 user minimums are protected, and the grand total must match funds.
    Only individual expense amounts and savings can change at this stage.
    """
    if not isinstance(edited_allocations, list):
        raise BudgetError("Submit the edited P1/P2 expense allocations as a list.")
    original = proposed_plan["allocations"]
    flexible = {a["expense_id"]: a for a in original if a["priority"] in ("P1", "P2")}
    received = {}
    for item in edited_allocations:
        if not isinstance(item, dict):
            raise BudgetError("Invalid edited expense entry.")
        expense_id = item.get("expense_id")
        if not isinstance(expense_id, str) or expense_id not in flexible:
            raise BudgetError("Only existing P1/P2 expenses can be edited.")
        if expense_id in received:
            raise BudgetError("Duplicate edited expense.")
        amount = _money(item.get("amount"), f"{flexible[expense_id]['name']} amount")
        if amount <= 0:
            raise BudgetError(f"{flexible[expense_id]['name']} must receive a positive allocation.")
        received[expense_id] = amount
    if set(received) != set(flexible):
        raise BudgetError("Provide an allocation for every included P1/P2 expense.")
    savings_amount = _money(savings, "Planned savings")

    required_minima = {e["id"]: e["minimum"] for e in setup["expenses"]
                       if e["priority"] == "P1" and e["minimum"] is not None}
    for expense_id, minimum in required_minima.items():
        if received[expense_id] < minimum:
            raise BudgetError(f"{flexible[expense_id]['name']} must be at least {minimum:,} VND (P1 minimum).")

    allocations = [
        {**item, "amount": received[item["expense_id"]]}
        if item["priority"] in ("P1", "P2") else dict(item)
        for item in original
    ]
    total = sum(item["amount"] for item in allocations) + savings_amount
    if total != setup["available_funds"]:
        difference = setup["available_funds"] - total
        if difference > 0:
            raise BudgetError(f"Unallocated funds: {difference:,} VND. Update savings or expense amounts.")
        raise BudgetError(f"Over budget by {-difference:,} VND. Reduce savings or expense amounts.")

    totals = {"P0": 0, "P1": 0, "P2": 0, "Savings": savings_amount}
    for item in allocations:
        totals[item["priority"]] += item["amount"]
    return {
        **proposed_plan,
        "totals": totals,
        "allocations": allocations,
        "manually_adjusted": (
            savings_amount != proposed_plan["totals"]["Savings"]
            or any(a["amount"] != b["amount"] for a, b in zip(allocations, original))
        ),
    }
