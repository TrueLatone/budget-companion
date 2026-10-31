from datetime import date
import uuid

from app.extensions import db
from app.models import (
    AssignedExpenseTask,
    BudgetAllocation,
    BudgetExpense,
    BudgetMonth,
    BudgetPlan,
    ExpenseCategory,
    User,
)
from app.modules.expenses import services

USER = services.DEMO_USER_ID


def _seed_canonical_task(
    user_id: str,
    assigned_date: date,
    amount: int = 300000,
    title: str = "Tiền điện",
    schedule_tag: str = "MONTHLY",
    payment_due_date: date | None = None,
) -> AssignedExpenseTask:
    user_uuid = services.to_uuid(user_id)
    user = db.session.get(User, user_uuid)
    if not user:
        user = User(
            id=user_uuid,
            email=f"{user_id}@example.com",
            password_hash="fake-hash",
        )
        db.session.add(user)
        db.session.flush()

    month_start = date(assigned_date.year, assigned_date.month, 1)
    month = BudgetMonth.query.filter_by(
        user_id=user_uuid, month_start=month_start
    ).first()
    if not month:
        month = BudgetMonth(
            user_id=user_uuid,
            month_start=month_start,
            tracking_start_date=month_start,
            available_vnd=50000000,
        )
        db.session.add(month)
        db.session.flush()

    category = ExpenseCategory.query.filter_by(
        user_id=user_uuid, category_name="Hóa đơn"
    ).first()
    if not category:
        category = ExpenseCategory(user_id=user_uuid, category_name="Hóa đơn")
        db.session.add(category)
        db.session.flush()

    expense = BudgetExpense.query.filter_by(
        budget_month_id=month.id, expense_name=title
    ).first()
    if not expense:
        expense = BudgetExpense(
            budget_month=month,
            category=category,
            expense_name=title,
            priority="P0",
            allocation_frequency=schedule_tag,
            is_recurring=True,
        )
        db.session.add(expense)
        db.session.flush()

    plan = BudgetPlan.query.filter_by(
        budget_month_id=month.id, status="CONFIRMED"
    ).first()
    if not plan:
        plan = BudgetPlan(
            budget_month=month, plan_type="BALANCED", status="CONFIRMED"
        )
        db.session.add(plan)
        db.session.flush()

    allocation = BudgetAllocation.query.filter_by(
        plan_id=plan.id, budget_expense_id=expense.id
    ).first()
    if not allocation:
        allocation = BudgetAllocation(
            plan=plan, budget_expense=expense, allocated_amount=amount
        )
        db.session.add(allocation)
        db.session.flush()

    task = AssignedExpenseTask(
        allocation=allocation,
        assigned_date=assigned_date,
        period_end=assigned_date,
        original_limit=amount,
        current_limit=amount,
        task_status="PENDING",
        payment_due_date=payment_due_date,
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_expenses_page_renders(client):
    response = client.get("/expenses")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Expense Planning" in body
    assert "Lịch tháng" in body


def test_create_generate_checkin_and_history_flow(app, client):
    task = _seed_canonical_task(
        USER,
        date(2026, 10, 31),
        amount=300000,
        title="Tiền điện",
        schedule_tag="MONTHLY",
    )
    assert task.assigned_date == date(2026, 10, 31)

    response = client.post(
        f"/expenses/tasks/{task.id}/checkin",
        data={
            "action": "actual",
            "amount": "350000",
            "expense_date": "2026-10-31",
            "category": "Hóa đơn",
            "note": "Tăng giá",
            "view": "month",
            "date": "2026-10-15",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(task)
    assert services.get_task_status(task) == services.STATUS_OVER_BUDGET
    assert task.task_status == "RECORDED"

    response = client.post(
        "/expenses/records",
        data={
            "title": "Phát sinh",
            "amount": "50000",
            "expense_date": "2026-10-20",
            "category": "Khác",
            "note": "",
            "view": "month",
            "date": "2026-10-15",
        },
        follow_redirects=True,
    )
    assert "Đã thêm khoản chi bất ngờ" in response.data.decode("utf-8")

    history = client.get("/expenses/history?start=2026-10-01&end=2026-10-31")
    assert history.status_code == 200
    history_body = history.data.decode("utf-8")
    assert "Tiền điện" in history_body
    assert "Phát sinh" in history_body


def test_validation_error_is_shown_and_nothing_saved(app, client):
    response = client.post(
        "/expenses/records",
        data={
            "title": "",
            "amount": "0",
            "expense_date": "2026-10-20",
            "view": "month",
            "date": "2026-10-15",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Tên khoản chi không được để trống" in body or "Số tiền phải lớn hơn 0" in body
    records = services.list_records(USER, date(2026, 10, 1), date(2026, 10, 31))
    assert records == []


def test_clear_demo_only_removes_demo_rows(app, client):
    _seed_canonical_task(USER, date(2026, 10, 15), amount=10000)
    services.create_unexpected_record(
        USER,
        {
            "title": "Bản ghi demo",
            "amount": "10000",
            "expense_date": "2026-10-15",
            "category": "Khác",
        },
    )

    other_user = "00000000-0000-0000-0000-000000000002"
    _seed_canonical_task(other_user, date(2026, 10, 15), amount=20000)
    services.create_unexpected_record(
        other_user,
        {
            "title": "Bản ghi chính thức",
            "amount": "20000",
            "expense_date": "2026-10-15",
            "category": "Khác",
        },
    )

    response = client.post("/expenses/demo/clear", follow_redirects=True)
    assert response.status_code == 200

    remaining = services.list_records(USER, date(2026, 10, 1), date(2026, 10, 31))
    assert remaining == []
    other_remaining = services.list_records(other_user, date(2026, 10, 1), date(2026, 10, 31))
    assert len(other_remaining) == 1
    assert other_remaining[0].title == "Bản ghi chính thức"


def test_unknown_task_returns_404(client):
    fake_uuid = str(uuid.uuid4())
    response = client.post(
        f"/expenses/tasks/{fake_uuid}/checkin",
        data={"action": "no_expense"},
    )
    assert response.status_code == 404


def test_payment_status_route_updates_status(client, app):
    task = _seed_canonical_task(
        USER,
        date(2026, 10, 25),
        amount=500000,
        title="Hóa đơn mạng",
        payment_due_date=date(2026, 10, 28),
    )
    assert task.payment_status is None

    response = client.post(
        f"/expenses/tasks/{task.id}/payment-status",
        data={"payment_status": "PAID"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(task)
    assert task.payment_status == "PAID"

    # Toggle to UNPAID
    response = client.post(
        f"/expenses/tasks/{task.id}/payment-status",
        data={"payment_status": "UNPAID"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(task)
    assert task.payment_status == "UNPAID"
