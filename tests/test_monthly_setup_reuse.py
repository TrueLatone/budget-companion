"""Two-month setup, goal enforcement and the confirmed-schedule boundary."""
from uuid import uuid4

import pytest

from app.extensions import db
from app.models import AssignedExpenseTask, BudgetMonth, User
from app.modules.budget_periods.services import create_budget_month
from app.modules.budgets import services
from app.modules.budgets.rules import BudgetError

BASE_SETUP = {
    "suggestion": ["rent", "electricity", "water", "food"],
    "rent_estimated_amount": "2000000", "rent_due_day": "5", "rent_is_recurring": "on",
    "electricity_estimated_amount": "300000", "water_estimated_amount": "200000",
    "food_minimum_amount": "1200000", "food_is_recurring": "on",
    "expense_name": "Cinema", "priority": "P2", "allocation_frequency": "WEEKLY",
}


@pytest.fixture()
def months(app, client):
    with app.app_context():
        user = User(email="planner@example.test", password_hash="test")
        db.session.add(user)
        db.session.commit()
        owner = user.id
        december = create_budget_month(owner, "2026-12", 7_000_000)
        january = create_budget_month(owner, "2027-01", 6_000_000)
        ids = (owner, december.id, january.id)
    with client.session_transaction() as session:
        session["user_id"] = str(owner)
    return ids


@pytest.mark.parametrize("mode, expected", [
    ("all", {"Rent", "Electricity", "Water", "Food", "Cinema"}),
    ("recurring", {"Rent", "Food"}),
])
def test_copy_confirmed_setup_into_empty_owned_month(app, client, months, mode, expected):
    owner, old, new = months
    old_url, new_url = f"/budget/{old}", f"/budget/{new}"
    post = {"mode": mode, "source_month": str(old)}
    assert client.post(new_url + "/reuse", data=post).status_code == 409
    assert client.post(old_url + "/plans/generate", data=BASE_SETUP).status_code == 302
    with app.app_context():
        plan = services.list_plans(owner, old)[0]
        services.confirm_and_schedule(owner, old, plan.id)
        original_tasks = {t.id: t.original_limit for t in db.session.scalars(db.select(AssignedExpenseTask))}
    assert client.post(new_url + "/reuse", data={**post, "source_month": str(uuid4())}).status_code == 409
    assert client.post(new_url + "/reuse", data=post).status_code == 302
    assert client.post(new_url + "/reuse", data=post).status_code == 409
    with app.app_context():
        copied = {e.expense_name: e for e in services.list_expenses(owner, new)}
        assert set(copied) == expected
        assert copied["Rent"].is_recurring and copied["Rent"].due_day == 5
        assert copied["Rent"].estimated_amount == 2_000_000
        assert copied["Food"].minimum_amount == 1_200_000
        assert copied["Food"].allocation_frequency == "DAILY"
        original = services.list_expenses(owner, old)
        assert {e.id for e in original}.isdisjoint(e.id for e in copied.values())
        assert services.get_month(owner, new).available_vnd == 6_000_000
        assert not services.list_plans(owner, new)
        assert {t.id: t.original_limit for t in db.session.scalars(db.select(AssignedExpenseTask))} == original_tasks


@pytest.mark.parametrize("locale,hint,excess", [
    ("en", "Example per month", "3,299,000 VND"),
    ("vi", "Tham khảo mỗi tháng", "3.299.000 VND"),
])
def test_savings_goal_and_hints_through_budget_flow(app, client, months, locale, hint, excess):
    owner, old, _ = months
    url = f"/budget/{old}"
    assert hint in client.get(url + "?lang=" + locale).text
    response = client.post(url + "/plans/generate", data={**BASE_SETUP, "savings_target": "4000000"})
    assert response.status_code == 400 and excess in response.text
    with app.app_context():
        assert not services.list_expenses(owner, old)
    assert client.post(url + "/plans/generate", data={**BASE_SETUP, "savings_target": "2500000"}).status_code == 302
    with app.app_context():
        month = db.session.get(BudgetMonth, old)
        assert month.savings_target == 2_500_000
        plans = services.list_plans(owner, old)
        for plan in plans:
            assert plan.planned_savings >= month.savings_target
            assert sum(a.allocated_amount for a in plan.allocations) + plan.planned_savings == month.available_vnd
        plan = plans[0]
        editable = {str(a.budget_expense_id): a.allocated_amount for a in plan.allocations
                    if a.budget_expense.priority != "P0"}
        editable[next(iter(editable))] += 1000
        fingerprint = services.customization_fingerprint(owner, old, plan.id)
        with pytest.raises(BudgetError, match="savings target"):
            services.save_manual_plan(owner, old, plan.id, editable, expected_fingerprint=fingerprint)
        services.confirm_and_schedule(owner, old, plan.id)
        for allocation in plan.allocations:
            assert sum(task.original_limit for task in allocation.tasks) == allocation.allocated_amount


def test_blank_goal_restores_original_candidates(app, client, months):
    owner, old, _ = months
    url = f"/budget/{old}/plans/generate"
    def snapshot():
        with app.app_context():
            return [(p.plan_type, p.planned_savings,
                     sorted((a.budget_expense_id, a.allocated_amount) for a in p.allocations))
                    for p in services.list_plans(owner, old)]
    assert client.post(url, data=BASE_SETUP).status_code == 302
    original = snapshot()
    assert client.post(url, data={"savings_target": "2500000"}).status_code == 302
    assert snapshot() != original
    assert client.post(url, data={"savings_target": ""}).status_code == 302
    assert snapshot() == original


def test_reuse_respects_ownership_calendar_and_csrf(app, client, months):
    owner, december, january = months
    assert client.post(f"/budget/{december}/plans/generate", data=BASE_SETUP).status_code == 302
    with app.app_context():
        services.confirm_and_schedule(owner, december, services.list_plans(owner, december)[0].id)
        other = User(email="other-planner@example.test", password_hash="test")
        db.session.add(other)
        db.session.commit()
        other_month = create_budget_month(other.id, "2027-01", 6_000_000).id
        march = create_budget_month(owner, "2027-03", 7_000_000).id
    data = {"mode": "all", "source_month": str(december)}
    assert client.post(f"/budget/{other_month}/reuse", data=data).status_code == 404
    assert client.post(f"/budget/{march}/reuse", data=data).status_code == 409
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post(f"/budget/{january}/reuse", data=data).status_code == 400


@pytest.mark.parametrize("case", range(44, 59), ids=lambda n: f"BP-{n}")
def test_reviewed_planning_case(app, client, months, case):
    owner, old, new = months
    source = f"/budget/{old}/plans/generate"
    setup = BASE_SETUP.copy()
    if case == 51:
        setup.pop("rent_is_recurring")
        setup.pop("food_is_recurring")
    if case >= 54:
        goal = {54:"", 55:"2500000", 56:"3299000", 57:"3300000", 58:"2500000"}[case]
        result = client.post(source, data={**setup, "savings_target":goal})
        with app.app_context():
            plans = services.list_plans(owner, old)
            if case == 57:
                assert result.status_code == 400 and not plans
                assert "3,299,000" in result.text
            else:
                assert result.status_code == 302 and len(plans) == 3
                assert all(p.planned_savings >= int(goal or 0) for p in plans)
                if case == 54:
                    assert services.get_month(owner, old).savings_target is None
                    assert len({p.planned_savings for p in plans}) > 1
                if case == 58:
                    p = plans[0]
                    values = {str(a.budget_expense_id):a.allocated_amount for a in p.allocations if a.budget_expense.priority != "P0"}
                    values[next(iter(values))] += 1000
                    with pytest.raises(BudgetError, match="savings target"):
                        services.save_manual_plan(owner, old, p.id, values, expected_fingerprint=services.customization_fingerprint(owner,old,p.id))
        return
    assert client.post(source,data=setup).status_code == 302
    with app.app_context():
        if case != 46:
            services.confirm_and_schedule(owner,old,services.list_plans(owner,old)[0].id)
        if case == 48:
            new = create_budget_month(owner,"2027-03",6_000_000).id
    data = {"source_month":str(old),"mode":"all" if case < 49 else "recurring"}
    url = f"/budget/{new}/reuse"
    result = client.post(url,data=data)
    if case in (46,48,51):
        assert result.status_code == (400 if case==51 else 409)
        with app.app_context():
            assert not services.list_expenses(owner,new)
        return
    assert result.status_code == 302
    with app.app_context():
        rows = {e.expense_name:e for e in services.list_expenses(owner,new)}
        if case == 44:
            assert set(rows)=={"Rent","Electricity","Water","Food","Cinema"}
        elif case == 45:
            assert services.get_month(owner,new).available_vnd == 6_000_000 and not services.list_plans(owner,new)
        elif case == 49:
            assert set(rows)=={"Rent","Food"}
        elif case == 50:
            assert rows["Rent"].due_day==5 and rows["Food"].minimum_amount==1_200_000 and rows["Food"].is_recurring
        elif case == 52:
            assert rows["Food"].allocation_frequency=="DAILY" and rows["Rent"].allocation_frequency=="MONTHLY"
        elif case in (47,53):
            assert client.post(url,data=data).status_code==409
            assert len(services.list_expenses(owner,new))==len(rows)


@pytest.mark.parametrize("locale,expected", [("vi","Tiền trọ"),("en","Rent")],ids=["BP-59","BP-60"])
def test_schedule_handoff_language(app,client,months,locale,expected):
    owner, month, _ = months
    assert client.post(f"/budget/{month}/plans/generate",data=BASE_SETUP).status_code == 302
    with app.app_context():
        services.confirm_and_schedule(owner,month,services.list_plans(owner,month)[0].id)
    response = client.get(f"/expenses?budget_month_id={month}&view=day&date=2026-12-01&lang={locale}")
    assert response.status_code == 200
    assert f"<strong>{expected}</strong>" in response.text
    assert "<strong>Cinema</strong>" in response.text
