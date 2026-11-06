"""KAN-11 follow-up: F06 customization and Budget -> initial schedule handoff.

All data is synthetic and created in the disposable test DB supplied by
conftest.py. The Expense module is exercised as a *consumer*, not modified.
"""
from collections import Counter
from datetime import date
from uuid import UUID

import pytest

from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAllocation, BudgetExpense, BudgetMonth,
    BudgetPlan, ExpenseCategory, ExpenseRecord, User,
)
from app.modules.budgets import services as budget_service
from app.modules.budgets.rules import BudgetError
from app.modules.expenses import services as expense_service
from app.modules.expenses.validators import ValidationError


@pytest.fixture
def scenario(app):
    with app.app_context():
        owner = User(email="jira-budget-owner@example.com", password_hash="test")
        other = User(email="jira-budget-outsider@example.com", password_hash="test")
        db.session.add_all([owner, other])
        db.session.flush()
        month = BudgetMonth(
            user_id=owner.id, month_start=date(2026, 11, 1),
            tracking_start_date=date(2026, 11, 6), available_vnd=7_000_000,
        )
        category = ExpenseCategory(user_id=owner.id, category_name="Jira budget test")
        db.session.add_all([month, category])
        db.session.flush()
        for name, priority, estimate, minimum, frequency, due in [
            ("Rent", "P0", 2_000_000, None, "MONTHLY", 5),
            ("Electricity", "P0", 200_000, None, "MONTHLY", 31),
            ("Water", "P0", 100_000, None, "MONTHLY", 31),
            ("Food", "P1", None, 1_000_000, "DAILY", None),
            ("Transportation", "P1", None, 200_000, "WEEKLY", None),
            ("Entertainment", "P2", 0, None, "MONTHLY", None),
        ]:
            db.session.add(BudgetExpense(
                budget_month_id=month.id, category_id=category.id, expense_name=name,
                priority=priority, estimated_amount=estimate, minimum_amount=minimum,
                allocation_frequency=frequency, due_day=due,
            ))
        db.session.commit()
        return {"owner": owner.id, "other": other.id, "month": month.id}


@pytest.fixture
def owner_client(client, scenario):
    with client.session_transaction() as cookie:
        cookie["user_id"] = str(scenario["owner"])
        cookie["active_budget_month_id"] = str(scenario["month"])
    return client


def _generate(scenario):
    plans = budget_service.generate_budget_plans(scenario["owner"], scenario["month"])
    return next(p for p in plans if p.plan_type == "BALANCED")


def _editable(plan):
    return {str(a.budget_expense_id): a.allocated_amount for a in plan.allocations
            if a.budget_expense.priority in ("P1", "P2")}


def _food_id(plan):
    return str(next(a.budget_expense_id for a in plan.allocations
                    if a.budget_expense.expense_name == "Food"))


def _assert_conserved(scenario, plan):
    assert len(plan.allocations) == 6
    assert sum(a.allocated_amount for a in plan.allocations) + plan.planned_savings == 7_000_000
    assert all(a.allocated_amount > 0 for a in plan.allocations)
    assert all(a.budget_expense.budget_month_id == scenario["month"] for a in plan.allocations)
    assert all(a.allocated_amount == a.budget_expense.estimated_amount for a in plan.allocations
               if a.budget_expense.priority == "P0")
    assert all(a.allocated_amount >= a.budget_expense.minimum_amount for a in plan.allocations
               if a.budget_expense.priority == "P1" and a.budget_expense.minimum_amount is not None)


def test_f06_manual_persists_without_rewriting_original_candidates(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        initial = {a.budget_expense_id: a.allocated_amount for a in balanced.allocations}
        source_id, source_savings = balanced.id, balanced.planned_savings
        amounts = _editable(balanced)
        amounts[_food_id(balanced)] += 100_000
        token = budget_service.customization_fingerprint(scenario["owner"], scenario["month"], balanced.id)
        manual = budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], source_id,
            amounts, expected_fingerprint=token, auto_savings=True,
        )
        manual_id = manual.id
        assert manual.plan_type == "MANUAL" and manual.status == "GENERATED"
        assert manual_id != source_id
        assert manual.planned_savings == source_savings - 100_000
        _assert_conserved(scenario, manual)
        assert budget_service.get_plan(scenario["owner"], scenario["month"], source_id).planned_savings == source_savings
        assert {a.budget_expense_id: a.allocated_amount for a in balanced.allocations} == initial
        assert Counter(plan.plan_type for plan in budget_service.list_plans(
            scenario["owner"], scenario["month"])) == {
                "SAVING": 1, "BALANCED": 1, "LIFESTYLE": 1, "MANUAL": 1,
            }
        db.session.remove()
        reopened = budget_service.get_plan(scenario["owner"], scenario["month"], manual_id)
        assert reopened.id == manual_id and reopened.planned_savings == source_savings - 100_000
        _assert_conserved(scenario, reopened)


def test_f06_newer_manual_draft_rejects_stale_generated_tab(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        saved = _editable(balanced)
        food = _food_id(balanced)
        token_from_two_tabs = budget_service.customization_fingerprint(
            scenario["owner"], scenario["month"], balanced.id)
        saved[food] += 50_000
        manual = budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], balanced.id,
            saved, expected_fingerprint=token_from_two_tabs, auto_savings=True,
        )
        initial_manual_id = manual.id
        savings = manual.planned_savings
        stale_amounts = _editable(balanced)
        stale_amounts[food] += 150_000
        with pytest.raises(budget_service.BudgetConflict, match="another tab"):
            budget_service.save_manual_plan(
                scenario["owner"], scenario["month"], balanced.id, stale_amounts,
                expected_fingerprint=token_from_two_tabs, auto_savings=True,
            )
        current = budget_service.get_plan(scenario["owner"], scenario["month"], initial_manual_id)
        assert current.planned_savings == savings
        new_token = budget_service.customization_fingerprint(
            scenario["owner"], scenario["month"], current.id)
        next_amounts = _editable(current)
        next_amounts[food] += 10_000
        updated = budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], current.id, next_amounts,
            expected_fingerprint=new_token, auto_savings=True,
        )
        assert updated.id == initial_manual_id and updated.planned_savings == savings - 10_000
        assert sum(p.plan_type == "MANUAL" for p in budget_service.list_plans(
            scenario["owner"], scenario["month"])) == 1


@pytest.mark.parametrize("bad_value", ["", "-1", "0", "not-number", "1.5", "999999999999999999999999999999"])
def test_f06_bad_amounts_never_create_partial_draft(app, scenario, bad_value):
    with app.app_context():
        balanced = _generate(scenario)
        values = _editable(balanced)
        values[_food_id(balanced)] = bad_value
        token = budget_service.customization_fingerprint(scenario["owner"], scenario["month"], balanced.id)
        with pytest.raises(BudgetError):
            budget_service.save_manual_plan(
                scenario["owner"], scenario["month"], balanced.id,
                values, expected_fingerprint=token, auto_savings=True,
            )
        assert len(budget_service.list_plans(scenario["owner"], scenario["month"])) == 3


def test_f06_rejects_below_minimum_overbudget_missing_or_injected_p0(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        source_id = balanced.id
        token = budget_service.customization_fingerprint(scenario["owner"], scenario["month"], source_id)
        valid = _editable(balanced)
        food = _food_id(balanced)
        cases = []
        below = dict(valid); below[food] = "999999"; cases.append(below)
        over = dict(valid); over[food] = "7000001"; cases.append(over)
        missing = dict(valid); missing.pop(food); cases.append(missing)
        injected = dict(valid)
        p0_id = str(next(a.budget_expense_id for a in balanced.allocations
                         if a.budget_expense.priority == "P0"))
        injected[p0_id] = "1"; cases.append(injected)
        for invalid in cases:
            with pytest.raises(BudgetError):
                budget_service.save_manual_plan(
                    scenario["owner"], scenario["month"], source_id,
                    invalid, expected_fingerprint=token, auto_savings=True,
                )
        assert len(budget_service.list_plans(scenario["owner"], scenario["month"])) == 3


def test_f06_missing_stale_or_changed_fund_token_rejected(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        values = _editable(balanced)
        expected = budget_service.customization_fingerprint(
            scenario["owner"], scenario["month"], balanced.id)
        for missing in (None, "", "not-a-version", "a" * 64):
            with pytest.raises(budget_service.BudgetConflict):
                budget_service.save_manual_plan(
                    scenario["owner"], scenario["month"], balanced.id,
                    values, expected_fingerprint=missing, auto_savings=True,
                )
        month = db.session.get(BudgetMonth, scenario["month"])
        month.available_vnd = 7_000_001
        db.session.commit()
        with pytest.raises(budget_service.BudgetConflict):
            budget_service.save_manual_plan(
                scenario["owner"], scenario["month"], balanced.id,
                values, expected_fingerprint=expected, auto_savings=True,
            )
        assert len(budget_service.list_plans(scenario["owner"], scenario["month"])) == 3


def test_f06_post_guards_p0_duplicates_and_invalid_form(app, scenario, owner_client):
    with app.app_context():
        balanced = _generate(scenario)
        source_id = balanced.id
        valid = _editable(balanced)
        token = budget_service.customization_fingerprint(
            scenario["owner"], scenario["month"], source_id)
        p0_id = str(next(a.budget_expense_id for a in balanced.allocations
                         if a.budget_expense.priority == "P0"))
    path = f"/budget/{scenario['month']}/plans/{source_id}/customize"
    assert owner_client.get(path).status_code == 200
    request = {"plan_snapshot": token} | {"allocation_" + key: str(amount)
                                            for key, amount in valid.items()}
    assert owner_client.post(path, data=request | {"allocation_" + p0_id: "1"}).status_code == 400
    assert owner_client.post(path, data={"plan_snapshot": token}).status_code == 400
    assert owner_client.post(path, data=request | {"plan_snapshot": ""}).status_code == 409
    assert owner_client.post(path, data=request).status_code == 302
    with app.app_context():
        plans = budget_service.list_plans(scenario["owner"], scenario["month"])
        assert len(plans) == 4
        assert sum(p.plan_type == "MANUAL" for p in plans) == 1


def test_f06_confirms_once_and_prevents_any_further_budget_changes(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        values = _editable(balanced)
        token = budget_service.customization_fingerprint(scenario["owner"], scenario["month"], balanced.id)
        manual = budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], balanced.id, values,
            expected_fingerprint=token, auto_savings=True,
        )
        confirmed = budget_service.confirm_plan(scenario["owner"], scenario["month"], manual.id)
        assert confirmed.id == manual.id and confirmed.status == "CONFIRMED"
        assert budget_service.confirm_plan(scenario["owner"], scenario["month"], manual.id).id == manual.id
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        with pytest.raises(budget_service.BudgetConflict):
            budget_service.confirm_plan(scenario["owner"], scenario["month"], balanced.id)
        with pytest.raises(budget_service.BudgetConflict):
            budget_service.generate_budget_plans(scenario["owner"], scenario["month"])
        with pytest.raises(budget_service.BudgetConflict):
            budget_service.save_manual_plan(
                scenario["owner"], scenario["month"], manual.id, values,
                expected_fingerprint=token, auto_savings=True,
            )



def test_f06_manual_confirm_requires_current_saved_snapshot(app, scenario, owner_client):
    with app.app_context():
        balanced = _generate(scenario)
        source = balanced.id
        manual = budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], source, _editable(balanced),
            expected_fingerprint=budget_service.customization_fingerprint(
                scenario["owner"], scenario["month"], source), auto_savings=True,
        )
        manual_id = manual.id
        old_snapshot = budget_service.plan_draft_fingerprint(manual)
        values = _editable(manual)
        values[_food_id(manual)] += 100_000
        budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], manual_id, values,
            expected_fingerprint=budget_service.customization_fingerprint(
                scenario["owner"], scenario["month"], manual_id), auto_savings=True,
        )
        new_snapshot = budget_service.plan_draft_fingerprint(
            budget_service.get_plan(scenario["owner"], scenario["month"], manual_id))
        assert old_snapshot != new_snapshot
    path = f"/budget/{scenario['month']}/plans/{manual_id}/confirm"
    assert owner_client.post(path, data={"confirm_snapshot": old_snapshot}).status_code == 409
    assert owner_client.post(path, data={}).status_code == 409
    with app.app_context():
        assert budget_service.get_plan(scenario["owner"], scenario["month"], manual_id).status == "GENERATED"
    assert owner_client.post(path, data={"confirm_snapshot": new_snapshot}).status_code == 302
    with app.app_context():
        assert budget_service.get_plan(scenario["owner"], scenario["month"], manual_id).status == "CONFIRMED"
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0

def test_schedule_handoff_persists_only_confirmed_uuid_allocations_and_rounding(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        manual = budget_service.save_manual_plan(
            scenario["owner"], scenario["month"], balanced.id, _editable(balanced),
            expected_fingerprint=budget_service.customization_fingerprint(
                scenario["owner"], scenario["month"], balanced.id),
            auto_savings=True,
        )
        confirmed_id = manual.id
        assert expense_service.get_schedule_state(scenario["owner"], scenario["month"]).code == "UNCONFIRMED"
        with pytest.raises(ValidationError):
            expense_service.ensure_tasks_for_month(scenario["owner"], scenario["month"])
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        budget_service.confirm_plan(scenario["owner"], scenario["month"], confirmed_id)
        assert expense_service.get_schedule_state(scenario["owner"], scenario["month"]).code == "NOT_SCHEDULED"
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        first = expense_service.ensure_tasks_for_month(scenario["owner"], scenario["month"])
        assert expense_service.get_schedule_state(scenario["owner"], scenario["month"]).code == "READY"
        assert first and all(isinstance(task.id, UUID) for task in first)
        before_ids = {task.id for task in first}
        persisted = budget_service.get_plan(scenario["owner"], scenario["month"], confirmed_id)
        for alloc in persisted.allocations:
            tasks = list(db.session.scalars(db.select(AssignedExpenseTask).where(
                AssignedExpenseTask.allocation_id == alloc.id)))
            assert tasks and all(task.assigned_date >= date(2026, 11, 6) for task in tasks)
            assert sum(t.original_limit for t in tasks) == alloc.allocated_amount
            assert all(t.original_limit == t.current_limit and t.task_status == "PENDING" for t in tasks)
        assert sum(t.original_limit for t in first) + persisted.planned_savings == 7_000_000
        assert all(t.allocation.plan_id == confirmed_id for t in first)
        assert len(first) == 34  # 25 Food days + 5 Transportation weeks + 4 monthly bills
        food_tasks = [t for t in first if t.allocation.budget_expense.expense_name == "Food"]
        assert len(food_tasks) == 25
        assert {t.assigned_date for t in food_tasks} == {
            date(2026, 11, day) for day in range(6, 31)
        }
        weekly = sorted((t for t in first
                         if t.allocation.budget_expense.expense_name == "Transportation"),
                        key=lambda t: t.assigned_date)
        assert len(weekly) == 5 and weekly[0].assigned_date == date(2026, 11, 6)
        assert weekly[0].period_end == date(2026, 11, 8)
        assert weekly[-1].assigned_date == weekly[-1].period_end == date(2026, 11, 30)
        for task in first:
            if task.allocation.budget_expense.expense_name in {"Electricity", "Water"}:
                assert task.payment_due_date == date(2026, 11, 30)  # day 31 is clipped
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0
        # Repeated scheduling must not rewrite records or assign different UUIDs.
        second = expense_service.ensure_tasks_for_month(scenario["owner"], scenario["month"])
        assert {task.id for task in second} == before_ids
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_schedule_retries_preserve_downstream_mutable_limits(app, scenario, owner_client):
    with app.app_context():
        balanced = _generate(scenario)
        budget_service.confirm_plan(scenario["owner"], scenario["month"], balanced.id)
        tasks = expense_service.ensure_tasks_for_month(scenario["owner"], scenario["month"])
        target = next(t for t in tasks if t.allocation.budget_expense.expense_name == "Food")
        initial_limit = target.original_limit
        target.current_limit = initial_limit + 17
        target_id = target.id
        db.session.commit()
    path = f"/budget/{scenario['month']}/schedule?view=day&date=2026-11-06"
    assert owner_client.get(path).status_code == 200
    with app.app_context():
        # Budget page is read-only, and a reschedule must preserve mutable data
        # that may be owned by Expense Planning. No check-in functionality added.
        state = db.session.get(AssignedExpenseTask, target_id)
        assert state.current_limit == initial_limit + 17
        expense_service.ensure_tasks_for_month(scenario["owner"], scenario["month"])
        saved = db.session.get(AssignedExpenseTask, target_id)
        assert saved.original_limit == initial_limit
        assert saved.current_limit == initial_limit + 17
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_cross_account_cannot_customize_confirm_or_schedule(app, scenario):
    with app.app_context():
        balanced = _generate(scenario)
        values = _editable(balanced)
        for action in (
            lambda: budget_service.customization_fingerprint(
                scenario["other"], scenario["month"], balanced.id),
            lambda: budget_service.save_manual_plan(
                scenario["other"], scenario["month"], balanced.id, values,
                expected_fingerprint="a" * 64, auto_savings=True,
            ),
            lambda: budget_service.confirm_plan(scenario["other"], scenario["month"], balanced.id),
            lambda: expense_service.ensure_tasks_for_month(scenario["other"], scenario["month"]),
        ):
            with pytest.raises((budget_service.BudgetNotFound, expense_service.NotFoundError)):
                action()
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
