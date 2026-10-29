from flask import Blueprint, abort, flash, g, redirect, render_template, session, url_for

from app.i18n import format_month, translate
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
    if form.validate_on_submit():
        try:
            budget_month = create_budget_month(
                g.current_user.id,
                form.month.data,
                form.available_vnd.data,
                tracking_start_date=form.tracking_start_date.data,
            )
        except DuplicateBudgetMonthError:
            form.month.errors.append(translate("budget_duplicate_month"))
        else:
            session["active_budget_month_id"] = str(budget_month.id)
            flash(translate("budget_create_success"), "success")
            return redirect(url_for("budget_periods.index"))

    return render_template(
        "budget_periods/form.html",
        form=form,
        heading=translate("budget_create_title"),
    )


@bp.route("/<uuid:budget_month_id>/edit", methods=("GET", "POST"))
@login_required
def edit(budget_month_id):
    budget_month = get_budget_month(g.current_user.id, budget_month_id)
    if budget_month is None:
        abort(404)

    form = BudgetMonthUpdateForm(obj=budget_month)
    if form.validate_on_submit():
        update_available_vnd(budget_month, form.available_vnd.data)
        flash(translate("budget_update_success"), "success")
        return redirect(url_for("budget_periods.index"))

    return render_template(
        "budget_periods/form.html",
        form=form,
        heading=translate("budget_edit_title").format(
            month=format_month(budget_month.month_start)
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
            month=format_month(budget_month.month_start)
        ),
        "success",
    )
    return redirect(url_for("budget_periods.index"))
