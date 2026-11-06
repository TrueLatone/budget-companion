import uuid

from sqlalchemy import Uuid

from app.extensions import db


class BudgetAdjustmentDetail(db.Model):
    """The before/after limit for one task in an applied adjustment."""

    __tablename__ = "budget_adjustment_details"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    adjustment_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_adjustments.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    task_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("assigned_expense_tasks.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    previous_limit = db.Column(db.BigInteger, nullable=False)
    new_limit = db.Column(db.BigInteger, nullable=False)

    adjustment = db.relationship("BudgetAdjustment", back_populates="details")
    task = db.relationship("AssignedExpenseTask", back_populates="adjustment_details")

    __table_args__ = (
        db.UniqueConstraint("adjustment_id", "task_id"),
        db.CheckConstraint("previous_limit >= 0", name="previous_limit_nonnegative"),
        db.CheckConstraint("new_limit >= 0", name="new_limit_nonnegative"),
    )
