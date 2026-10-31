import re
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAllocation, BudgetExpense, BudgetMonth,
    BudgetPlan, ExpenseCategory, User,
)
from app.modules.budgets import services
from app.modules.budgets.rules import BudgetError


@pytest.fixture
def budget(app):
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="test-only")
        other = User(email="other@example.com", password_hash="test-only")
        month = BudgetMonth(user=owner, month_start=date(2026, 10, 1), available_vnd=6_000_000)
        other_month = BudgetMonth(user=other, month_start=date(2026, 10, 1), available_vnd=6_000_000)
        category = ExpenseCategory(user=owner, category_name="Living")
        other_category = ExpenseCategory(user=other, category_name="Private category")
        builtin = ExpenseCategory(category_name="Built-in")
        db.session.add_all([owner, other, month, other_month, category, other_category, builtin])
        db.session.flush()
        items = []
        for name, priority, estimate, minimum, frequency in [
            ("Rent", "P0", 2_000_000, None, "MONTHLY"),
            ("Electricity", "P0", 200_000, None, "MONTHLY"),
            ("Water", "P0", 100_000, None, "MONTHLY"),
            ("Food", "P1", None, 1_000_000, "DAILY"),
            ("Entertainment", "P2", 0, None, "WEEKLY"),
        ]:
            expense = BudgetExpense(
                budget_month=month, category=category, expense_name=name, priority=priority,
                estimated_amount=estimate, minimum_amount=minimum, allocation_frequency=frequency,
            )
            db.session.add(expense)
            items.append(expense)
        db.session.commit()
        return dict(user=owner.id, other=other.id, month=month.id, other_month=other_month.id,
                    category=category.id, other_category=other_category.id, builtin=builtin.id,
                    expenses=[e.id for e in items])


@pytest.fixture
def signed_client(client, budget):
    with client.session_transaction() as session:
        session["user_id"] = str(budget["user"])
        session["active_budget_month_id"] = str(budget["month"])
    return client


def expense_data(budget, **overrides):
    return dict(expense_name="Study", category_id=str(budget["category"]), priority="P1",
                estimated_amount="", minimum_amount="", allocation_frequency="WEEKLY", **overrides)


def test_generate_save_and_load_in_new_session(app, budget):
    with app.app_context():
        plans = services.generate_budget_plans(budget["user"], budget["month"])
        ids = [plan.id for plan in plans]
        assert len(ids) == 3 and all(isinstance(value, UUID) for value in ids)
        assert db.session.scalar(db.select(db.func.count(BudgetAllocation.id))) == 15
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        db.session.remove()
        plan = services.get_plan(budget["user"], budget["month"], ids[0])
        assert plan.status == "GENERATED"
        assert len(plan.allocations) == 5
        assert sum(a.allocated_amount for a in plan.allocations) + plan.planned_savings == 6_000_000
        assert all(a.budget_expense.budget_month_id == plan.budget_month_id for a in plan.allocations)


def test_expense_crud_preserves_unknown_and_zero_and_invalidates_drafts(app, budget):
    with app.app_context():
        item = services.save_expense(budget["user"], budget["month"], expense_data(budget))
        item_id = item.id
        assert item.estimated_amount is None
        services.generate_budget_plans(budget["user"], budget["month"])
        data = expense_data(budget)
        data.update(estimated_amount="0", category_id="", category_name="Learning", is_recurring=True)
        item = services.save_expense(budget["user"], budget["month"], data, expense_id=item_id)
        assert item.estimated_amount == 0 and item.is_recurring
        assert item.category.user_id == budget["user"]
        assert item.category.category_name == "Learning"
        assert services.list_plans(budget["user"], budget["month"]) == []
        assert db.session.scalar(db.select(db.func.count(BudgetAllocation.id))) == 0
        services.delete_expense(budget["user"], budget["month"], item_id)
        assert db.session.get(BudgetExpense, item_id) is None


def test_builtin_category_is_allowed_and_private_category_is_not(app, budget):
    with app.app_context():
        data = expense_data(budget)
        data["category_id"] = str(budget["builtin"])
        assert services.save_expense(budget["user"], budget["month"], data).category_id == budget["builtin"]
        data["expense_name"] = "Another expense"
        data["category_id"] = str(budget["other_category"])
        with pytest.raises(services.BudgetNotFound):
            services.save_expense(budget["user"], budget["month"], data)


@pytest.mark.parametrize("changes", [
    {"estimated_amount": "-1"}, {"estimated_amount": 1.5}, {"minimum_amount": "0"},
    {"priority": "P2", "minimum_amount": "10"}, {"priority": "P3"},
    {"allocation_frequency": "YEARLY"}, {"due_day": "32"},
    {"due_day": "10"}, {"is_recurring": "yes"}, {"expense_name": "rEnT"},
])
def test_invalid_expense_leaves_existing_drafts_untouched(app, budget, changes):
    with app.app_context():
        ids = [p.id for p in services.generate_budget_plans(budget["user"], budget["month"])]
        data = expense_data(budget)
        data.update(changes)
        with pytest.raises(BudgetError):
            services.save_expense(budget["user"], budget["month"], data)
        assert {p.id for p in services.list_plans(budget["user"], budget["month"])} == set(ids)


def test_confirmation_is_idempotent_locks_setup_and_keeps_original_funds(app, budget):
    with app.app_context():
        first, second, _ = services.generate_budget_plans(budget["user"], budget["month"])
        first_id, second_id = first.id, second.id
        assert services.confirm_plan(budget["user"], budget["month"], first_id).status == "CONFIRMED"
        original = [(a.id, a.allocated_amount) for a in first.allocations]
        services.get_month(budget["user"], budget["month"]).available_vnd = 7_000_000
        db.session.commit()
        services.confirm_plan(budget["user"], budget["month"], first_id)
        assert [(a.id, a.allocated_amount) for a in first.allocations] == original
        assert sum(a.allocated_amount for a in first.allocations) + first.planned_savings == 6_000_000
        for operation in [
            lambda: services.confirm_plan(budget["user"], budget["month"], second_id),
            lambda: services.generate_budget_plans(budget["user"], budget["month"]),
            lambda: services.save_expense(budget["user"], budget["month"], expense_data(budget)),
            lambda: services.save_expense(budget["user"], budget["month"], expense_data(budget), expense_id=budget["expenses"][0]),
            lambda: services.delete_expense(budget["user"], budget["month"], budget["expenses"][0]),
        ]:
            with pytest.raises(services.BudgetConflict):
                operation()
        assert db.session.scalar(db.select(db.func.count(BudgetPlan.id)).where(BudgetPlan.status == "CONFIRMED")) == 1


@pytest.mark.parametrize("change", ["funds", "allocation", "missing", "foreign_expense", "minimum", "category"])
def test_confirmation_revalidates_saved_data(app, budget, change):
    with app.app_context():
        plan = services.generate_budget_plans(budget["user"], budget["month"])[0]
        plan_id = plan.id
        if change == "funds":
            plan.budget_month.available_vnd += 1
        elif change == "allocation":
            plan.allocations[0].allocated_amount += 1
        elif change == "missing":
            db.session.delete(plan.allocations[0])
        elif change == "foreign_expense":
            foreign = BudgetExpense(
                budget_month_id=budget["other_month"], category_id=budget["other_category"],
                expense_name="Private", priority="P0", estimated_amount=1, allocation_frequency="MONTHLY",
            )
            db.session.add(foreign)
            db.session.flush()
            plan.allocations[0].budget_expense_id = foreign.id
        elif change == "minimum":
            db.session.get(BudgetExpense, budget["expenses"][3]).minimum_amount = 5_000_000
        else:
            db.session.get(BudgetExpense, budget["expenses"][0]).category_id = budget["other_category"]
        db.session.commit()
        db.session.remove()
        with pytest.raises(BudgetError):
            services.confirm_plan(budget["user"], budget["month"], plan_id)
        # Inspect persistence directly: corrupt cross-owner references must also
        # be rejected by the normal authorized read service.
        assert db.session.get(BudgetPlan, plan_id).status == "GENERATED"


def test_drafts_with_tasks_cannot_be_replaced(app, budget):
    with app.app_context():
        plan = services.generate_budget_plans(budget["user"], budget["month"])[0]
        db.session.add(AssignedExpenseTask(allocation=plan.allocations[0], assigned_date=date(2026, 10, 1),
                                          period_end=date(2026, 10, 31), original_limit=1, current_limit=1))
        db.session.commit()
        with pytest.raises(services.BudgetConflict):
            services.generate_budget_plans(budget["user"], budget["month"])
        assert len(services.list_plans(budget["user"], budget["month"])) == 3


def test_http_budget_flow(signed_client, app, budget):
    root = f"/budget/{budget['month']}"
    assert b"Budget planning" in signed_client.get("/budget").data
    assert b"Unknown" in signed_client.get(root).data
    data = expense_data(budget)
    assert signed_client.post(root + "/expenses/new", data=data).status_code == 302
    with app.app_context():
        expense = db.session.scalar(db.select(BudgetExpense).where(BudgetExpense.expense_name == "Study"))
        expense_id = expense.id
    edit_page = signed_client.get(f"{root}/expenses/{expense_id}/edit")
    assert edit_page.status_code == 200
    data["estimated_amount"] = "0"
    assert signed_client.post(f"{root}/expenses/{expense_id}/edit", data=data).status_code == 302
    assert signed_client.post(f"{root}/expenses/{expense_id}/delete").status_code == 302
    assert signed_client.post(root + "/plans/generate").status_code == 302
    with app.app_context():
        plan_id = services.list_plans(budget["user"], budget["month"])[0].id
    url = f"{root}/plans/{plan_id}"
    assert b"GENERATED" in signed_client.get(url).data
    # Submitted identity/allocation fields are never used by confirmation.
    assert signed_client.post(url + "/confirm", data={"user_id": str(budget["other"]), "allocated_amount": "1"}).status_code == 302
    assert b"CONFIRMED" in signed_client.get(url).data
    assert signed_client.post(url + "/confirm").status_code == 302
    assert signed_client.post(root + "/expenses/new", data=data).status_code == 409


def test_cross_user_routes_never_authorize_posted_user_id(signed_client, app, budget):
    root = f"/budget/{budget['month']}"
    with app.app_context():
        plan_id = services.generate_budget_plans(budget["user"], budget["month"])[0].id
    with signed_client.session_transaction() as session:
        session["user_id"] = str(budget["other"])
        session.pop("active_budget_month_id", None)
    data = expense_data(budget)
    data["user_id"] = str(budget["user"])
    for method, path in [
        ("get", root), ("get", f"/budget?budget_month_id={budget['month']}"),
        ("get", f"{root}/plans/{plan_id}"), ("get", root + "/expenses/new"),
        ("get", f"{root}/expenses/{budget['expenses'][0]}/edit"),
        ("post", root + "/expenses/new"), ("post", root + "/plans/generate"),
        ("post", f"{root}/plans/{plan_id}/confirm"),
        ("post", f"{root}/expenses/{budget['expenses'][0]}/edit"),
        ("post", f"{root}/expenses/{budget['expenses'][0]}/delete"),
    ]:
        assert signed_client.open(path, method=method.upper(), data=data).status_code == 404


def test_foreign_expense_and_plan_under_owned_month_are_hidden(signed_client, app, budget):
    with app.app_context():
        foreign_plan = services.generate_budget_plans(budget["user"], budget["month"])[0].id
    with signed_client.session_transaction() as session:
        session["user_id"] = str(budget["other"])
    root = f"/budget/{budget['other_month']}"
    assert signed_client.get(f"{root}/plans/{foreign_plan}").status_code == 404
    assert signed_client.post(f"{root}/plans/{foreign_plan}/confirm").status_code == 404
    assert signed_client.post(f"{root}/expenses/{budget['expenses'][0]}/delete").status_code == 404


def test_csrf_required_and_valid_form_token_works(signed_client, app, budget):
    app.config["WTF_CSRF_ENABLED"] = True
    root = f"/budget/{budget['month']}"
    assert signed_client.post(root + "/plans/generate").status_code == 400
    assert signed_client.post(root + "/expenses/new", data=expense_data(budget)).status_code == 400
    markup = signed_client.get(root).get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', markup).group(1)
    assert signed_client.post(root + "/plans/generate", data={"csrf_token": token}).status_code == 302


def test_unauthenticated_and_malformed_identifiers(client, signed_client, budget):
    assert signed_client.get("/budget?budget_month_id=invalid").status_code == 404
    with signed_client.session_transaction() as session:
        session.clear()
    assert client.get("/budget").status_code == 302
    assert client.post(f"/budget/{budget['month']}/plans/generate").status_code == 302


def test_regeneration_replaces_only_drafts_and_rollback_keeps_them(app, budget):
    with app.app_context():
        old_ids = {p.id for p in services.generate_budget_plans(budget["user"], budget["month"])}
        new_ids = {p.id for p in services.generate_budget_plans(budget["user"], budget["month"])}
        assert old_ids.isdisjoint(new_ids)
        assert db.session.scalar(db.select(db.func.count(BudgetAllocation.id))) == 15
        services.get_month(budget["user"], budget["month"]).available_vnd = 0
        db.session.commit()
        with pytest.raises(BudgetError):
            services.generate_budget_plans(budget["user"], budget["month"])
        assert {p.id for p in services.list_plans(budget["user"], budget["month"])} == new_ids


def test_database_failure_rolls_back_replacement_and_all_allocations(app, budget):
    def reject_insert(mapper, connection, target):
        raise IntegrityError("simulated allocation insert failure", {}, RuntimeError("database rejected write"))

    with app.app_context():
        old_ids = {p.id for p in services.generate_budget_plans(budget["user"], budget["month"])}
        event.listen(BudgetAllocation, "before_insert", reject_insert)
        try:
            with pytest.raises(services.BudgetConflict):
                services.generate_budget_plans(budget["user"], budget["month"])
        finally:
            event.remove(BudgetAllocation, "before_insert", reject_insert)
        assert {p.id for p in services.list_plans(budget["user"], budget["month"])} == old_ids
        assert db.session.scalar(db.select(db.func.count(BudgetAllocation.id))) == 15


def test_budget_flow_on_migrated_database(tmp_path):
    from flask_migrate import upgrade

    from app import create_app

    migrated_app = create_app({
        "TESTING": True, "SECRET_KEY": "migration-test-only", "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "budget.sqlite").as_posix(),
    })
    with migrated_app.app_context():
        try:
            upgrade()
            user = User(email="migration@example.com", password_hash="test-only")
            month = BudgetMonth(user=user, month_start=date(2026, 10, 1), available_vnd=6_000_000)
            db.session.add_all([user, month])
            db.session.commit()
            user_id, month_id = user.id, month.id
            for name, amount in [("Rent", "2000000"), ("Electricity", "200000"), ("Water", "100000")]:
                services.save_expense(user_id, month_id, {
                    "expense_name": name, "category_name": "Bills", "priority": "P0",
                    "estimated_amount": amount, "allocation_frequency": "MONTHLY", "due_day": "15",
                })
            plan_id = services.generate_budget_plans(user_id, month_id)[0].id
            services.confirm_plan(user_id, month_id, plan_id)
            db.session.remove()
            assert services.get_plan(user_id, month_id, plan_id).status == "CONFIRMED"
            assert len(services.list_categories(user_id)) == 1
        finally:
            db.session.remove()
            db.engine.dispose()


def test_no_months_offers_month_creation(client, app):
    with app.app_context():
        user = User(email="empty@example.com", password_hash="test-only")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as session:
        session["user_id"] = str(user_id)
    response = client.get("/budget")
    assert response.status_code == 200
    assert b"Create a budget month before adding expenses" in response.data


def test_pretracking_dates_do_not_get_scheduled_by_budget(app, budget):
    with app.app_context():
        services.get_month(budget["user"], budget["month"]).tracking_start_date = date(2026, 10, 15)
        db.session.commit()
        plan = services.generate_budget_plans(budget["user"], budget["month"])[0]
        services.confirm_plan(budget["user"], budget["month"], plan.id)
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        assert services.get_month(budget["user"], budget["month"]).tracking_start_date == date(2026, 10, 15)


def test_corrupt_cross_owner_reference_does_not_expose_private_category(signed_client, app, budget):
    with app.app_context():
        plan_id = services.generate_budget_plans(budget["user"], budget["month"])[0].id
        db.session.get(BudgetExpense, budget["expenses"][0]).category_id = budget["other_category"]
        db.session.commit()
    root = f"/budget/{budget['month']}"
    for path in [root, f"{root}/plans/{plan_id}", f"{root}/expenses/{budget['expenses'][0]}/edit"]:
        response = signed_client.get(path)
        assert response.status_code == 400
        assert b"Private category" not in response.data
