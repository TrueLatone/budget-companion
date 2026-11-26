from datetime import date

import pytest

from app.extensions import db
from app.models import BudgetMonth, ExpenseRecord, User
from app.modules.budget_periods.services import create_budget_month
from app.modules.budgets import services as budgets
from app.modules.budgets.rules import BudgetError, meal_breakdown
from app.modules.expenses import services as expenses


def test_whole_thousands_month_to_schedule_and_deletion(app, client):
    with app.app_context():
        owner = User(email="owner@example.test", password_hash="test")
        other = User(email="other@example.test", password_hash="test")
        db.session.add_all([owner, other])
        db.session.commit()
        owner_id, other_id = owner.id, other.id
        with pytest.raises(BudgetError):
            create_budget_month(owner_id, "2026-11", 7_000_500)
        month = create_budget_month(owner_id, "2026-11", 7_000_000, date(2026, 11, 23))
        retained = create_budget_month(owner_id, "2026-12", 1_000_000)
        month_id, retained_id = month.id, retained.id
        for name, priority, amount, freq in [
            ("Water", "P0", 100_000, "MONTHLY"), ("Electricity", "P0", 200_000, "MONTHLY"),
            ("Rent", "P0", 2_000_000, "MONTHLY"), ("Food", "P1", 1_300_000, "DAILY"),
            ("Transport", "P1", 100_000, "WEEKLY"),
        ]:
            budgets.save_expense(owner_id, month_id, dict(expense_name=name, priority=priority,
                estimated_amount=amount, allocation_frequency=freq, category_name=name,
                due_day=15 if freq=="MONTHLY" else None))
        plans = budgets.generate_budget_plans(owner_id, month_id)
        for plan in plans:
            values = [a.allocated_amount for a in plan.allocations] + [plan.planned_savings]
            assert sum(values) == 7_000_000 and all(v % 1000 == 0 for v in values)
        plan_id = plans[0].id
        lifestyle_id = next(p.id for p in plans if p.plan_type == "LIFESTYLE")

    client.set_cookie("bc_language", "vi")
    with client.session_transaction() as session:
        session["user_id"] = str(owner_id)
        session["active_budget_month_id"] = str(month_id)
    overview = client.get(f"/budget/{month_id}").text
    sidebar = overview.split('<aside class="ws-budget-summary">')[1].split('</aside>')[0]
    assert '7.000.000' in sidebar and 'ws-summary-breakdown' not in sidebar
    assert 'BALANCED' not in sidebar and 'Bản nháp' not in sidebar
    detail = client.get(f"/budget/{month_id}/plans/{lifestyle_id}").text
    assert 'Linh hoạt · 11/2026' in detail and 'GENERATED' in detail
    edit = client.post(f"/budget-periods/{month_id}/edit", data={"available_vnd":"1000000"})
    assert edit.status_code == 409 and "Nguồn tiền gốc đã khóa" in edit.text
    confirmed = client.post(f"/budget/{month_id}/plans/{plan_id}/confirm")
    assert confirmed.status_code == 302
    from urllib.parse import parse_qs, urlsplit
    target = urlsplit(confirmed.location)
    assert target.path == "/expenses"
    assert parse_qs(target.query) == {"budget_month_id": [str(month_id)], "view": ["month"]}
    assert client.get(confirmed.location).status_code == 200
    assert "Nguồn tiền ban đầu" in client.get(f"/budget/{month_id}").text
    year = client.get("/budget?view=year&year=2026")
    assert "11/2026" in year.text and "12/2026" in year.text
    with app.app_context():
        for a in budgets.get_confirmed_allocations(owner_id, month_id):
            tasks = [t for t in expenses.ensure_tasks_for_month(owner_id, month_id) if t.allocation_id == a.id]
            assert sum(t.original_limit for t in tasks) == a.allocated_amount
            assert all(t.original_limit % 1000 == 0 for t in tasks)
            if a.budget_expense.expense_name == "Food":
                for t in tasks:
                    meals = meal_breakdown(t.original_limit, 1000)
                    assert sum(meals.values()) == t.original_limit and all(v % 1000 == 0 for v in meals.values())
                expenses.checkin_task(owner_id, tasks[0].id, action="actual", amount_raw="12785", idempotency_key="revision-check")
    path = f"/budget-periods/{month_id}/delete"
    assert client.post(path).status_code == 400
    with client.session_transaction() as session:
        session["user_id"] = str(other_id)
    assert client.post(path, data={"confirm_month":str(month_id)}).status_code == 404
    with client.session_transaction() as session:
        session["user_id"] = str(owner_id)
    assert client.post(path, data={"confirm_month":str(month_id)}).status_code == 302
    assert client.get("/budget").status_code == 200
    with app.app_context():
        assert db.session.get(BudgetMonth, month_id) is None
        assert db.session.get(BudgetMonth, retained_id) is not None
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0
