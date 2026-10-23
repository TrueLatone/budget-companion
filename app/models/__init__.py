"""Shared database models visible to Flask-Migrate."""

from app.models.budget_month import BudgetMonth
from app.models.user import User

__all__ = ["BudgetMonth", "User"]
