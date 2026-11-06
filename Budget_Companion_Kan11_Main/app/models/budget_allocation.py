import uuid

from sqlalchemy import Uuid

from app.extensions import db


class BudgetAllocation(db.Model):
    """The monthly amount a particular plan assigns to one planned expense."""

    __tablename__ = "budget_allocations"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_plans.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    budget_expense_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_expenses.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    allocated_amount = db.Column(db.BigInteger, nullable=False)

    plan = db.relationship("BudgetPlan", back_populates="allocations")
    budget_expense = db.relationship("BudgetExpense", back_populates="allocations")
    tasks = db.relationship(
        "AssignedExpenseTask", back_populates="allocation", passive_deletes="all",
    )

    __table_args__ = (
        db.UniqueConstraint("plan_id", "budget_expense_id"),
        db.CheckConstraint("allocated_amount > 0", name="allocated_amount_positive"),
    )
