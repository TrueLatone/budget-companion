"""Dependency-free budget arithmetic verification (no Flask or live database).

Run: python scripts/verify_budget_rules_offline.py
This is a small pure-rule smoke check, not a substitute for pytest/HTTP/DB tests.
"""
import runpy
from pathlib import Path
from uuid import UUID

rules = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app/modules/budgets/rules.py"))
ExpenseInput = rules["ExpenseInput"]
BudgetError = rules["BudgetError"]
make = lambda number: UUID(int=number)
inputs = [
    ExpenseInput(make(1), "Rent", "P0", 2_000_000, None),
    ExpenseInput(make(2), "Electricity", "P0", 200_000, None),
    ExpenseInput(make(3), "Water", "P0", 100_000, None),
    ExpenseInput(make(4), "Food", "P1", None, 1_000_000),
    ExpenseInput(make(5), "Transportation", "P1", None, 200_000),
    ExpenseInput(make(6), "Entertainment", "P2", 0, None),
]
funds = 7_000_000
plans = rules["generate_plans"](funds, inputs)
assert {p["plan_type"] for p in plans} == {"SAVING", "BALANCED", "LIFESTYLE"}
for plan in plans:
    rules["validate_allocations"](funds, inputs, plan["allocations"], plan["planned_savings"])
    assert sum(value for _, value in plan["allocations"]) + plan["planned_savings"] == funds
    assert dict(plan["allocations"])[make(1)] == 2_000_000

balanced = next(p for p in plans if p["plan_type"] == "BALANCED")
modified = [(key, value + 100_000 if key == make(4) else value)
            for key, value in balanced["allocations"]]
new_savings = balanced["planned_savings"] - 100_000
rules["validate_allocations"](funds, inputs, modified, new_savings)
assert new_savings >= 0

for invalid in (
    [(key, 999_999 if key == make(4) else value) for key, value in modified],
    [(key, 1 if key == make(1) else value) for key, value in modified],
    [(key, 7_000_001 if key == make(4) else value) for key, value in modified],
):
    try:
        rules["validate_allocations"](funds, inputs, invalid, new_savings)
    except BudgetError:
        pass
    else:
        raise AssertionError("Invalid allocation was accepted")

for total, count in [(11, 4), (101, 29), (0, 3), (9_223_372_036_854_775_807, 31)]:
    split = rules["split_integer"](total, [1] * count)
    assert len(split) == count and sum(split) == total
    assert max(split) - min(split) <= 1

print("PASS: three generated plans, exact VND conservation, P0/P1 constraints,")
print("      manual savings adjustment, invalid-allocation rejection, BIGINT rounding")
