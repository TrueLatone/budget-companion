"""PA4 integration regressions; all database writes use disposable SQLite."""

from datetime import date
import re
from uuid import UUID, uuid4

from flask_migrate import upgrade
import pytest
import sqlalchemy as sa

from app import create_app
from app.extensions import db
from app.models import AssignedExpenseTask, BudgetExpense, BudgetPlan, ExpenseRecord, User
from app.modules.budget_periods.services import create_budget_month


@pytest.mark.parametrize("available", [4_000_000, 5_000_000, 6_000_000])
def test_build2_upgrade_preserves_financial_rows_and_legacy_units(tmp_path, available):
    application = create_app({
        "TESTING": True, "SECRET_KEY": "pa4-migration-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "build2.sqlite").as_posix(),
    })
    with application.app_context():
        try:
            upgrade(revision="19a01e000002")
            legacy = sa.MetaData()
            legacy.reflect(bind=db.engine)
            owner, month, category, plan, expense, allocation, task, record = [uuid4().hex for _ in range(8)]
            with db.engine.begin() as connection:
                for name, values in [
                    ("users", dict(id=owner, email="legacy-pa4@example.test", password_hash="preserve")),
                    ("budget_months", dict(id=month, user_id=owner, month_start=date(2026, 10, 1),
                        tracking_start_date=date(2026, 10, 1), available_vnd=available)),
                    ("expense_categories", dict(id=category, user_id=owner, category_name="Legacy Food")),
                    ("budget_plans", dict(id=plan, budget_month_id=month, plan_type="BALANCED",
                        status="CONFIRMED", planned_savings=999_997)),
                    ("budget_expenses", dict(id=expense, budget_month_id=month, category_id=category,
                        expense_name="Legacy Food", priority="P1", allocation_frequency="DAILY")),
                    ("budget_allocations", dict(id=allocation, plan_id=plan, budget_expense_id=expense,
                        allocated_amount=4_000_003)),
                    ("assigned_expense_tasks", dict(id=task, allocation_id=allocation,
                        assigned_date=date(2026, 10, 1), period_end=date(2026, 10, 1),
                        original_limit=129_033, current_limit=129_044, task_status="RECORDED")),
                    ("expense_records", dict(id=record, budget_month_id=month, task_id=task,
                        category_id=category, amount=12_785, expense_date=date(2026, 10, 1),
                        record_type="PLANNED", priority="P1", idempotency_key="legacy-pa4")),
                ]:
                    connection.execute(legacy.tables[name].insert().values(**values))
            def snapshot():
                with db.engine.connect() as connection:
                    return {name: connection.execute(sa.select(table).order_by(*table.primary_key.columns)).all()
                            for name, table in legacy.tables.items() if name != "alembic_version"}
            before = snapshot()
            upgrade()
            assert snapshot() == before
            with db.engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT planning_unit FROM budget_months")) == 1
            new_month = create_budget_month(UUID(owner), "2026-11", 7_000_000)
            assert new_month.planning_unit == 1000
            upgrade()
            with db.engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT available_vnd FROM budget_months WHERE id=:id"), {"id": month}) == available
        finally:
            db.session.remove()
            db.engine.dispose()


@pytest.mark.parametrize("action", ["expenses/new", "plans/generate"])
def test_visible_custom_expense_without_category_controls(app, client, action):
    with app.app_context():
        user = User(email="pa4-form@example.test", password_hash="test")
        db.session.add(user)
        db.session.commit()
        owner = user.id
        month = create_budget_month(owner, "2026-10", 7_000_000)
        month_id = month.id
    with client.session_transaction() as session:
        session["user_id"] = str(owner)
    app.config["WTF_CSRF_ENABLED"] = True
    root = f"/budget/{month_id}"
    page = client.get(root)
    assert b'name="category_id"' not in page.data
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
    fields = dict(expense_name="Entertainment", priority="P2", allocation_frequency="MONTHLY",
                  estimated_amount="200000", csrf_token=token)
    if action == "plans/generate":
        fields.update(suggestion=["rent", "electricity", "water"], rent_estimated_amount="2000000",
                      electricity_estimated_amount="200000", water_estimated_amount="100000")
    response = client.post(root + "/" + action, data=fields)
    assert response.status_code == 302
    with app.app_context():
        custom = db.session.scalar(db.select(BudgetExpense).where(BudgetExpense.expense_name == "Entertainment"))
        assert custom.category.category_name == "Entertainment"
        assert custom.estimated_amount == 200_000
        assert len(db.session.scalars(db.select(BudgetPlan)).all()) == (3 if action == "plans/generate" else 0)


def test_build3_customized_budget_to_checkin_history_dashboard_and_restart(tmp_path):
    application = create_app({
        "TESTING": True, "SECRET_KEY": "pa4-flow-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "flow.sqlite").as_posix(),
    })
    with application.app_context():
        upgrade()
    client = application.test_client()
    def csrf(path):
        page = client.get(path)
        assert page.status_code == 200
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
    credentials = dict(email="pa4-flow@example.com", password="pa4-test-password")
    assert client.post("/register", data=credentials | {"confirm_password": credentials["password"],
        "csrf_token": csrf("/register")}).status_code == 302
    assert client.post("/login", data=credentials | {"csrf_token": csrf("/login")}).status_code == 302
    token = csrf("/budget-periods/new")
    assert client.post("/budget-periods/new", data=dict(month="2026-10", available_vnd="7000000",
        tracking_start_date="2026-10-01", csrf_token=token)).status_code == 302
    with application.app_context():
        from app.models import BudgetMonth
        month_id = db.session.scalar(db.select(BudgetMonth.id))
    root = f"/budget/{month_id}"
    assert client.post(root + "/plans/generate", data=dict(
        suggestion=["rent", "electricity", "water", "food", "transportation"],
        rent_estimated_amount="2000000", electricity_estimated_amount="200000", water_estimated_amount="100000",
        food_minimum_amount="1200000", transportation_minimum_amount="200000",
        expense_name="Entertainment", priority="P2", allocation_frequency="MONTHLY",
        estimated_amount="200000", csrf_token=token)).status_code == 302
    assert client.get(root).status_code == 200
    with application.app_context():
        plans = db.session.scalars(db.select(BudgetPlan)).all()
        assert {p.plan_type for p in plans} == {"SAVING", "BALANCED", "LIFESTYLE"}
        balanced = next(p for p in plans if p.plan_type == "BALANCED")
        plan_id = balanced.id
        p0 = {a.budget_expense_id: a.allocated_amount for a in balanced.allocations if a.budget_expense.priority == "P0"}
        values = {"allocation_" + str(a.budget_expense_id): str(a.allocated_amount)
                  for a in balanced.allocations if a.budget_expense.priority != "P0"}
        food_key = next("allocation_" + str(a.budget_expense_id) for a in balanced.allocations if a.budget_expense.expense_name == "Food")
        values[food_key] = str(int(values[food_key]) + 10_000)
    editor = client.get(f"{root}/plans/{plan_id}/customize")
    fingerprint = re.search(r'name="plan_snapshot"[^>]*value="([^"]+)"', editor.text).group(1)
    saved = client.post(f"{root}/plans/{plan_id}/customize", data=values | dict(plan_snapshot=fingerprint, csrf_token=token))
    assert saved.status_code == 302
    detail = client.get(saved.location)
    confirm_snapshot = re.search(r'name="confirm_snapshot"[^>]*value="([^"]+)"', detail.text).group(1)
    with application.app_context():
        manual = db.session.scalar(db.select(BudgetPlan).where(BudgetPlan.plan_type == "MANUAL"))
        manual_id = manual.id
        original = {a.id: a.allocated_amount for a in manual.allocations}
        assert sum(original.values()) + manual.planned_savings == 7_000_000
        assert {a.budget_expense_id: a.allocated_amount for a in manual.allocations if a.budget_expense.priority == "P0"} == p0
    confirm = f"{root}/plans/{manual_id}/confirm"
    for _ in range(2):
        assert client.post(confirm, data=dict(confirm_snapshot=confirm_snapshot, csrf_token=token)).status_code == 302
    with application.app_context():
        tasks = db.session.scalars(db.select(AssignedExpenseTask)).all()
        ids = {t.id for t in tasks}
        assert len(ids) == 40
        assert all(t.original_limit % 1000 == 0 for t in tasks)
        for allocation in db.session.get(BudgetPlan, manual_id).allocations:
            assert sum(t.original_limit for t in allocation.tasks) == allocation.allocated_amount
        food = sorted((t for t in tasks if t.allocation.budget_expense.expense_name == "Food"), key=lambda t: t.assigned_date)
        actual_id, empty_id = food[0].id, food[1].id
    purchase = dict(action="actual", amount="12785", expense_date="2026-10-01", idempotency_key="pa4-purchase", csrf_token=token)
    for _ in range(2):
        assert client.post(f"/expenses/tasks/{actual_id}/checkin", data=purchase).status_code == 302
        assert client.post(f"/expenses/tasks/{empty_id}/checkin", data=dict(action="no_expense", csrf_token=token)).status_code == 302
    assert client.post(f"/expenses/tasks/{actual_id}/checkin", data=purchase | {"amount": "12786"}).status_code == 409
    history = client.get("/expenses/history?start=2026-10-01&end=2026-10-31")
    assert history.status_code == 200 and 'value="12785"' in history.text
    from app.modules.dashboard.services import build_dashboard
    with application.app_context():
        dashboard = build_dashboard(db.session.scalar(db.select(User.id)), month_id)
        assert dashboard["spent"] == 12_785 and dashboard["remaining"] is None
        assert len(db.session.scalars(db.select(ExpenseRecord)).all()) == 1
        assert {a.id: a.allocated_amount for a in db.session.get(BudgetPlan, manual_id).allocations} == original
    result = client.post("/recommendations/generate", json={"month": "2026-10"}, headers={"X-CSRFToken": token})
    assert result.status_code == 200 and result.json["status"] == "SKIPPED_INSUFFICIENT_DATA"
    assert result.json["completeness"]["complete_transaction_count"] == 1
    assert client.post(confirm).status_code == 400
    reopened = create_app(dict(application.config))
    with reopened.app_context():
        upgrade()
        assert set(db.session.scalars(db.select(AssignedExpenseTask.id))) == ids
        assert len(db.session.scalars(db.select(ExpenseRecord)).all()) == 1
        assert db.session.get(AssignedExpenseTask, empty_id).task_status == "NO_EXPENSE"
        assert {a.id: a.allocated_amount for a in db.session.get(BudgetPlan, manual_id).allocations} == original
        db.session.remove()
        db.engine.dispose()
    with application.app_context():
        db.session.remove()
        db.engine.dispose()
