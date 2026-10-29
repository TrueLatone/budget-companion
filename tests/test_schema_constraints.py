"""Exercise the same financial invariants on ORM-created and migrated databases."""

from datetime import date
import uuid

import pytest
from flask_migrate import upgrade
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAdjustment, BudgetAdjustmentDetail,
    BudgetAllocation, BudgetExpense, BudgetMonth, BudgetPlan, ExpenseCategory,
    ExpenseRecord, MonthlyReview, Recommendation, User, UserPreference,
)


@pytest.fixture(params=["metadata", "migrations"])
def schema_app(request, tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "schema-test-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "schema.sqlite").as_posix(),
        "WTF_CSRF_ENABLED": False,
    })
    with application.app_context():
        if request.param == "metadata":
            db.create_all()
        else:
            upgrade()
        try:
            yield application
        finally:
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def graph(schema_app):
    user = User(email="schema@example.com", password_hash="test-only")
    month = BudgetMonth(
        user=user, month_start=date(2026, 10, 1),
        tracking_start_date=date(2026, 10, 15), available_vnd=5_000_000_000,
    )
    category = ExpenseCategory(user=user, category_name="Food")
    expense = BudgetExpense(
        budget_month=month, category=category, expense_name="Meals", priority="P1",
        allocation_frequency="DAILY", minimum_amount=500_000,
    )
    plan = BudgetPlan(budget_month=month, plan_type="BALANCED", status="CONFIRMED")
    allocation = BudgetAllocation(plan=plan, budget_expense=expense, allocated_amount=1_500_000)
    task = AssignedExpenseTask(
        allocation=allocation, assigned_date=date(2026, 10, 15),
        period_end=date(2026, 10, 15), original_limit=50_000, current_limit=50_000,
    )
    db.session.add_all([user, month, category, expense, plan, allocation, task])
    db.session.commit()
    return {"user": user, "month": month, "category": category, "expense": expense,
            "plan": plan, "allocation": allocation, "task": task}


def record_values(graph, **changes):
    values = dict(
        budget_month_id=graph["month"].id, category_id=graph["category"].id,
        amount=25_000, expense_date=date(2026, 10, 15),
        record_type="UNEXPECTED", priority="P1",
    )
    values.update(changes)
    return values


def reject(instance):
    db.session.add(instance)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_full_relationship_graph_round_trips(graph):
    recommendation = Recommendation(
        budget_month=graph["month"], reason="Reported overspending",
        expected_impact="Protect future limits", proposed_changes={"tasks": []},
        status="ACCEPTED",
    )
    adjustment = BudgetAdjustment(
        recommendation=recommendation, effective_date=date(2026, 10, 16),
        reason="Accepted suggestion", adjustment_type="RECOMMENDATION",
    )
    detail = BudgetAdjustmentDetail(
        adjustment=adjustment, task=graph["task"], previous_limit=50_000, new_limit=45_000,
    )
    review = MonthlyReview(budget_month=graph["month"], rating=4, comment="Helpful")
    preference = UserPreference(user=graph["user"], preferred_plan_type="BALANCED")
    db.session.add_all([recommendation, adjustment, detail, review, preference])
    db.session.commit()
    db.session.expire_all()

    assert graph["user"].preference is preference
    assert graph["user"].expense_categories == [graph["category"]]
    assert graph["month"].review is review
    assert graph["month"].plans == [graph["plan"]]
    assert graph["month"].recommendations == [recommendation]
    assert graph["month"].available_vnd == 5_000_000_000
    assert recommendation.adjustment.details == [detail]
    assert detail.task.allocation.plan.budget_month is graph["month"]
    assert graph["expense"].allocations == [graph["allocation"]]
    assert preference.budget_alerts_enabled is True


def test_multiple_planned_transactions_per_task_are_preserved(graph):
    for amount, token in [(25_000, "breakfast"), (30_000, "lunch")]:
        db.session.add(ExpenseRecord(**record_values(
            graph, record_type="PLANNED", task_id=graph["task"].id,
            priority=None, amount=amount, idempotency_key=token,
        )))
    db.session.commit()
    assert len(graph["task"].records) == 2
    assert sum(record.amount for record in graph["task"].records) == 55_000
    assert graph["task"].original_limit == 50_000


@pytest.mark.parametrize("changes", [
    {"amount": 0}, {"amount": -1}, {"record_type": "OTHER"},
    {"priority": None}, {"priority": "P3"}, {"category_id": None},
    {"budget_impact_scope": "YEARLY"},
    {"record_type": "PLANNED"},
    {"record_type": "FUNDS_ADDED", "priority": None},
    {"record_type": "FUNDS_ADDED", "category_id": None},
    {"record_type": "FUNDS_ADDED", "category_id": None, "priority": None,
     "budget_impact_scope": "DAILY"},
])
def test_invalid_transaction_shapes_are_rejected(graph, changes):
    reject(ExpenseRecord(**record_values(graph, **changes)))


def test_task_links_only_allow_planned_transactions(graph):
    reject(ExpenseRecord(**record_values(graph, task_id=graph["task"].id)))


def test_planned_transaction_requires_category(graph):
    reject(ExpenseRecord(**record_values(
        graph, record_type="PLANNED", task_id=graph["task"].id, category_id=None,
    )))


@pytest.mark.parametrize("scope", [None, "DAILY", "WEEKLY", "MONTHLY"])
def test_unexpected_scope_and_funds_addition_are_representable(graph, scope):
    db.session.add_all([
        ExpenseRecord(**record_values(graph, budget_impact_scope=scope)),
        ExpenseRecord(**record_values(
            graph, record_type="FUNDS_ADDED", priority=None, category_id=None,
        )),
    ])
    db.session.commit()
    assert len(graph["month"].expense_records) == 2


def test_idempotency_is_scoped_to_budget_month(graph):
    db.session.add(ExpenseRecord(**record_values(graph, idempotency_key="request-1")))
    db.session.commit()
    reject(ExpenseRecord(**record_values(graph, idempotency_key="request-1")))
    next_month = BudgetMonth(
        user=graph["user"], month_start=date(2026, 11, 1), available_vnd=100_000,
    )
    db.session.add(next_month)
    db.session.flush()
    db.session.add(ExpenseRecord(**record_values(
        graph, budget_month_id=next_month.id, expense_date=date(2026, 11, 1),
        idempotency_key="request-1",
    )))
    db.session.commit()
    assert next_month.tracking_start_date == date(2026, 11, 1)


def test_multiple_candidates_but_only_one_confirmed_plan(graph):
    db.session.add_all([
        BudgetPlan(budget_month_id=graph["month"].id, plan_type="SAVING"),
        BudgetPlan(budget_month_id=graph["month"].id, plan_type="LIFESTYLE"),
    ])
    db.session.commit()
    reject(BudgetPlan(
        budget_month_id=graph["month"].id, plan_type="MANUAL", status="CONFIRMED",
    ))
    assert len(graph["month"].plans) == 3


def test_unique_allocation_and_logical_task_period(graph):
    reject(BudgetAllocation(
        plan_id=graph["plan"].id, budget_expense_id=graph["expense"].id, allocated_amount=1,
    ))
    reject(AssignedExpenseTask(
        allocation_id=graph["allocation"].id, assigned_date=graph["task"].assigned_date,
        period_end=date(2026, 10, 16), original_limit=1, current_limit=1,
    ))


@pytest.mark.parametrize("changes", [
    {"period_end": date(2026, 10, 15)}, {"original_limit": -1},
    {"current_limit": -1}, {"task_status": "OVER_BUDGET"},
    {"task_status": "UNRECORDED"}, {"payment_status": "PROCESSED"},
])
def test_task_limits_periods_and_stored_states(graph, changes):
    values = dict(
        allocation_id=graph["allocation"].id, assigned_date=date(2026, 10, 16),
        period_end=date(2026, 10, 16), original_limit=0, current_limit=0,
    )
    values.update(changes)
    reject(AssignedExpenseTask(**values))


def test_zero_limits_and_explicit_no_expense_are_representable(graph):
    task = AssignedExpenseTask(
        allocation_id=graph["allocation"].id, assigned_date=date(2026, 10, 16),
        period_end=date(2026, 10, 16), original_limit=0, current_limit=0,
        task_status="NO_EXPENSE", payment_status="UNPAID",
    )
    db.session.add(task)
    db.session.commit()
    assert task.records == []


@pytest.mark.parametrize("owner_kind", ["builtin", "owned"])
def test_category_names_are_unique_after_trim_and_case_normalization(graph, owner_kind):
    owner = graph["user"].id if owner_kind == "owned" else None
    db.session.add(ExpenseCategory(user_id=owner, category_name="Transport"))
    db.session.commit()
    reject(ExpenseCategory(user_id=owner, category_name=" transport "))


def test_categories_allow_separate_owner_and_builtin_namespaces(graph):
    other = User(email="other@example.com", password_hash="test-only")
    db.session.add_all([
        ExpenseCategory(category_name="Food"),
        ExpenseCategory(user=other, category_name="Food"),
    ])
    db.session.commit()
    assert db.session.scalar(db.select(db.func.count(ExpenseCategory.id))) == 3


@pytest.mark.parametrize("field,value", [
    ("priority", "P3"), ("allocation_frequency", "DATE"), ("minimum_amount", 0),
    ("minimum_amount", -1), ("estimated_amount", -1), ("due_day", 0), ("due_day", 32),
])
def test_invalid_planning_inputs_are_rejected(graph, field, value):
    values = dict(
        budget_month_id=graph["month"].id, category_id=graph["category"].id,
        expense_name="Bill", priority="P0", allocation_frequency="MONTHLY",
    )
    values[field] = value
    reject(BudgetExpense(**values))


def test_preferences_and_reviews_are_one_per_parent(graph):
    db.session.add_all([
        UserPreference(user_id=graph["user"].id),
        MonthlyReview(budget_month_id=graph["month"].id),
    ])
    db.session.commit()
    reject(UserPreference(user_id=graph["user"].id))
    reject(MonthlyReview(budget_month_id=graph["month"].id))


@pytest.mark.parametrize("rating", [0, 6])
def test_rating_bounds(graph, rating):
    reject(MonthlyReview(budget_month_id=graph["month"].id, rating=rating))


def test_recommendation_can_trigger_at_most_one_adjustment(graph):
    recommendation = Recommendation(
        budget_month=graph["month"], reason="Reason", expected_impact="Impact",
        proposed_changes={"tasks": []},
    )
    db.session.add(recommendation)
    db.session.flush()
    values = dict(recommendation_id=recommendation.id, effective_date=date(2026, 10, 16),
                  reason="Reason", adjustment_type="RECOMMENDATION")
    db.session.add(BudgetAdjustment(**values))
    db.session.commit()
    reject(BudgetAdjustment(**values))


def test_adjustment_detail_uniqueness_and_limit_bounds(graph):
    adjustment = BudgetAdjustment(
        effective_date=date(2026, 10, 16), reason="Manual change", adjustment_type="MANUAL",
    )
    db.session.add(adjustment)
    db.session.flush()
    values = dict(adjustment_id=adjustment.id, task_id=graph["task"].id,
                  previous_limit=50_000, new_limit=45_000)
    reject(BudgetAdjustmentDetail(**{**values, "new_limit": -1}))
    # The failed transaction also rolls back the uncommitted adjustment.
    db.session.add(adjustment)
    db.session.flush()
    values["adjustment_id"] = adjustment.id
    db.session.add(BudgetAdjustmentDetail(**values))
    db.session.commit()
    reject(BudgetAdjustmentDetail(**values))


def test_foreign_keys_reject_unknown_tasks(graph):
    reject(ExpenseRecord(**record_values(
        graph, record_type="PLANNED", task_id=uuid.uuid4(), priority=None,
    )))


def test_referenced_financial_history_cannot_be_deleted(graph):
    # Even with relationships loaded, the ORM must let RESTRICT protect history.
    assert graph["category"].budget_expenses
    db.session.delete(graph["category"])
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    db.session.delete(graph["user"])
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.get(BudgetMonth, graph["month"].id) is not None


def test_allocation_amount_and_plan_savings_bounds(graph):
    reject(BudgetPlan(
        budget_month_id=graph["month"].id, plan_type="SAVING", planned_savings=-1,
    ))
    plan = BudgetPlan(budget_month_id=graph["month"].id, plan_type="SAVING")
    db.session.add(plan)
    db.session.commit()
    reject(BudgetAllocation(
        plan_id=plan.id, budget_expense_id=graph["expense"].id, allocated_amount=0,
    ))


def test_tracking_constraint_applies_to_both_schema_creation_paths(graph):
    reject(BudgetMonth(
        user_id=graph["user"].id, month_start=date(2026, 11, 1),
        tracking_start_date=date(2025, 11, 15), available_vnd=100,
    ))
    # Use Core to bypass the ORM's compatibility default and test NOT NULL itself.
    with pytest.raises(IntegrityError):
        db.session.execute(db.insert(BudgetMonth).values(
            id=uuid.uuid4(), user_id=graph["user"].id, month_start=date(2026, 11, 1),
            tracking_start_date=None, available_vnd=100,
        ))
        db.session.commit()
    db.session.rollback()
