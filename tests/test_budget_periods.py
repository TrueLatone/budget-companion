from datetime import date

from app.extensions import db
from app.models import BudgetMonth
from app.modules.accounts.services import register_user


def sign_in(client, app, email="student@example.com"):
    with app.app_context():
        register_user(email, "correct-horse")
    return client.post("/login", data={"email": email, "password": "correct-horse"})


def test_budget_periods_require_login(client):
    response = client.get("/budget-periods")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_create_budget_month_accepts_zero_and_selects_it(client, app):
    sign_in(client, app)
    response = client.post(
        "/budget-periods/new",
        data={"month": "2026-10", "available_vnd": "0"},
    )

    assert response.status_code == 302
    with app.app_context():
        period = db.session.scalar(db.select(BudgetMonth))
        assert period.month_start == date(2026, 10, 1)
        assert period.available_vnd == 0
    with client.session_transaction() as session:
        assert session["active_budget_month_id"] == str(period.id)

    response = client.get("/budget-periods")
    assert response.status_code == 200
    assert b"October 2026" in response.data
    assert b"Selected" in response.data


def test_duplicate_budget_month_is_rejected(client, app):
    sign_in(client, app)
    data = {"month": "2026-10", "available_vnd": "1000000"}
    assert client.post("/budget-periods/new", data=data).status_code == 302

    response = client.post("/budget-periods/new", data=data)
    assert response.status_code == 200
    assert b"already have a budget period" in response.data


def test_same_calendar_month_is_allowed_for_different_users(client, app):
    sign_in(client, app, "first@example.com")
    assert client.post(
        "/budget-periods/new",
        data={"month": "2026-10", "available_vnd": "100"},
    ).status_code == 302
    client.post("/logout")

    sign_in(client, app, "second@example.com")
    assert client.post(
        "/budget-periods/new",
        data={"month": "2026-10", "available_vnd": "200"},
    ).status_code == 302

    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 2


def test_negative_available_funds_are_rejected(client, app):
    sign_in(client, app)
    response = client.post(
        "/budget-periods/new",
        data={"month": "2026-10", "available_vnd": "-1"},
    )

    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 0


def test_user_cannot_edit_or_select_another_users_period(client, app):
    with app.app_context():
        owner = register_user("owner@example.com", "correct-horse")
        intruder = register_user("intruder@example.com", "correct-horse")
        period = BudgetMonth(
            user_id=owner.id,
            month_start=date(2026, 10, 1),
            available_vnd=500,
        )
        db.session.add(period)
        db.session.commit()
        period_id = period.id
        intruder_email = intruder.email

    client.post(
        "/login",
        data={"email": intruder_email, "password": "correct-horse"},
    )
    assert client.post(
        f"/budget-periods/{period_id}/edit",
        data={"available_vnd": "999"},
    ).status_code == 404
    assert client.post(f"/budget-periods/{period_id}/select").status_code == 404

    with app.app_context():
        assert db.session.get(BudgetMonth, period_id).available_vnd == 500


def test_update_available_funds_does_not_replace_period(client, app):
    sign_in(client, app)
    client.post(
        "/budget-periods/new",
        data={"month": "2026-10", "available_vnd": "100"},
    )
    with app.app_context():
        period_id = db.session.scalar(db.select(BudgetMonth.id))

    response = client.post(
        f"/budget-periods/{period_id}/edit",
        data={"available_vnd": "250"},
    )
    assert response.status_code == 302

    with app.app_context():
        period = db.session.get(BudgetMonth, period_id)
        assert period.available_vnd == 250
        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 1


def test_budget_month_page_uses_vietnamese_copy_and_formatting(client, app):
    client.set_cookie("bc_language", "vi")
    sign_in(client, app)
    client.post(
        "/budget-periods/new",
        data={"month": "2026-10", "available_vnd": "1500000"},
    )

    response = client.get("/budget-periods")

    assert response.status_code == 200
    assert "Ngân sách tháng" in response.get_data(as_text=True)
    assert "Tháng 10 2026" in response.get_data(as_text=True)
    assert "1.500.000 VND" in response.get_data(as_text=True)
