from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.budgets.rules import (
    MAX_VND, BudgetError, ExpenseInput, generate_plans, money, validate_allocations,
)


@pytest.fixture
def expenses():
    return [
        ExpenseInput(uuid4(), "Rent", "P0", 200, None),
        ExpenseInput(uuid4(), "Electricity", "P0", 50, None),
        ExpenseInput(uuid4(), "Water", "P0", 50, None),
        ExpenseInput(uuid4(), "Food", "P1", None, 300),
        ExpenseInput(uuid4(), "Entertainment", "P2", 0, None),
    ]


@pytest.mark.parametrize("funds", [1000, 601, MAX_VND])
def test_plans_conserve_every_vnd_and_protect_minimums(expenses, funds):
    plans = generate_plans(funds, expenses)
    assert [p["plan_type"] for p in plans] == ["SAVING", "BALANCED", "LIFESTYLE"]
    for plan in plans:
        values = dict(plan["allocations"])
        assert sum(values.values()) + plan["planned_savings"] == funds
        assert values[expenses[0].id] == 200
        assert values[expenses[3].id] >= 300
        assert values[expenses[4].id] >= 1
        assert all(type(value) is int for value in values.values())
        assert type(plan["planned_savings"]) is int


def test_prototype_strategy_targets_apply_after_p0(expenses):
    plans = generate_plans(1300, expenses)
    assert [(dict(p["allocations"])[expenses[3].id], dict(p["allocations"])[expenses[4].id], p["planned_savings"]) for p in plans] == [
        (700, 50, 250), (650, 150, 200), (600, 300, 100),
    ]


def test_minimums_take_discretionary_surplus_before_savings(expenses):
    expenses[3] = replace(expenses[3], minimum_amount=950)
    for plan in generate_plans(1300, expenses):
        assert dict(plan["allocations"])[expenses[3].id] == 950
        assert sum(amount for _, amount in plan["allocations"]) + plan["planned_savings"] == 1300


def test_p0_only_moves_unselected_groups_to_savings(expenses):
    for plan in generate_plans(1000, expenses[:3]):
        assert plan["planned_savings"] == 700


@pytest.mark.parametrize("amount", [None, 0])
def test_required_p0_unknown_and_zero_both_block_generation(expenses, amount):
    expenses[0] = replace(expenses[0], estimated_amount=amount)
    with pytest.raises(BudgetError, match="P0 Rent"):
        generate_plans(1000, expenses)


@pytest.mark.parametrize("priority", ["P1", "P2"])
def test_mandatory_name_must_be_p0(expenses, priority):
    expenses[0] = replace(expenses[0], priority=priority)
    with pytest.raises(BudgetError, match="missing.*rent"):
        generate_plans(1000, expenses)


def test_shortfall_saves_no_unrealistic_plan(expenses):
    with pytest.raises(BudgetError, match="shortfall"):
        generate_plans(600, expenses)


@pytest.mark.parametrize("value", [True, False, 1.5, "1.5", "1e3", "1,000", -1, MAX_VND + 1, "9" * 5000])
def test_invalid_money_is_rejected(value):
    with pytest.raises(BudgetError):
        money(value, "Amount")


def test_unknown_and_zero_are_distinct():
    assert money(None, "Estimate", optional=True) is None
    assert money("", "Estimate", optional=True) is None
    assert money("0", "Estimate", optional=True) == 0


@pytest.mark.parametrize("mutation", ["negative", "zero", "float", "bool", "p0", "minimum", "missing", "duplicate", "foreign", "total", "savings"])
def test_invalid_allocations_are_rejected(expenses, mutation):
    plan = generate_plans(1300, expenses)[0]
    allocations = list(plan["allocations"])
    savings = plan["planned_savings"]
    if mutation in {"negative", "zero", "float", "bool", "p0"}:
        value = {"negative": -1, "zero": 0, "float": 200.5, "bool": True, "p0": 199}[mutation]
        allocations[0] = (expenses[0].id, value)
    elif mutation == "minimum":
        allocations[3] = (expenses[3].id, 299)
    elif mutation == "missing":
        allocations.pop()
    elif mutation == "duplicate":
        allocations.append(allocations[0])
    elif mutation == "foreign":
        allocations[0] = (uuid4(), 200)
    elif mutation == "total":
        savings += 1
    else:
        savings = -1
    with pytest.raises(BudgetError):
        validate_allocations(1300, expenses, allocations, savings)


def test_tiny_remainder_still_funds_every_included_item(expenses):
    expenses[3] = replace(expenses[3], minimum_amount=None)
    for index in range(4):
        expenses.append(ExpenseInput(uuid4(), f"Extra {index}", "P2", None, None))
    for plan in generate_plans(306, expenses):
        assert all(amount > 0 for _, amount in plan["allocations"])
        assert plan["planned_savings"] == 0
