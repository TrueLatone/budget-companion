import uuid

from sqlalchemy import Uuid

from app.extensions import db


class MonthlyReview(db.Model):
    """Optional monthly feedback; financial report totals remain derived."""

    __tablename__ = "monthly_reviews"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_month_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_months.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    rating = db.Column(db.SmallInteger, nullable=True)
    comment = db.Column(db.Text, nullable=True)

    budget_month = db.relationship("BudgetMonth", back_populates="review")

    __table_args__ = (
        db.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_valid"),
    )
