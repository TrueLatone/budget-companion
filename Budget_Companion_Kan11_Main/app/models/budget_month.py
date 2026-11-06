import uuid

from sqlalchemy import Uuid

from app.extensions import db


def _default_tracking_start_date(context):
    """Keep existing callers' full-month behavior; never infer from creation time."""
    return context.get_current_parameters()["month_start"]


class BudgetMonth(db.Model):
    __tablename__ = "budget_months"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        Uuid(as_uuid=True),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    month_start = db.Column(db.Date, nullable=False)
    tracking_start_date = db.Column(
        db.Date, nullable=False, default=_default_tracking_start_date,
    )
    available_vnd = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    user = db.relationship("User", back_populates="budget_months")
    budget_expenses = db.relationship(
        "BudgetExpense", back_populates="budget_month", passive_deletes="all",
    )
    plans = db.relationship("BudgetPlan", back_populates="budget_month", passive_deletes="all")
    expense_records = db.relationship(
        "ExpenseRecord", back_populates="budget_month", passive_deletes="all",
    )
    recommendations = db.relationship(
        "Recommendation", back_populates="budget_month", passive_deletes="all",
    )
    review = db.relationship(
        "MonthlyReview", back_populates="budget_month", uselist=False, passive_deletes="all",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "month_start",
            name="uq_budget_months_user_id_month_start",
        ),
        db.CheckConstraint(available_vnd >= 0, name="available_vnd_nonnegative"),
        db.CheckConstraint(
            db.extract("day", month_start) == 1,
            name="month_starts_first_day",
        ),
        db.CheckConstraint(
            db.and_(
                db.extract("year", tracking_start_date) == db.extract("year", month_start),
                db.extract("month", tracking_start_date) == db.extract("month", month_start),
            ),
            name="tracking_within_month",
        ),
    )

    def __repr__(self):
        return f"<BudgetMonth {self.id} {self.month_start:%Y-%m}>"
