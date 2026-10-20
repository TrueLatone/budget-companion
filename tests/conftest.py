import pytest
from app import create_app


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "unit-test-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
    })
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
