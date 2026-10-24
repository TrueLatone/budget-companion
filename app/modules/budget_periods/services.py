from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import BudgetMonth


class DuplicateBudgetMonthError(ValueError):
    """Raised when a user already has the requested calendar month."""


def parse_month(value):
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def list_budget_months(user_id):
    statement = (
        db.select(BudgetMonth)
        .where(BudgetMonth.user_id == user_id)
        .order_by(BudgetMonth.month_start.desc())
    )
    return list(db.session.scalars(statement))


def get_budget_month(user_id, budget_month_id):
    return db.session.scalar(
        db.select(BudgetMonth).where(
            BudgetMonth.id == budget_month_id,
            BudgetMonth.user_id == user_id,
        )
    )


def create_budget_month(user_id, month, available_vnd):
    budget_month = BudgetMonth(
        user_id=user_id,
        month_start=parse_month(month),
        available_vnd=available_vnd,
    )
    db.session.add(budget_month)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise DuplicateBudgetMonthError from exc

    return budget_month


def update_available_vnd(budget_month, available_vnd):
    budget_month.available_vnd = available_vnd
    db.session.commit()
    return budget_month
