import uuid

from sqlalchemy import Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db


class Recommendation(db.Model):
    """An explainable proposal; JSON task references require service validation."""

    __tablename__ = "recommendations"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_month_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("budget_months.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    reason = db.Column(db.Text, nullable=False)
    expected_impact = db.Column(db.Text, nullable=False)
    proposed_changes = db.Column(
        db.JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
        nullable=False,
    )
    status = db.Column(
        db.String(20), nullable=False, default="PENDING", server_default="PENDING",
    )

    budget_month = db.relationship("BudgetMonth", back_populates="recommendations")
    adjustment = db.relationship(
        "BudgetAdjustment", back_populates="recommendation", uselist=False,
        passive_deletes="all",
    )

    __table_args__ = (
        db.CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'REJECTED')", name="status_valid"),
    )
