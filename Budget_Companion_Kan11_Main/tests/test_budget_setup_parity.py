"""KAN-11 core behavior on the integrated KAN-21/KAN-23 database contracts."""

from datetime import date
from html.parser import HTMLParser
import re
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAllocation, BudgetExpense, BudgetMonth,
    BudgetPlan, ExpenseCategory, ExpenseRecord, User,
)
from app.modules.budget_periods.services import create_budget_month
from app.modules.budgets import services
from app.modules.budgets.rules import BudgetError, MAX_VND, meal_breakdown
from app.modules.budgets.suggestions import SUGGESTED_EXPENSES
from app.modules.expenses import services as expenses
from app.modules.expenses.presentation import ExpenseTaskAdapter


DEFAULT_KEYS = [item.key for item in SUGGESTED_EXPENSES if item.selected]


def example_values():
    return {
        item.key: {"estimated_amount": item.example_amount, "due_day": item.example_due_day}
        for item in SUGGESTED_EXPENSES
    }


def snapshot():
    return {
        model.__tablename__: list(db.session.execute(db.select(*model.__table__.columns).order_by(model.id)))
        for model in (BudgetMonth, BudgetExpense, BudgetPlan, BudgetAllocation,
                      AssignedExpenseTask, ExpenseRecord, ExpenseCategory)
    }


@pytest.fixture
def setup(app, client):
    with app.app_context():
        owner = User(email="parity@example.com", password_hash="test-only")
        other = User(email="parity-other@example.com", password_hash="test-only")
        db.session.add_all([owner, other])
        db.session.commit()
        month = create_budget_month(owner.id, "2026-10", 5_000_000, date(2026, 10, 1))
        foreign_month = create_budget_month(other.id, "2026-10", 5_000_000, date(2026, 10, 1))
        data = {"user": owner.id, "other": other.id, "month": month.id, "foreign_month": foreign_month.id}
    with client.session_transaction() as session:
        session["user_id"] = str(data["user"])
    return data


def root(setup):
    return f"/budget/{setup['month']}"


def suggestion_data(keys=DEFAULT_KEYS, *, example=False):
    data = {"suggestion": keys}
    if example:
        for item in SUGGESTED_EXPENSES:
            if item.example_amount is not None:
                data[f"{item.key}_estimated_amount"] = str(item.example_amount)
                data[f"{item.key}_due_day"] = str(item.example_due_day)
    return data


def prepare_plan(setup):
    services.apply_suggested_expenses(setup["user"], setup["month"], DEFAULT_KEYS, example_values())
    services.save_expense(setup["user"], setup["month"], {
        "expense_name": "Shopping", "priority": "P2", "category_name": "Shopping",
        "allocation_frequency": "MONTHLY", "estimated_amount": 0,
    })
    return services.generate_budget_plans(setup["user"], setup["month"])


def test_suggested_list_matches_prototype_core_defaults():
    assert [(item.name, item.priority, item.frequency, item.selected) for item in SUGGESTED_EXPENSES] == [
        ("Rent", "P0", "MONTHLY", True), ("Electricity", "P0", "MONTHLY", True),
        ("Water", "P0", "MONTHLY", True), ("Internet", "P0", "MONTHLY", False),
        ("Food", "P1", "DAILY", True), ("Transportation", "P1", "WEEKLY", True),
    ]
    assert [item.example_amount for item in SUGGESTED_EXPENSES[:4]] == [1_500_000, 200_000, 100_000, 100_000]
    assert [item.example_due_day for item in SUGGESTED_EXPENSES[:4]] == [5, 12, 12, 1]


class Inputs(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.inputs = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))


def test_gets_show_unsaved_suggestions_without_seeding(app, client, setup):
    with app.app_context():
        before = snapshot()
    for path in ("/budget", root(setup), root(setup)):
        response = client.get(path)
        assert response.status_code == 200
    fields = Inputs(response.get_data(as_text=True)).inputs
    for item in SUGGESTED_EXPENSES:
        estimate = next(f for f in fields if f.get("name") == f"{item.key}_estimated_amount")
        assert estimate.get("value", "") == ""
        check = next(f for f in fields if f.get("name") == "suggestion" and f["value"] == item.key)
        assert ("checked" in check) == item.selected
    assert b"Load Example amounts" in response.data
    assert b"budget-setup.js" in response.data
    with app.app_context():
        assert snapshot() == before


def test_blank_suggestions_preserve_unknown_and_require_p0_amounts(app, setup):
    with app.app_context():
        created = services.apply_suggested_expenses(setup["user"], setup["month"], DEFAULT_KEYS)
        assert len(created) == 5
        assert all(item.estimated_amount is None and item.minimum_amount is None for item in created)
        assert all(isinstance(item.id, UUID) and isinstance(item.category_id, UUID) for item in created)
        assert all(item.budget_month_id == setup["month"] for item in created)
        with pytest.raises(BudgetError, match="P0"):
            services.generate_budget_plans(setup["user"], setup["month"])
        assert services.list_plans(setup["user"], setup["month"]) == []


@pytest.mark.parametrize("selected", [["rent", "electricity", "water"], ["internet"], ["food"], ["transportation"]])
def test_only_explicitly_selected_expenses_are_created(app, setup, selected):
    with app.app_context():
        created = services.apply_suggested_expenses(setup["user"], setup["month"], selected)
        expected = {item.name for item in SUGGESTED_EXPENSES if item.key in selected}
        assert {item.expense_name for item in created} == expected
        assert {item.expense_name for item in services.list_expenses(setup["user"], setup["month"])} == expected


def test_repeated_initialization_skips_existing_user_values_and_preserves_drafts(app, setup):
    with app.app_context():
        services.save_expense(setup["user"], setup["month"], {
            "expense_name": "fOoD", "priority": "P1", "category_name": "My essentials",
            "estimated_amount": 0, "minimum_amount": 4567,
            "allocation_frequency": "WEEKLY", "is_recurring": True,
        })
        services.save_expense(setup["user"], setup["month"], {
            "expense_name": "Medical", "priority": "P0", "category_name": "My essentials",
            "estimated_amount": 12, "allocation_frequency": "MONTHLY",
        })
        originals = snapshot()["budget_expenses"]
        added = services.apply_suggested_expenses(setup["user"], setup["month"], DEFAULT_KEYS, example_values())
        assert len(added) == 4
        assert set(originals).issubset(set(snapshot()["budget_expenses"]))
        plans = services.generate_budget_plans(setup["user"], setup["month"])
        before = snapshot()
        assert services.apply_suggested_expenses(setup["user"], setup["month"], DEFAULT_KEYS, example_values()) == []
        assert snapshot() == before
        assert {p.id for p in services.list_plans(setup["user"], setup["month"])} == {p.id for p in plans}


def test_explicit_values_frequency_and_optional_minimums_use_canonical_validation(app, setup):
    with app.app_context():
        rows = services.apply_suggested_expenses(setup["user"], setup["month"], ["food", "transportation"], {
            "food": {"estimated_amount": "0", "minimum_amount": "800000", "allocation_frequency": "WEEKLY"},
            "transportation": {"allocation_frequency": "MONTHLY", "due_day": "31"},
        })
        food, transport = rows
        assert (food.estimated_amount, food.minimum_amount, food.allocation_frequency) == (0, 800000, "WEEKLY")
        assert (transport.estimated_amount, transport.minimum_amount, transport.allocation_frequency, transport.due_day) == (None, None, "MONTHLY", 31)


@pytest.mark.parametrize("selected, values", [
    ([], None), (["rent", "rent"], None), (["not-a-suggestion"], None), ("rent", None),
    (["rent"], []), (["rent"], {"rent": []}),
    (["rent", "food"], {"food": {"minimum_amount": "0"}}),
    (["rent", "food"], {"food": {"allocation_frequency": "YEARLY"}}),
    (["rent", "food"], {"food": {"estimated_amount": "1.5"}}),
    (["rent", "food"], {"food": {"due_day": "5"}}),
])
def test_invalid_batch_rolls_back_every_created_expense_and_category(app, setup, selected, values):
    with app.app_context():
        before = snapshot()
        with pytest.raises(BudgetError):
            services.apply_suggested_expenses(setup["user"], setup["month"], selected, values)
        assert snapshot() == before


def test_invalid_batch_keeps_original_drafts(app, setup):
    with app.app_context():
        prepare_plan(setup)
        before = snapshot()
        with pytest.raises(BudgetError):
            services.apply_suggested_expenses(setup["user"], setup["month"], ["internet"], {
                "internet": {"minimum_amount": 12},
            })
        assert snapshot() == before
        services.apply_suggested_expenses(setup["user"], setup["month"], ["internet"], example_values())
        assert services.list_plans(setup["user"], setup["month"]) == []


def test_database_failure_rolls_back_whole_initialization(app, setup):
    def reject_second(mapper, connection, row):
        if row.expense_name == "Food":
            raise IntegrityError("simulated insert conflict", {}, RuntimeError("conflict"))

    with app.app_context():
        before = snapshot()
        event.listen(BudgetExpense, "before_insert", reject_second)
        try:
            with pytest.raises(services.BudgetConflict):
                services.apply_suggested_expenses(setup["user"], setup["month"], ["rent", "food"])
        finally:
            event.remove(BudgetExpense, "before_insert", reject_second)
        assert snapshot() == before


def test_example_setup_generates_three_unchanged_algorithms_and_breakdowns(app, client, setup):
    with app.app_context():
        plans = prepare_plan(setup)
        expected = [(2_240_000, 160_000, 800_000), (2_080_000, 480_000, 640_000), (1_920_000, 960_000, 320_000)]
        assert [p.plan_type for p in plans] == ["SAVING", "BALANCED", "LIFESTYLE"]
        for plan, amounts in zip(plans, expected):
            totals = services.plan_breakdown(setup["user"], setup["month"], plan.id)
            assert totals == dict(P0=1_800_000, P1=amounts[0], P2=amounts[1], Savings=amounts[2])
            assert sum(totals.values()) == 5_000_000
        before = snapshot()
    markup = client.get(root(setup)).data
    assert b"Compare saved plans" in markup and b"P0" in markup and b"P1" in markup and b"P2" in markup
    with app.app_context():
        assert snapshot() == before


def test_suggestion_post_is_authenticated_csrf_protected_and_retry_safe(app, client, setup):
    app.config["WTF_CSRF_ENABLED"] = True
    path = root(setup) + "/expenses/suggested"
    assert client.post(path, data=suggestion_data(example=True)).status_code == 400
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get(root(setup)).get_data(as_text=True)).group(1)
    data = suggestion_data(example=True) | {"csrf_token": token, "user_id": str(setup["other"])}
    for _ in range(2):
        response = client.post(path, data=data, follow_redirects=True)
        assert response.status_code == 200
    with app.app_context():
        assert len(services.list_expenses(setup["user"], setup["month"])) == 5
        assert services.list_expenses(setup["other"], setup["foreign_month"]) == []
        assert services.get_month(setup["user"], setup["month"]).available_vnd == 5_000_000
    with client.session_transaction() as session:
        session.clear()
    app.config["WTF_CSRF_ENABLED"] = False
    assert client.post(path, data=data).status_code == 302


def test_cross_user_month_is_hidden_for_service_and_route(app, client, setup):
    with app.app_context():
        before = snapshot()
        with pytest.raises(services.BudgetNotFound):
            services.apply_suggested_expenses(setup["user"], setup["foreign_month"], DEFAULT_KEYS)
    response = client.post(f"/budget/{setup['foreign_month']}/expenses/suggested", data=suggestion_data() | {"user_id": str(setup["other"])})
    assert response.status_code == 404
    with app.app_context():
        assert snapshot() == before


@pytest.mark.parametrize("action", ["suggestions", "generate", "edit", "delete", "confirm_other"])
def test_confirmed_plan_and_spending_remain_unchanged(app, client, setup, action):
    with app.app_context():
        plans = prepare_plan(setup)
        plan_id, other_plan_id = plans[1].id, plans[0].id
        services.confirm_plan(setup["user"], setup["month"], plan_id)
        tasks = expenses.ensure_tasks_for_month(setup["user"], setup["month"])
        food = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Food")
        expenses.checkin_task(setup["user"], food.id, action="actual", amount_raw="123", idempotency_key=uuid4().hex)
        expense_id = food.allocation.budget_expense_id
        before = snapshot()
    paths = {
        "suggestions": root(setup) + "/expenses/suggested", "generate": root(setup) + "/plans/generate",
        "edit": f"{root(setup)}/expenses/{expense_id}/edit", "delete": f"{root(setup)}/expenses/{expense_id}/delete",
        "confirm_other": f"{root(setup)}/plans/{other_plan_id}/confirm",
    }
    data = suggestion_data(example=True) | {
        "expense_name": "Food", "priority": "P1", "category_name": "Food", "allocation_frequency": "DAILY",
        "estimated_amount": "1", "minimum_amount": "", "allocations": "1", "savings": "0",
    }
    assert client.post(paths[action], data=data).status_code == 409
    assert client.post(f"{root(setup)}/plans/{plan_id}/confirm", data=data).status_code == 302
    assert b"Continue to Spending Schedule" in client.get(f"{root(setup)}/plans/{plan_id}").data
    with app.app_context():
        assert snapshot() == before


@pytest.mark.parametrize("amount", [0, 1, 2, 3, 7, 10, 100_003, MAX_VND])
def test_meal_guidance_conserves_every_vnd_without_float_rounding(amount):
    meals = meal_breakdown(amount)
    assert list(meals) == ["Breakfast", "Lunch", "Dinner"]
    assert sum(meals.values()) == amount
    assert all(type(value) is int and value >= 0 for value in meals.values())
    if amount == 10:
        assert meals == {"Breakfast": 3, "Lunch": 4, "Dinner": 3}


@pytest.mark.parametrize("amount", [None, True, -1, 1.1, MAX_VND + 1])
def test_meal_guidance_does_not_turn_unknown_or_invalid_data_into_zero(amount):
    with pytest.raises(BudgetError):
        meal_breakdown(amount)


@pytest.mark.parametrize("month, start, days", [("2026-10", 15, 17), ("2027-02", 1, 28), ("2028-02", 1, 29)])
def test_food_meals_sum_to_original_schedule_without_creating_financial_rows(app, setup, month, start, days):
    with app.app_context():
        if month != "2026-10":
            period = create_budget_month(setup["user"], month, 5_000_000, date.fromisoformat(month + f"-{start:02d}"))
            setup = setup | {"month": period.id}
        else:
            services.get_month(setup["user"], setup["month"]).tracking_start_date = date(2026, 10, start)
            db.session.commit()
        plan = prepare_plan(setup)[1]
        services.confirm_plan(setup["user"], setup["month"], plan.id)
        tasks = expenses.ensure_tasks_for_month(setup["user"], setup["month"])
        before = snapshot()
        food_tasks = [task for task in tasks if task.allocation.budget_expense.expense_name == "Food"]
        assert len(food_tasks) == days
        food_allocation = food_tasks[0].allocation
        for task in tasks:
            meals = ExpenseTaskAdapter(task).meal_guidance
            if task in food_tasks:
                assert sum(meals.values()) == task.current_limit
            else:
                assert meals is None
        assert sum(sum(ExpenseTaskAdapter(task).meal_guidance.values()) for task in food_tasks) == food_allocation.allocated_amount
        assert sum(task.original_limit for task in tasks) + plan.planned_savings == 5_000_000
        assert snapshot() == before


def test_complete_setup_compare_confirm_schedule_and_food_display(app, client, setup):
    assert client.post(root(setup) + "/expenses/suggested", data=suggestion_data(example=True)).status_code == 302
    # Additional expenses can be entered on the same workspace with no add screen.
    markup = client.get(root(setup)).data
    assert b"Save expense and add another" in markup
    assert client.post(root(setup) + "/expenses/new", data={
        "expense_name": "Entertainment", "priority": "P2", "category_name": "Flexible",
        "category_id": "",
        "allocation_frequency": "WEEKLY", "estimated_amount": "", "minimum_amount": "",
    }).headers["Location"].endswith("#add-expense")
    assert client.post(root(setup) + "/plans/generate").headers["Location"].endswith("#compare")
    with app.app_context():
        plan_id = services.list_plans(setup["user"], setup["month"])[0].id
    assert client.post(f"{root(setup)}/plans/{plan_id}/confirm").status_code == 302
    assert client.post(f"/expenses/months/{setup['month']}/schedule").status_code == 302
    with app.app_context():
        before = snapshot()
    response = client.get(f"/expenses?budget_month_id={setup['month']}&view=day&date=2026-10-01")
    assert response.status_code == 200
    assert all(word in response.data for word in (b"Optional meal guidance", b"Breakfast", b"Lunch", b"Dinner"))
    with app.app_context():
        assert snapshot() == before


@pytest.mark.parametrize("frequency", ["DAILY", "WEEKLY", "MONTHLY"])
def test_meal_guidance_uses_current_daily_limit_only(app, setup, frequency):
    with app.app_context():
        services.apply_suggested_expenses(setup["user"], setup["month"], DEFAULT_KEYS, example_values() | {
            "food": {"allocation_frequency": frequency},
        })
        plan = services.generate_budget_plans(setup["user"], setup["month"])[0]
        services.confirm_plan(setup["user"], setup["month"], plan.id)
        tasks = expenses.ensure_tasks_for_month(setup["user"], setup["month"])
        food = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Food")
        original = food.original_limit
        # Simulate a current task limit from a future adjustment consumer. The
        # Budget allocation and original schedule snapshot remain unchanged.
        food.current_limit = 7
        db.session.commit()
        before = snapshot()
        assert ExpenseTaskAdapter(food).meal_guidance == (
            {"Breakfast": 2, "Lunch": 3, "Dinner": 2} if frequency == "DAILY" else None
        )
        assert food.original_limit == original
        assert snapshot() == before


def test_zero_food_allowance_is_guidance_not_a_zero_spending_checkin(app, setup):
    with app.app_context():
        month = services.get_month(setup["user"], setup["month"])
        month.available_vnd = 4
        db.session.commit()
        services.apply_suggested_expenses(setup["user"], setup["month"], ["rent", "electricity", "water", "food"], {
            key: {"estimated_amount": 1} for key in ("rent", "electricity", "water")
        })
        plan = services.generate_budget_plans(setup["user"], setup["month"])[0]
        services.confirm_plan(setup["user"], setup["month"], plan.id)
        tasks = expenses.ensure_tasks_for_month(setup["user"], setup["month"])
        food = [task for task in tasks if task.allocation.budget_expense.expense_name == "Food"]
        assert len(food) == 31
        assert sum(task.current_limit for task in food) == 1
        zero_days = [task for task in food if task.current_limit == 0]
        assert len(zero_days) == 30
        before = snapshot()
        for task in zero_days:
            assert ExpenseTaskAdapter(task).meal_guidance == {"Breakfast": 0, "Lunch": 0, "Dinner": 0}
            assert task.task_status == "PENDING" and task.records == []
        assert snapshot() == before
