from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import BudgetMonth, User
from app.modules.accounts.services import register_user


def test_database_rejects_non_first_day_budget_month(app):
    with app.app_context():
        user = register_user("student@example.com", "correct-horse")
        db.session.add(
            BudgetMonth(
                user_id=user.id,
                month_start=date(2026, 10, 2),
                available_vnd=100,
            )
        )

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_database_rejects_non_normalized_email(app):
    with app.app_context():
        db.session.add(
            User(
                email="Student@Example.com",
                password_hash="not-a-real-hash",
            )
        )

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_deleting_user_cascades_to_owned_budget_months(app):
    with app.app_context():
        user = register_user("student@example.com", "correct-horse")
        db.session.add(
            BudgetMonth(
                user_id=user.id,
                month_start=date(2026, 10, 1),
                available_vnd=100,
            )
        )
        db.session.commit()

        db.session.delete(user)
        db.session.commit()

        assert db.session.scalar(db.select(db.func.count(BudgetMonth.id))) == 0


@pytest.mark.parametrize("tracking", [date(2026, 9, 30), date(2026, 11, 1), date(2025, 10, 15)])
def test_database_rejects_tracking_start_outside_month(app, tracking):
    with app.app_context():
        user = register_user("student@example.com", "correct-horse")
        db.session.add(BudgetMonth(
            user_id=user.id, month_start=date(2026, 10, 1),
            tracking_start_date=tracking, available_vnd=100,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
