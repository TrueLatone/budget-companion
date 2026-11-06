import uuid

from sqlalchemy import Uuid, text

from app.extensions import db


class BudgetPlan(db.Model):
    """A candidate strategy or the month's single confirmed allocation snapshot."""

    __tablename__ = "budget_plans"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_month_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_months.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    plan_type = db.Column(db.String(20), nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="GENERATED", server_default="GENERATED",
    )
    planned_savings = db.Column(
        db.BigInteger, nullable=False, default=0, server_default=text("0"),
    )

    budget_month = db.relationship("BudgetMonth", back_populates="plans")
    allocations = db.relationship(
        "BudgetAllocation", back_populates="plan", passive_deletes="all",
    )

    __table_args__ = (
        db.CheckConstraint(
            "plan_type IN ('SAVING', 'BALANCED', 'LIFESTYLE', 'MANUAL')", name="plan_type_valid",
        ),
        db.CheckConstraint("status IN ('GENERATED', 'CONFIRMED')", name="status_valid"),
        db.CheckConstraint("planned_savings >= 0", name="planned_savings_nonnegative"),
        db.Index(
            "uq_budget_plans_confirmed_month", "budget_month_id", unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
            sqlite_where=text("status = 'CONFIRMED'"),
        ),
    )
