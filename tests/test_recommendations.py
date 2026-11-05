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
        month = create_budget_month(owner.id, "2026-10", 5_000_000, date(2026, 10, 1))
        foreign_month = create_budget_month(other.id, "2026-09", 5_000_000)
        data = dict(user=owner.id, other=other.id, month=month.id, foreign_month=foreign_month.id)
        budgets.apply_suggested_expenses(owner.id, month.id, [s.key for s in SUGGESTED_EXPENSES if s.selected], {
            s.key: {"estimated_amount": s.example_amount} for s in SUGGESTED_EXPENSES
        })
        budgets.save_expense(owner.id, month.id, dict(expense_name="Entertainment", priority="P2",
            category_name="Fun", allocation_frequency="MONTHLY"))
        db.session.add_all([
            ExpenseCategory(user_id=owner.id, category_name="Health"),
            ExpenseCategory(user_id=owner.id, category_name="Repairs"),
        ])
        db.session.commit()
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
                expense_date_raw="2026-10-31" if name == "Rent" else task.assigned_date.isoformat())
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
        assert "8000 VND" in food["reason"] and result["baseline_guidance"] == []
        assert row_count(Recommendation) == 0 and financial_snapshot() == before
    for path in ("/recommendations", "/recommendations/analysis?month=2026-10", "/recommendations/completeness?month=2026-10", "/recommendations/monthly-review?month=2026-10"):
        response = client.get(path)
        assert response.status_code == 200
    assert b"Data-backed observations" in client.get("/recommendations").data
    with app.app_context():
        assert row_count(Recommendation) == 0 and financial_snapshot() == before


def test_insufficient_data_returns_baseline_without_inventing_transactions(app, client, setup):
    with app.app_context():
        before = financial_snapshot()
        result = generate(setup)
        assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"
        assert result["findings"] == result["recommendations"] == [] and len(result["baseline_guidance"]) == 3
        assert result["completeness"]["insufficient_reasons"]
        assert result["review"]["planned_task_total"] is None and result["review"]["remaining_vs_plan"] is None
        assert row_count(Recommendation) == 0 and financial_snapshot() == before
    page = client.get("/recommendations")
    assert page.status_code == 200 and b"Baseline guidance" in page.data
    assert b"No personalized recommendations were generated" in page.data


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


def test_accept_is_disabled_even_for_malicious_cross_user_json(app, client, seeded):
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
    for _ in range(2):
        response = client.post(f"/recommendations/{item_id}/decision", json={"decision": "ACCEPT", "user_id": str(seeded["other"])})
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
        period = create_budget_month(setup["user"], "2026-09", 100, date(2026, 9, 15))
        category = budgets.list_categories(setup["user"])[0]
        for index in range(10):
            expenses.create_unexpected_record(setup["user"], dict(budget_month_id=str(period.id), title="Test purchase", category=category.category_name,
                priority="P1", amount="1", expense_date="2026-09-15" if index < 9 else "2026-09-30"))
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
            amount="20", expense_date="2026-10-10"))
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
    assert b"Saved guidance for this data snapshot" in page.data and b"Dismiss guidance" in page.data
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
        create_budget_month(setup["user"], "2026-12", 5000000)
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
        assert not current["findings"] and not current["recommendations"]
        assert current["completeness"]["status"] == "INSUFFICIENT"
    page = client.get("/recommendations")
    assert b"Baseline guidance" in page.data and b"Saved guidance for this data snapshot" not in page.data
    detail = client.get(f"/recommendations/{item_id}")
    assert detail.status_code == 200 and "current data may differ" in detail.json["snapshot_notice"]


def test_on_budget_history_does_not_invent_a_recommendation(app, setup):
    with app.app_context():
        plan = budgets.generate_budget_plans(setup["user"], setup["month"])[0]
        budgets.confirm_plan(setup["user"], setup["month"], plan.id)
        for item in expenses.ensure_tasks_for_month(setup["user"], setup["month"]):
            expenses.checkin_task(setup["user"], item.id, action="planned")
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
            month = create_budget_month(owner.id, "2026-10", 5_000_000)
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
            priority="P1", amount="20", expense_date="2026-10-10"))
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
    assert response.status_code == 200 and b"Create a Budget Month" in response.data
    with app.app_context():
        assert financial_snapshot() == before
