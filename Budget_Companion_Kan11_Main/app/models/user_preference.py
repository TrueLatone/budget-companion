import uuid

from sqlalchemy import Uuid

from app.extensions import db


class UserPreference(db.Model):
    """Optional persistent planning and in-app reminder preferences."""

    __tablename__ = "user_preferences"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    preferred_plan_type = db.Column(db.String(20), nullable=True)
    budget_alerts_enabled = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.true(),
    )
    payment_reminders_enabled = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.true(),
    )

    user = db.relationship("User", back_populates="preference")

    __table_args__ = (
        db.CheckConstraint(
            "preferred_plan_type IS NULL OR preferred_plan_type IN "
            "('SAVING', 'BALANCED', 'LIFESTYLE', 'MANUAL')",
            name="preferred_plan_type_valid",
        ),
    )
