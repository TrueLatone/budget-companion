import uuid

from sqlalchemy import Uuid

from app.extensions import db


class ExpenseCategory(db.Model):
    """A user-owned category, or a built-in category when user_id is NULL."""

    __tablename__ = "expense_categories"

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    category_name = db.Column(db.String(100), nullable=False)

    user = db.relationship("User", back_populates="expense_categories")
    budget_expenses = db.relationship(
        "BudgetExpense", back_populates="category", passive_deletes="all",
    )
    expense_records = db.relationship(
        "ExpenseRecord", back_populates="category", passive_deletes="all",
    )

    __table_args__ = (
        db.CheckConstraint(
            "length(trim(category_name)) > 0", name="category_name_nonempty",
        ),
        db.Index(
            "uq_expense_categories_owned_name", user_id,
            db.func.lower(db.func.trim(category_name)), unique=True,
            postgresql_where=user_id.is_not(None),
            sqlite_where=user_id.is_not(None),
        ),
        db.Index(
            "uq_expense_categories_builtin_name",
            db.func.lower(db.func.trim(category_name)), unique=True,
            postgresql_where=user_id.is_(None),
            sqlite_where=user_id.is_(None),
        ),
    )
