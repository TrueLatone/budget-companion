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
    for path in ("/account", "/budget", "/expenses", "/dashboard", "/recommendations"):
        response = client.get(path)
        assert response.status_code == 200
        assert "placeholder" in response.get_data(as_text=True)
