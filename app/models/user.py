import uuid

from sqlalchemy import Uuid

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(320), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )
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

    budget_months = db.relationship(
        "BudgetMonth",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            email == db.func.lower(db.func.trim(email)),
            name="email_normalized",
        ),
    )

    def __repr__(self):
        return f"<User {self.id}>"
