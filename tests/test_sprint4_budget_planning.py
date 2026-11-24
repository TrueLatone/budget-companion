"""Sprint 4 Budget Planning acceptance cases for the supplied MAIN snapshot.

One pytest function per automated BP case in Budget_Planning_Test_Cases_Sprint4.xlsx.
BP-04, BP-14 and BP-28 use the browser procedures in the KAN-71 verification report.
All state is confined to disposable SQLite fixtures; no real accounts or funds.

D1: Nov 2026, 7,000,000 VND, seven expenses with P0=2,500,000.
D2: Nov 2026, tracking starts Nov 6, six expenses, 34 expected tasks.
"""
from collections import Counter
from datetime import date
from uuid import UUID

import pytest

from app.extensions import db
from app.models import AssignedExpenseTask, BudgetExpense, BudgetMonth, ExpenseRecord, User
from app.modules.accounts.services import register_user
from app.modules.budgets import services as budgets
from app.modules.budgets.rules import BudgetError
from app.modules.expenses import services as expenses
from app.modules.expenses.validators import ValidationError


D1_EXPENSES = [
    ("Rent", "P0", 2_000_000, None, "MONTHLY", 5),
    ("Electricity", "P0", 200_000, None, "MONTHLY", 31),
    ("Water", "P0", 100_000, None, "MONTHLY", 31),
    ("Internet", "P0", 200_000, None, "MONTHLY", None),
    ("Food", "P1", 1_500_000, 1_200_000, "DAILY", None),
    ("Transportation", "P1", 400_000, 300_000, "WEEKLY", None),
    ("Entertainment", "P2", 200_000, None, "MONTHLY", None),
]
D2_EXPENSES = [
    ("Rent", "P0", 2_000_000, None, "MONTHLY", 5),
    ("Electricity", "P0", 200_000, None, "MONTHLY", 31),
    ("Water", "P0", 100_000, None, "MONTHLY", 31),
    ("Food", "P1", None, 1_000_000, "DAILY", None),
    ("Transportation", "P1", None, 200_000, "WEEKLY", None),
    ("Entertainment", "P2", 0, None, "MONTHLY", None),
]


def _entry(row):
    name, priority, estimate, minimum, frequency, due = row
    return {
        "expense_name": name, "priority": priority,
        "estimated_amount": estimate, "minimum_amount": minimum,
        "allocation_frequency": frequency, "due_day": due,
        "category_name": "Sprint4 test", "is_recurring": False,
    }


@pytest.fixture
def d1(app):
    with app.app_context():
        owner = User(email="sprint4-owner@example.com", password_hash="test")
        other = User(email="sprint4-other@example.com", password_hash="test")
        db.session.add_all([owner, other])
        db.session.flush()
        month = BudgetMonth(
            user_id=owner.id, month_start=date(2026, 11, 1),
            tracking_start_date=date(2026, 11, 6), available_vnd=7_000_000,
        )
        db.session.add(month)
        db.session.commit()
        result = {"owner": owner.id, "other": other.id, "month": month.id}
        for row in D1_EXPENSES:
            budgets.save_expense(owner.id, month.id, _entry(row))
        return result


@pytest.fixture
def d2(app):
    with app.app_context():
        owner = User(email="sprint4-owner@example.com", password_hash="test")
        other = User(email="sprint4-other@example.com", password_hash="test")
        db.session.add_all([owner, other])
        db.session.flush()
        month = BudgetMonth(
            user_id=owner.id, month_start=date(2026, 11, 1),
            tracking_start_date=date(2026, 11, 6), available_vnd=7_000_000,
        )
        db.session.add(month)
        db.session.commit()
        result = {"owner": owner.id, "other": other.id, "month": month.id}
        for row in D2_EXPENSES:
            budgets.save_expense(owner.id, month.id, _entry(row))
        return result


def _generate(scenario, style="BALANCED"):
    candidates = budgets.generate_budget_plans(scenario["owner"], scenario["month"])
    return next(p for p in candidates if p.plan_type == style)


def _editable(plan):
    return {str(a.budget_expense_id): a.allocated_amount for a in plan.allocations
            if a.budget_expense.priority in ("P1", "P2")}


def _expense_allocation(plan, name):
    return next(a for a in plan.allocations if a.budget_expense.expense_name == name)


def _save_manual(scenario, balanced, overrides=None):
    values = _editable(balanced)
    if overrides:
        for name, amount in overrides.items():
            values[str(_expense_allocation(balanced, name).budget_expense_id)] = amount
    token = budgets.customization_fingerprint(scenario["owner"], scenario["month"], balanced.id)
    return budgets.save_manual_plan(
        scenario["owner"], scenario["month"], balanced.id,
        values, expected_fingerprint=token,
    )


def _signed_in(client, app):
    with app.app_context():
        register_user("sprint4-login@example.com", "correct-horse")
    assert client.post("/login", data={"email": "sprint4-login@example.com", "password": "correct-horse"}).status_code == 302


# UC05: Monthly budget period creation

def test_BP_01_create_budget_month(app, client):
    _signed_in(client, app)
    assert client.post("/budget-periods/new", data={"month": "2026-11", "available_vnd": "7000000"}).status_code == 302
    with app.app_context():
        month = db.session.scalar(db.select(BudgetMonth))
        assert month.month_start == date(2026, 11, 1) and month.available_vnd == 7_000_000
        assert budgets.list_plans(month.user_id, month.id) == []
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0


def test_BP_02_prevent_duplicate_month(app, client):
    _signed_in(client, app)
    data = {"month": "2026-11", "available_vnd": "7000000"}
    assert client.post("/budget-periods/new", data=data).status_code == 302
    assert client.post("/budget-periods/new", data=data).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 1


def test_BP_03_reject_invalid_month(app, client):
    _signed_in(client, app)
    for invalid in ("2026-13", "2026"):
        assert client.post("/budget-periods/new", data={"month": invalid, "available_vnd": "7000000"}).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 0


# UC08: Setup and validation

def test_BP_05_persist_seven_expenses(app, d1):
    with app.app_context():
        saved = budgets.list_expenses(d1["owner"], d1["month"])
        assert len(saved) == 7
        assert Counter(e.priority for e in saved) == {"P0": 4, "P1": 2, "P2": 1}
        assert {e.expense_name: e.allocation_frequency for e in saved}["Food"] == "DAILY"
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0


def test_BP_06_reject_case_insensitive_duplicate(app, d1):
    with app.app_context():
        data = _entry(("rent", "P0", 2_000_000, None, "MONTHLY", None))
        with pytest.raises(BudgetError):
            budgets.save_expense(d1["owner"], d1["month"], data)
        assert len(budgets.list_expenses(d1["owner"], d1["month"])) == 7
        assert next(e for e in budgets.list_expenses(d1["owner"], d1["month"]) if e.expense_name == "Rent").estimated_amount == 2_000_000


def test_BP_07_reject_noninteger_and_negative_amounts(app, d1):
    with app.app_context():
        for bad in ("-1", "1.5", "abc"):
            data = _entry(("Snacks", "P2", bad, None, "MONTHLY", None))
            with pytest.raises(BudgetError):
                budgets.save_expense(d1["owner"], d1["month"], data)
        assert len(budgets.list_expenses(d1["owner"], d1["month"])) == 7


def test_BP_08_reject_invalid_priority_and_frequency(app, d1):
    with app.app_context():
        for row in (("Custom", "P3", 1_000, None, "MONTHLY", None),
                    ("Custom", "P2", 1_000, None, "YEARLY", None)):
            with pytest.raises(BudgetError):
                budgets.save_expense(d1["owner"], d1["month"], _entry(row))
        assert len(budgets.list_expenses(d1["owner"], d1["month"])) == 7


def test_BP_09_reject_invalid_due_day(app, d1):
    with app.app_context():
        for row in (("Custom", "P2", 1_000, None, "MONTHLY", 32),
                    ("Custom", "P2", 1_000, None, "DAILY", 10)):
            with pytest.raises(BudgetError):
                budgets.save_expense(d1["owner"], d1["month"], _entry(row))
        assert len(budgets.list_expenses(d1["owner"], d1["month"])) == 7


# UC09: Three generated proposals

def test_BP_10_generate_three_draft_plans(app, d1):
    with app.app_context():
        _generate(d1)
        plans = budgets.list_plans(d1["owner"], d1["month"])
        assert {p.plan_type for p in plans} == {"SAVING", "BALANCED", "LIFESTYLE"}
        assert all(p.status == "GENERATED" and len(p.allocations) == 7 for p in plans)


def test_BP_11_conserve_funds_and_respect_floors(app, d1):
    with app.app_context():
        _generate(d1)
        expected = {"SAVING": (3_150_000, 225_000, 1_125_000),
                    "BALANCED": (2_925_000, 675_000, 900_000),
                    "LIFESTYLE": (2_700_000, 1_350_000, 450_000)}
        for plan in budgets.list_plans(d1["owner"], d1["month"]):
            by_priority = {p: sum(a.allocated_amount for a in plan.allocations if a.budget_expense.priority == p)
                           for p in ("P0", "P1", "P2")}
            assert by_priority["P0"] == 2_500_000
            assert (by_priority["P1"], by_priority["P2"], plan.planned_savings) == expected[plan.plan_type]
            assert sum(a.allocated_amount for a in plan.allocations) + plan.planned_savings == 7_000_000
            assert all(a.allocated_amount > 0 for a in plan.allocations)
            assert all(a.allocated_amount >= a.budget_expense.minimum_amount for a in plan.allocations
                       if a.budget_expense.priority == "P1")


def test_BP_12_reject_missing_required_P0(app, d1):
    with app.app_context():
        water = next(e for e in budgets.list_expenses(d1["owner"], d1["month"]) if e.expense_name == "Water")
        budgets.delete_expense(d1["owner"], d1["month"], water.id)
        with pytest.raises(BudgetError, match="Required P0"):
            budgets.generate_budget_plans(d1["owner"], d1["month"])
        assert budgets.list_plans(d1["owner"], d1["month"]) == []


def test_BP_13_reject_insufficient_funds(app, d1):
    with app.app_context():
        month = db.session.get(BudgetMonth, d1["month"])
        month.available_vnd = 2_000_000
        db.session.commit()
        with pytest.raises(BudgetError, match="shortfall"):
            budgets.generate_budget_plans(d1["owner"], d1["month"])
        assert budgets.list_plans(d1["owner"], d1["month"]) == []


# UC27: Invalid MANUAL edits; BP-14 editor appearance is manual-only

def test_BP_15_reject_forged_P0_field(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        values = _editable(balanced)
        values[str(_expense_allocation(balanced, "Rent").budget_expense_id)] = 1
        token = budgets.customization_fingerprint(d1["owner"], d1["month"], balanced.id)
        with pytest.raises(BudgetError):
            budgets.save_manual_plan(d1["owner"], d1["month"], balanced.id, values, expected_fingerprint=token)
        assert len(budgets.list_plans(d1["owner"], d1["month"])) == 3


def test_BP_16_reject_P1_below_minimum(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        values = _editable(balanced)
        values[str(_expense_allocation(balanced, "Food").budget_expense_id)] = 1_199_000
        token = budgets.customization_fingerprint(d1["owner"], d1["month"], balanced.id)
        with pytest.raises(BudgetError, match="minimum"):
            budgets.save_manual_plan(d1["owner"], d1["month"], balanced.id, values, expected_fingerprint=token)
        assert len(budgets.list_plans(d1["owner"], d1["month"])) == 3


def test_BP_17_reject_overbudget_MANUAL(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        values = _editable(balanced)
        values[str(_expense_allocation(balanced, "Food").budget_expense_id)] = 7_001_000
        token = budgets.customization_fingerprint(d1["owner"], d1["month"], balanced.id)
        with pytest.raises(BudgetError, match="exceed"):
            budgets.save_manual_plan(d1["owner"], d1["month"], balanced.id, values, expected_fingerprint=token)
        assert len(budgets.list_plans(d1["owner"], d1["month"])) == 3


def test_BP_18_reject_malformed_manual_submission(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        valid = _editable(balanced)
        food = str(_expense_allocation(balanced, "Food").budget_expense_id)
        token = budgets.customization_fingerprint(d1["owner"], d1["month"], balanced.id)
        malformed = []
        missing = dict(valid); missing.pop(food); malformed.append(missing)
        for bad in ("-1", "0", "1.5", "abc", ""):
            changed = dict(valid); changed[food] = bad; malformed.append(changed)
        for values in malformed:
            with pytest.raises(BudgetError):
                budgets.save_manual_plan(d1["owner"], d1["month"], balanced.id, values, expected_fingerprint=token)
        assert len(budgets.list_plans(d1["owner"], d1["month"])) == 3


def test_BP_19_reject_stale_manual_edit(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        initial = _editable(balanced)
        food = str(_expense_allocation(balanced, "Food").budget_expense_id)
        old_token = budgets.customization_fingerprint(d1["owner"], d1["month"], balanced.id)
        first = dict(initial); first[food] += 10_000
        saved = budgets.save_manual_plan(d1["owner"], d1["month"], balanced.id, first, expected_fingerprint=old_token)
        saved_id, savings = saved.id, saved.planned_savings
        stale = dict(initial); stale[food] += 20_000
        with pytest.raises(budgets.BudgetConflict):
            budgets.save_manual_plan(d1["owner"], d1["month"], balanced.id, stale, expected_fingerprint=old_token)
        persisted = budgets.get_plan(d1["owner"], d1["month"], saved_id)
        assert persisted.planned_savings == savings


# UC10: Confirm and persist originals

def test_BP_20_confirm_generated_and_reload(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        plan_id = balanced.id
        budgets.confirm_plan(d1["owner"], d1["month"], plan_id)
        db.session.remove()
        plan = budgets.get_plan(d1["owner"], d1["month"], plan_id)
        assert plan.status == "CONFIRMED" and plan.planned_savings == 900_000
        assert len(plan.allocations) == 7
        assert sum(a.allocated_amount for a in plan.allocations) + plan.planned_savings == 7_000_000
        assert sum(p.status == "CONFIRMED" for p in budgets.list_plans(d1["owner"], d1["month"])) == 1
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0


def test_BP_21_confirm_custom_plan_1250000_savings(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        manual = _save_manual(d1, balanced, {"Food": 2_000_000,
                                            "Transportation": 675_000,
                                            "Entertainment": 575_000})
        assert manual.planned_savings == 1_250_000 and manual.status == "GENERATED"
        snapshot = budgets.plan_draft_fingerprint(manual)
        mid = manual.id
        budgets.confirm_plan(d1["owner"], d1["month"], mid, expected_fingerprint=snapshot)
        db.session.remove()
        persisted = budgets.get_plan(d1["owner"], d1["month"], mid)
        assert persisted.status == "CONFIRMED" and persisted.planned_savings == 1_250_000
        assert len(persisted.allocations) == 7
        assert sum(a.allocated_amount for a in persisted.allocations) == 5_750_000
        assert len(budgets.list_plans(d1["owner"], d1["month"])) == 4


def test_BP_22_reject_confirming_different_plan(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        saving = next(p for p in budgets.list_plans(d1["owner"], d1["month"]) if p.plan_type == "SAVING")
        budgets.confirm_plan(d1["owner"], d1["month"], balanced.id)
        with pytest.raises(budgets.BudgetConflict):
            budgets.confirm_plan(d1["owner"], d1["month"], saving.id)
        assert budgets.confirm_plan(d1["owner"], d1["month"], balanced.id).id == balanced.id
        assert sum(p.status == "CONFIRMED" for p in budgets.list_plans(d1["owner"], d1["month"])) == 1


def test_BP_23_reject_financial_edits_after_confirmation(app, d1):
    with app.app_context():
        balanced = _generate(d1)
        budgets.confirm_plan(d1["owner"], d1["month"], balanced.id)
        original = {a.id: a.allocated_amount for a in balanced.allocations}
        for action in (
            lambda: budgets.generate_budget_plans(d1["owner"], d1["month"]),
            lambda: budgets.save_expense(d1["owner"], d1["month"], _entry(("New", "P2", 100, None, "MONTHLY", None))),
        ):
            with pytest.raises(budgets.BudgetConflict):
                action()
        assert {a.id: a.allocated_amount for a in budgets.get_plan(d1["owner"], d1["month"], balanced.id).allocations} == original


# UC11: Explicit schedule handoff

def test_BP_24_block_scheduling_before_confirmation(app, d2):
    with app.app_context():
        _generate(d2)
        assert expenses.get_schedule_state(d2["owner"], d2["month"]).code == "UNCONFIRMED"
        with pytest.raises(ValidationError):
            expenses.ensure_tasks_for_month(d2["owner"], d2["month"])
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0


def test_BP_25_generate_34_initial_tasks(app, d2):
    with app.app_context():
        balanced = _generate(d2)
        budgets.confirm_plan(d2["owner"], d2["month"], balanced.id)
        assert expenses.get_schedule_state(d2["owner"], d2["month"]).code == "NOT_SCHEDULED"
        tasks = expenses.ensure_tasks_for_month(d2["owner"], d2["month"])
        assert expenses.get_schedule_state(d2["owner"], d2["month"]).code == "READY"
        assert len(tasks) == 34 and all(isinstance(task.id, UUID) for task in tasks)
        assert Counter(task.allocation.budget_expense.expense_name for task in tasks) == {
            "Food": 25, "Transportation": 5, "Rent": 1,
            "Electricity": 1, "Water": 1, "Entertainment": 1,
        }
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_BP_26_dates_due_day_and_exact_integer_split(app, d2):
    with app.app_context():
        balanced = _generate(d2)
        budgets.confirm_plan(d2["owner"], d2["month"], balanced.id)
        tasks = expenses.ensure_tasks_for_month(d2["owner"], d2["month"])
        for allocation in balanced.allocations:
            children = [t for t in tasks if t.allocation_id == allocation.id]
            assert sum(t.original_limit for t in children) == allocation.allocated_amount
            assert all(t.original_limit == t.current_limit for t in children)
            assert all(t.original_limit >= 0 and t.task_status == "PENDING" for t in children)
        food = [t for t in tasks if t.allocation.budget_expense.expense_name == "Food"]
        assert {t.assigned_date for t in food} == {date(2026, 11, n) for n in range(6, 31)}
        weeks = sorted((t for t in tasks if t.allocation.budget_expense.expense_name == "Transportation"), key=lambda t: t.assigned_date)
        assert len(weeks) == 5
        assert (weeks[0].assigned_date, weeks[0].period_end) == (date(2026, 11, 6), date(2026, 11, 8))
        assert (weeks[-1].assigned_date, weeks[-1].period_end) == (date(2026, 11, 30), date(2026, 11, 30))
        for t in tasks:
            if t.allocation.budget_expense.expense_name in {"Electricity", "Water"}:
                assert t.payment_due_date == date(2026, 11, 30)
        assert sum(t.original_limit for t in tasks) + balanced.planned_savings == 7_000_000


def test_BP_27_repeat_schedule_preserves_saved_tasks(app, d2):
    with app.app_context():
        balanced = _generate(d2)
        budgets.confirm_plan(d2["owner"], d2["month"], balanced.id)
        first = expenses.ensure_tasks_for_month(d2["owner"], d2["month"])
        ids = {t.id for t in first}
        selected = first[0]
        selected_id = selected.id
        selected.current_limit += 111
        db.session.commit()
        original = selected.original_limit
        second = expenses.ensure_tasks_for_month(d2["owner"], d2["month"])
        assert {t.id for t in second} == ids and len(second) == 34
        persisted = db.session.get(AssignedExpenseTask, selected_id)
        assert persisted.original_limit == original and persisted.current_limit == original + 111
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


# Security: owner-only Budget and Expense service access

def test_BP_29_reject_cross_user_budget_access(app, d1):
    with app.app_context():
        plan = _generate(d1)
        with pytest.raises(budgets.BudgetNotFound):
            budgets.get_plan(d1["other"], d1["month"], plan.id)
        with pytest.raises(budgets.BudgetNotFound):
            budgets.save_expense(d1["other"], d1["month"], _entry(("Attack", "P2", 100, None, "MONTHLY", None)))
        assert len(budgets.list_expenses(d1["owner"], d1["month"])) == 7


def test_BP_30_reject_cross_user_schedule_access(app, d2):
    with app.app_context():
        balanced = _generate(d2)
        budgets.confirm_plan(d2["owner"], d2["month"], balanced.id)
        original = expenses.ensure_tasks_for_month(d2["owner"], d2["month"])
        ids = {t.id for t in original}
        with pytest.raises(expenses.NotFoundError):
            expenses.get_schedule_state(d2["other"], d2["month"])
        with pytest.raises(expenses.NotFoundError):
            expenses.ensure_tasks_for_month(d2["other"], d2["month"])
        assert set(db.session.scalars(db.select(AssignedExpenseTask.id))) == ids
