"""Database models for Budget Companion.

Shared database models are imported here so Flask-Migrate/Alembic
can detect every table.
"""

from app.models.assigned_expense_task import AssignedExpenseTask
from app.models.budget_adjustment import BudgetAdjustment
from app.models.budget_adjustment_detail import BudgetAdjustmentDetail
from app.models.budget_allocation import BudgetAllocation
from app.models.budget_expense import BudgetExpense
from app.models.budget_month import BudgetMonth
from app.models.budget_plan import BudgetPlan
from app.models.expense_category import ExpenseCategory
from app.models.expense_record import ExpenseRecord
from app.models.monthly_review import MonthlyReview
from app.models.recommendation import Recommendation
from app.models.user import User
from app.models.user_preference import UserPreference

__all__ = [
    "AssignedExpenseTask", "BudgetAdjustment", "BudgetAdjustmentDetail",
    "BudgetAllocation", "BudgetExpense", "BudgetMonth", "BudgetPlan",
    "ExpenseCategory", "ExpenseRecord", "MonthlyReview", "Recommendation",
    "User", "UserPreference",
]
