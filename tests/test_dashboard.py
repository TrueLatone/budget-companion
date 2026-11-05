"""KAN-25 connects Thien's workspace to real Budget/Expense/Recommendation data."""

from datetime import date, datetime
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from flask import template_rendered
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User, BudgetMonth, BudgetPlan, ExpenseCategory, ExpenseRecord
from app.modules.budget_periods.services import create_budget_month, update_available_vnd
from app.modules.budgets import services as budgets
from app.modules.budgets.suggestions import SUGGESTED_EXPENSES
from app.modules.expenses import services as expenses, presentation
from app.modules.recommendations import services as recommendations
from app.modules.dashboard import services


def snapshot():
    return {table.name: list(db.session.execute(db.select(table).order_by(*table.primary_key.columns)))
            for table in db.metadata.sorted_tables}


@pytest.fixture
def setup(app, client, monkeypatch):
    monkeypatch.setattr(expenses, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(recommendations, "today_vn", lambda: date(2026, 11, 3))
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 11, 3, 12))
    with app.app_context():
        owner = User(email="workspace@example.com", password_hash=generate_password_hash("test-password"))
        other = User(email="private-workspace@example.com", password_hash="test-only")
        db.session.add_all([owner, other])
        db.session.commit()
        month = create_budget_month(owner.id, "2026-10", 5_000_000, date(2026, 10, 15))
        later = create_budget_month(owner.id, "2026-11", 500_003)
        foreign = create_budget_month(other.id, "2026-10", 99_000_000)
        budgets.apply_suggested_expenses(owner.id, month.id, [s.key for s in SUGGESTED_EXPENSES if s.selected], {
            s.key: {"estimated_amount": s.example_amount} for s in SUGGESTED_EXPENSES
        })
        budgets.save_expense(owner.id, month.id, dict(expense_name="Entertainment", category_name="Fun", priority="P2", allocation_frequency="MONTHLY"))
        db.session.add(ExpenseCategory(user_id=other.id, category_name="Private category"))
        db.session.commit()
        plans = budgets.generate_budget_plans(owner.id, month.id)
        data = dict(user=owner.id, other=other.id, month=month.id, later=later.id, foreign=foreign.id, plan=plans[1].id)
    with client.session_transaction() as session:
        session["user_id"] = str(data["user"])
        session["active_budget_month_id"] = str(data["month"])
    return data


def schedule(data):
    budgets.confirm_plan(data["user"], data["month"], data["plan"])
    return expenses.ensure_tasks_for_month(data["user"], data["month"])


def actual(data, task, amount="100"):
    return expenses.checkin_task(data["user"], task.id, action="actual", amount_raw=amount)


def page(app, client, url):
    context = {}
    def capture(sender, template, context: dict, **kw):
        result.update(context)
    result = context
    with template_rendered.connected_to(capture, app):
        response = client.get(url)
    assert response.status_code == 200
    return response, context


def test_dashboard_no_confirmation_never_uses_drafts_or_sample_finances(app, client, setup):
    with app.app_context():
        before = snapshot()
        view = services.build_dashboard(setup["user"], setup["month"])
        assert view["planned"] is view["savings"] is view["remaining"] is None
        assert view["unallocated"] == 5_000_000 and view["spent"] == 0
        assert view["schedule_state"].code == "UNCONFIRMED"
    response, _ = page(app, client, "/dashboard")
    assert b"Example data" not in response.data and b"Browser preview" not in response.data
    assert b"workspace.css" in response.data and b"dashboard.css" in response.data
    with app.app_context():
        assert snapshot() == before


def test_confirm_schedule_and_calendar_connect_to_dashboard(app, client, setup):
    assert client.post(f"/budget/{setup['month']}/plans/{setup['plan']}/confirm").status_code == 302
    response, context = page(app, client, "/dashboard")
    assert context["view"]["schedule_state"].code == "READY"
    assert context["view"]["planned"] == 4_360_000
    assert context["view"]["savings"] == 640_000 and context["view"]["remaining"] is None
    assert context["view"]["task_count"] == 24 and context["view"]["missing"] == 24
    calendar = client.get(f"/expenses?budget_month_id={setup['month']}&view=month")
    assert b"Food" in calendar.data and b"AssignedDate" in calendar.data


def test_checkins_unexpected_and_funds_additions_update_real_dashboard_correctly(app, client, setup):
    with app.app_context():
        tasks = schedule(setup)
        food = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Food")
        task_id = food.id
    assert client.post(f"/expenses/tasks/{task_id}/checkin", data={"action": "actual", "amount": "100"}).status_code == 302
    with app.app_context():
        expenses.create_unexpected_record(setup["user"], dict(budget_month_id=str(setup["month"]), title="Real repair", category="Food",
            priority="P2", amount="23", expense_date="2026-10-20"))
        db.session.add(ExpenseRecord(budget_month_id=setup["month"], amount=1_000_000, record_type="FUNDS_ADDED", expense_date=date(2026, 10, 20)))
        db.session.commit()
        before = snapshot()
    response, context = page(app, client, "/dashboard")
    view = context["view"]
    assert view["spent"] == 123 and view["remaining"] is None
    assert {row["priority"]: row["spent"] for row in view["groups"]} == {"P0": 0, "P1": 100, "P2": 23}
    assert len(view["records"]) == 2 and sum(row["amount"] for row in view["breakdown"]) == 123
    assert sum(row["share"] for row in view["breakdown"]) == 1000
    assert b"Real repair" in response.data and b"FUNDS_ADDED" not in response.data
    with app.app_context():
        assert snapshot() == before


def test_explicit_no_expense_and_recorded_status_enable_known_balance_only_when_complete(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        actual(setup, tasks[0], "123")
        assert services.build_dashboard(setup["user"], setup["month"])["remaining"] is None
        for task in tasks[1:]:
            expenses.checkin_task(setup["user"], task.id, action="no_expense")
        view = services.build_dashboard(setup["user"], setup["month"])
        assert view["data_complete"] and view["remaining"] == view["planned"] - 123
        assert view["counts"]["no_expense"] == 23 and view["missing"] == 0
        assert view["completeness"]["status"] == "INSUFFICIENT"  # F18 readiness is a different question.


def test_savings_and_unallocated_funds_never_double_count_saved_plan(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        actual(setup, tasks[0])
        month = budgets.get_month(setup["user"], setup["month"])
        update_available_vnd(month, 6_000_000)
        view = services.build_dashboard(setup["user"], setup["month"])
        assert view["planned"] == 4_360_000 and view["saved_total"] == 5_000_000
        assert view["savings"] == 640_000 and view["available"] == 6_000_000
        assert view["unallocated"] == 1_000_000 and view["funding_shortfall"] == 0
        assert view["remaining"] is None  # 6M funding is not a spending balance.
        update_available_vnd(month, 4_000_000)
        view = services.build_dashboard(setup["user"], setup["month"])
        assert view["funding_shortfall"] == 1_000_000 and view["unallocated"] == 0
        assert view["saved_total"] == 5_000_000


def test_dashboard_missing_tasks_and_unknown_checkins_never_produce_zero_remaining(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        for task in tasks:
            expenses.checkin_task(setup["user"], task.id, action="no_expense")
        assert services.build_dashboard(setup["user"], setup["month"])["data_complete"]
        db.session.delete(tasks[0])
        db.session.commit()
        view = services.build_dashboard(setup["user"], setup["month"])
        assert not view["data_complete"] and view["remaining"] is None
        assert view["schedule_state"].code == "INCOMPLETE"


def test_recent_transactions_are_owned_sorted_and_escaped(app, client, setup):
    with app.app_context():
        expenses.create_unexpected_record(setup["user"], dict(budget_month_id=str(setup["month"]), title="<script>bad()</script>", category="Food",
            priority="P1", amount="7", expense_date="2026-10-20"))
        expenses.create_unexpected_record(setup["other"], dict(budget_month_id=str(setup["foreign"]), title="Private transaction", category="Private category",
            priority="P2", amount="99999", expense_date="2026-10-21"))
        before = snapshot()
    response, context = page(app, client, "/dashboard")
    assert context["view"]["spent"] == 7
    assert b"&lt;script&gt;bad()&lt;/script&gt;" in response.data and b"<script>bad()" not in response.data
    assert b"Private transaction" not in response.data and b"Private category" not in response.data
    assert client.get(f"/dashboard?budget_month_id={setup['foreign']}").status_code == 404
    with app.app_context():
        assert snapshot() == before


@pytest.mark.parametrize("query", ["month=2026-13", "month=bad", "budget_month_id=bad", "month=2025-01"])
def test_dashboard_rejects_invalid_or_unowned_months_without_sample_fallback(client, setup, query):
    assert client.get("/dashboard?" + query).status_code == 404


class WorkspaceLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = {}
        self.language_links = []
        self.feed(html)
    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "a" and "data-workspace-page" in attrs:
            self.links[attrs["data-workspace-page"]] = attrs["href"]
        if tag == "a" and attrs.get("hreflang") in ("en", "vi"):
            self.language_links.append(attrs["href"])


@pytest.mark.parametrize("path", ["/dashboard", "/budget", "/expenses", "/recommendations"])
def test_workspace_navigation_preserves_owned_selected_month_on_all_four_pages(app, client, setup, path):
    with client.session_transaction() as session:
        session["active_budget_month_id"] = str(setup["later"])
    response = client.get(path + f"?budget_month_id={setup['month']}")
    assert response.status_code == 200
    markup = WorkspaceLinks(response.get_data(as_text=True))
    assert set(markup.links) == {"dashboard", "budgets", "expenses", "recommendations"}
    for destination in markup.links.values():
        assert parse_qs(urlsplit(destination).query)["budget_month_id"] == [str(setup["month"])]
        assert client.get(destination).status_code == 200
    assert b"workspace-sidebar" in response.data and b"workspace.js" in response.data
    assert all(str(setup["month"]) in url for url in markup.language_links)


def test_workspace_month_alias_and_date_history_keep_the_same_context(app, client, setup):
    for path in ("/dashboard?month=2026-10", "/budget?month=2026-10", "/expenses/history?start=2026-10-15&end=2026-10-31"):
        response = client.get(path)
        assert response.status_code == 200
        assert all(str(setup["month"]) in url for url in WorkspaceLinks(response.get_data(as_text=True)).links.values())
    assert client.get("/budget?month=2026-13").status_code == 404


@pytest.mark.parametrize("locale", ["en", "vi"])
def test_workspace_dashboard_and_budget_preserve_language_and_month(client, setup, locale):
    response = client.get(f"/dashboard?budget_month_id={setup['month']}&lang={locale}")
    assert f'<html lang="{locale}">'.encode() in response.data
    assert ("Funding and saved plan" if locale == "en" else "Nguồn tiền và kế hoạch đã lưu").encode() in response.data
    response = client.get(f"/budget?budget_month_id={setup['month']}")
    assert f'<html lang="{locale}">'.encode() in response.data
    assert ("Expense name" if locale == "en" else "Tên khoản chi").encode() in response.data


def test_zero_data_account_and_empty_owned_month_render_no_demo(client, app):
    with app.app_context():
        owner = User(email="empty-workspace@example.com", password_hash="test-only")
        db.session.add(owner)
        db.session.commit()
        owner_id = owner.id
    with client.session_transaction() as session:
        session["user_id"] = str(owner_id)
    assert b"No Budget Month yet" in client.get("/dashboard").data
    with app.app_context():
        month = create_budget_month(owner_id, "2026-10", 0)
        month_id = month.id
    response, context = page(app, client, f"/dashboard?budget_month_id={month_id}")
    assert context["view"]["available"] == 0 and context["view"]["remaining"] is None
    assert context["view"]["records"] == [] and b"Example data" not in response.data


def test_bigint_dashboard_totals_and_chart_shares_remain_exact(app, setup):
    from app.modules.budgets.rules import MAX_VND
    with app.app_context():
        month = budgets.get_month(setup["user"], setup["month"])
        update_available_vnd(month, MAX_VND)
        plans = budgets.generate_budget_plans(setup["user"], setup["month"])
        setup = setup | {"plan": plans[1].id}
        tasks = schedule(setup)
        actual(setup, tasks[0], str(MAX_VND))
        view = services.build_dashboard(setup["user"], setup["month"])
        assert view["spent"] == MAX_VND and view["saved_total"] == MAX_VND
        assert view["planned"] + view["savings"] == MAX_VND
        assert all(type(view[key]) is int for key in ("spent", "planned", "savings", "saved_total", "available"))
        assert sum(row["share"] for row in view["breakdown"]) == 1000


def test_workspace_login_csrf_budget_confirmation_schedule_and_dashboard_refresh(app, client, setup):
    app.config["WTF_CSRF_ENABLED"] = True
    with client.session_transaction() as session:
        session.clear()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"email": "workspace@example.com", "password": "test-password", "csrf_token": token}).status_code == 302
    root = f"/budget/{setup['month']}"
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get(root).get_data(as_text=True)).group(1)
    assert client.post(f"{root}/plans/{setup['plan']}/confirm", data={"csrf_token": token}).status_code == 302
    assert client.post(f"/expenses/months/{setup['month']}/schedule", data={"csrf_token": token}).status_code == 302
    with app.app_context():
        food_id = next(t.id for t in expenses.list_tasks(setup["user"], date(2026, 10, 1), date(2026, 10, 31)) if t.title == "Food")
    assert client.post(f"/expenses/tasks/{food_id}/checkin", data={"action": "actual", "amount": "321", "csrf_token": token}).status_code == 302
    _, context = page(app, client, f"/dashboard?budget_month_id={setup['month']}")
    assert context["view"]["spent"] == 321
    assert client.get(f"/recommendations?budget_month_id={setup['month']}").status_code == 200


def test_live_assets_never_activate_browser_financial_persistence():
    from pathlib import Path
    for name in ("workspace.js", "dashboard.js"):
        source = Path("app/static/js", name).read_text(encoding="utf-8")
        assert "localStorage" not in source and "sessionStorage" not in source and "defaultPlan" not in source
    assert not Path("app/ui_demo.py").exists()


def test_invalid_confirmed_snapshot_does_not_present_saved_savings_as_unallocated_cash(app, setup):
    with app.app_context():
        month = create_budget_month(setup["user"], "2026-09", 1000)
        # Legacy/incomplete imported state, never produced by Budget confirmation.
        db.session.add(BudgetPlan(budget_month_id=month.id, plan_type="MANUAL", status="CONFIRMED", planned_savings=1000))
        db.session.commit()
        view = services.build_dashboard(setup["user"], month.id)
        assert view["schedule_state"].code == "NO_ALLOCATIONS"
        assert view["savings"] == 1000
        assert view["saved_total"] is view["unallocated"] is view["remaining"] is None
