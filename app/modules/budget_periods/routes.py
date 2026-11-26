from flask import Blueprint, abort, flash, g, redirect, render_template, session, url_for, request

from app.i18n import get_ui_language, translate
from app.modules.budgets.rules import BudgetError
from app.modules.budgets.services import BudgetConflict, BudgetNotFound
from app.modules.budget_periods.services import delete_month
from app.modules.accounts.auth import login_required
from app.modules.budget_periods.forms import BudgetMonthCreateForm, BudgetMonthUpdateForm
from app.modules.budget_periods.services import (
    DuplicateBudgetMonthError,
    create_budget_month,
    get_budget_month,
    list_budget_months,
    update_available_vnd,
)

bp = Blueprint("budget_periods", __name__, url_prefix="/budget-periods")


@bp.get("")
@login_required
def index():
    return render_template(
        "budget_periods/index.html",
        budget_months=list_budget_months(g.current_user.id),
        active_budget_month_id=session.get("active_budget_month_id"),
    )


@bp.route("/new", methods=("GET", "POST"))
@login_required
def create():
    form = BudgetMonthCreateForm()
    from app.modules.expenses.presentation import today_vn
    today = today_vn()
    existing = None
    if request.method == "GET":
        form.month.data = today.strftime("%Y-%m")
        form.tracking_start_day.data = today.day
    if form.validate_on_submit():
        try:
            budget_month = create_budget_month(
                g.current_user.id,
                form.month.data,
                form.available_vnd.data,
                tracking_start_date=form.tracking_start_date.data,
            )
        except BudgetError as error:
            form.available_vnd.errors.append(str(error))
        except DuplicateBudgetMonthError:
            existing = next((m for m in list_budget_months(g.current_user.id) if m.month_start.strftime("%Y-%m") == form.month.data), None)
            form.month.errors.append(translate("budget_duplicate_month"))
        else:
            session["active_budget_month_id"] = str(budget_month.id)
            flash(translate("budget_create_success"), "success")
            return redirect(url_for("budget_periods.index"))

    return render_template(
        "budget_periods/form.html",
        form=form,
        heading=translate("budget_create_title"), existing=existing, today=today,
    )


@bp.route("/<uuid:budget_month_id>/edit", methods=("GET", "POST"))
@login_required
def edit(budget_month_id):
    budget_month = get_budget_month(g.current_user.id, budget_month_id)
    if budget_month is None:
        abort(404)

    if budget_month.plans:
        return render_template("budgets/error.html", message="Funds are locked after generating plans."), 409
    form = BudgetMonthUpdateForm(obj=budget_month)
    if form.validate_on_submit():
        try:
            update_available_vnd(budget_month, form.available_vnd.data)
        except BudgetConflict as error:
            return render_template("budgets/error.html", message=str(error)), 409
        except BudgetError as error:
            form.available_vnd.errors.append(str(error))
        else:
            flash(translate("budget_update_success"), "success")
            return redirect(url_for("budget_periods.index"))

    return render_template(
        "budget_periods/form.html",
        form=form,
        heading=translate("budget_edit_title").format(
            month=budget_month.month_start.strftime('%m/%Y')
        ),
        budget_month=budget_month,
    )


@bp.post("/<uuid:budget_month_id>/select")
@login_required
def select(budget_month_id):
    budget_month = get_budget_month(g.current_user.id, budget_month_id)
    if budget_month is None:
        abort(404)

    session["active_budget_month_id"] = str(budget_month.id)
    flash(
        translate("budget_select_success").format(
            month=budget_month.month_start.strftime('%m/%Y')
        ),
        "success",
    )
    return redirect(url_for("budget_periods.index"))


@bp.post("/<uuid:month_id>/delete")
@login_required
def remove(month_id):
    if request.form.get("confirm_month") != str(month_id):
        abort(400)
    try:
        delete_month(g.current_user.id, month_id)
    except BudgetNotFound:
        abort(404)
    except BudgetConflict as error:
        return render_template("budgets/error.html", message=str(error)), 409
    if session.get("active_budget_month_id") == str(month_id):
        session.pop("active_budget_month_id", None)
    flash("Đã xóa tháng ngân sách." if get_ui_language() == "vi" else "Budget month deleted.", "success")
    return redirect(url_for("budget_periods.index"))
