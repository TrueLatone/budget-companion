from flask import Blueprint, g, render_template

from app.modules.accounts.auth import login_required
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets import services as budgets
from app.modules.expenses import services as expenses
from app.modules.recommendations.services import RecommendationServiceError
from app.modules.dashboard import services
from app.workspace import select_month

bp = Blueprint("dashboard", __name__)


@bp.get("/dashboard")
@login_required
def index():
    month = select_month(g.current_user.id)
    view = services.build_dashboard(g.current_user.id, month.id) if month else None
    return render_template("pages/dashboard.html", month=month, months=list_budget_months(g.current_user.id), view=view)


@bp.errorhandler(budgets.BudgetNotFound)
def not_found(error):
    return render_template("dashboard/error.html", message="live_month_not_found"), 404


@bp.errorhandler(budgets.BudgetError)
@bp.errorhandler(expenses.ValidationError)
@bp.errorhandler(expenses.NotFoundError)
@bp.errorhandler(RecommendationServiceError)
def invalid_data(error):
    return render_template("dashboard/error.html", message="live_data_error"), 409
