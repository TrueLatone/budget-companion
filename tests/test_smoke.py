def test_home_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Budget Companion" in response.data


def test_app_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "service": "budget-companion"}


def test_database_health(client):
    response = client.get("/api/health/database")
    assert response.status_code == 200
    assert response.json["database"] == "connected"


def test_module_placeholders(client):
    for path in ("/dashboard",):
        response = client.get(path)
        assert response.status_code == 200
        assert "placeholder" in response.get_data(as_text=True)


def test_recommendations_require_login(client):
    response = client.get("/recommendations")
    assert response.status_code == 302 and "/login" in response.location


def test_budget_requires_login(client):
    response = client.get("/budget")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_expenses_require_login(client):
    assert client.get("/expenses").status_code == 302


def test_account_requires_login(client):
    response = client.get("/account")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
