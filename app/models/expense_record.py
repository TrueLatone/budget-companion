import uuid

from sqlalchemy import Uuid

from app.extensions import db


class ExpenseRecord(db.Model):
    """One actual transaction or funds addition, rather than a check-in total."""

    __tablename__ = "expense_records"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_month_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_months.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    task_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("assigned_expense_tasks.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    category_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    amount = db.Column(db.BigInteger, nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    record_type = db.Column(db.String(20), nullable=False)
    # The revised DOCX explicitly adds this attribute; the relationship ERD omits it.
    priority = db.Column(db.String(2), nullable=True)
    title = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)
    budget_impact_scope = db.Column(db.String(10), nullable=True)
    idempotency_key = db.Column(db.String(64), nullable=True)

    budget_month = db.relationship("BudgetMonth", back_populates="expense_records")
    task = db.relationship("AssignedExpenseTask", back_populates="records")
    category = db.relationship("ExpenseCategory", back_populates="expense_records")

    __table_args__ = (
        db.Index("ix_expense_records_month_date", "budget_month_id", "expense_date"),
        db.UniqueConstraint("budget_month_id", "idempotency_key"),
        db.CheckConstraint("amount > 0", name="amount_positive"),
        db.CheckConstraint(
            "record_type IN ('PLANNED', 'UNEXPECTED', 'FUNDS_ADDED')", name="record_type_valid",
        ),
        db.CheckConstraint(
            "(record_type = 'PLANNED' AND task_id IS NOT NULL) OR "
            "(record_type IN ('UNEXPECTED', 'FUNDS_ADDED') AND task_id IS NULL)",
            name="task_matches_record_type",
        ),
        db.CheckConstraint(
            "(record_type IN ('PLANNED', 'UNEXPECTED') AND category_id IS NOT NULL) OR "
            "(record_type = 'FUNDS_ADDED' AND category_id IS NULL)",
            name="category_matches_record_type",
        ),
        db.CheckConstraint(
            "priority IS NULL OR priority IN ('P0', 'P1', 'P2')", name="priority_valid",
        ),
        db.CheckConstraint(
            "(record_type = 'UNEXPECTED' AND priority IS NOT NULL) OR "
            "(record_type = 'FUNDS_ADDED' AND priority IS NULL) OR record_type = 'PLANNED'",
            name="priority_matches_record_type",
        ),
        db.CheckConstraint(
            "budget_impact_scope IS NULL OR (record_type = 'UNEXPECTED' AND "
            "budget_impact_scope IN ('DAILY', 'WEEKLY', 'MONTHLY'))",
            name="budget_impact_scope_valid",
        ),
    )
