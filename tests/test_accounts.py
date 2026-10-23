from werkzeug.security import check_password_hash

from app.extensions import db
from app.models import User


def register(client, email="student@example.com", password="correct-horse"):
    return client.post(
        "/register",
        data={
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )


def login(client, email="student@example.com", password="correct-horse", **query):
    return client.post("/login", query_string=query, data={"email": email, "password": password})


def test_registration_normalizes_email_and_hashes_password(client, app):
    response = register(client, email="  Student@Example.COM ")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert user.email == "student@example.com"
        assert user.password_hash != "correct-horse"
        assert check_password_hash(user.password_hash, "correct-horse")


def test_duplicate_email_is_rejected_case_insensitively(client):
    assert register(client).status_code == 302
    response = register(client, email="STUDENT@example.com")

    assert response.status_code == 200
    assert b"already exists" in response.data


def test_login_and_logout(client):
    register(client)

    response = login(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")
    assert client.get("/account").status_code == 200

    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get("/account").status_code == 302


def test_login_rejects_wrong_password(client):
    register(client)
    response = login(client, password="not-the-password")

    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_login_does_not_redirect_to_external_next_url(client):
    register(client)
    response = login(client, next="https://example.net/phishing")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")


def test_login_rejects_ambiguous_scheme_relative_next_url(client):
    register(client)
    response = login(client, next="///example.net/phishing")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")


def test_invalid_session_user_is_cleared(client):
    with client.session_transaction() as session:
        session["user_id"] = "not-a-uuid"

    assert client.get("/account").status_code == 302
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_csrf_rejects_unprotected_registration(app):
    app.config["WTF_CSRF_ENABLED"] = True
    csrf_client = app.test_client()

    response = csrf_client.post(
        "/register",
        data={
            "email": "student@example.com",
            "password": "correct-horse",
            "confirm_password": "correct-horse",
        },
    )

    assert response.status_code == 400
