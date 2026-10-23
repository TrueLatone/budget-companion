import uuid

from sqlalchemy import Uuid

from app.extensions import db


class BudgetMonth(db.Model):
    __tablename__ = "budget_months"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        Uuid(as_uuid=True),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    month_start = db.Column(db.Date, nullable=False)
    available_vnd = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    user = db.relationship("User", back_populates="budget_months")

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "month_start",
            name="uq_budget_months_user_id_month_start",
        ),
        db.CheckConstraint(available_vnd >= 0, name="available_vnd_nonnegative"),
        db.CheckConstraint(
            db.extract("day", month_start) == 1,
            name="month_starts_first_day",
        ),
    )

    def __repr__(self):
        return f"<BudgetMonth {self.id} {self.month_start:%Y-%m}>"
