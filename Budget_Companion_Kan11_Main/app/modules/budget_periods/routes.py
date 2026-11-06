from flask import Blueprint, abort, flash, g, redirect, render_template, session, url_for, request
from datetime import datetime, timezone, timedelta, date

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


def _today_vn():
    return datetime.now(timezone(timedelta(hours=7))).date()


def _month_options(today, count=36):
    """Numeric month/year labels rather than browser-specific English month names."""
    result = []
    for offset in range(count):
        total = (today.month - 1) + offset
        year, month = today.year + total // 12, 1 + total % 12
        result.append((f"{year:04d}-{month:02d}", f"Tháng {month:02d}/{year:04d}"))
    return result


def _creation_tracking_start(form, today):
    """Derive an immutable tracking start from a numeric day and selected month."""
    try:
        month_start = datetime.strptime(form.month.data, "%Y-%m").date()
    except (TypeError, ValueError):
        return None
    if month_start < today.replace(day=1):
        form.month.errors.append("Chỉ có thể lập ngân sách cho tháng hiện tại hoặc các tháng tiếp theo.")
        return None
    legacy_date = form.tracking_start_date.data
    if legacy_date is not None and form.tracking_start_day.data is None:
        start_date = legacy_date
    else:
        default_day = today.day if month_start == today.replace(day=1) else 1
        day = form.tracking_start_day.data if form.tracking_start_day.data is not None else default_day
        try:
            start_date = date(month_start.year, month_start.month, day)
        except (TypeError, ValueError):
            form.tracking_start_day.errors.append("Ngày bắt đầu phải thuộc tháng đã chọn.")
            return None
    if start_date.replace(day=1) != month_start:
        form.tracking_start_day.errors.append("Ngày bắt đầu phải thuộc tháng đã chọn.")
        return None
    if start_date < today:
        form.tracking_start_day.errors.append(
            f"Ngày bắt đầu không được trước hôm nay ({today:%d/%m/%Y})."
        )
        return None
    return start_date



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
    today = _today_vn()
    if request.method == "GET":
        form.month.data = today.strftime("%Y-%m")
        form.tracking_start_day.data = today.day
    if form.validate_on_submit():
        start = _creation_tracking_start(form, today)
        if start is not None:
            try:
                budget_month = create_budget_month(
                    g.current_user.id,
                    form.month.data,
                    form.available_vnd.data,
                    tracking_start_date=start,
                )
            except DuplicateBudgetMonthError:
                form.month.errors.append(translate("budget_duplicate_month"))
            else:
                session["active_budget_month_id"] = str(budget_month.id)
                flash("Đã tạo ngân sách tháng. Hãy nhập các khoản dự kiến.", "success")
                return redirect(url_for("budgets.month", month_id=budget_month.id))

    return render_template(
        "budget_periods/form.html",
        form=form,
        heading=translate("budget_create_title"),
        month_options=_month_options(today), today_vn=today,
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
