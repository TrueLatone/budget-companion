import uuid

from sqlalchemy import Uuid

from app.extensions import db


class BudgetExpense(db.Model):
    """An expense to fund when generating a month's alternative plans."""

    __tablename__ = "budget_expenses"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_month_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_months.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    category_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    expense_name = db.Column(db.String(120), nullable=False)
    priority = db.Column(db.String(2), nullable=False)
    estimated_amount = db.Column(db.BigInteger, nullable=True)
    minimum_amount = db.Column(db.BigInteger, nullable=True)
    allocation_frequency = db.Column(db.String(10), nullable=False)
    is_recurring = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false(),
    )
    due_day = db.Column(db.SmallInteger, nullable=True)

    budget_month = db.relationship("BudgetMonth", back_populates="budget_expenses")
    category = db.relationship("ExpenseCategory", back_populates="budget_expenses")
    allocations = db.relationship(
        "BudgetAllocation", back_populates="budget_expense", passive_deletes="all",
    )

    __table_args__ = (
        db.CheckConstraint("priority IN ('P0', 'P1', 'P2')", name="priority_valid"),
        db.CheckConstraint(
            "estimated_amount IS NULL OR estimated_amount >= 0",
            name="estimated_amount_nonnegative",
        ),
        db.CheckConstraint(
            "minimum_amount IS NULL OR minimum_amount > 0", name="minimum_amount_positive",
        ),
        db.CheckConstraint(
            "allocation_frequency IN ('DAILY', 'WEEKLY', 'MONTHLY')",
            name="allocation_frequency_valid",
        ),
        db.CheckConstraint("due_day IS NULL OR due_day BETWEEN 1 AND 31", name="due_day_valid"),
    )
