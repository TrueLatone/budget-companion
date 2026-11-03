from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from app.modules.accounts.auth import login_required
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets import services
from app.modules.budgets.forms import BudgetActionForm, ExpenseForm
from app.modules.budgets.rules import BudgetError
from app.modules.budgets.suggestions import SUGGESTED_EXPENSES

bp = Blueprint("budgets", __name__)


@bp.get("/budget")
@login_required
def index():
    months = list_budget_months(g.current_user.id)
    month_id = request.args.get("budget_month_id") or session.get("active_budget_month_id")
    if month_id:
        month = services.get_month(g.current_user.id, month_id)
    else:
        month = months[0] if months else None
    return _workspace(month, months)


@bp.get("/budget/<uuid:month_id>")
@login_required
def month(month_id):
    return _workspace(services.get_month(g.current_user.id, month_id))


def _workspace(month, months=None):
    expenses = services.list_expenses(g.current_user.id, month.id) if month else []
    plans = services.list_plans(g.current_user.id, month.id) if month else []
    form = ExpenseForm()
    _category_choices(form)
    return render_template(
        "budgets/index.html", month=month, expenses=expenses, plans=plans,
        months=months if months is not None else list_budget_months(g.current_user.id),
        locked=any(plan.status == "CONFIRMED" for plan in plans), action_form=BudgetActionForm(),
        expense_form=form, suggestions=SUGGESTED_EXPENSES,
        existing_names={expense.expense_name.strip().casefold() for expense in expenses},
        breakdowns={plan.id: services.plan_breakdown(g.current_user.id, month.id, plan.id) for plan in plans},
    )


@bp.route("/budget/<uuid:month_id>/expenses/new", methods=("GET", "POST"))
@login_required
def create_expense(month_id):
    return _expense_form(month_id)


@bp.route("/budget/<uuid:month_id>/expenses/<uuid:expense_id>/edit", methods=("GET", "POST"))
@login_required
def edit_expense(month_id, expense_id):
    return _expense_form(month_id, expense_id)


def _expense_form(month_id, expense_id=None):
    month = services.get_month(g.current_user.id, month_id)
    expense = services.get_expense(g.current_user.id, month.id, expense_id) if expense_id else None
    form = ExpenseForm(obj=expense)
    _category_choices(form)
    if request.method == "GET" and expense:
        form.category_id.data = str(expense.category_id)
    if form.validate_on_submit():
        services.save_expense(g.current_user.id, month.id, form.data, expense_id=expense_id)
        return redirect(url_for("budgets.month", month_id=month.id, _anchor="setup" if expense_id else "add-expense"))
    return render_template("budgets/expense_form.html", month=month, form=form, expense=expense), 400 if request.method == "POST" else 200


def _category_choices(form):
    form.category_id.choices = [("", "Enter a new category below")] + [
        (str(category.id), category.category_name)
        for category in services.list_categories(g.current_user.id)
    ]


@bp.post("/budget/<uuid:month_id>/expenses/suggested")
@login_required
def apply_suggestions(month_id):
    _require_action()
    values = {
        suggestion.key: {
            field: request.form.get(f"{suggestion.key}_{field}")
            for field in ("estimated_amount", "minimum_amount", "due_day")
        } | {"allocation_frequency": request.form.get(
            f"{suggestion.key}_allocation_frequency", suggestion.frequency,
        )}
        for suggestion in SUGGESTED_EXPENSES
    }
    created = services.apply_suggested_expenses(
        g.current_user.id, month_id, request.form.getlist("suggestion"), values,
    )
    flash(f"Added {len(created)} suggested expenses. Existing expenses were kept unchanged.", "success")
    return redirect(url_for("budgets.month", month_id=month_id, _anchor="setup"))


def _require_action():
    if not BudgetActionForm().validate_on_submit():
        abort(400)


@bp.post("/budget/<uuid:month_id>/expenses/<uuid:expense_id>/delete")
@login_required
def delete_expense(month_id, expense_id):
    _require_action()
    services.delete_expense(g.current_user.id, month_id, expense_id)
    return redirect(url_for("budgets.month", month_id=month_id))


@bp.post("/budget/<uuid:month_id>/plans/generate")
@login_required
def generate(month_id):
    _require_action()
    services.generate_budget_plans(g.current_user.id, month_id)
    return redirect(url_for("budgets.month", month_id=month_id, _anchor="compare"))


@bp.get("/budget/<uuid:month_id>/plans/<uuid:plan_id>")
@login_required
def plan(month_id, plan_id):
    saved_plan = services.get_plan(g.current_user.id, month_id, plan_id)
    return render_template(
        "budgets/plan.html", plan=saved_plan, month=saved_plan.budget_month,
        action_form=BudgetActionForm(),
        breakdown=services.plan_breakdown(g.current_user.id, month_id, plan_id),
    )


@bp.post("/budget/<uuid:month_id>/plans/<uuid:plan_id>/confirm")
@login_required
def confirm(month_id, plan_id):
    _require_action()
    services.confirm_plan(g.current_user.id, month_id, plan_id)
    return redirect(url_for("budgets.plan", month_id=month_id, plan_id=plan_id))


@bp.errorhandler(services.BudgetNotFound)
def not_found(error):
    return "Budget resource not found.", 404


@bp.errorhandler(BudgetError)
def invalid_budget(error):
    return render_template("budgets/error.html", message=str(error)), 409 if isinstance(error, services.BudgetConflict) else 400
