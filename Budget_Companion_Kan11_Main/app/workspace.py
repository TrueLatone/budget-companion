"""Live workspace selection/presentation helpers; no demo financial state."""

from datetime import date
import re

from flask import g, request, session, url_for

from app.extensions import db
from app.i18n import format_money, translate
from app.models import BudgetMonth
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets import services as budgets


def select_month(user_id):
    if request.args.get("budget_month_id"):
        return budgets.get_month(user_id, request.args["budget_month_id"])
    if request.args.get("month"):
        raw = request.args["month"]
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", raw):
                raise ValueError
            start = date.fromisoformat(raw + "-01")
        except ValueError:
            raise budgets.BudgetNotFound("Budget month not found.") from None
        month = db.session.scalar(db.select(BudgetMonth).where(
            BudgetMonth.user_id == user_id, BudgetMonth.month_start == start,
        ))
        if month is None:
            raise budgets.BudgetNotFound("Budget month not found.")
        return month
    if session.get("active_budget_month_id"):
        return budgets.get_month(user_id, session["active_budget_month_id"])
    months = list_budget_months(user_id)
    return months[0] if months else None


def register_workspace(app):
    @app.context_processor
    def context():
        def fallback_month():
            if g.current_user is None:
                return None
            # Error/history pages may lack a month view model; use only an
            # authorized session/default month, never unchecked query/form IDs.
            try:
                if session.get("active_budget_month_id"):
                    return budgets.get_month(g.current_user.id, session["active_budget_month_id"])
            except budgets.BudgetNotFound:
                return None
            months = list_budget_months(g.current_user.id)
            return months[0] if months else None

        def links(month):
            args = {"budget_month_id": month.id} if month else {}
            return {
                "dashboard": url_for("dashboard.index", **args),
                "budgets": url_for("budgets.index", **args),
                "expenses": url_for("expenses.index", view="month", **args),
                "recommendations": url_for("recommendations.index", **args),
            }

        return {"workspace_fallback_month": fallback_month, "workspace_links": links,
                "workspace_owned_months": lambda: list_budget_months(g.current_user.id),
                "workspace_money": lambda value: translate("live_unknown") if value is None else format_money(value) + " ₫"}
