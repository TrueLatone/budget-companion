"""KAN-27 uses real canonical Budget/Expense services, never CSV/demo data."""

from datetime import date, datetime
from types import SimpleNamespace
import re
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (
    User, BudgetMonth, BudgetExpense, ExpenseCategory, BudgetPlan, BudgetAllocation,
    AssignedExpenseTask, ExpenseRecord, Recommendation, BudgetAdjustment,
    BudgetAdjustmentDetail, MonthlyReview,
)
from app.modules.budget_periods.services import create_budget_month
from app.modules.budgets import services as budgets
from app.modules.budgets.suggestions import SUGGESTED_EXPENSES
from app.modules.expenses import services as expenses, presentation
from app.modules.recommendations import services, rules


def financial_snapshot():
    return {model.__tablename__: list(db.session.execute(db.select(*model.__table__.columns).order_by(model.id)))
            for model in (User, BudgetMonth, ExpenseCategory, BudgetExpense, BudgetPlan,
                          BudgetAllocation, AssignedExpenseTask, ExpenseRecord,
                          BudgetAdjustment, BudgetAdjustmentDetail)}


def row_count(model):
    return db.session.scalar(db.select(db.func.count(model.id)))


@pytest.fixture
def setup(app, client, monkeypatch):
    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(expenses, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 11, 3, 12))
    with app.app_context():
        owner = User(email="analysis@example.com", password_hash=generate_password_hash("test-password"))
        other = User(email="other-analysis@example.com", password_hash="test-only")
        db.session.add_all([owner, other])
        db.session.commit()
        month = create_budget_month(owner.id, "2026-10", 5_000_000, date(2026, 10, 1), planning_unit=1)
        foreign_month = create_budget_month(other.id, "2026-09", 5_000_000, planning_unit=1)
        data = dict(user=owner.id, other=other.id, month=month.id, foreign_month=foreign_month.id)
        budgets.apply_suggested_expenses(owner.id, month.id, [s.key for s in SUGGESTED_EXPENSES if s.selected], {
            s.key: {"estimated_amount": s.example_amount} for s in SUGGESTED_EXPENSES
        })
        budgets.save_expense(owner.id, month.id, dict(expense_name="Entertainment", priority="P2",
            category_name="Fun", allocation_frequency="MONTHLY"))
    with client.session_transaction() as session:
        session["user_id"] = str(data["user"])
    return data


def seed_real_history(data):
    """Ten synthetic test purchases spanning 31 days; all other tasks explicit NO_EXPENSE."""
    plans = budgets.generate_budget_plans(data["user"], data["month"])
    budgets.confirm_plan(data["user"], data["month"], plans[1].id)
    tasks = expenses.ensure_tasks_for_month(data["user"], data["month"])
    food_dates = {1, 5, 9, 13, 17, 21, 25, 31}
    for task in tasks:
        name = task.allocation.budget_expense.expense_name
        amount = 1000 if name == "Food" and task.assigned_date.day in food_dates else None
        if name == "Transportation" and task.assigned_date.day == 1:
            amount = 100_000
        if name == "Rent":
            amount = 1_500_000
        if amount:
            expenses.checkin_task(data["user"], task.id, action="actual", amount_raw=str(amount),
                expense_date_raw="2026-10-31" if name == "Rent" else task.assigned_date.isoformat(),
                idempotency_key=uuid4().hex)
        else:
            expenses.checkin_task(data["user"], task.id, action="no_expense")
    return plans[1].id


@pytest.fixture
def seeded(app, setup):
    with app.app_context():
        return setup | {"plan": seed_real_history(setup)}


def generate(data):
    return services.generate_recommendations(db.session.get(User, data["user"]), "2026-10")


def record(*, amount=1, category_id=None, expense_date=date(2026, 10, 1), record_type="UNEXPECTED", task_id=None):
    return SimpleNamespace(id=uuid4(), amount=amount, category_id=category_id or uuid4(),
        expense_date=expense_date, record_type=record_type, task_id=task_id)


def task(status="PENDING", start=date(2026, 10, 1), end=date(2026, 10, 31)):
    return SimpleNamespace(id=uuid4(), assigned_date=start, period_end=end, task_status=status)


def test_f18_exact_thresholds_and_coverage_are_not_silently_lowered():
    categories = [uuid4(), uuid4(), uuid4()]
    records = [record(category_id=categories[i % 3], expense_date=date(2026, 10, 1 if i < 9 else 30)) for i in range(10)]
    result = rules.build_completeness_result(records, [], date(2026, 10, 31))
    assert result["status"] == "SUFFICIENT" and result["coverage_days"] == 30
    assert result["thresholds"] == dict(complete_transactions=10, categories=3, coverage_days=30, completeness_rate=0.8)
    for changed in (records[:-1], [SimpleNamespace(**(vars(r) | {"category_id": categories[0]})) for r in records],
                    [SimpleNamespace(**(vars(r) | {"expense_date": date(2026, 10, 2)})) for r in records]):
        assert rules.build_completeness_result(changed, [], date(2026, 10, 31))["status"] == "INSUFFICIENT"


def test_incomplete_transaction_is_reported_but_does_not_override_the_80_percent_gate():
    categories = [uuid4(), uuid4(), uuid4()]
    records = [record(category_id=categories[i % 3], expense_date=date(2026, 10, 1 if i < 9 else 30))
               for i in range(10)]
    records.append(record(amount=None, category_id=None))
    data = SimpleNamespace(
        records=records, tasks=[], as_of=date(2026, 10, 31), closed=False,
        allocations=[object()],
        schedule_state=SimpleNamespace(code="READY", message="Ready"),
        month=SimpleNamespace(month_start=date(2026, 10, 1), tracking_start_date=date(2026, 10, 1)),
    )

    rules_result = rules.build_completeness_result(records, [], date(2026, 10, 31))
    service_result = services._completeness(data)

    assert rules_result["incomplete_transaction_count"] == 1
    assert rules_result["completeness_rate"] == round(10 / 11, 4)
    assert all(rules.is_complete_expense_record(item) for item in records[:10])
    assert not rules.is_complete_expense_record(records[-1])
    assert any(issue["type"] == "INCOMPLETE_TRANSACTION" for issue in rules_result["issues"])
    assert rules_result["checks"]["no_incomplete_transactions"] is False
    assert rules_result["status"] == "SUFFICIENT"
    assert service_result["status"] == "SUFFICIENT"
    assert service_result["insufficient_reasons"] == []


def test_completeness_denominator_does_not_count_contradictory_no_expense_as_zero():
    no_expense = task("NO_EXPENSE")
    inconsistent = task("NO_EXPENSE")
    pending = task(end=date(2026, 10, 2))
    records = [record(task_id=inconsistent.id, record_type="PLANNED")]
    result = rules.build_completeness_result(records, [no_expense, inconsistent, pending], date(2026, 10, 31))
    assert result["no_expense_task_count"] == 1 and result["inconsistent_task_count"] == 1
    assert result["complete_item_count"] == 2 and result["expected_item_count"] == 4
    assert result["completeness_rate"] == 0.5


def test_pending_periods_are_missing_only_after_the_period_ends():
    tasks = [task(end=date(2026, 10, 31)), task(start=date(2026, 10, 12), end=date(2026, 10, 18)),
             task(start=date(2026, 10, 16), end=date(2026, 10, 16)), task(start=date(2026, 10, 15), end=date(2026, 10, 15))]
    assert rules.build_completeness_result([], tasks, date(2026, 10, 15))["unrecorded_task_count"] == 0
    assert rules.build_completeness_result([], tasks, date(2026, 10, 15), as_of_closed=True)["unrecorded_task_count"] == 1
    assert rules.build_completeness_result([], tasks, date(2026, 10, 19))["unrecorded_task_count"] == 3


@pytest.mark.parametrize("changes", [{"amount": None}, {"amount": 0}, {"amount": True}, {"amount": 1.5},
                                   {"category_id": None}, {"expense_date": None}])
def test_invalid_transaction_values_stay_incomplete(changes):
    item = record()
    item.__dict__.update(changes)
    result = rules.build_completeness_result([item], [], date(2026, 10, 31))
    assert result["incomplete_transaction_count"] == 1 and result["complete_transaction_count"] == 0


@pytest.mark.parametrize("priority", ["P0", "P1", "P2"])
def test_category_signals_use_exact_money_and_protect_p0(priority):
    assert rules.choose_category_adjustment(110, 100, priority) == (None if priority == "P0" else "REVIEW_OVER_BUDGET")
    assert rules.choose_category_adjustment(80, 100, priority) == (None if priority == "P0" else "REVIEW_UNDER_BUDGET")
    assert rules.choose_category_adjustment(100, 100, priority) is None
    assert rules.choose_category_adjustment(rules.MAX_VND, rules.MAX_VND, priority) is None


def test_category_proposals_protect_p0_p1_minimum_and_savings():
    assert rules.propose_category_adjustment(200, 100, "P0", 500, 100, 1_000) is None

    p1_under = rules.propose_category_adjustment(100, 1_000, "P1", 600, 500, 0)
    assert p1_under["change_amount"] == -100
    assert p1_under["suggested_monthly_amount"] == 500
    assert p1_under["suggested_monthly_amount"] >= 500

    p1_over = rules.propose_category_adjustment(1_500, 1_000, "P1", 600, 500, 200)
    assert p1_over["change_amount"] == 200
    assert p1_over["suggested_monthly_amount"] == 800
    assert p1_over["funding_source"] == "PLANNED_SAVINGS"

    no_savings = rules.propose_category_adjustment(1_500, 1_000, "P2", 600, 0, 0)
    assert no_savings["change_amount"] == 0
    assert no_savings["suggested_monthly_amount"] == 600
    assert no_savings["constraint_applied"] == "NO_AVAILABLE_SAVINGS"


def test_real_persisted_spending_readiness_and_analysis_do_not_write(app, client, seeded):
    with app.app_context():
        before = financial_snapshot()
        result = services.analyze_spending(seeded["user"], "2026-10")
        completeness = result["completeness"]
        assert completeness["status"] == "SUFFICIENT"
        assert completeness["complete_transaction_count"] == 10 and completeness["category_count"] == 3
        assert completeness["coverage_days"] == 31 and completeness["completeness_rate"] == 1
        assert result["review"]["recorded_expense_total"] == 1_608_000
        assert result["review"]["confirmed_allocation_total"] == sum(a.allocated_amount for a in budgets.get_confirmed_allocations(seeded["user"], seeded["month"]))
        assert {item["priority"] for item in result["findings"]} == {"P1", "P2"}
        food = next(item for item in result["findings"] if item["category_name"] == "Food")
        assert food["actual_amount"] == 8000 and type(food["planned_amount"]) is int
        assert "8.000 đồng" in food["reason"] and result["baseline_guidance"] == []
        assert row_count(Recommendation) == 0 and financial_snapshot() == before
    for path in ("/recommendations", "/recommendations/analysis?month=2026-10", "/recommendations/completeness?month=2026-10", "/recommendations/monthly-review?month=2026-10"):
        response = client.get(path)
        assert response.status_code == 200
    assert "GỢI Ý CÁ NHÂN HÓA".encode() in client.get("/recommendations").data
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


@pytest.mark.parametrize("cutoff, expected_count, expected_status", [
    ("2026-10-30", 8, "SKIPPED_INSUFFICIENT_DATA"),
    ("2026-10-31", 10, "GENERATED"),
])
def test_f16_01_generation_respects_cutoff_and_excludes_funds_added(
    app, client, seeded, cutoff, expected_count, expected_status
):
    with app.app_context():
        db.session.add(ExpenseRecord(
            budget_month_id=seeded["month"], amount=100_000,
            expense_date=date(2026, 10, 15), record_type="FUNDS_ADDED",
        ))
        db.session.commit()
        before = financial_snapshot()

    response = client.post("/recommendations/generate", json={
        "month": "2026-10", "as_of": cutoff,
    })
    result = response.json

    assert response.status_code == (201 if expected_status == "GENERATED" else 200)
    assert result["status"] == expected_status
    assert result["as_of"] == cutoff
    assert result["completeness"]["complete_transaction_count"] == expected_count
    if cutoff == "2026-10-31":
        assert result["completeness"]["status"] == "SUFFICIENT"
        assert result["completeness"]["category_count"] == 3
        assert result["completeness"]["coverage_days"] == 31
        assert result["review"]["recorded_expense_total"] == 1_608_000
        assert len(result["recommendations"]) == 3
        food_evidence = []
        for recommendation in result["recommendations"]:
            detail = client.get(f"/recommendations/{recommendation['id']}").json
            assert detail["status"] == "PENDING"
            assert detail["reason"] and detail["expected_impact"]
            if detail["proposed_changes"]["category_name"] == "Food":
                food_evidence = detail["proposed_changes"]["evidence"]
        assert len(food_evidence) == 8
    else:
        assert result["completeness"]["coverage_days"] < 31
        assert not result["recommendations"]
    with app.app_context():
        assert financial_snapshot() == before


def test_insufficient_data_returns_baseline_without_inventing_transactions(app, client, setup):
    with app.app_context():
        before = financial_snapshot()
        result = generate(setup)
        assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
        assert result["findings"] == result["recommendations"] == []
        assert len(result["baseline_guidance"]) == 2
        assert {item["code"] for item in result["suggestions"]} == {
            "BASELINE_AMOUNT_SPLIT", "CREATE_CONFIRMED_PLAN",
        }
        assert all(item["kind"] == "BASELINE_GUIDANCE" and not item["personalized"]
                   for item in result["suggestions"])
        assert all("đồng" in message for message in result["baseline_guidance"])
        assert result["completeness"]["insufficient_reasons"]
        assert result["review"]["planned_task_total"] is None and result["review"]["remaining_vs_plan"] is None
        assert row_count(Recommendation) == 0 and financial_snapshot() == before
    page = client.get("/recommendations")
    assert page.status_code == 200 and "GỢI Ý CHUNG".encode() in page.data
    assert "GỢI Ý CÁ NHÂN HÓA".encode() not in page.data


def test_early_category_signals_are_not_saved_when_f18_data_is_insufficient(app, seeded):
    with app.app_context():
        incomplete_task = db.session.scalar(
            db.select(AssignedExpenseTask).where(AssignedExpenseTask.task_status == "NO_EXPENSE")
        )
        incomplete_task.task_status = "PENDING"
        db.session.commit()
        before = financial_snapshot()

        result = generate(seeded)

        assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
        assert result["completeness"]["status"] == "INSUFFICIENT"
        assert result["findings"]
        early_signals = [item for item in result["suggestions"] if item["kind"] == "EARLY_SIGNAL"]
        assert early_signals and all(not item["personalized"] for item in early_signals)
        assert result["recommendations"] == [] and row_count(Recommendation) == 0
        assert financial_snapshot() == before


def test_no_expense_only_can_complete_review_without_personalization(app, setup):
    with app.app_context():
        plan = budgets.generate_budget_plans(setup["user"], setup["month"])[0]
        budgets.confirm_plan(setup["user"], setup["month"], plan.id)
        for item in expenses.ensure_tasks_for_month(setup["user"], setup["month"]):
            expenses.checkin_task(setup["user"], item.id, action="no_expense")
        result = generate(setup)
        assert result["completeness"]["complete_transaction_count"] == 0 and result["completeness"]["coverage_days"] == 0
        assert result["completeness"]["status"] == "INSUFFICIENT" and not result["recommendations"]
        assert result["review"]["data_complete"] and result["review"]["recorded_expense_total"] == 0


def test_funds_added_never_inflate_spending_transactions_categories_or_coverage(app, seeded):
    with app.app_context():
        before = services.analyze_spending(seeded["user"], "2026-10")
        db.session.add(ExpenseRecord(budget_month_id=seeded["month"], amount=rules.MAX_VND,
                                    expense_date=date(2026, 10, 15), record_type="FUNDS_ADDED"))
        db.session.commit()
        after = services.analyze_spending(seeded["user"], "2026-10")
        assert after == before
        assert rules.build_completeness_result([record(record_type="FUNDS_ADDED")], [], date(2026, 10, 31))["complete_transaction_count"] == 0


def test_generation_replay_reuses_uuid_and_dismissal_remains_dismissed(app, seeded):
    with app.app_context():
        before = financial_snapshot()
        first = generate(seeded)
        assert first["status"] == "GENERATED" and first["created_count"] == 3
        ids = {item["id"] for item in first["recommendations"]}
        assert all(isinstance(UUID(item_id), UUID) for item_id in ids)
        for item_id in ids:
            services.decide_recommendation(seeded["user"], item_id, "REJECT")
            services.decide_recommendation(seeded["user"], item_id, "REJECT")
        again = generate(seeded)
        assert again["status"] == "UNCHANGED" and again["reused_count"] == 3 and again["created_count"] == 0
        assert {item["id"] for item in again["recommendations"]} == ids
        assert {item["status"] for item in again["recommendations"]} == {"REJECTED"}
        assert row_count(Recommendation) == 3 and financial_snapshot() == before


def test_accept_and_reject_only_change_recommendation_status(app, client, seeded):
    with app.app_context():
        generated = generate(seeded)
        accepted_id, rejected_id = [item["id"] for item in generated["recommendations"][:2]]
        before = financial_snapshot()

    accepted = client.post(f"/recommendations/{accepted_id}/decision", json={"decision": "ACCEPT"})
    assert accepted.status_code == 200
    assert accepted.json["status"] == "ACCEPTED"
    assert accepted.json["adjustments_enabled"] is False
    assert accepted.json["financial_adjustment_applied"] is False

    rejected = client.post(f"/recommendations/{rejected_id}/decision", json={"decision": "REJECT"})
    assert rejected.status_code == 200 and rejected.json["status"] == "REJECTED"
    with app.app_context():
        assert db.session.get(Recommendation, UUID(accepted_id)).status == "ACCEPTED"
        assert db.session.get(Recommendation, UUID(rejected_id)).status == "REJECTED"
        assert financial_snapshot() == before


def test_stale_recommendation_cannot_be_accepted_after_source_expense_changes(app, client, seeded):
    with app.app_context():
        generated = generate(seeded)
        recommendation_id = generated["recommendations"][0]["id"]
        food = db.session.scalar(db.select(ExpenseRecord).where(
            ExpenseRecord.title == "Food", ExpenseRecord.expense_date == date(2026, 10, 1)
        ))
        expenses.update_record(seeded["user"], food.id, dict(
            amount="2000000", expense_date="2026-10-01", category="Food"
        ))
        before_decision = financial_snapshot()

    response = client.post(
        f"/recommendations/{recommendation_id}/decision", json={"decision": "ACCEPT"}
    )

    assert response.status_code == 409
    assert "refresh" in response.json["error"].lower()
    with app.app_context():
        assert db.session.get(Recommendation, UUID(recommendation_id)).status == "PENDING"
        assert financial_snapshot() == before_decision


def test_unsafe_legacy_proposal_cannot_be_accepted_or_change_financial_data(app, client, seeded):
    with app.app_context():
        budgets.apply_suggested_expenses(seeded["other"], seeded["foreign_month"], [s.key for s in SUGGESTED_EXPENSES if s.selected], {
            s.key: {"estimated_amount": s.example_amount} for s in SUGGESTED_EXPENSES
        })
        plan = budgets.generate_budget_plans(seeded["other"], seeded["foreign_month"])[0]
        budgets.confirm_plan(seeded["other"], seeded["foreign_month"], plan.id)
        foreign_task = expenses.ensure_tasks_for_month(seeded["other"], seeded["foreign_month"])[0]
        recommendation = Recommendation(budget_month_id=seeded["month"], reason="Legacy proposal", expected_impact="Unsafe change",
            proposed_changes={"changes": [{"task_id": str(foreign_task.id), "new_limit": -1}], "category_id": str(uuid4())})
        db.session.add(recommendation)
        db.session.commit()
        item_id = recommendation.id
        before = financial_snapshot()
    response = client.post(
        f"/recommendations/{item_id}/decision",
        json={"decision": "ACCEPT", "user_id": str(seeded["other"])},
    )
    assert response.status_code == 409 and "read-only" in response.json["error"]
    detail = client.get(f"/recommendations/{item_id}").json
    assert detail["proposed_changes"] == {"mode": "READ_ONLY", "changes": [], "legacy_proposal_withheld": True}
    with app.app_context():
        assert db.session.get(Recommendation, item_id).status == "PENDING"
        assert financial_snapshot() == before


def test_ownership_blocks_pages_generation_detail_decisions_and_feedback(app, client, seeded):
    with app.app_context():
        item_id = generate(seeded)["recommendations"][0]["id"]
        before = financial_snapshot()
    with client.session_transaction() as session:
        session["user_id"] = str(seeded["other"])
    paths = ["/recommendations?month=2026-10", f"/recommendations?budget_month_id={seeded['month']}",
             "/recommendations/completeness?month=2026-10", "/recommendations/analysis?month=2026-10",
             "/recommendations/monthly-review?month=2026-10", f"/recommendations/{item_id}"]
    for path in paths:
        assert client.get(path).status_code == 404
    for path, data in [("/recommendations/generate", {"month": "2026-10"}),
                       (f"/recommendations/{item_id}/decision", {"decision": "ACCEPT"}),
                       ("/recommendations/monthly-review/feedback", {"month": "2026-10", "rating": 3})]:
        assert client.post(path, json=data | {"user_id": str(seeded["user"])}).status_code == 404
    assert client.post(f"/recommendations/{item_id}/dismiss").status_code == 404
    assert client.post("/recommendations/analyze", data={"month": "2026-10", "user_id": str(seeded["user"])}).status_code == 404
    with app.app_context():
        assert financial_snapshot() == before and row_count(MonthlyReview) == 0


def test_authenticated_user_id_cannot_be_replaced_in_generation_payload(app, client, seeded):
    response = client.post("/recommendations/generate", json={"month": "2026-10", "user_id": str(seeded["other"])})
    assert response.status_code == 201
    assert all(item["budget_month_id"] == str(seeded["month"]) for item in response.json["recommendations"])


def test_missing_schedule_and_missing_checkins_are_never_known_zero(app, seeded):
    with app.app_context():
        food = next(t.raw_task for t in expenses.list_tasks(seeded["user"], date(2026, 10, 1), date(2026, 10, 31))
                    if t.title == "Food" and t.task_status == "NO_EXPENSE")
        food.task_status = "PENDING"
        db.session.commit()
        result = generate(seeded)
        assert result["status"] == "SKIPPED_INSUFFICIENT_DATA" and result["review"]["remaining_vs_plan"] is None
        assert result["completeness"]["unrecorded_task_count"] == 1
        db.session.delete(food)
        db.session.commit()
        result = generate(seeded)
        assert not result["completeness"]["checks"]["complete_schedule"]
        assert result["completeness"]["schedule_state"] == "INCOMPLETE"


def test_short_month_and_midmonth_history_do_not_reduce_coverage_threshold(app, setup):
    with app.app_context():
        period = create_budget_month(setup["user"], "2026-09", 100, date(2026, 9, 15), planning_unit=1)
        category = budgets.list_categories(setup["user"])[0]
        for index in range(10):
            expenses.create_unexpected_record(setup["user"], dict(budget_month_id=str(period.id), title="Test purchase", category=category.category_name,
                priority="P1", amount="1", expense_date="2026-09-15" if index < 9 else "2026-09-30", idempotency_key=uuid4().hex))
        result = services.get_completeness(setup["user"], "2026-09")
        assert result["coverage_days"] == 16 and not result["checks"]["minimum_coverage_days"]
        february = [record(expense_date=date(2026, 2, 1 if i < 9 else 28)) for i in range(10)]
        assert not rules.build_completeness_result(february, [], date(2026, 2, 28))["checks"]["minimum_coverage_days"]


def test_as_of_filters_future_records_without_claiming_historical_checkin_states(app, seeded):
    with app.app_context():
        result = services.analyze_spending(seeded["user"], "2026-10", "2026-10-30")
        assert result["review"]["recorded_expense_total"] == 107_000
        assert result["completeness"]["status"] == "INSUFFICIENT"  # Rent's current RECORDED state has no transaction visible yet.
        assert not result["recommendations"] and result["review"]["remaining_vs_plan"] is None


def test_current_month_does_not_compare_active_monthly_limits_with_partial_spending(app, seeded, monkeypatch):
    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 10, 31))
    with app.app_context():
        result = services.analyze_spending(seeded["user"], "2026-10")
        assert result["completeness"]["status"] == "SUFFICIENT"
        assert not any(item["category_name"] == "Fun" for item in result["findings"])  # Monthly period still open today.
        assert result["review"]["remaining_vs_plan"] is None


def test_category_priority_groups_do_not_overwrite_p0_with_p1(app, setup):
    with app.app_context():
        food = next(e for e in budgets.list_expenses(setup["user"], setup["month"]) if e.expense_name == "Food")
        budgets.save_expense(setup["user"], setup["month"], dict(expense_name="Food", priority="P1",
            category_name="Housing", allocation_frequency="DAILY"), expense_id=food.id)
        seed_real_history(setup)
        expenses.create_unexpected_record(setup["user"], dict(budget_month_id=str(setup["month"]), title="Health", category="Health", priority="P1",
            amount="20", expense_date="2026-10-10", idempotency_key=uuid4().hex))
        result = services.analyze_spending(setup["user"], "2026-10")
        assert result["completeness"]["status"] == "SUFFICIENT"
        housing = [row for row in result["review"]["category_review"] if row["category_name"] == "Housing"]
        assert {row["priority"] for row in housing} == {"P0", "P1"}
        assert all(item["priority"] != "P0" for item in result["findings"])


def test_generation_rollback_preserves_finances_and_all_recommendations(app, seeded):
    def fail_insert(mapper, connection, target):
        raise IntegrityError("simulated recommendation failure", {}, RuntimeError("failure"))
    with app.app_context():
        before = financial_snapshot()
        event.listen(Recommendation, "before_insert", fail_insert)
        try:
            with pytest.raises(services.RecommendationServiceError) as exc:
                generate(seeded)
            assert exc.value.status_code == 409
        finally:
            event.remove(Recommendation, "before_insert", fail_insert)
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


@pytest.mark.parametrize("action", ["generate", "decision", "feedback", "analyze", "dismiss"])
def test_every_mutation_requires_csrf(app, client, seeded, action):
    with app.app_context():
        item_id = generate(seeded)["recommendations"][0]["id"]
    app.config["WTF_CSRF_ENABLED"] = True
    paths = dict(generate="/recommendations/generate", decision=f"/recommendations/{item_id}/decision",
                 feedback="/recommendations/monthly-review/feedback", analyze="/recommendations/analyze",
                 dismiss=f"/recommendations/{item_id}/dismiss")
    response = client.post(paths[action], json={"month": "2026-10", "decision": "REJECT"})
    assert response.status_code == 400 and b"CSRF token is missing" in response.data


def test_login_analyze_save_display_dismiss_and_json_csrf_flow(app, client, seeded):
    app.config["WTF_CSRF_ENABLED"] = True
    with client.session_transaction() as session:
        session.clear()
    def token(page):
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.get_data(as_text=True)).group(1)
    csrf = token(client.get("/login"))
    assert client.post("/login", data={"email": "analysis@example.com", "password": "test-password", "csrf_token": csrf}).status_code == 302
    csrf = token(client.get("/recommendations"))
    with app.app_context():
        before = financial_snapshot()
    response = client.post("/recommendations/generate", json={"month": "2026-10"}, headers={"X-CSRFToken": csrf})
    assert response.status_code == 201
    item_id = response.json["recommendations"][0]["id"]
    page = client.get("/recommendations")
    assert "Gợi ý đã lưu".encode() in page.data and "Ẩn gợi ý".encode() in page.data
    assert client.post("/recommendations/analyze", data={"month": "2026-10", "csrf_token": csrf}, follow_redirects=True).status_code == 200
    assert client.post(f"/recommendations/{item_id}/dismiss", data={"csrf_token": csrf}).status_code == 302
    assert client.post(f"/recommendations/{item_id}/decision", json={"decision": "REJECT"}, headers={"X-CSRFToken": csrf}).status_code == 200
    assert client.post("/recommendations/monthly-review/feedback", json={"month": "2026-10", "rating": 4, "comment": "Useful"}, headers={"X-CSRFToken": csrf}).status_code == 200
    with app.app_context():
        assert financial_snapshot() == before and row_count(MonthlyReview) == 1


@pytest.mark.parametrize("rating,comment", [(True, ""), (1.5, ""), ("3", ""), (0, ""), (6, ""), (3, []), (3, "x" * 2001)])
def test_feedback_rejects_invalid_values_without_writes(app, client, setup, rating, comment):
    response = client.post("/recommendations/monthly-review/feedback", json={"month": "2026-10", "rating": rating, "comment": comment})
    assert response.status_code == 400
    with app.app_context():
        assert row_count(MonthlyReview) == 0


@pytest.mark.parametrize("payload", [[], None, "text", 3])
def test_json_object_is_required(client, setup, payload):
    assert client.post("/recommendations/generate", json=payload).status_code == 400


@pytest.mark.parametrize("month,as_of", [("2026-1", None), ("2026-13", None), (None, None), ("2026-10", "bad"),
                                       ("2026-10", "2026-11-01"), ("2026-10", "2026-10-40")])
def test_invalid_month_and_cutoff_are_explicit(client, setup, month, as_of):
    assert client.post("/recommendations/generate", json={"month": month, "as_of": as_of}).status_code == 400


def test_unauthenticated_html_redirects_and_json_returns_401(app, client, setup):
    with client.session_transaction() as session:
        session.clear()
    assert client.get("/recommendations").status_code == 302
    for path in ("analysis", "completeness", "monthly-review"):
        assert client.get(f"/recommendations/{path}?month=2026-10").status_code == 401
    for path in ("generate", "monthly-review/feedback", f"{uuid4()}/decision"):
        assert client.post(f"/recommendations/{path}", json={"month": "2026-10"}).status_code == 401


def test_future_month_and_empty_account_produce_no_fabricated_history(app, client, setup):
    with app.app_context():
        create_budget_month(setup["user"], "2026-12", 5000000, planning_unit=1)
        result = services.analyze_spending(setup["user"], "2026-12")
        assert not result["completeness"]["checks"]["tracking_started"] and not result["findings"]
        before = financial_snapshot()
    assert client.get("/recommendations?month=2026-12").status_code == 200
    assert client.post("/recommendations/analyze", data={"month": "2026-12"}, follow_redirects=True).status_code == 200
    with app.app_context():
        assert financial_snapshot() == before


def test_eighty_percent_gate_is_preserved_alongside_source_consistency_checks():
    records = [record(expense_date=date(2026, 10, 1 if i < 9 else 30)) for i in range(10)]
    tasks = [task("NO_EXPENSE"), task("NO_EXPENSE")] + [task(end=date(2026, 10, 1)) for _ in range(3)]
    result = rules.build_completeness_result(records, tasks, date(2026, 10, 31))
    assert result["completeness_rate"] == .8 and result["checks"]["minimum_completeness_rate"]
    assert result["status"] == "INSUFFICIENT" and not result["checks"]["no_unresolved_tasks"]
    tasks.append(task(end=date(2026, 10, 1)))
    assert not rules.build_completeness_result(records, tasks, date(2026, 10, 31))["checks"]["minimum_completeness_rate"]


def test_draft_tasks_are_not_a_fallback_source_for_analysis(app, setup):
    with app.app_context():
        draft = budgets.generate_budget_plans(setup["user"], setup["month"])[0]
        db.session.add(AssignedExpenseTask(allocation_id=draft.allocations[0].id, assigned_date=date(2026, 10, 1),
                                         period_end=date(2026, 10, 31), original_limit=1, current_limit=1))
        db.session.commit()
        before = financial_snapshot()
        result = generate(setup)
        assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
        assert not result["completeness"]["checks"]["confirmed_plan"]
        assert result["completeness"]["task_status_counts"] == {} and result["review"]["planned_task_total"] is None
        assert financial_snapshot() == before


def test_actual_overspending_changes_evidence_and_snapshot_without_adjustment(app, seeded):
    with app.app_context():
        old = generate(seeded)
        food = db.session.scalar(db.select(ExpenseRecord).where(ExpenseRecord.title == "Food", ExpenseRecord.expense_date == date(2026, 10, 1)))
        expenses.update_record(seeded["user"], food.id, dict(amount="2000000", expense_date="2026-10-01", category="Food"))
        before = financial_snapshot()
        changed = generate(seeded)
        finding = next(item for item in changed["findings"] if item["category_name"] == "Food")
        assert finding["direction"] == "REVIEW_OVER_BUDGET" and finding["actual_amount"] == 2_007_000
        assert changed["analysis_key"] != old["analysis_key"]
        assert {item["id"] for item in changed["recommendations"]}.isdisjoint({item["id"] for item in old["recommendations"]})
        assert financial_snapshot() == before


def test_saved_guidance_is_withheld_when_current_evidence_becomes_insufficient(app, client, seeded):
    with app.app_context():
        old = generate(seeded)
        item_id = old["recommendations"][0]["id"]
        record_id = db.session.scalar(db.select(ExpenseRecord.id).where(ExpenseRecord.title == "Food"))
        expenses.delete_record(seeded["user"], record_id)
        current = services.analyze_spending(seeded["user"], "2026-10")
        assert not current["recommendations"]
        assert all(not suggestion["personalized"]
                   for suggestion in current["suggestions"])
        assert all(suggestion["kind"] in {"EARLY_SIGNAL", "BASELINE_GUIDANCE"}
                   for suggestion in current["suggestions"])
        assert current["completeness"]["status"] == "INSUFFICIENT"
    page = client.get("/recommendations")
    assert "GỢI Ý CHUNG".encode() in page.data and "Gợi ý đã lưu".encode() not in page.data
    detail = client.get(f"/recommendations/{item_id}")
    assert detail.status_code == 200 and "current data may differ" in detail.json["snapshot_notice"]


def test_on_budget_history_does_not_invent_a_recommendation(app, setup):
    with app.app_context():
        plan = budgets.generate_budget_plans(setup["user"], setup["month"])[0]
        budgets.confirm_plan(setup["user"], setup["month"], plan.id)
        for item in expenses.ensure_tasks_for_month(setup["user"], setup["month"]):
            expenses.checkin_task(setup["user"], item.id, action="planned", idempotency_key=uuid4().hex)
        before = financial_snapshot()
        result = generate(setup)
        assert result["completeness"]["status"] == "SUFFICIENT"
        assert result["status"] == "NO_ACTION_REQUIRED" and not result["recommendations"] and not result["findings"]
        assert financial_snapshot() == before and row_count(Recommendation) == 0


@pytest.mark.parametrize("decision", [None, True, "APPLY"])
def test_invalid_decision_rolls_back_metadata(app, client, seeded, decision):
    with app.app_context():
        item_id = generate(seeded)["recommendations"][0]["id"]
    assert client.post(f"/recommendations/{item_id}/decision", json={"decision": decision}).status_code == 400
    with app.app_context():
        assert db.session.get(Recommendation, UUID(item_id)).status == "PENDING"


def test_feedback_replay_upserts_only_owned_metadata(app, client, setup):
    for _ in range(2):
        assert client.post("/recommendations/monthly-review/feedback", json={"month": "2026-10", "rating": 5, "comment": "Useful"}).status_code == 200
    with app.app_context():
        assert row_count(MonthlyReview) == 1
        review = db.session.scalar(db.select(MonthlyReview))
        assert review.budget_month_id == setup["month"] and review.rating == 5


def test_recommendation_persistence_on_migrated_schema(tmp_path, monkeypatch):
    from flask_migrate import upgrade
    from app import create_app
    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(expenses, "today_vn", lambda: date(2026, 11, 3))
    app = create_app({"TESTING": True, "SECRET_KEY": "migration-test-only", "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "recommendations.sqlite").as_posix()})
    with app.app_context():
        try:
            upgrade()
            owner = User(email="migrated-analysis@example.com", password_hash="test-only")
            db.session.add(owner)
            db.session.commit()
            month = create_budget_month(owner.id, "2026-10", 5_000_000, planning_unit=1)
            data = dict(user=owner.id, month=month.id)
            budgets.apply_suggested_expenses(owner.id, month.id, [s.key for s in SUGGESTED_EXPENSES if s.selected], {
                s.key: {"estimated_amount": s.example_amount} for s in SUGGESTED_EXPENSES
            })
            seed_real_history(data)
            saved = generate(data)["recommendations"][0]
            db.session.remove()
            reloaded = services.get_recommendation(data["user"], saved["id"])
            assert reloaded == saved | {"snapshot_notice": reloaded["snapshot_notice"]}
            assert type(reloaded["proposed_changes"]["planned_amount"]) is int
            assert isinstance(db.session.get(Recommendation, UUID(saved["id"])).budget_month_id, UUID)
        finally:
            db.session.remove()
            db.engine.dispose()


def test_observed_unexpected_spending_without_schedule_keeps_planned_amount_unknown(app, setup):
    with app.app_context():
        plan = budgets.generate_budget_plans(setup["user"], setup["month"])[0]
        budgets.confirm_plan(setup["user"], setup["month"], plan.id)
        expenses.create_unexpected_record(setup["user"], dict(budget_month_id=str(setup["month"]), title="Repair", category="Repairs",
            priority="P1", amount="20", expense_date="2026-10-10", idempotency_key=uuid4().hex))
        result = services.analyze_spending(setup["user"], "2026-10")
        assert result["completeness"]["schedule_state"] == "NOT_SCHEDULED"
        assert result["review"]["recorded_expense_total"] == 20
        assert result["review"]["category_review"][0]["planned_amount"] is None
        assert result["review"]["remaining_vs_plan"] is None and not result["findings"]


def test_new_account_has_functional_page_without_creating_financial_data(app, client):
    with app.app_context():
        owner = User(email="empty-analysis@example.com", password_hash="test-only")
        db.session.add(owner)
        db.session.commit()
        owner_id = owner.id
        before = financial_snapshot()
    with client.session_transaction() as session:
        session["user_id"] = str(owner_id)
    response = client.get("/recommendations")
    assert response.status_code == 200 and "Tạo tháng ngân sách".encode() in response.data
    with app.app_context():
        assert financial_snapshot() == before


# KAN-65: expanded UC23-UC26 cases. Existing KAN-59 tests above stay intact.
@pytest.fixture
def kan65_month(app, client, monkeypatch, request):
    """Real confirmed Budget/Expense inputs, with a controllable test clock."""
    options = getattr(request, "param", {})
    month_value = options.get("month", "2026-10")
    today = options.get("today", date(2026, 11, 3))
    monkeypatch.setattr(services, "today_vn", lambda: today)
    monkeypatch.setattr(expenses, "today_vn", lambda: today)
    with app.app_context():
        owner = User(email="kan65@example.com", password_hash="test-only")
        db.session.add(owner)
        db.session.commit()
        month = create_budget_month(owner.id, month_value, 5_000_000)
        for index in range(3):
            budgets.save_expense(owner.id, month.id, dict(
                expense_name=f"KAN65 {index}", category_name=f"KAN65 category {index}",
                priority=options.get("priority", "P1") if index == 0 else "P1",
                estimated_amount=100_000,
                allocation_frequency=options.get("frequency", "MONTHLY") if index == 0 else "MONTHLY",
            ))
        for index, name in enumerate(("Rent", "Electricity", "Water")):
            budgets.save_expense(owner.id, month.id, dict(
                expense_name=name, category_name=f"KAN65 category {index}",
                priority="P0", estimated_amount=100_000, allocation_frequency="MONTHLY",
            ))
        plan = budgets.generate_budget_plans(owner.id, month.id)[1]
        budgets.confirm_plan(owner.id, month.id, plan.id)
        scheduled = expenses.ensure_tasks_for_month(owner.id, month.id)
        # Test a known current limit while retaining the confirmed allocations
        # and original schedule limits used by schedule-readiness validation.
        for item in scheduled:
            item.current_limit = 100_000
        db.session.commit()
        for item in scheduled:
            if item.assigned_date <= today:
                expenses.checkin_task(owner.id, item.id, action="no_expense")
        assert expenses.get_schedule_state(owner.id, month.id).code == "READY"
        data = dict(user=owner.id, month=month.id, month_value=month_value, plan=plan.id,
                    tasks=[item.id for item in scheduled])
    with client.session_transaction() as session:
        session["user_id"] = str(data["user"])
    return data


def _kan65_add_history(data, count=10, categories=3, coverage_days=30):
    """Add distinct purchases; all three monthly tasks are resolved explicitly."""
    scheduled = sorted(
        (db.session.get(AssignedExpenseTask, item_id) for item_id in data["tasks"]),
        key=lambda item: item.allocation.budget_expense.expense_name,
    )
    selected_categories = sorted({item.allocation.budget_expense.category.category_name for item in scheduled})[:categories]
    eligible = [item for item in scheduled if item.allocation.budget_expense.category.category_name in selected_categories]
    start = db.session.get(BudgetMonth, data["month"]).month_start
    for index in range(count):
        when = start.replace(day=coverage_days) if index == count - 1 else start
        expenses.checkin_task(
            data["user"], eligible[index % len(eligible)].id,
            action="actual", amount_raw="1000", expense_date_raw=when.isoformat(),
            idempotency_key=uuid4().hex,
        )


def test_kan65_f16_02_nine_purchases_allow_only_provisional_guidance(app, client, kan65_month):
    """UC23 AF2: insufficient history does not suppress valid early observations."""
    with app.app_context():
        _kan65_add_history(kan65_month, count=9, coverage_days=31)
        before = financial_snapshot()
    result = client.post("/recommendations/generate", json={
        "month": "2026-10", "as_of": "2026-10-31",
    }).json
    assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
    assert result["completeness"]["complete_transaction_count"] == 9
    assert result["completeness"]["category_count"] == 3
    assert result["completeness"]["coverage_days"] == 31
    assert result["baseline_guidance"] and result["completeness"]["insufficient_reasons"]
    assert any(item["kind"] == "EARLY_SIGNAL" for item in result["suggestions"])
    assert all(not item["personalized"] for item in result["suggestions"])
    assert not result["recommendations"]
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


@pytest.mark.parametrize("kan65_month", [{"priority": "P0"}, {"priority": "P1"}, {"priority": "P2"}], indirect=True)
@pytest.mark.parametrize("actual, direction", [
    (79_999, "REVIEW_UNDER_BUDGET"), (80_000, "REVIEW_UNDER_BUDGET"),
    (80_001, None), (109_999, None),
    (110_000, "REVIEW_OVER_BUDGET"), (110_001, "REVIEW_OVER_BUDGET"),
])
def test_kan65_f16_05_completed_period_boundaries_and_p0(app, client, kan65_month, actual, direction):
    """UC23 BF4: inclusive thresholds, with P0 excluded from variance signals."""
    with app.app_context():
        target = next(db.session.get(AssignedExpenseTask, item_id) for item_id in kan65_month["tasks"]
                      if db.session.get(AssignedExpenseTask, item_id).allocation.budget_expense.expense_name == "KAN65 0")
        priority = target.allocation.budget_expense.priority
        category_id = str(target.allocation.budget_expense.category_id)
        expenses.checkin_task(kan65_month["user"], target.id, action="actual", amount_raw=str(actual),
                              expense_date_raw="2026-10-31", idempotency_key=uuid4().hex)
        before = financial_snapshot()
    response = client.get("/recommendations/analysis?month=2026-10&as_of=2026-10-31")
    assert response.status_code == 200
    findings = [f for f in response.json["findings"] if f["category_id"] == category_id]
    if priority == "P0" or direction is None:
        assert findings == []
    else:
        assert len(findings) == 1
        assert findings[0]["direction"] == direction
        assert findings[0]["planned_amount"] == 100_000 and findings[0]["actual_amount"] == actual
    with app.app_context():
        assert financial_snapshot() == before


@pytest.mark.parametrize("kan65_month", [{"frequency": "DAILY", "today": date(2026, 10, 15)}], indirect=True)
@pytest.mark.parametrize("actual, open_direction", [(110_000, "REVIEW_OVER_BUDGET"), (80_000, None)])
def test_kan65_f16_06_open_period_signal_waits_for_low_spend_closure(
    app, client, kan65_month, monkeypatch, actual, open_direction
):
    """UC23 BF4-5: open overrun is evidence; low spending must wait for closure."""
    with app.app_context():
        tasks = [db.session.get(AssignedExpenseTask, item_id) for item_id in kan65_month["tasks"]]
        target = next(item for item in tasks if item.allocation.budget_expense.expense_name == "KAN65 0"
                      and item.assigned_date == date(2026, 10, 15))
        monthly = sorted((item for item in tasks if item.allocation.budget_expense.expense_name in {"KAN65 1", "KAN65 2"}),
                         key=lambda item: item.allocation.budget_expense.expense_name)
        for item, day in [(monthly[0], 6), (monthly[0], 8), (monthly[1], 10), (monthly[1], 12)]:
            expenses.checkin_task(kan65_month["user"], item.id, action="actual", amount_raw="1000",
                                  expense_date_raw=f"2026-10-{day:02d}", idempotency_key=uuid4().hex)
        expenses.checkin_task(kan65_month["user"], target.id, action="actual", amount_raw=str(actual),
                              expense_date_raw="2026-10-15", idempotency_key=uuid4().hex)
        record_id = str(target.records[0].id)
        before = financial_snapshot()

    def directions_containing_purchase(result):
        return {finding["direction"] for finding in result["findings"]
                if any(item["record_id"] == record_id for item in finding["evidence"])}

    result = client.post("/recommendations/generate", json={
        "month": "2026-10", "as_of": "2026-10-15",
    }).json
    assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
    assert result["completeness"]["complete_transaction_count"] == 5
    assert result["completeness"]["category_count"] == 3
    assert directions_containing_purchase(result) == ({open_direction} if open_direction else set())
    assert not result["recommendations"]
    assert all(not item["personalized"] for item in result["suggestions"])
    if open_direction:
        assert any(item["code"] == open_direction and item["kind"] == "EARLY_SIGNAL"
                   for item in result["suggestions"])
    else:
        monkeypatch.setattr(services, "today_vn", lambda: date(2026, 10, 16))
        closed = client.get("/recommendations/analysis?month=2026-10&as_of=2026-10-15").json
        assert "REVIEW_UNDER_BUDGET" in directions_containing_purchase(closed)
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


def test_kan65_f17_04_legacy_changes_are_withheld_and_refused(app, client, seeded):
    """UC24 AF2: unvalidated legacy task edits cannot become an action API."""
    with app.app_context():
        target_id = db.session.scalar(db.select(AssignedExpenseTask.id))
        proposal = Recommendation(budget_month_id=seeded["month"], reason="Legacy",
                                  expected_impact="Read-only legacy proposal",
                                  proposed_changes={"changes": [{"task_id": str(target_id), "new_limit": 100}]})
        db.session.add(proposal)
        db.session.commit()
        item_id = str(proposal.id)
        before = financial_snapshot()
    detail = client.get(f"/recommendations/{item_id}").json
    assert detail["proposed_changes"] == {"mode": "READ_ONLY", "changes": [], "legacy_proposal_withheld": True}
    response = client.post(f"/recommendations/{item_id}/decision", json={"decision": "ACCEPT"})
    assert response.status_code == 409 and "refresh" in response.json["error"].lower()
    with app.app_context():
        assert db.session.get(Recommendation, UUID(item_id)).status == "PENDING"
        assert financial_snapshot() == before


def test_kan65_f17_05_repeated_decisions_preserve_finances(app, client, seeded):
    """UC24 AF3: dismissal is idempotent; an accepted item is terminal."""
    with app.app_context():
        rejected_id, accepted_id = [item["id"] for item in generate(seeded)["recommendations"][:2]]
        before = financial_snapshot()
    for _ in range(2):
        response = client.post(f"/recommendations/{rejected_id}/decision", json={"decision": "REJECT"})
        assert response.status_code == 200 and response.json["status"] == "REJECTED"
    first_accept = client.post(f"/recommendations/{accepted_id}/decision", json={"decision": "ACCEPT"})
    assert first_accept.status_code == 200 and first_accept.json["status"] == "ACCEPTED"
    assert first_accept.json["financial_adjustment_applied"] is False
    for decision in ("ACCEPT", "REJECT"):
        assert client.post(f"/recommendations/{accepted_id}/decision", json={"decision": decision}).status_code == 409
    assert client.get(f"/recommendations/{accepted_id}").json["status"] == "ACCEPTED"
    assert client.get(f"/recommendations/{rejected_id}").json["status"] == "REJECTED"
    with app.app_context():
        assert financial_snapshot() == before


@pytest.mark.parametrize("id_kind", ["foreign", "missing"])
def test_kan65_f17_06_foreign_and_missing_recommendations_are_hidden(app, client, seeded, id_kind):
    """UC24 AF4: lookup and both decisions must enforce ownership."""
    with app.app_context():
        foreign = Recommendation(budget_month_id=seeded["foreign_month"], reason="Private owner evidence",
                                 expected_impact="Private impact",
                                 proposed_changes={"mode": "READ_ONLY", "changes": []})
        db.session.add(foreign)
        db.session.commit()
        foreign_id = foreign.id
        item_id = str(foreign_id) if id_kind == "foreign" else str(uuid4())
        before = financial_snapshot()
    responses = [client.get(f"/recommendations/{item_id}")]
    responses.extend(client.post(f"/recommendations/{item_id}/decision", json={"decision": decision})
                     for decision in ("ACCEPT", "REJECT"))
    assert all(response.status_code == 404 for response in responses)
    assert all(b"Private owner evidence" not in response.data for response in responses)
    with app.app_context():
        assert db.session.get(Recommendation, foreign_id).status == "PENDING"
        assert financial_snapshot() == before


def test_kan65_f18_01_incomplete_transaction_is_reported_without_blocking_valid_history(app, kan65_month):
    """Report and exclude invalid spending; evaluate readiness using the configured gates."""
    with app.app_context():
        _kan65_add_history(kan65_month)
        data = services._load(kan65_month["user"], "2026-10", "2026-10-31")
        # Canonical storage rejects NULL amounts; inject the malformed input at
        # the recommendation boundary to test its completeness handling.
        invalid = record(amount=None, category_id=data.records[0].category_id)
        invalid.priority = "P1"
        data.records.append(invalid)
        before = financial_snapshot()
        result = services._completeness(data)
        assert result["complete_transaction_count"] == 10 and result["incomplete_transaction_count"] == 1
        assert result["category_count"] == 3 and result["coverage_days"] == 30
        assert result["completeness_rate"] == .9091
        assert any(issue["type"] == "INCOMPLETE_TRANSACTION" for issue in result["issues"])
        assert result["checks"]["no_incomplete_transactions"] is False
        assert result["insufficient_reasons"] == []
        assert sum(item.amount for item in data.records if rules.is_complete_expense_record(item)) == 10_000
        assert financial_snapshot() == before
        assert result["status"] == "SUFFICIENT"
        analysis = services._analysis(data)
        assert analysis["review"]["recorded_expense_total"] == 10_000
        assert analysis["completeness"]["status"] == "SUFFICIENT"
        assert financial_snapshot() == before


def test_kan65_f18_02_overdue_active_and_no_expense_counters():
    """UC25 AF2/4: exact three-period fixture, rather than monthly-review output."""
    overdue = task(end=date(2026, 10, 14))
    active = task(end=date(2026, 10, 20))
    no_expense = task("NO_EXPENSE", end=date(2026, 10, 14))
    result = rules.build_completeness_result([], [overdue, active, no_expense], date(2026, 10, 15))
    assert result["unrecorded_task_count"] == 1 and result["no_expense_task_count"] == 1
    assert result["complete_transaction_count"] == result["category_count"] == result["coverage_days"] == 0
    assert len(result["issues"]) == 1
    assert result["issues"][0]["type"] == "UNRECORDED_TASK"
    assert result["issues"][0]["task_id"] == str(overdue.id)
    assert result["status"] == "INSUFFICIENT"


@pytest.mark.parametrize("count,categories,days,failed_gate", [
    (10, 3, 30, None), (9, 3, 30, "minimum_complete_transactions"),
    (10, 2, 30, "minimum_categories"), (10, 3, 29, "minimum_coverage_days"),
])
def test_kan65_f18_05_exact_readiness_thresholds(app, client, kan65_month, count, categories, days, failed_gate):
    """UC25 AF1: one below each readiness threshold must block personalization."""
    with app.app_context():
        _kan65_add_history(kan65_month, count=count, categories=categories, coverage_days=days)
        before = financial_snapshot()
    result = client.get("/recommendations/completeness?month=2026-10&as_of=2026-10-31").json
    assert result["complete_transaction_count"] == count and result["category_count"] == categories
    assert result["coverage_days"] == days
    assert result["status"] == ("INSUFFICIENT" if failed_gate else "SUFFICIENT")
    if failed_gate:
        assert result["checks"][failed_gate] is False and result["insufficient_reasons"]
    with app.app_context():
        assert financial_snapshot() == before


@pytest.mark.parametrize("invalid_count,rate,rate_gate", [(3, .8, True), (4, .75, False)])
def test_kan65_f18_05_rate_gate_includes_invalid_records_in_denominator(app, kan65_month, invalid_count, rate, rate_gate):
    """Invalid rows are reported; 80% passes and 75% fails when other gates pass."""
    with app.app_context():
        _kan65_add_history(kan65_month, count=12)
        data = services._load(kan65_month["user"], "2026-10", "2026-10-31")
        data.records.extend(record(amount=None, category_id=data.records[0].category_id) for _ in range(invalid_count))
        before = financial_snapshot()
        result = services._completeness(data)
        assert result["no_expense_task_count"] == 0
        assert result["complete_transaction_count"] == 12 and result["incomplete_transaction_count"] == invalid_count
        assert result["completeness_rate"] == rate and result["checks"]["minimum_completeness_rate"] is rate_gate
        assert financial_snapshot() == before
        assert result["checks"]["no_incomplete_transactions"] is False
        assert len([issue for issue in result["issues"] if issue["type"] == "INCOMPLETE_TRANSACTION"]) == invalid_count
        assert result["status"] == ("SUFFICIENT" if rate_gate else "INSUFFICIENT")
        assert bool(result["insufficient_reasons"]) is not rate_gate
        assert sum(item.amount for item in data.records if rules.is_complete_expense_record(item)) == 12_000


@pytest.mark.parametrize("prerequisite,gate", [
    ("plan", "confirmed_plan"), ("schedule", "complete_schedule"), ("tracking", "tracking_started"),
])
def test_kan65_f18_06_prerequisites_explain_insufficient_data(app, client, kan65_month, monkeypatch, prerequisite, gate):
    """UC25 AF5: prerequisites remain independent of numerical thresholds."""
    with app.app_context():
        if prerequisite == "plan":
            db.session.get(BudgetPlan, kan65_month["plan"]).status = "GENERATED"
            db.session.commit()
        elif prerequisite == "schedule":
            db.session.delete(db.session.get(AssignedExpenseTask, kan65_month["tasks"][0]))
            db.session.commit()
        else:
            monkeypatch.setattr(services, "today_vn", lambda: date(2026, 9, 30))
        before = financial_snapshot()
    result = client.get("/recommendations/completeness?month=2026-10").json
    assert result["status"] == "INSUFFICIENT" and result["checks"][gate] is False
    assert result["insufficient_reasons"]
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


@pytest.mark.parametrize("kan65_month", [{"month": "2027-02", "today": date(2027, 3, 1)}], indirect=True)
def test_kan65_f18_07_february_does_not_lower_coverage_requirement(app, client, kan65_month):
    """UC25 AF6: month-scoped analysis cannot invent the missing two days."""
    with app.app_context():
        _kan65_add_history(kan65_month, coverage_days=28)
        before = financial_snapshot()
    result = client.get("/recommendations/completeness?month=2027-02&as_of=2027-02-28").json
    assert result["complete_transaction_count"] == 10 and result["category_count"] == 3
    assert result["coverage_days"] == 28 and result["thresholds"]["coverage_days"] == 30
    assert result["checks"]["minimum_coverage_days"] is False and result["status"] == "INSUFFICIENT"
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f19_06_closed_no_expense_month_is_complete_without_personalization(app, client, kan65_month):
    """UC26 AF4/5: resolved zero spending can be known while F18 remains insufficient."""
    with app.app_context():
        before = financial_snapshot()
    review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    completeness = client.get("/recommendations/completeness?month=2026-10&as_of=2026-10-31").json
    assert review["review_status"] == "COMPLETE"
    assert review["recorded_expense_total"] == 0 and review["recorded_expense_count"] == 0
    assert review["planned_task_total"] == review["remaining_vs_plan"] == 600_000
    assert completeness["status"] == "INSUFFICIENT"
    assert completeness["complete_transaction_count"] == completeness["category_count"] == completeness["coverage_days"] == 0
    with app.app_context():
        assert row_count(MonthlyReview) == 0 and financial_snapshot() == before


def test_kan65_f19_07_last_day_is_not_a_closed_month(app, client, kan65_month, monkeypatch):
    """UC26 AF3: the exact month-end date remains provisional until the next day."""
    with app.app_context():
        _kan65_add_history(kan65_month, coverage_days=31)
        before = financial_snapshot()
    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 10, 31))
    open_review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    assert open_review["review_status"] == "INCOMPLETE_DATA"
    assert open_review["recorded_expense_total"] == 10_000
    assert open_review["planned_task_total"] is open_review["remaining_vs_plan"] is None
    assert all(row["variance"] is None for row in open_review["category_review"])
    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 11, 1))
    closed_review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    assert closed_review["review_status"] == "COMPLETE"
    assert closed_review["planned_task_total"] == 600_000 and closed_review["remaining_vs_plan"] == 590_000
    assert all(row["variance"] is not None for row in closed_review["category_review"])
    with app.app_context():
        assert financial_snapshot() == before


def test_kan74_incomplete_data_is_visible_without_blocking_sufficient_history(app, client, seeded, monkeypatch):
    """Invalid input stays visible while valid history can still support read-only guidance."""
    with app.app_context():
        data = services._load(seeded["user"], "2026-10", "2026-10-31")
        invalid = record(amount=None, category_id=data.records[0].category_id)
        invalid.priority = "P1"
        data.records.append(invalid)
        before = financial_snapshot()
        monkeypatch.setattr(services, "_load", lambda *args, **kwargs: data)

        response = client.get("/recommendations?month=2026-10&as_of=2026-10-31")
        assert response.status_code == 200
        page = response.get_data(as_text=True)
        assert "Đủ điều kiện phân tích cá nhân hóa" in page
        assert "Thông tin cần kiểm tra" in page
        result = client.post("/recommendations/generate", json={
            "month": "2026-10", "as_of": "2026-10-31",
        }).json
        assert result["status"] == "GENERATED"
        assert result["completeness"]["incomplete_transaction_count"] == 1
        assert result["completeness"]["insufficient_reasons"] == []
        assert result["review"]["recorded_expense_total"] == 1_608_000
        assert result["recommendations"] and row_count(Recommendation) == len(result["recommendations"])
        review = services._review(data, result["completeness"])
        assert review["review_status"] == "INCOMPLETE_DATA" and review["remaining_vs_plan"] is None
        assert financial_snapshot() == before


def test_kan74_missing_expense_date_keeps_analysis_available(app, client, seeded, monkeypatch):
    """Malformed input at the service boundary is flagged without crashing the analysis page."""
    with app.app_context():
        data = services._load(seeded["user"], "2026-10", "2026-10-31")
        invalid = record(amount=1000, category_id=data.records[0].category_id, expense_date=None)
        invalid.priority = "P1"
        data.records.append(invalid)
        before = financial_snapshot()
        monkeypatch.setattr(services, "_load", lambda *args, **kwargs: data)
        response = client.get("/recommendations?month=2026-10&as_of=2026-10-31")
        assert response.status_code == 200
        page = response.get_data(as_text=True)
        assert "Đủ điều kiện phân tích cá nhân hóa" in page
        assert "Thông tin cần kiểm tra" in page
        assert services._completeness(data)["incomplete_transaction_count"] == 1
        assert financial_snapshot() == before


def test_kan74_html_offers_dismissal_without_accepting_budget_changes(app, client, seeded):
    """UC24: HTML only offers dismissal; generated guidance remains financially read-only."""
    with app.app_context():
        generated = generate(seeded)
        item_id = generated["recommendations"][0]["id"]
        before = financial_snapshot()
    page = client.get("/recommendations?month=2026-10").get_data(as_text=True)
    assert "Ẩn gợi ý" in page
    assert "Chấp nhận đề xuất" not in page
    assert 'value="ACCEPT"' not in page
    assert client.post(f"/recommendations/{item_id}/dismiss").status_code == 302
    with app.app_context():
        assert db.session.get(Recommendation, UUID(item_id)).status == "REJECTED"
        assert financial_snapshot() == before


# Complete KAN-65 coverage: one named case for every ID in the standalone document.
def test_kan65_f16_01_sufficient_recorded_expenses_generate_explained_guidance(app, client, seeded):
    with app.app_context():
        db.session.add(ExpenseRecord(budget_month_id=seeded["month"], record_type="FUNDS_ADDED",
                                    amount=100_000, expense_date=date(2026, 10, 15)))
        db.session.commit()
        before = financial_snapshot()
    response = client.post("/recommendations/generate", json={"month": "2026-10", "as_of": "2026-10-31"})
    assert response.status_code == 201
    result = response.json
    assert result["status"] == "GENERATED" and len(result["recommendations"]) == 3
    assert result["completeness"]["complete_transaction_count"] == 10
    assert result["completeness"]["category_count"] == 3 and result["completeness"]["coverage_days"] == 31
    assert result["review"]["recorded_expense_total"] == 1_608_000
    food = next(item for item in result["recommendations"] if item["proposed_changes"]["category_name"] == "Food")
    detail = client.get(f"/recommendations/{food['id']}").json
    assert detail["reason"] and detail["expected_impact"] and detail["status"] == "PENDING"
    assert len(detail["proposed_changes"]["evidence"]) == 8
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f16_03_no_confirmed_plan_blocks_personalization(app, client, setup):
    with app.app_context():
        for index in range(10):
            expenses.create_unexpected_record(setup["user"], dict(
                budget_month_id=str(setup["month"]), title="Recorded purchase",
                category=f"Actual category {index % 3}", priority="P1", amount="1000",
                expense_date="2026-10-30" if index == 9 else "2026-10-01",
                idempotency_key=uuid4().hex,
            ))
        before = financial_snapshot()
    result = client.post("/recommendations/generate", json={"month": "2026-10", "as_of": "2026-10-31"}).json
    assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
    assert result["completeness"]["complete_transaction_count"] == 10
    assert result["completeness"]["checks"]["confirmed_plan"] is False
    assert result["completeness"]["insufficient_reasons"] and not result["recommendations"]
    assert all(not item["personalized"] for item in result["suggestions"])
    assert result["review"]["remaining_vs_plan"] is None
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


def test_kan65_f16_04_on_budget_history_requires_no_action(app, client, setup):
    with app.app_context():
        plan = budgets.generate_budget_plans(setup["user"], setup["month"])[1]
        budgets.confirm_plan(setup["user"], setup["month"], plan.id)
        for item in expenses.ensure_tasks_for_month(setup["user"], setup["month"]):
            expenses.checkin_task(setup["user"], item.id, action="planned", idempotency_key=uuid4().hex)
        before = financial_snapshot()
    result = client.post("/recommendations/generate", json={"month": "2026-10", "as_of": "2026-10-31"}).json
    assert result["completeness"]["status"] == "SUFFICIENT"
    assert result["status"] == "NO_ACTION_REQUIRED" and not result["findings"] and not result["recommendations"]
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


def test_kan65_f17_01_explanation_and_rejection_are_read_only(app, client, seeded):
    with app.app_context():
        item = next(item for item in generate(seeded)["recommendations"]
                    if item["proposed_changes"]["category_name"] == "Food")
        before = financial_snapshot()
    detail = client.get(f"/recommendations/{item['id']}").json
    assert detail["reason"] and detail["expected_impact"] and detail["snapshot_notice"]
    assert detail["status"] == "PENDING" and len(detail["proposed_changes"]["evidence"]) == 8
    response = client.post(f"/recommendations/{item['id']}/decision", json={"decision": "REJECT"})
    assert response.status_code == 200 and response.json["status"] == "REJECTED"
    assert client.get(f"/recommendations/{item['id']}").json["status"] == "REJECTED"
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f17_02_accept_records_only_the_decision(app, client, seeded):
    with app.app_context():
        item_id = generate(seeded)["recommendations"][0]["id"]
        before = financial_snapshot()
    response = client.post(f"/recommendations/{item_id}/decision", json={"decision": "ACCEPT", "as_of": "2026-10-31"})
    assert response.status_code == 200 and response.json["status"] == "ACCEPTED"
    assert response.json["adjustments_enabled"] is False and response.json["financial_adjustment_applied"] is False
    assert client.get(f"/recommendations/{item_id}").json["status"] == "ACCEPTED"
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f17_03_changed_source_refuses_stale_acceptance(app, client, seeded):
    with app.app_context():
        item_id = generate(seeded)["recommendations"][0]["id"]
        food = db.session.scalar(db.select(ExpenseRecord).where(
            ExpenseRecord.title == "Food", ExpenseRecord.expense_date == date(2026, 10, 1)))
        expenses.update_record(seeded["user"], food.id, dict(amount="2000000", expense_date="2026-10-01", category="Food"))
        before = financial_snapshot()
    response = client.post(f"/recommendations/{item_id}/decision", json={"decision": "ACCEPT", "as_of": "2026-10-31"})
    assert response.status_code == 409
    assert client.get(f"/recommendations/{item_id}").json["status"] == "PENDING"
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f18_03_no_expense_is_not_purchase_history(app, client, kan65_month):
    with app.app_context():
        before = financial_snapshot()
    result = client.post("/recommendations/generate", json={"month": "2026-10", "as_of": "2026-10-31"}).json
    completeness = result["completeness"]
    assert completeness["complete_transaction_count"] == completeness["category_count"] == completeness["coverage_days"] == 0
    assert completeness["no_expense_task_count"] == 6 and completeness["status"] == "INSUFFICIENT"
    assert result["baseline_guidance"] and not result["recommendations"]
    assert all(not item["personalized"] for item in result["suggestions"])
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


def test_kan65_f18_04_contradictory_no_expense_is_not_zero(app, client, kan65_month):
    with app.app_context():
        _kan65_add_history(kan65_month)
        target = db.session.get(AssignedExpenseTask, kan65_month["tasks"][0])
        assert target.records
        target.task_status = "NO_EXPENSE"
        db.session.commit()
        before = financial_snapshot()
    completeness = client.get("/recommendations/completeness?month=2026-10&as_of=2026-10-31").json
    assert completeness["inconsistent_task_count"] == 1 and completeness["no_expense_task_count"] == 0
    assert any(issue["type"] == "INCONSISTENT_CHECKIN" for issue in completeness["issues"])
    assert completeness["status"] == "INSUFFICIENT"
    review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    assert review["review_status"] == "INCOMPLETE_DATA" and review["remaining_vs_plan"] is None
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f19_01_closed_resolved_month_has_supported_totals(app, client, seeded):
    with app.app_context():
        db.session.add(ExpenseRecord(budget_month_id=seeded["month"], record_type="FUNDS_ADDED",
                                    amount=100_000, expense_date=date(2026, 10, 15)))
        db.session.commit()
        before = financial_snapshot()
    review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    assert review["review_status"] == "COMPLETE" and review["recorded_expense_count"] == 10
    assert review["recorded_expense_total"] == 1_608_000 and review["planned_task_total"] == 4_360_000
    assert review["remaining_vs_plan"] == 2_752_000
    assert all(row["variance"] == row["planned_amount"] - row["actual_amount"] for row in review["category_review"])
    with app.app_context():
        assert financial_snapshot() == before


@pytest.mark.parametrize("kan65_month", [{"frequency": "DAILY", "today": date(2026, 10, 15)}], indirect=True)
def test_kan65_f19_02_missing_checkin_withholds_midmonth_balance(app, client, kan65_month):
    with app.app_context():
        tasks = [db.session.get(AssignedExpenseTask, item_id) for item_id in kan65_month["tasks"]]
        overdue = next(item for item in tasks if item.assigned_date == date(2026, 10, 14))
        overdue.task_status = "PENDING"
        db.session.commit()
        today_task = next(item for item in tasks if item.assigned_date == date(2026, 10, 15))
        expenses.checkin_task(kan65_month["user"], today_task.id, action="actual", amount_raw="25000",
                              expense_date_raw="2026-10-15", idempotency_key=uuid4().hex)
        before = financial_snapshot()
    completeness = client.get("/recommendations/completeness?month=2026-10&as_of=2026-10-15").json
    assert completeness["unrecorded_task_count"] == 1
    review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-15").json
    assert review["review_status"] == "INCOMPLETE_DATA" and review["recorded_expense_total"] == 25_000
    assert review["planned_task_total"] is review["remaining_vs_plan"] is None
    assert all(row["variance"] is None for row in review["category_review"])
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f19_03_no_plan_shows_only_observed_expenses(app, client, setup):
    with app.app_context():
        expenses.create_unexpected_record(setup["user"], dict(
            budget_month_id=str(setup["month"]), title="Repair", category="Repairs", priority="P1",
            amount="250000", expense_date="2026-10-10", idempotency_key=uuid4().hex))
        before = financial_snapshot()
    review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    assert review["review_status"] == "INCOMPLETE_DATA" and review["recorded_expense_total"] == 250_000
    assert review["planned_task_total"] is review["remaining_vs_plan"] is None
    assert review["recorded_expense_count"] == 1
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f19_04_no_purchases_with_pending_periods_are_incomplete(app, client, kan65_month):
    with app.app_context():
        for item_id in kan65_month["tasks"]:
            db.session.get(AssignedExpenseTask, item_id).task_status = "PENDING"
        db.session.commit()
        before = financial_snapshot()
    completeness = client.get("/recommendations/completeness?month=2026-10&as_of=2026-10-31").json
    assert completeness["unrecorded_task_count"] == 6
    review = client.get("/recommendations/monthly-review?month=2026-10&as_of=2026-10-31").json
    assert review["recorded_expense_count"] == 0 and review["recorded_expense_total"] == 0
    assert review["review_status"] == "INCOMPLETE_DATA" and review["remaining_vs_plan"] is None
    with app.app_context():
        assert financial_snapshot() == before


def test_kan65_f19_05_feedback_boundaries_preserve_valid_response(app, client, kan65_month):
    with app.app_context():
        before = financial_snapshot()
    path = "/recommendations/monthly-review/feedback"
    for rating in (1, 5):
        response = client.post(path, json={"month": "2026-10", "rating": rating, "comment": "x" * 2000})
        assert response.status_code == 200
        review = client.get("/recommendations/monthly-review?month=2026-10").json
        assert review["rating"] == rating and review["comment"] == "x" * 2000
    for rating, comment in [(0, "bad"), (6, "bad"), (3, "x" * 2001)]:
        assert client.post(path, json={"month": "2026-10", "rating": rating, "comment": comment}).status_code == 400
        review = client.get("/recommendations/monthly-review?month=2026-10").json
        assert review["rating"] == 5 and review["comment"] == "x" * 2000
    with app.app_context():
        assert row_count(MonthlyReview) == 1 and row_count(Recommendation) == 0
        assert financial_snapshot() == before


def test_kan65_ui_e2e_01_budget_expense_to_recommendations(app, client, monkeypatch):
    """Submit the public HTML forms; analysis reads the saved purchase without financial edits."""
    from app.modules.budget_periods import forms as period_forms

    today = date(2026, 11, 26)
    monkeypatch.setattr(period_forms, "today_vn", lambda: today)
    monkeypatch.setattr(expenses, "today_vn", lambda: today)
    monkeypatch.setattr(services, "today_vn", lambda: today)
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 11, 26, 12))
    with app.app_context():
        owner = User(email="kan65-ui@example.com", password_hash=generate_password_hash("kan65-ui-password"))
        db.session.add(owner)
        db.session.commit()
        owner_id = owner.id
    login = client.post("/login", data={"email": "kan65-ui@example.com", "password": "kan65-ui-password"})
    assert login.status_code == 302
    created = client.post("/budget-periods/new", data={
        "month": "11/2026", "tracking_start_day": "26", "available_vnd": "7000000",
    })
    assert created.status_code == 302
    with app.app_context():
        month = db.session.scalar(db.select(BudgetMonth).where(BudgetMonth.user_id == owner_id))
        month_id = month.id
    budget_path = f"/budget/{month_id}"
    assert client.get(budget_path).status_code == 200
    generated = client.post(f"{budget_path}/plans/generate", data={
        "suggestion": ["rent", "electricity", "water", "food", "transportation"],
        "rent_estimated_amount": "2000000", "electricity_estimated_amount": "200000",
        "water_estimated_amount": "100000", "food_minimum_amount": "1200000",
        "transportation_minimum_amount": "200000",
    })
    assert generated.status_code == 302
    with app.app_context():
        plan = db.session.scalar(db.select(BudgetPlan).where(
            BudgetPlan.budget_month_id == month_id, BudgetPlan.plan_type == "BALANCED"))
        plan_id = plan.id
    confirmed = client.post(f"{budget_path}/plans/{plan_id}/confirm", data={})
    assert confirmed.status_code == 302 and "/expenses?" in confirmed.location
    expense_path = f"/expenses?budget_month_id={month_id}&view=day&date=2026-11-26"
    assert client.get(expense_path).status_code == 200
    with app.app_context():
        tasks = list(db.session.scalars(db.select(AssignedExpenseTask).join(BudgetAllocation).where(
            BudgetAllocation.plan_id == plan_id)))
        food = next(t for t in tasks if t.allocation.budget_expense.expense_name == "Food"
                    and t.assigned_date == today)
        task_id = food.id
        assert row_count(ExpenseRecord) == 0
    checked = client.post(f"/expenses/tasks/{task_id}/checkin", data={
        "action": "actual", "amount": "12785", "expense_date": "2026-11-26",
        "submission_token": uuid4().hex, "budget_month_id": str(month_id), "view": "day",
        "date": "2026-11-26",
    })
    assert checked.status_code == 302
    history = client.get("/expenses/history?start=2026-11-01&end=2026-11-30")
    assert history.status_code == 200 and 'value="12785"' in history.get_data(as_text=True)
    with app.app_context():
        before = financial_snapshot()
    page = client.get(f"/recommendations?budget_month_id={month_id}&lang=vi")
    assert page.status_code == 200
    assert "Chưa đủ để đưa ra kết luận cá nhân hóa" in page.get_data(as_text=True)
    analyzed = client.post("/recommendations/analyze", data={"month": "2026-11", "as_of": "2026-11-26"}, follow_redirects=True)
    assert analyzed.status_code == 200
    assert "12.785" in analyzed.get_data(as_text=True)
    assert 'value="ACCEPT"' not in analyzed.get_data(as_text=True)
    result = client.get("/recommendations/analysis?month=2026-11&as_of=2026-11-26").json
    assert result["completeness"]["complete_transaction_count"] == 1
    assert result["completeness"]["category_count"] == 1 and result["completeness"]["coverage_days"] == 1
    assert result["completeness"]["status"] == "INSUFFICIENT" and not result["recommendations"]
    assert result["review"]["recorded_expense_total"] == 12_785
    assert result["review"]["review_status"] == "INCOMPLETE_DATA" and result["review"]["remaining_vs_plan"] is None
    with app.app_context():
        assert row_count(ExpenseRecord) == 1 and row_count(Recommendation) == 0
        assert financial_snapshot() == before


@pytest.mark.parametrize("kan65_month", [{
    "month": "2026-11", "today": date(2026, 11, 15),
}], indirect=True)
def test_kan65_f19_08_open_month_feedback_preserves_provisional_review(app, client, kan65_month):
    """UC26 BF5: feedback persists without making an open month's balance reliable."""
    with app.app_context():
        _kan65_add_history(kan65_month, count=3, categories=3, coverage_days=15)
        before = financial_snapshot()

    review_path = "/recommendations/monthly-review?month=2026-11&as_of=2026-11-15"
    initial = client.get(review_path)
    assert initial.status_code == 200
    assert initial.json["review_status"] == "INCOMPLETE_DATA"
    assert initial.json["remaining_vs_plan"] is None
    assert initial.json["recorded_expense_total"] == 3_000

    saved = client.post("/recommendations/monthly-review/feedback", json={
        "month": "2026-11", "rating": 4, "comment": "Needs review",
    })
    assert saved.status_code == 200 and saved.json["status"] == "SAVED"

    reloaded = client.get(review_path)
    assert reloaded.status_code == 200
    review = reloaded.json
    assert review["rating"] == 4 and review["comment"] == "Needs review"
    assert review["review_status"] == "INCOMPLETE_DATA"
    assert review["remaining_vs_plan"] is None and review["planned_task_total"] is None
    assert review["recorded_expense_total"] == 3_000
    with app.app_context():
        assert row_count(MonthlyReview) == 1 and row_count(Recommendation) == 0
        assert financial_snapshot() == before
