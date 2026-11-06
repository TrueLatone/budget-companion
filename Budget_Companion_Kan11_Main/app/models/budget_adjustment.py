import uuid

from sqlalchemy import Uuid

from app.extensions import db


class BudgetAdjustment(db.Model):
    """Applied adjustment event, optionally originating from a recommendation."""

    __tablename__ = "budget_adjustments"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("recommendations.id", ondelete="RESTRICT"),
        nullable=True, unique=True,
    )
    effective_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    adjustment_type = db.Column(db.String(24), nullable=False)

    recommendation = db.relationship("Recommendation", back_populates="adjustment")
    details = db.relationship(
        "BudgetAdjustmentDetail", back_populates="adjustment", passive_deletes="all",
    )

    __table_args__ = (
        db.CheckConstraint(
            "length(trim(adjustment_type)) > 0", name="adjustment_type_nonempty",
        ),
    )
