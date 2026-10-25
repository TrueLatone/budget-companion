from datetime import date

from app.extensions import db
from app.modules.expenses import services


def test_expenses_page_renders(client):
    response = client.get("/expenses")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Expense Planning" in body
    assert "DỮ LIỆU DEMO" in body
    assert "Tạo / cập nhật lịch task" in body


def test_create_generate_checkin_and_history_flow(app, client):
    response = client.post(
        "/expenses/sources",
        data={
            "title": "Tiền điện",
            "planned_amount": "300000",
            "amount_source": "USER_ENTERED",
            "priority": "P0",
            "schedule_tag": "MONTHLY",
            "is_active": "1",
            "view": "month",
            "date": "2026-10-15",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Đã thêm khoản chi demo" in response.data.decode("utf-8")

    item = services.list_plan_items(services.DEMO_USER_ID, demo_only=True)[0]
    assert item.planned_amount == 300000

    response = client.post(
        "/expenses/plan/generate",
        data={
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "view": "month",
            "date": "2026-10-15",
        },
        follow_redirects=True,
    )
    assert "Đã tạo 1 task" in response.data.decode("utf-8")

    task = services.list_tasks(
        services.DEMO_USER_ID, date(2026, 10, 1), date(2026, 10, 31)
    )[0]
    assert task.assigned_date == date(2026, 10, 31)

    response = client.post(
        f"/expenses/tasks/{task.task_id}/checkin",
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
    assert task.task_status == services.STATUS_OVER_BUDGET

    response = client.post(
        f"/expenses/tasks/{task.task_id}/due-date",
        data={
            "payment_due_date": "2026-11-05",
            "view": "month",
            "date": "2026-10-15",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(task)
    assert task.payment_due_date == date(2026, 11, 5)

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
        "/expenses/sources",
        data={
            "title": "",
            "planned_amount": "0",
            "schedule_tag": "WEEKLY",
            "day_of_week": "1",
            "view": "month",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Tên khoản chi không được để trống" in response.data.decode("utf-8")
    assert services.list_plan_items(services.DEMO_USER_ID) == []


def test_clear_demo_only_removes_demo_rows(app, client):
    client.post(
        "/expenses/sources",
        data={
            "title": "Demo",
            "planned_amount": "10000",
            "amount_source": "USER_ENTERED",
            "priority": "P1",
            "schedule_tag": "DATE",
            "specific_date": "2026-10-21",
            "is_active": "1",
        },
    )
    services.create_plan_item(
        services.DEMO_USER_ID,
        {
            "title": "Chính thức",
            "planned_amount": "20000",
            "amount_source": "USER_ENTERED",
            "priority": "P1",
            "schedule_tag": "MONTHLY",
            "is_active": "1",
        },
        is_demo=False,
    )

    response = client.post("/expenses/demo/clear", follow_redirects=True)
    assert response.status_code == 200

    remaining = services.list_plan_items(services.DEMO_USER_ID)
    assert [item.title for item in remaining] == ["Chính thức"]


def test_unknown_task_returns_404(client):
    response = client.post(
        "/expenses/tasks/01012026-abcdefabcdef/checkin",
        data={"action": "no_expense"},
    )
    assert response.status_code == 404
