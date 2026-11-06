"""Migration checks always target temporary SQLite or offline PostgreSQL SQL."""

from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
import uuid
import warnings

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
import pytest
import sqlalchemy as sa

from app import create_app
from app.extensions import db
from app.models import BudgetMonth


@pytest.fixture
def migration_app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "migration-test-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "migration.sqlite").as_posix(),
    })
    with application.app_context():
        try:
            yield application
        finally:
            db.session.remove()
            db.engine.dispose()


def table_rows(table):
    with db.engine.connect() as connection:
        return [dict(row) for row in connection.execute(sa.select(table).order_by(table.c.id)).mappings()]


def test_upgrade_preserves_existing_data_and_explicit_tracking_dates(migration_app):
    upgrade(revision="de12e989405f")
    old = sa.MetaData()
    old.reflect(bind=db.engine)
    users = old.tables["users"]
    months = old.tables["budget_months"]
    user_id = uuid.uuid4().hex
    month_ids = [uuid.uuid4().hex for _ in range(3)]
    audit_time = datetime(2026, 10, 20, 3, 4, 5, tzinfo=timezone.utc)
    with db.engine.begin() as connection:
        connection.execute(users.insert().values(
            id=user_id, email="legacy@example.com", password_hash="preserve-this-hash",
            is_active=False, created_at=audit_time, updated_at=audit_time,
        ))
        connection.execute(months.insert(), [
            dict(id=month_id, user_id=user_id, month_start=month_start,
                 available_vnd=5_000_000_000, created_at=audit_time, updated_at=audit_time)
            for month_id, month_start in zip(month_ids, [
                date(2025, 12, 1), date(2026, 10, 1), date(2027, 1, 1),
            ])
        ])
    users_before, months_before = table_rows(users), table_rows(months)

    upgrade(revision="19a01e000001")
    with db.engine.begin() as connection:
        connection.execute(sa.text(
            "UPDATE budget_months SET tracking_start_date = :start WHERE id = :id"
        ), {"start": date(2026, 10, 15), "id": month_ids[1]})
    upgrade()

    assert table_rows(users) == users_before
    assert table_rows(months) == months_before
    for period in db.session.scalars(db.select(BudgetMonth)):
        expected = date(2026, 10, 15) if period.id.hex == month_ids[1] else period.month_start
        assert period.tracking_start_date == expected
    assert set(sa.inspect(db.engine).get_table_names()) == set(db.metadata.tables) | {"alembic_version"}
    assert len(db.metadata.tables) == 13

    # Autogenerate does not compare SQLite expression indexes; behavioral tests
    # exercise their uniqueness and these assertions verify both were migrated.
    with db.engine.connect() as connection:
        indexes = set(connection.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )).scalars())
        assert {"uq_expense_categories_owned_name", "uq_expense_categories_builtin_name"} <= indexes
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*expression-based index.*")
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            assert compare_metadata(context, db.metadata) == []


def test_empty_new_tables_can_round_trip_without_replacing_foundation(migration_app):
    upgrade()
    table = db.metadata.tables["users"]
    user_id = uuid.uuid4()
    with db.engine.begin() as connection:
        connection.execute(table.insert().values(
            id=user_id, email="roundtrip@example.com", password_hash="keep",
        ))
        connection.execute(db.metadata.tables["budget_months"].insert().values(
            id=uuid.uuid4(), user_id=user_id, month_start=date(2026, 10, 1), available_vnd=123,
        ))
    users_before = table_rows(table)
    legacy_month_columns = [c for c in db.metadata.tables["budget_months"].columns
                            if c.name != "tracking_start_date"]
    with db.engine.connect() as connection:
        months_before = connection.execute(sa.select(*legacy_month_columns)).all()
    downgrade(revision="de12e989405f")
    assert set(sa.inspect(db.engine).get_table_names()) == {"users", "budget_months", "alembic_version"}
    assert "tracking_start_date" not in {c["name"] for c in sa.inspect(db.engine).get_columns("budget_months")}
    assert table_rows(table) == users_before
    with db.engine.connect() as connection:
        assert connection.execute(sa.select(*legacy_month_columns)).all() == months_before
    upgrade()
    assert table_rows(table) == users_before
    with db.engine.connect() as connection:
        assert connection.execute(sa.select(*legacy_month_columns)).all() == months_before


def test_postgresql_upgrade_sql_compiles_without_connecting():
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "offline-test-only",
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://unused:unused@127.0.0.1/unused",
    })
    output = StringIO()
    with application.app_context():
        try:
            # sql=True uses the dialect only; no database connection is opened.
            with redirect_stdout(output):
                upgrade(sql=True)
        finally:
            db.engine.dispose()
    sql = output.getvalue()
    assert "CREATE TABLE expense_records" in sql
    assert "proposed_changes JSONB" in sql
    assert "BOOLEAN DEFAULT true" in sql
    assert "BOOLEAN DEFAULT false" in sql
    assert "CREATE UNIQUE INDEX uq_budget_plans_confirmed_month" in sql
    assert "uq_expense_categories_builtin_name" in sql
    assert "EXTRACT(year FROM tracking_start_date)" in sql


def test_append_only_migration_graph_has_one_head():
    scripts = ScriptDirectory("migrations")
    assert scripts.get_heads() == ["19a01e000002"]
    assert scripts.get_revision("19a01e000001").down_revision == "de12e989405f"
    assert scripts.get_revision("de12e989405f").down_revision is None
