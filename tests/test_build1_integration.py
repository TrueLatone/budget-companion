"""Build 1 acceptance gate: isolated migrations, startup and authenticated HTTP flow."""

import ast
from collections import Counter
from datetime import date, datetime
from http.client import HTTPConnection
import json
from pathlib import Path
import re
from threading import Thread
from uuid import UUID
import warnings

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import template_rendered, url_for
from flask.cli import routes_command
from flask_migrate import upgrade
import pytest
import sqlalchemy as sa
from werkzeug.serving import make_server

from app import create_app
from app.extensions import db
from app.models import (
    User, BudgetMonth, BudgetExpense, BudgetPlan, BudgetAllocation,
    AssignedExpenseTask, ExpenseRecord, Recommendation,
)
from app.modules.expenses import services as expenses, presentation
from app.modules.recommendations import services as recommendations


@pytest.fixture
def build_app(tmp_path, monkeypatch):
    monkeypatch.setattr(expenses, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(recommendations, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 11, 3, 12))
    application = create_app({
        "TESTING": True, "DEBUG": False, "SECRET_KEY": "isolated-build1-acceptance-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "build1.sqlite").as_posix(),
        "WTF_CSRF_ENABLED": True, "SESSION_COOKIE_SECURE": False,
    })
    with application.app_context():
        upgrade()  # Never db.create_all: exercise the actual migration lineage.
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


def snapshot():
    return {table.name: list(db.session.execute(db.select(table).order_by(*table.primary_key.columns)))
            for table in db.metadata.sorted_tables}


def count(model):
    return db.session.scalar(db.select(db.func.count(model.id)))


def token(response):
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True))
    assert match, response.status_code
    return match.group(1)


def page(application, client, path):
    captured = {}
    def capture(sender, template, context, **kw):
        captured.update(context)
    with template_rendered.connected_to(capture, application):
        response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response, captured


def register_and_login(client, email):
    csrf = token(client.get("/register"))
    response = client.post("/register", data={"email": email, "password": "build1-test-password",
                           "confirm_password": "build1-test-password", "csrf_token": csrf})
    assert response.status_code == 302 and response.location.endswith("/login")
    csrf = token(client.get("/login"))
    assert client.post("/login", data={"email": email, "password": "build1-test-password", "csrf_token": csrf}).status_code == 302
    return token(client.get("/budget-periods/new"))  # Login rotates the session/CSRF token.


def test_build1_models_routes_and_single_migration_head(build_app):
    application = build_app
    assert set(application.blueprints) == {"core", "accounts", "budget_periods", "budgets", "expenses", "dashboard", "recommendations"}
    seen = set()
    for rule in application.url_map.iter_rules():
        assert rule.endpoint in application.view_functions
        normalized = re.sub(r"<([^:<>]+):[^<>]+>", r"<\1>", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            assert (normalized, method) not in seen, (rule, method)
            seen.add((normalized, method))
    cli = application.test_cli_runner().invoke(routes_command)
    assert cli.exit_code == 0
    assert all(prefix + "." in cli.output for prefix in application.blueprints)

    config = Config("migrations/alembic.ini")
    config.set_main_option("script_location", "migrations")
    assert ScriptDirectory.from_config(config).get_heads() == ["19a01e000002"]
    with application.app_context():
        mappers = list(db.Model.registry.mappers)
        assert len(mappers) == len(db.metadata.tables) == 13
        assert set(Counter(mapper.local_table.name for mapper in mappers).values()) == {1}
        for mapper in mappers:
            assert mapper.class_.__module__.startswith("app.models.")
            for column in mapper.columns:
                if column.primary_key or column.foreign_keys:
                    assert isinstance(column.type, sa.Uuid) and column.type.as_uuid
        assert db.session.scalar(sa.text("SELECT version_num FROM alembic_version")) == "19a01e000002"
        assert db.session.scalar(sa.text("PRAGMA foreign_keys")) == 1
        with db.engine.connect() as connection, warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*expression-based index.*")
            assert compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), db.metadata) == []

    definitions = []
    for path in Path("app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "SQLAlchemy":
                definitions.append(path.as_posix())
    assert definitions == ["app/extensions.py"]


def test_build1_real_http_startup_uses_only_disposable_database(build_app):
    server = make_server("127.0.0.1", 0, build_app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        for path in ("/api/health", "/api/health/database"):
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 200
            body = json.loads(response.read())
            assert body.get("status") == "ok"
        for path in ("/", "/register", "/login", "/static/css/workspace.css", "/static/js/workspace.js", "/static/css/dashboard.css", "/static/js/dashboard.js"):
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 200, path
            response.read()
        for path in ("/dashboard", "/budget", "/expenses", "/recommendations"):
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 302 and "/login" in response.getheader("Location")
            response.read()
    finally:
        connection.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    with build_app.app_context():
        assert count(User) == count(BudgetMonth) == count(ExpenseRecord) == 0


def test_build1_registration_to_recommendation_survives_replay_and_restart(build_app):
    application = build_app
    client = application.test_client()
    csrf = register_and_login(client, "build1-owner@example.com")
    assert client.post("/budget-periods/new", data={"month": "2026-10", "available_vnd": "5000000",
                       "tracking_start_date": "2026-10-01", "csrf_token": csrf}).status_code == 302
    with application.app_context():
        month = db.session.scalar(db.select(BudgetMonth))
        month_id, owner_id = month.id, month.user_id
        assert isinstance(month_id, UUID) and isinstance(owner_id, UUID)
        assert count(BudgetExpense) == count(BudgetPlan) == count(AssignedExpenseTask) == count(ExpenseRecord) == 0
        empty_snapshot = snapshot()
    root = f"/budget/{month_id}"
    for path in (root, f"/dashboard?budget_month_id={month_id}", f"/expenses?budget_month_id={month_id}", f"/recommendations?budget_month_id={month_id}"):
        assert client.get(path).status_code == 200
    with application.app_context():
        assert snapshot() == empty_snapshot  # No automatic suggested/sample financial rows.

    suggested = {"suggestion": ["rent", "electricity", "water", "food", "transportation"],
                 "rent_estimated_amount": "1500000", "electricity_estimated_amount": "200000", "water_estimated_amount": "100000",
                 "food_minimum_amount": "300000", "transportation_minimum_amount": "100000", "csrf_token": csrf}
    for _ in range(2):
        assert client.post(root + "/expenses/suggested", data=suggested).status_code == 302
    assert client.post(root + "/expenses/new", data={"expense_name": "Entertainment", "priority": "P2", "category_id": "",
        "category_name": "Fun", "allocation_frequency": "MONTHLY", "estimated_amount": "", "minimum_amount": "", "csrf_token": csrf}).status_code == 302
    with application.app_context():
        assert count(BudgetExpense) == 6
        assert db.session.scalar(db.select(BudgetExpense).where(BudgetExpense.expense_name == "Food")).estimated_amount is None
    assert client.post(root + "/plans/generate", data={"csrf_token": csrf}).status_code == 302
    assert b"Compare saved plans" in client.get(root).data
    with application.app_context():
        plans = list(db.session.scalars(db.select(BudgetPlan)))
        assert {plan.plan_type for plan in plans} == {"SAVING", "BALANCED", "LIFESTYLE"}
        assert len(plans) == 3 and count(BudgetAllocation) == 18
        for plan in plans:
            assert sum(a.allocated_amount for a in plan.allocations) + plan.planned_savings == 5_000_000
        plan_id = next(plan.id for plan in plans if plan.plan_type == "BALANCED")
    assert client.post(f"{root}/plans/{plan_id}/confirm", data={"csrf_token": csrf, "allocated_amount": "1"}).status_code == 302
    with application.app_context():
        assert count(AssignedExpenseTask) == 0
        assert db.session.get(BudgetPlan, plan_id).status == "CONFIRMED"
    assert b"schedule has not been created" in client.get(f"/expenses?budget_month_id={month_id}&view=month").data
    assert client.post(f"/expenses/months/{month_id}/schedule", data={"csrf_token": csrf}).status_code == 302
    calendar, context = page(application, client, f"/expenses?budget_month_id={month_id}&view=month")
    cells = {cell.day: cell for week in context["calendar"] for cell in week if cell}
    assert len(cells) == 31 and all("Food" in cell.daily_names for cell in cells.values())
    with application.app_context():
        tasks = list(db.session.scalars(db.select(AssignedExpenseTask)))
        assert len(tasks) == 40
        assert all(isinstance(task.id, UUID) and isinstance(task.allocation_id, UUID) and type(task.original_limit) is int for task in tasks)
        for allocation in db.session.get(BudgetPlan, plan_id).allocations:
            assert sum(task.original_limit for task in tasks if task.allocation_id == allocation.id) == allocation.allocated_amount
        by_name_date = {(task.allocation.budget_expense.expense_name, task.assigned_date): task.id for task in tasks}
        first_task = by_name_date[("Food", date(2026, 10, 1))]
        no_expense_task = by_name_date[("Food", date(2026, 10, 2))]

    first_body = {"action": "actual", "amount": "123456", "expense_date": "2026-10-01", "idempotency_key": "build1-first-purchase"}
    for _ in range(2):
        assert client.post(f"/expenses/tasks/{first_task}/checkin", data=first_body | {"csrf_token": csrf}).status_code == 302
    assert client.post(f"/expenses/tasks/{first_task}/checkin", data=first_body | {"amount": "123457", "csrf_token": csrf}).status_code == 409
    for _ in range(2):
        assert client.post(f"/expenses/tasks/{no_expense_task}/checkin", data={"action": "no_expense", "csrf_token": csrf}).status_code == 302
    _, context = page(application, client, f"/dashboard?budget_month_id={month_id}")
    assert context["view"]["spent"] == 123456 and context["view"]["remaining"] is None
    assert context["view"]["planned"] == 4_360_000 and context["view"]["savings"] == 640_000
    insufficient = client.post("/recommendations/generate", json={"month": "2026-10"}, headers={"X-CSRFToken": csrf})
    assert insufficient.status_code == 200 and insufficient.json["status"] == "SKIPPED_INSUFFICIENT_DATA"
    assert insufficient.json["recommendations"] == [] and insufficient.json["baseline_guidance"]
    with application.app_context():
        assert count(ExpenseRecord) == 1 and count(Recommendation) == 0

    # Extend only this synthetic test account with explicitly submitted purchases
    # and explicit check-ins, never by lowering F18 or auto-inserting transactions.
    for day in (5, 9, 13, 17, 21, 25, 31):
        task_id = by_name_date[("Food", date(2026, 10, day))]
        assert client.post(f"/expenses/tasks/{task_id}/checkin", data={"action": "actual", "amount": "1000",
            "idempotency_key": f"build1-food-{day}", "csrf_token": csrf}).status_code == 302
    for name, amount, expense_date in (("Rent", "1500000", "2026-10-31"), ("Transportation", "100000", "2026-10-01")):
        task_id = by_name_date[(name, date(2026, 10, 1))]
        assert client.post(f"/expenses/tasks/{task_id}/checkin", data={"action": "actual", "amount": amount, "expense_date": expense_date,
            "idempotency_key": "build1-" + name.lower(), "csrf_token": csrf}).status_code == 302
    with application.app_context():
        unresolved = list(db.session.scalars(db.select(AssignedExpenseTask.id).where(AssignedExpenseTask.task_status == "PENDING")))
    for task_id in unresolved:
        assert client.post(f"/expenses/tasks/{task_id}/checkin", data={"action": "no_expense", "csrf_token": csrf}).status_code == 302
    response = client.post("/recommendations/generate", json={"month": "2026-10"}, headers={"X-CSRFToken": csrf})
    assert response.status_code == 201 and response.json["completeness"]["status"] == "SUFFICIENT"
    assert response.json["completeness"]["complete_transaction_count"] == 10
    assert response.json["completeness"]["category_count"] == 3 and response.json["completeness"]["coverage_days"] == 31
    recommendation_ids = {row["id"] for row in response.json["recommendations"]}
    assert recommendation_ids and not response.json["adjustments_enabled"]
    recommendation_id = next(iter(recommendation_ids))
    again = client.post("/recommendations/generate", json={"month": "2026-10"}, headers={"X-CSRFToken": csrf})
    assert again.status_code == 200 and {row["id"] for row in again.json["recommendations"]} == recommendation_ids
    with application.app_context():
        before_accept = snapshot()
    accepted = client.post(
        f"/recommendations/{recommendation_id}/decision",
        json={"decision": "ACCEPT"},
        headers={"X-CSRFToken": csrf},
    )
    assert accepted.status_code == 200
    assert accepted.json == {
        "status": "ACCEPTED",
        "recommendation_id": recommendation_id,
        "adjustments_enabled": False,
        "financial_adjustment_applied": False,
    }
    with application.app_context():
        after_accept = snapshot()
        assert db.session.get(Recommendation, UUID(recommendation_id)).status == "ACCEPTED"
        assert {
            name: rows for name, rows in after_accept.items()
            if name != Recommendation.__tablename__
        } == {
            name: rows for name, rows in before_accept.items()
            if name != Recommendation.__tablename__
        }
    _, context = page(application, client, f"/dashboard?budget_month_id={month_id}")
    assert context["view"]["spent"] == 1_730_456
    assert context["view"]["remaining"] == 2_629_544 and context["view"]["data_complete"]
    with application.app_context():
        assert count(ExpenseRecord) == 10 and count(AssignedExpenseTask) == 40
        record_id = db.session.scalar(db.select(ExpenseRecord.id))
        expense_id = db.session.scalar(db.select(BudgetExpense.id))
        stable = snapshot()
        assert all(isinstance(r.id, UUID) and isinstance(r.budget_month_id, UUID) and type(r.amount) is int
                   for r in db.session.scalars(db.select(ExpenseRecord)))

    read_paths = [root, f"{root}/plans/{plan_id}", f"{root}/expenses/new", f"{root}/expenses/{expense_id}/edit",
        "/account", "/budget-periods", f"/budget-periods/{month_id}/edit",
        f"/expenses?budget_month_id={month_id}&view=month", "/expenses?view=day&date=2026-10-01",
        "/expenses?view=year&year=2026", "/expenses/history?start=2026-10-01&end=2026-10-31",
        f"/dashboard?budget_month_id={month_id}", f"/recommendations?budget_month_id={month_id}",
        "/recommendations/analysis?month=2026-10", "/recommendations/completeness?month=2026-10",
        "/recommendations/monthly-review?month=2026-10", f"/recommendations/{recommendation_id}"]
    for path in read_paths:
        assert client.get(path).status_code == 200, path
    assert client.post(f"/expenses/months/{month_id}/schedule", data={"csrf_token": csrf}).status_code == 302
    assert client.post(f"{root}/plans/{plan_id}/confirm", data={"csrf_token": csrf}).status_code == 302
    assert client.post(root + "/plans/generate", data={"csrf_token": csrf}).status_code == 409
    values = dict(month_id=month_id, budget_month_id=month_id, expense_id=expense_id,
                  plan_id=plan_id, task_id=first_task, record_id=record_id, recommendation_id=recommendation_id)
    # Every registered mutating route is guarded by the existing global CSRF.
    for rule in application.url_map.iter_rules():
        if "POST" in rule.methods:
            with application.test_request_context():
                path = url_for(rule.endpoint, **{key: values[key] for key in rule.arguments})
            assert client.post(path).status_code == 400, path
    with application.app_context():
        assert snapshot() == stable

    intruder = application.test_client()
    other_csrf = register_and_login(intruder, "build1-other@example.com")
    for path in (f"/dashboard?budget_month_id={month_id}", root, f"/expenses?budget_month_id={month_id}", f"/recommendations/{recommendation_id}"):
        assert intruder.get(path).status_code == 404, path
    assert intruder.post(f"/expenses/months/{month_id}/schedule", data={"csrf_token": other_csrf, "user_id": str(owner_id)}).status_code == 404
    assert intruder.post(f"/recommendations/{recommendation_id}/decision", json={"decision": "REJECT", "user_id": str(owner_id)}, headers={"X-CSRFToken": other_csrf}).status_code == 404
    with application.app_context():
        stable = snapshot()

    # Reopen the real migrated file under a fresh factory/session and re-login.
    reopened = create_app(dict(application.config))
    with reopened.app_context():
        upgrade()  # Repeated upgrade at head must preserve all existing records.
        assert snapshot() == stable
    reopened_client = reopened.test_client()
    fresh_csrf = token(reopened_client.get("/login"))
    assert reopened_client.post("/login", data={"email": "build1-owner@example.com", "password": "build1-test-password", "csrf_token": fresh_csrf}).status_code == 302
    fresh_csrf = token(reopened_client.get("/budget-periods/new"))
    assert reopened_client.post(f"/expenses/tasks/{first_task}/checkin", data=first_body | {"csrf_token": fresh_csrf}).status_code == 302
    for locale in ("en", "vi"):
        for path in ("/dashboard", "/budget", "/expenses", "/recommendations"):
            response = reopened_client.get(path + f"?budget_month_id={month_id}&lang={locale}")
            assert response.status_code == 200 and f'<html lang="{locale}">'.encode() in response.data
            assert b"workspace-sidebar" in response.data
    with reopened.app_context():
        assert snapshot() == stable
        db.session.remove()
        db.engine.dispose()
