"""KAN-23 adapts KAN-8 scenarios to real Budget services and canonical UUIDs."""

from datetime import date, datetime
import re
from uuid import UUID, uuid4

import pytest
from flask import template_rendered
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AssignedExpenseTask, BudgetAllocation, BudgetMonth, BudgetPlan, ExpenseRecord, User
from app.modules.budget_periods.services import create_budget_month, update_available_vnd
from app.modules.budgets import services as budgets
from app.modules.expenses import presentation, services
from app.modules.expenses.validators import ValidationError


def make_budget(user_id, month="2026-10", tracking=None, *, tiny=False):
    """Every plan/expense/allocation comes through the canonical Budget flow."""
    period = create_budget_month(user_id, month, 4 if tiny else 100_003, tracking)
    specs = [
        ("Rent", "P0", 1 if tiny else 20_000, None, "MONTHLY", 1),
        ("Electricity", "P0", 1 if tiny else 4_000, None, "MONTHLY", 15),
        ("Water", "P0", 1 if tiny else 1_000, None, "MONTHLY", 31),
        ("Food", "P1", None, None if tiny else 20_000, "DAILY", None),
    ]
    if not tiny:
        specs += [("Transportation", "P1", None, 5000, "WEEKLY", None),
                  ("Entertainment", "P2", 0, None, "MONTHLY", None)]
    for name, priority, amount, minimum, frequency, due_day in specs:
        budgets.save_expense(user_id, period.id, {
            "expense_name": name, "priority": priority, "estimated_amount": amount,
            "minimum_amount": minimum, "allocation_frequency": frequency,
            "due_day": due_day, "category_name": "Living", "is_recurring": False,
        })
    plans = budgets.generate_budget_plans(user_id, period.id)
    return dict(user=user_id, month=period.id, plans=[plan.id for plan in plans])


@pytest.fixture
def setup(app, monkeypatch):
    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 10, 31))
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 10, 31, 16))
    with app.app_context():
        user = User(email="expenses@example.com", password_hash=generate_password_hash("correct-horse"))
        other = User(email="private@example.com", password_hash="test-only")
        db.session.add_all([user, other])
        db.session.commit()
        data = make_budget(user.id, tracking=date(2026, 10, 15))
        data["other"] = other.id
        return data


@pytest.fixture
def signed_client(client, setup):
    with client.session_transaction() as session:
        session["user_id"] = str(setup["user"])
        session["active_budget_month_id"] = str(setup["month"])
    return client


def schedule(setup):
    budgets.confirm_plan(setup["user"], setup["month"], setup["plans"][1])
    return services.ensure_tasks_for_month(setup["user"], setup["month"])


def food_task(tasks):
    return next(task for task in tasks if task.allocation.budget_expense.expense_name == "Food")


def actual(setup, task_id, amount="100", token=None, **kw):
    return services.checkin_task(setup["user"], task_id, action="actual", amount_raw=amount,
                                 idempotency_key=token or uuid4().hex, **kw)


def unexpected(setup, **overrides):
    form = dict(budget_month_id=str(setup["month"]), title="Repair", category="Repairs", priority="P1",
                amount="123", expense_date="2026-10-20", idempotency_key=uuid4().hex)
    form.update(overrides)
    return form


def test_drafts_never_schedule_and_reads_do_not_write(app, setup, signed_client):
    assert signed_client.get("/expenses").status_code == 200
    with app.app_context():
        with pytest.raises(ValidationError, match="Confirm"):
            services.ensure_tasks_for_month(setup["user"], setup["month"])
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        assert all(plan.status == "GENERATED" for plan in budgets.list_plans(setup["user"], setup["month"]))


def test_schedule_conserves_each_monthly_allocation_and_uses_canonical_dates(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        allocations = budgets.get_confirmed_allocations(setup["user"], setup["month"])
        for allocation in allocations:
            selected = [task for task in tasks if task.allocation_id == allocation.id]
            assert sum(task.original_limit for task in selected) == allocation.allocated_amount
            assert all(task.current_limit == task.original_limit and task.task_status == "PENDING" for task in selected)
            assert all(isinstance(task.id, UUID) and isinstance(task.allocation_id, UUID) for task in selected)
            assert all(date(2026, 10, 15) <= task.assigned_date <= task.period_end <= date(2026, 10, 31) for task in selected)
            assert all(type(task.original_limit) is int for task in selected)
        food = [task for task in tasks if task.allocation.budget_expense.expense_name == "Food"]
        weekly = [task for task in tasks if task.allocation.budget_expense.expense_name == "Transportation"]
        assert len(food) == 17
        assert [(task.assigned_date.day, task.period_end.day) for task in weekly] == [(15, 18), (19, 25), (26, 31)]
        assert max(task.original_limit for task in food) - min(task.original_limit for task in food) <= 1
        rent = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Rent")
        assert rent.payment_due_date == date(2026, 10, 1)  # Never shifted or assumed already paid.
        assert rent.payment_status == "UNPAID"
        assert sum(task.original_limit for task in tasks) + allocations[0].plan.planned_savings == 100_003


@pytest.mark.parametrize("month,tracking,last_day", [
    ("2028-02", date(2028, 2, 28), 29), ("2027-02", date(2027, 2, 28), 28),
    ("2026-12", date(2026, 12, 31), 31), ("2026-09", date(2026, 9, 1), 30),
])
def test_scheduling_handles_leap_year_single_day_and_partial_weeks(app, setup, month, tracking, last_day):
    with app.app_context():
        data = make_budget(setup["user"], month, tracking)
        tasks = schedule(data)
        for allocation in budgets.get_confirmed_allocations(data["user"], data["month"]):
            rows = [task for task in tasks if task.allocation_id == allocation.id]
            assert sum(task.original_limit for task in rows) == allocation.allocated_amount
            assert rows[0].assigned_date == tracking
            assert rows[-1].period_end.day == last_day
        water = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Water")
        assert water.payment_due_date.day == last_day


def test_schedule_retry_preserves_transactions_adjustments_and_original_snapshot(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        task = food_task(tasks)
        ids = {row.id for row in tasks}
        original = task.original_limit
        actual(setup, task.id)
        task.current_limit += 50
        db.session.commit()
        update_available_vnd(budgets.get_month(setup["user"], setup["month"]), 999_999)
        repeated = services.ensure_tasks_for_month(setup["user"], setup["month"])
        assert {row.id for row in repeated} == ids
        assert task.original_limit == original
        assert task.current_limit == original + 50 and task.task_status == "RECORDED"
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 1
        confirmed = budgets.get_plan(setup["user"], setup["month"], setup["plans"][1])
        assert sum(row.original_limit for row in repeated) + confirmed.planned_savings == 100_003


def test_scheduler_fills_missing_task_but_rejects_mismatched_history(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        removed_id = tasks[-1].id
        keep = {task.id for task in tasks[:-1]}
        db.session.delete(tasks[-1])
        db.session.commit()
        repaired = services.ensure_tasks_for_month(setup["user"], setup["month"])
        assert keep <= {task.id for task in repaired}
        assert removed_id not in {task.id for task in repaired}
        repaired[0].original_limit += 1
        db.session.commit()
        with pytest.raises(services.ExpenseConflict):
            services.ensure_tasks_for_month(setup["user"], setup["month"])
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == len(tasks)


def test_scheduler_failure_is_atomic(app, setup):
    def fail(mapper, connection, target):
        raise IntegrityError("simulated failure", {}, RuntimeError("rejected"))

    with app.app_context():
        budgets.confirm_plan(setup["user"], setup["month"], setup["plans"][1])
        event.listen(AssignedExpenseTask, "before_insert", fail)
        try:
            with pytest.raises(services.ExpenseConflict):
                services.ensure_tasks_for_month(setup["user"], setup["month"])
        finally:
            event.remove(AssignedExpenseTask, "before_insert", fail)
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
        assert budgets.get_plan(setup["user"], setup["month"], setup["plans"][1]).status == "CONFIRMED"


def test_actuals_are_multiple_transactions_with_payload_checked_retries(app, setup):
    with app.app_context():
        task = food_task(schedule(setup))
        token = uuid4().hex
        actual(setup, task.id, "100", token)
        actual(setup, task.id, "100", token)
        actual(setup, task.id, "200")
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 2
        spending = services.planned_records_for_tasks(setup["user"], [task.id])[str(task.id)]
        assert spending.amount == 300 and len(spending.records) == 2
        with pytest.raises(services.ExpenseConflict, match="different transaction"):
            actual(setup, task.id, "101", token)
        assert services.get_task(setup["user"], task.id).task_status == "RECORDED"


def test_no_expense_is_explicit_repeat_safe_and_cannot_hide_actuals(app, setup):
    with app.app_context():
        task = food_task(schedule(setup))
        for _ in range(2):
            services.checkin_task(setup["user"], task.id, action="no_expense")
        assert services.get_task(setup["user"], task.id).display_status == "NO_EXPENSE"
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0
        actual(setup, task.id)
        with pytest.raises(services.ExpenseConflict):
            services.checkin_task(setup["user"], task.id, action="no_expense")
        assert services.get_task(setup["user"], task.id).task_status == "RECORDED"


@pytest.mark.parametrize("amount", [None, "", "0", "-1", "1.5", True, "1,000", "9" * 5000])
def test_invalid_actual_amount_is_not_zero_and_never_saved(app, setup, amount):
    with app.app_context():
        task = food_task(schedule(setup))
        with pytest.raises(ValidationError):
            actual(setup, task.id, amount)
        assert services.get_task(setup["user"], task.id).task_status == "PENDING"
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_actual_record_edits_and_deletes_recalculate_from_all_purchases(app, setup):
    with app.app_context():
        task = food_task(schedule(setup))
        actual(setup, task.id, "100")
        actual(setup, task.id, "200")
        records = list(db.session.scalars(db.select(ExpenseRecord)))
        services.update_record(setup["user"], records[0].id, {
            "amount": "150", "expense_date": "2026-10-15", "category": "Living",
        })
        assert services.planned_records_for_tasks(setup["user"], [task.id])[str(task.id)].amount == 350
        services.delete_record(setup["user"], records[0].id)
        assert services.get_task(setup["user"], task.id).task_status == "RECORDED"
        services.delete_record(setup["user"], records[1].id)
        assert services.get_task(setup["user"], task.id).task_status == "PENDING"


@pytest.mark.parametrize("expense_date", ["2026-10-14", "2026-10-16", "2026-11-01", "2026-09-30"])
def test_daily_transactions_stay_in_the_task_period(app, setup, expense_date):
    with app.app_context():
        task = food_task(schedule(setup))
        with pytest.raises(ValidationError):
            actual(setup, task.id, expense_date_raw=expense_date)
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_zero_task_allowance_stays_unknown_until_explicit_checkin(app, setup):
    with app.app_context():
        data = make_budget(setup["user"], "2026-09", date(2026, 9, 1), tiny=True)
        tasks = schedule(data)
        task = next(task for task in tasks if task.original_limit == 0)
        assert task.task_status == "PENDING"
        with pytest.raises(ValidationError):
            services.checkin_task(data["user"], task.id, action="planned", idempotency_key=uuid4().hex)
        services.checkin_task(data["user"], task.id, action="no_expense")
        assert services.get_task(data["user"], task.id).task_status == "NO_EXPENSE"
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_unexpected_spending_is_month_scoped_and_retry_payload_is_checked(app, setup):
    with app.app_context():
        form = unexpected(setup)
        first = services.create_unexpected_record(setup["user"], form)
        assert services.create_unexpected_record(setup["user"], form).id == first.id
        with pytest.raises(services.ExpenseConflict):
            services.create_unexpected_record(setup["user"], dict(form, amount="999"))
        prior = create_budget_month(setup["user"], "2026-09", 1234)
        second = services.create_unexpected_record(setup["user"], dict(form, budget_month_id=str(prior.id), expense_date="2026-09-20"))
        assert second.id != first.id
        assert budgets.get_month(setup["user"], setup["month"]).available_vnd == 100_003
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 2


@pytest.mark.parametrize("changes", [
    {"priority": ""}, {"priority": "P3"}, {"category": ""}, {"idempotency_key": ""},
    {"amount": "0"}, {"expense_date": "2026-10-14"}, {"expense_date": "2026-11-01"},
    {"title": "a" * 121}, {"budget_impact_scope": "YEARLY"},
])
def test_invalid_unexpected_expense_never_creates_funds_or_months(app, setup, changes):
    with app.app_context():
        with pytest.raises(ValidationError):
            services.create_unexpected_record(setup["user"], unexpected(setup, **changes))
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0
        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 1


def test_cross_user_and_malformed_resource_access_is_rejected(app, setup):
    with app.app_context():
        task = food_task(schedule(setup))
        actual(setup, task.id)
        record_id = db.session.scalar(db.select(ExpenseRecord.id))
        operations = [
            lambda: services.ensure_tasks_for_month(setup["other"], setup["month"]),
            lambda: services.get_task(setup["other"], task.id),
            lambda: services.planned_records_for_tasks(setup["other"], [task.id]),
            lambda: services.checkin_task(setup["other"], task.id, action="no_expense"),
            lambda: services.get_record(setup["other"], record_id),
            lambda: services.delete_record(setup["other"], record_id),
            lambda: services.update_record(setup["other"], record_id, {}),
            lambda: services.create_unexpected_record(setup["other"], unexpected(setup)),
            lambda: services.get_task(setup["user"], "demo-user"),
        ]
        for operation in operations:
            with pytest.raises(services.NotFoundError):
                operation()
        assert services.list_tasks(setup["other"], date(2026, 10, 1), date(2026, 10, 31)) == []
        assert services.list_records(setup["other"], date(2026, 10, 1), date(2026, 10, 31)) == []


def test_summary_pending_is_unknown_and_funds_additions_are_not_spending(app, setup):
    with app.app_context():
        period = services.resolve_period("month", "2026-10-15")
        empty = services.build_summary(setup["user"], period)
        assert empty["plan_total"] is None and empty["difference"] is None
        tasks = schedule(setup)
        summary = services.build_summary(setup["user"], period)
        assert summary["actual_total"] == 0 and summary["difference"] is None
        actual(setup, food_task(tasks).id, "123")
        funds = ExpenseRecord(budget_month_id=setup["month"], amount=1000,
                              expense_date=date(2026, 10, 20), record_type="FUNDS_ADDED")
        db.session.add(funds)
        db.session.commit()
        summary = services.build_summary(setup["user"], period)
        assert summary["actual_total"] == 123 and summary["difference"] is None
        with pytest.raises(services.NotFoundError):
            services.delete_record(setup["user"], funds.id)


def csrf_token(response):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True)).group(1)


def test_complete_budget_to_expense_http_workflow_with_csrf(client, app, setup):
    app.config["WTF_CSRF_ENABLED"] = True
    token = csrf_token(client.get("/login"))
    assert client.post("/login", data={"email": "expenses@example.com", "password": "correct-horse", "csrf_token": token}).status_code == 302
    root = f"/budget/{setup['month']}/plans/{setup['plans'][1]}"
    token = csrf_token(client.get(root))
    assert client.post(root + "/confirm", data={"csrf_token": token}).status_code == 302
    assert client.post(f"/expenses/months/{setup['month']}/schedule", data={"csrf_token": token}).status_code == 302
    page = client.get("/expenses?view=day&date=2026-10-15")
    assert page.status_code == 200
    assert b"DEMO" not in page.data
    with app.app_context():
        tasks = list(db.session.scalars(services._task_statement(setup["user"])))
        task = food_task(tasks)
        task_id = task.id
        other_id = next(row.id for row in tasks if row.id != task_id and row.assigned_date <= date(2026, 10, 31))
    form = dict(action="actual", amount="123", expense_date="2026-10-15", csrf_token=token, idempotency_key=uuid4().hex)
    url = f"/expenses/tasks/{task_id}/checkin"
    assert client.post(url, data=form).status_code == 302
    assert client.post(url, data=form).status_code == 302
    assert client.post(f"/expenses/tasks/{other_id}/checkin", data={"action": "no_expense", "csrf_token": token}).status_code == 302
    assert client.post("/expenses/records", data=dict(unexpected(setup), csrf_token=token)).status_code == 302
    for path in ["/expenses?view=day&date=2026-10-15", "/expenses?view=month&month=2026-10", "/expenses?view=year&year=2026", "/expenses/history?start=2026-10-01&end=2026-10-31"]:
        assert client.get(path).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 2
        assert budgets.get_plan(setup["user"], setup["month"], setup["plans"][1]).status == "CONFIRMED"


@pytest.mark.parametrize("action", ["schedule", "checkin", "payment", "unexpected", "edit", "delete"])
def test_expense_mutations_require_csrf(signed_client, app, setup, action):
    with app.app_context():
        task = food_task(schedule(setup))
        actual(setup, task.id)
        task_id = task.id
        record_id = db.session.scalar(db.select(ExpenseRecord.id))
    app.config["WTF_CSRF_ENABLED"] = True
    urls = dict(schedule=f"/expenses/months/{setup['month']}/schedule", checkin=f"/expenses/tasks/{task_id}/checkin",
                payment=f"/expenses/tasks/{task_id}/payment-status", unexpected="/expenses/records",
                edit=f"/expenses/records/{record_id}/edit", delete=f"/expenses/records/{record_id}/delete")
    response = signed_client.post(urls[action], data=unexpected(setup))
    assert response.status_code == 400 and b"CSRF token is missing" in response.data


def test_no_anonymous_demo_identity_or_cleanup(client, app, setup):
    assert client.get("/expenses").status_code == 302
    assert client.get("/expenses/history").status_code == 302
    assert client.post(f"/expenses/months/{setup['month']}/schedule").status_code == 302
    assert client.post("/expenses/records", data=unexpected(setup)).status_code == 302
    assert client.post("/expenses/demo/clear").status_code == 404
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 2
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 0


def test_integrated_workflow_on_migrated_schema(tmp_path, monkeypatch):
    from flask_migrate import upgrade
    from app import create_app

    monkeypatch.setattr(services, "today_vn", lambda: date(2026, 10, 31))
    app = create_app({"TESTING": True, "SECRET_KEY": "migration-only", "SQLALCHEMY_DATABASE_URI":
                      "sqlite:///" + (tmp_path / "expenses.sqlite").as_posix()})
    with app.app_context():
        try:
            upgrade()
            user = User(email="migrated@example.com", password_hash="test-only")
            db.session.add(user)
            db.session.commit()
            data = make_budget(user.id, tracking=date(2026, 10, 15))
            task = food_task(schedule(data))
            task_id = task.id
            actual(data, task_id, "123")
            db.session.remove()
            assert services.get_task(data["user"], task_id).task_status == "RECORDED"
            assert len(services.ensure_tasks_for_month(data["user"], data["month"])) > 0
        finally:
            db.session.remove()
            db.engine.dispose()


def test_complete_summary_requires_every_scheduled_period_and_matching_dates(app, setup):
    with app.app_context():
        tasks = schedule(setup)
        rent = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Rent")
        actual(setup, rent.id, "100", expense_date_raw="2026-10-31")
        for task in tasks:
            if task.id != rent.id:
                services.checkin_task(setup["user"], task.id, action="no_expense")
        monthly = services.build_summary(setup["user"], services.resolve_period("month", "2026-10-15"))
        assert monthly["data_complete"] and monthly["difference"] == monthly["plan_total"] - 100
        daily = services.build_summary(setup["user"], services.resolve_period("day", "2026-10-15"))
        assert daily["difference"] is None  # Rent was recorded on a different date.
        db.session.delete(food_task(tasks))
        db.session.commit()
        missing = services.build_summary(setup["user"], services.resolve_period("month", "2026-10-15"))
        assert missing["difference"] is None  # Missing task rows are not zero spending.


def test_draft_tasks_are_never_listed_or_checkable(app, setup):
    with app.app_context():
        schedule(setup)
        draft = budgets.get_plan(setup["user"], setup["month"], setup["plans"][0])
        task = AssignedExpenseTask(allocation_id=draft.allocations[0].id,
                                   assigned_date=date(2026, 10, 15), period_end=date(2026, 10, 31),
                                   original_limit=1, current_limit=1, payment_due_date=date(2026, 10, 15))
        db.session.add(task)
        db.session.commit()
        assert task.id not in {row.id for row in services.list_tasks(setup["user"], date(2026, 10, 1), date(2026, 10, 31))}
        assert task.id not in {row.id for row in services.list_due_tasks(setup["user"], date(2026, 10, 1), date(2026, 10, 31))}
        with pytest.raises(services.NotFoundError):
            services.checkin_task(setup["user"], task.id, action="no_expense")


def test_future_tasks_cannot_be_converted_to_no_expense(app, setup):
    with app.app_context():
        future = make_budget(setup["user"], "2026-11", date(2026, 11, 1))
        task = food_task(schedule(future))
        with pytest.raises(ValidationError, match="Future tasks"):
            services.checkin_task(setup["user"], task.id, action="no_expense")
        assert services.get_task(setup["user"], task.id).task_status == "PENDING"


def test_retry_tokens_cannot_be_omitted_or_reused_for_a_different_record_type(app, setup):
    with app.app_context():
        task = food_task(schedule(setup))
        with pytest.raises(ValidationError, match="retry token"):
            services.checkin_task(setup["user"], task.id, action="actual", amount_raw="123")
        token = uuid4().hex
        actual(setup, task.id, "123", token)
        with pytest.raises(services.ExpenseConflict):
            services.create_unexpected_record(setup["user"], unexpected(setup, idempotency_key=token))
        assert db.session.scalar(db.select(db.func.count(ExpenseRecord.id))) == 1


def test_task_record_adapter_does_not_expose_a_foreign_category(app, setup):
    from app.models import ExpenseCategory

    with app.app_context():
        task = food_task(schedule(setup))
        actual(setup, task.id)
        private = ExpenseCategory(user_id=setup["other"], category_name="Private")
        db.session.add(private)
        db.session.flush()
        db.session.scalar(db.select(ExpenseRecord)).category_id = private.id
        db.session.commit()
        task_id = task.id
        db.session.remove()
        with pytest.raises(services.NotFoundError):
            services.planned_records_for_tasks(setup["user"], [task_id])


def test_integer_bigint_schedule_survives_database_round_trip(app, setup):
    from app.modules.budgets.rules import MAX_VND

    with app.app_context():
        update_available_vnd(budgets.get_month(setup["user"], setup["month"]), MAX_VND)
        setup["plans"] = [plan.id for plan in budgets.generate_budget_plans(setup["user"], setup["month"])]
        tasks = schedule(setup)
        count = len(tasks)
        db.session.remove()
        tasks = services.ensure_tasks_for_month(setup["user"], setup["month"])
        plan = budgets.get_plan(setup["user"], setup["month"], setup["plans"][1])
        assert len(tasks) == count
        assert sum(task.original_limit for task in tasks) + plan.planned_savings == MAX_VND
        assert all(type(task.original_limit) is int for task in tasks)
        actual(setup, food_task(tasks).id, str(MAX_VND))
        record = db.session.scalar(db.select(ExpenseRecord))
        assert record.amount == MAX_VND and type(record.amount) is int


def test_http_cross_user_posts_do_not_trust_submitted_identity(signed_client, app, setup):
    with app.app_context():
        task = food_task(schedule(setup))
        actual(setup, task.id)
        task_id = task.id
        record_id = db.session.scalar(db.select(ExpenseRecord.id))
    with signed_client.session_transaction() as session:
        session["user_id"] = str(setup["other"])
        session.pop("active_budget_month_id", None)
    for url in [f"/expenses/months/{setup['month']}/schedule", f"/expenses/tasks/{task_id}/checkin",
                f"/expenses/tasks/{task_id}/payment-status", f"/expenses/records/{record_id}/edit",
                f"/expenses/records/{record_id}/delete", "/expenses/records"]:
        response = signed_client.post(url, data=dict(unexpected(setup), user_id=str(setup["user"]), action="no_expense"))
        assert response.status_code == 404
    assert signed_client.get(f"/expenses?budget_month_id={setup['month']}").status_code == 404


def calendar_page(app, client, path):
    """Exercise the rendered Flask route and inspect its actual view model."""
    rendered = {}

    def capture(sender, template, context: dict, **extra):
        if template.name == "pages/expenses.html":
            rendered.update(context)

    with template_rendered.connected_to(capture, app):
        response = client.get(path)
    assert response.status_code == 200
    return response, rendered


def financial_snapshot():
    return {
        model.__tablename__: list(db.session.execute(db.select(*model.__table__.columns).order_by(model.id)))
        for model in (BudgetMonth, BudgetPlan, BudgetAllocation, AssignedExpenseTask, ExpenseRecord)
    }


def calendar_days(context):
    return {cell.day: cell for week in context["calendar"] for cell in week if cell}


def test_calendar_diagnosis_before_and_after_explicit_scheduling(app, setup, signed_client):
    with app.app_context():
        budgets.confirm_plan(setup["user"], setup["month"], setup["plans"][1])
        assert len(budgets.get_confirmed_allocations(setup["user"], setup["month"])) == 6
        before = financial_snapshot()
    response, context = calendar_page(app, signed_client, f"/expenses?budget_month_id={setup['month']}&view=month")
    assert context["schedule_state"].code == "NOT_SCHEDULED"
    assert b"schedule has not been created" in response.data
    assert b"Create spending schedule" in response.data
    assert not context["month_items"] and all(cell.task_count == 0 for cell in calendar_days(context).values())
    with app.app_context():
        assert financial_snapshot() == before
    assert signed_client.post(f"/expenses/months/{setup['month']}/schedule").status_code == 302
    response, context = calendar_page(app, signed_client, f"/expenses?budget_month_id={setup['month']}&view=month")
    assert context["schedule_state"].code == "READY"
    cells = calendar_days(context)
    assert all("Food" in cells[date(2026, 10, day)].daily_names for day in range(15, 32))
    assert all(not cells[date(2026, 10, day)].daily_names for day in range(1, 15))
    assert len([entry for entry in context["month_items"] if entry.task.title == "Food"]) == 17
    with app.app_context():
        allocations = budgets.get_confirmed_allocations(setup["user"], setup["month"])
        tasks = services.list_tasks(setup["user"], date(2026, 10, 1), date(2026, 10, 31))
        assert sum(cell.task_count for cell in cells.values()) == len(tasks)
        assert sum(cell.plan_total for cell in cells.values()) == sum(a.allocated_amount for a in allocations)
        for allocation in allocations:
            assert sum(task.original_limit for task in tasks if task.raw_task.allocation_id == allocation.id) == allocation.allocated_amount
        assert all(isinstance(task.id, UUID) and type(task.current_limit) is int for task in tasks)


def test_confirmation_guides_to_owned_month_and_safe_csrf_post(app, setup, client):
    app.config["WTF_CSRF_ENABLED"] = True
    token = csrf_token(client.get("/login"))
    assert client.post("/login", data={"email": "expenses@example.com", "password": "correct-horse", "csrf_token": token}).status_code == 302
    root = f"/budget/{setup['month']}/plans/{setup['plans'][1]}"
    token = csrf_token(client.get(root))
    response = client.post(root + "/confirm", data={"csrf_token": token})
    assert "/expenses?" in response.location and str(setup["month"]) in response.location
    page, context = calendar_page(app, client, response.location)
    assert context["selected_month"].id == setup["month"]
    assert context["schedule_state"].code == "NOT_SCHEDULED"
    assert str(setup["month"]).encode() in page.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(AssignedExpenseTask.id))) == 0
    schedule_url = f"/expenses/months/{setup['month']}/schedule"
    assert client.post(schedule_url).status_code == 400
    response = client.post(schedule_url, data={"csrf_token": csrf_token(page)}, follow_redirects=True)
    assert response.status_code == 200 and b'data-schedule-state="READY"' in response.data


@pytest.mark.parametrize("stage, expected, message", [
    ("empty", "NO_EXPENSES", b"No budget expenses or plan exist"),
    ("setup", "NO_PLAN", b"No budget plan exists"),
    ("draft", "UNCONFIRMED", b"No confirmed plan exists"),
    ("confirmed", "NOT_SCHEDULED", b"schedule has not been created"),
])
def test_calendar_empty_states_are_actionable_and_read_only(app, setup, signed_client, stage, expected, message):
    with app.app_context():
        empty = create_budget_month(setup["user"], "2026-09", 100_003)
        if stage == "empty":
            month_id = empty.id
        else:
            month_id = setup["month"]
            if stage == "setup":
                data = dict(expense_name="Study", category_name="Learning", priority="P1", allocation_frequency="DAILY")
                budgets.save_expense(setup["user"], month_id, data)  # Invalidates drafts.
            if stage == "confirmed":
                budgets.confirm_plan(setup["user"], month_id, setup["plans"][0])
        before = financial_snapshot()
    page, context = calendar_page(app, signed_client, f"/expenses?budget_month_id={month_id}&view=month")
    assert context["schedule_state"].code == expected
    assert message in page.data
    assert f"/budget/{month_id}".encode() in page.data
    assert bool(context["can_schedule"]) == (stage == "confirmed")
    with app.app_context():
        assert financial_snapshot() == before


def test_calendar_without_owned_month_explains_and_links_setup(app, setup, signed_client):
    page, context = calendar_page(app, signed_client, "/expenses?view=month&date=2025-01-15")
    assert context["selected_month"] is None
    assert b"no Budget Month exists" in page.data and b"/budget-periods/new" in page.data


@pytest.mark.parametrize("stale_query", ["date=2026-11-01", "month=2026-11", "year=2027"])
def test_explicit_calendar_month_wins_over_stale_navigation_fields(app, setup, signed_client, stale_query):
    with app.app_context():
        schedule(setup)
        november = make_budget(setup["user"], "2026-11")
    with signed_client.session_transaction() as session:
        session["active_budget_month_id"] = str(november["month"])
    _, context = calendar_page(app, signed_client, f"/expenses?budget_month_id={setup['month']}&view=month&{stale_query}")
    assert context["selected_month"].id == setup["month"]
    assert context["period"].start == date(2026, 10, 1)
    assert context["schedule_state"].code == "READY"
    # Date-only calendar navigation must still move away from the session month.
    _, context = calendar_page(app, signed_client, "/expenses?view=month&date=2026-10-16")
    assert context["selected_month"].id == setup["month"]


def test_continuing_periods_and_due_dates_do_not_repeat_financial_totals(app, setup, signed_client):
    with app.app_context():
        tasks = schedule(setup)
        weekly = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Transportation")
        rent = next(task for task in tasks if task.allocation.budget_expense.expense_name == "Rent")
        assert (weekly.assigned_date, weekly.period_end) == (date(2026, 10, 15), date(2026, 10, 18))
        before = financial_snapshot()
    page, context = calendar_page(app, signed_client, "/expenses?view=day&date=2026-10-16")
    items = {entry.task.title: entry for entry in context["day_items"]}
    assert {"Food", "Transportation", "Rent", "Electricity", "Water", "Entertainment"} == set(items)
    assert items["Food"].assigned_in_period
    assert not items["Transportation"].assigned_in_period and not items["Transportation"].due_in_period
    assert context["day_totals"].continuing_count == 5
    assert context["summary"]["plan_total"] == items["Food"].task.current_limit
    assert b"Continuing period; excluded" in page.data
    assert b"2026-10-16" in page.data  # Continuing task check-in uses the selected date.
    cells = calendar_days(context)
    assert cells[date(2026, 10, 1)].due_count == 1  # Rent due before tracking remains visible.
    assert cells[date(2026, 10, 1)].plan_total == 0
    assert cells[date(2026, 10, 15)].period_starts
    assert cells[date(2026, 10, 16)].continuing_count == 5
    assert cells[date(2026, 10, 16)].plan_total == items["Food"].task.current_limit
    with app.app_context():
        assert financial_snapshot() == before


def test_calendar_distinguishes_actual_pending_no_expense_and_unrecorded(app, setup, signed_client, monkeypatch):
    with app.app_context():
        tasks = schedule(setup)
        foods = sorted([task for task in tasks if task.allocation.budget_expense.expense_name == "Food"], key=lambda task: task.assigned_date)
        actual(setup, foods[0].id, "123")
        services.checkin_task(setup["user"], foods[1].id, action="no_expense")
        funds = ExpenseRecord(budget_month_id=setup["month"], amount=999999,
                              expense_date=date(2026, 10, 15), record_type="FUNDS_ADDED")
        db.session.add(funds)
        db.session.commit()
        before = financial_snapshot()
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 10, 17, 16))
    page, context = calendar_page(app, signed_client, "/expenses?view=month&date=2026-10-16")
    cells = calendar_days(context)
    assert cells[date(2026, 10, 15)].actual_total == 123
    assert cells[date(2026, 10, 15)].record_count == 1
    assert cells[date(2026, 10, 16)].no_expense_count == 1
    assert cells[date(2026, 10, 17)].pending_count > 0
    assert cells[date(2026, 10, 18)].record_count == 0
    assert context["summary"]["difference"] is None
    assert b"NO_EXPENSE" in page.data and b"PENDING" in page.data and b"UNRECORDED" not in page.data  # No unresolved task has yet ended.
    monkeypatch.setattr(presentation, "now_utc", lambda: datetime(2026, 10, 20, 16))
    page, context = calendar_page(app, signed_client, "/expenses?view=month&date=2026-10-16")
    # Both this Food day and its covering weekly Transportation period ended.
    assert calendar_days(context)[date(2026, 10, 17)].unrecorded_count == 2
    assert b"UNRECORDED" in page.data
    with app.app_context():
        assert financial_snapshot() == before


def test_calendar_scheduling_retry_preserves_ids_actuals_and_adjusted_limits(app, setup, signed_client):
    with app.app_context():
        tasks = schedule(setup)
        food = food_task(tasks)
        actual(setup, food.id, "7")
        untouched = next(task for task in tasks if task.id != food.id)
        services.checkin_task(setup["user"], untouched.id, action="no_expense")
        food.current_limit += 9
        db.session.commit()
        before = financial_snapshot()
    for _ in range(2):
        response = signed_client.post(f"/expenses/months/{setup['month']}/schedule", follow_redirects=True)
        assert response.status_code == 200
        assert b'data-schedule-state="READY"' in response.data
    with app.app_context():
        assert financial_snapshot() == before


def test_calendar_partial_schedule_is_explicit_and_repaired_without_overwriting(app, setup, signed_client):
    with app.app_context():
        tasks = schedule(setup)
        deleted = food_task(tasks)
        deleted_date = deleted.assigned_date
        db.session.delete(deleted)
        db.session.commit()
        existing_ids = {task.id for task in tasks if task.id != deleted.id}
    page, context = calendar_page(app, signed_client, "/expenses?view=month&date=2026-10-16")
    assert context["schedule_state"].code == "INCOMPLETE" and b"tasks are missing" in page.data
    assert "Food" not in calendar_days(context)[deleted_date].daily_names
    assert signed_client.post(f"/expenses/months/{setup['month']}/schedule").status_code == 302
    with app.app_context():
        assert services.get_schedule_state(setup["user"], setup["month"]).code == "READY"
        assert existing_ids.issubset({task.id for task in services.list_tasks(setup["user"], date(2026, 10, 1), date(2026, 10, 31))})


def test_conflicting_calendar_schedule_is_explained_and_not_overwritten(app, setup, signed_client):
    with app.app_context():
        task = food_task(schedule(setup))
        task.original_limit += 1
        db.session.commit()
        before = financial_snapshot()
    page, context = calendar_page(app, signed_client, "/expenses?view=month&date=2026-10-16")
    assert context["schedule_state"].code == "CONFLICT" and not context["can_schedule"]
    assert b"cannot be overwritten" in page.data
    assert signed_client.post(f"/expenses/months/{setup['month']}/schedule").status_code == 409
    with app.app_context():
        assert financial_snapshot() == before


def test_calendar_readiness_and_display_never_include_other_users_data(app, setup, signed_client):
    with app.app_context():
        foreign = make_budget(setup["other"])
        schedule(foreign)
        with pytest.raises(services.NotFoundError):
            services.get_schedule_state(setup["user"], foreign["month"])
        before = financial_snapshot()
    assert signed_client.get(f"/expenses?budget_month_id={foreign['month']}").status_code == 404
    assert signed_client.post(f"/expenses/months/{foreign['month']}/schedule", data={"user_id": str(setup["other"])}).status_code == 404
    page, context = calendar_page(app, signed_client, "/expenses?view=month&date=2026-10-16")
    assert context["schedule_state"].code == "UNCONFIRMED"
    assert sum(cell.task_count for cell in calendar_days(context).values()) == 0
    assert context["month_items"] == []
    with app.app_context():
        assert financial_snapshot() == before


def test_confirmed_plan_without_allocations_explains_corrupt_handoff(app, setup, signed_client):
    with app.app_context():
        empty = create_budget_month(setup["user"], "2026-09", 1000)
        # An incomplete legacy/imported row; normal Budget confirmation never
        # produces this. Diagnostics must explain it rather than invent tasks.
        db.session.add(BudgetPlan(budget_month_id=empty.id, plan_type="MANUAL", status="CONFIRMED", planned_savings=1000))
        db.session.commit()
        month_id = empty.id
        before = financial_snapshot()
    page, context = calendar_page(app, signed_client, f"/expenses?budget_month_id={month_id}&view=month")
    assert context["schedule_state"].code == "NO_ALLOCATIONS"
    assert not context["can_schedule"] and b"has no allocations" in page.data
    assert signed_client.post(f"/expenses/months/{month_id}/schedule").status_code == 400
    with app.app_context():
        assert financial_snapshot() == before


def test_ownership_date_filter_cannot_disguise_a_conflicting_saved_schedule(app, setup, signed_client):
    with app.app_context():
        food = food_task(schedule(setup))
        food.assigned_date = date(2026, 10, 14)  # Before tracking; ordinary reads exclude it.
        db.session.commit()
        before = financial_snapshot()
    page, context = calendar_page(app, signed_client, f"/expenses?budget_month_id={setup['month']}&view=month")
    assert context["schedule_state"].code == "CONFLICT" and b"cannot be overwritten" in page.data
    assert signed_client.post(f"/expenses/months/{setup['month']}/schedule").status_code == 409
    with app.app_context():
        assert financial_snapshot() == before


def test_schedule_post_failure_preserves_confirmation_and_allows_retry(app, setup, signed_client):
    def fail_insert(mapper, connection, target):
        raise IntegrityError("simulated schedule insert failure", {}, RuntimeError("failure"))

    url = f"/expenses/months/{setup['month']}/schedule"
    assert signed_client.post(f"/budget/{setup['month']}/plans/{setup['plans'][1]}/confirm").status_code == 302
    with app.app_context():
        before = financial_snapshot()
        event.listen(AssignedExpenseTask, "before_insert", fail_insert)
    try:
        assert signed_client.post(url).status_code == 409
    finally:
        event.remove(AssignedExpenseTask, "before_insert", fail_insert)
    with app.app_context():
        assert financial_snapshot() == before
        assert services.get_schedule_state(setup["user"], setup["month"]).code == "NOT_SCHEDULED"
    assert signed_client.post(url, follow_redirects=True).status_code == 200
    with app.app_context():
        assert services.get_schedule_state(setup["user"], setup["month"]).code == "READY"
