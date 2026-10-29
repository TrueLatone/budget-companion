import uuid

from sqlalchemy import Uuid

from app.extensions import db


class AssignedExpenseTask(db.Model):
    """A scheduled period; comparison and overdue labels are derived by services."""

    __tablename__ = "assigned_expense_tasks"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    allocation_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_allocations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    assigned_date = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    original_limit = db.Column(db.BigInteger, nullable=False)
    current_limit = db.Column(db.BigInteger, nullable=False)
    task_status = db.Column(
        db.String(20), nullable=False, default="PENDING", server_default="PENDING",
    )
    payment_due_date = db.Column(db.Date, nullable=True, index=True)
    payment_status = db.Column(db.String(20), nullable=True)

    allocation = db.relationship("BudgetAllocation", back_populates="tasks")
    records = db.relationship("ExpenseRecord", back_populates="task", passive_deletes="all")
    adjustment_details = db.relationship(
        "BudgetAdjustmentDetail", back_populates="task", passive_deletes="all",
    )

    __table_args__ = (
        db.UniqueConstraint("allocation_id", "assigned_date"),
        db.CheckConstraint("period_end >= assigned_date", name="period_order_valid"),
        db.CheckConstraint("original_limit >= 0", name="original_limit_nonnegative"),
        db.CheckConstraint("current_limit >= 0", name="current_limit_nonnegative"),
        db.CheckConstraint(
            "task_status IN ('PENDING', 'RECORDED', 'NO_EXPENSE')", name="task_status_valid",
        ),
        db.CheckConstraint(
            "payment_status IS NULL OR payment_status IN ('PAID', 'UNPAID')",
            name="payment_status_valid",
        ),
    )
