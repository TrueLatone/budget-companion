from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.modules.accounts.auth import login_required
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets import services
from app.modules.budgets.forms import BudgetActionForm, ExpenseForm
from app.modules.budgets.rules import BudgetError
from app.modules.budgets.suggestions import BUILTIN_LABELS, P1_REFERENCE_RANGES, SUGGESTED_EXPENSES
from app.workspace import select_month
from app.i18n import get_ui_language, translate

bp = Blueprint("budgets", __name__)


@bp.app_template_filter("budget_label")
def budget_label(name):
    key = BUILTIN_LABELS.get(name)
    return translate(key) if key else name


@bp.get("/budget")
@login_required
def index():
    months = list_budget_months(g.current_user.id)
    month = select_month(g.current_user.id)
    if request.args.get("view") == "year":
        from app.modules.expenses.presentation import today_vn
        year = request.args.get("year", type=int) or (month.month_start.year if month else today_vn().year)
        periods = [m for m in months if m.month_start.year == year]
        summaries = []
        for m in periods:
            plan = next((p for p in m.plans if p.status == "CONFIRMED"), None)
            allocated = sum(a.allocated_amount for a in plan.allocations) if plan else 0
            summaries.append((m, plan, allocated))
        return render_template("budgets/year.html", month=month, months=months, year=year,
                               years=sorted({year, *(m.month_start.year for m in months)}, reverse=True), summaries=summaries)
    return _workspace(month, months)


@bp.get("/budget/<uuid:month_id>")
@login_required
def month(month_id):
    return _workspace(services.get_month(g.current_user.id, month_id))


def _workspace(month, months=None, *, setup_error=None, invalid_form=None):
    expenses = services.list_expenses(g.current_user.id, month.id) if month else []
    plans = services.list_plans(g.current_user.id, month.id) if month else []
    form = invalid_form or ExpenseForm()
    _category_choices(form)
    summary_plan = next((plan for plan in plans if plan.status == "CONFIRMED"), None)
    signatures = [(p.planned_savings, sorted((str(a.budget_expense_id), a.allocated_amount)
                  for a in p.allocations)) for p in plans if p.plan_type != "MANUAL"]
    identical = len(signatures) == 3 and signatures.count(signatures[0]) == 3
    return render_template(
        "budgets/index.html", identical=identical, setup_error=setup_error, invalid_form=invalid_form, month=month, expenses=expenses, plans=plans,
        months=months if months is not None else list_budget_months(g.current_user.id),
        locked=summary_plan is not None, action_form=BudgetActionForm(),
        expense_form=form, suggestions=SUGGESTED_EXPENSES, ranges=P1_REFERENCE_RANGES,
        previous=services.previous_confirmed_month(month) if month and not expenses and not plans else None,
        summary_plan=summary_plan,
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
        data = form.data
        if not expense_id and not data["category_id"] and not data["category_name"]:
            data["category_name"] = data["expense_name"]
        try:
            services.save_expense(g.current_user.id, month.id, data, expense_id=expense_id)
        except BudgetError as exc:
            if expense_id:
                raise
            return _extra_error(month, form, exc)
        return redirect(url_for("budgets.month", month_id=month.id, _anchor="setup" if expense_id else "add-expense"))
    if not expense_id and request.method == "POST":
        return _workspace(month, invalid_form=form), 400
    return render_template("budgets/expense_form.html", month=month, form=form, expense=expense, ranges=P1_REFERENCE_RANGES), 400 if request.method == "POST" else 200


def _extra_error(month, form, error):
    # Route a service validation failure back to the input that can correct it.
    message = str(error)
    for fragment, field in (("uplicate", "expense_name"), ("unique", "expense_name"),
            ("expense name", "expense_name"), ("minimum", "minimum_amount"),
            ("Minimum", "minimum_amount"), ("Due day", "due_day"),
            ("Estimated amount", "estimated_amount"), ("category name", "expense_name")):
        if fragment in message:
            form[field].errors = [*form[field].errors, message]
            return _workspace(month, invalid_form=form), 400
    return _workspace(month, setup_error=message, invalid_form=form), 409 if isinstance(error, services.BudgetConflict) else 400


def _category_choices(form):
    form.category_id.choices = [("", translate("live_enter_category"))] + [
        (str(category.id), category.category_name)
        for category in services.list_categories(g.current_user.id)
    ]


@bp.post("/budget/<uuid:month_id>/reuse")
@login_required
def reuse_setup(month_id):
    _require_action()
    count, review = services.reuse_previous_setup(
        g.current_user.id, month_id, request.form.get("source_month"), request.form.get("mode"))
    flash(translate("bp_reused").format(count=count), "success")
    if review:
        flash(translate("bp_review_units"), "warning")
    return redirect(url_for("budgets.month", month_id=month_id, _anchor="saved-expenses"))


@bp.post("/budget/<uuid:month_id>/expenses/suggested")
@login_required
def apply_suggestions(month_id):
    _require_action()
    values = _suggested_values()
    created = services.apply_suggested_expenses(
        g.current_user.id, month_id, request.form.getlist("suggestion"), values,
    )
    flash(f"Added {len(created)} suggested expenses. Existing expenses were kept unchanged.", "success")
    return redirect(url_for("budgets.month", month_id=month_id, _anchor="setup"))


def _suggested_values():
    return {
        suggestion.key: {
            field: request.form.get(f"{suggestion.key}_{field}")
            for field in ("estimated_amount", "minimum_amount", "due_day")
        } | {"allocation_frequency": request.form.get(
            f"{suggestion.key}_allocation_frequency", suggestion.frequency,
        ), "is_recurring": request.form.get(f"{suggestion.key}_is_recurring") == "on"}
        for suggestion in SUGGESTED_EXPENSES
    }


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
    month = services.get_month(g.current_user.id, month_id)
    if any(p.status == "CONFIRMED" for p in services.list_plans(g.current_user.id, month.id)):
        raise services.BudgetConflict("This budget month is already confirmed.")
    form = ExpenseForm()
    _category_choices(form)
    try:
        custom = None
        if any(request.form.get(key) for key in ("expense_name", "category_name", "category_id",
                "estimated_amount", "minimum_amount", "due_day", "is_recurring")):
            if not form.validate_on_submit():
                return _workspace(month, invalid_form=form), 400
            custom = form.data
            if not custom["category_id"] and not custom["category_name"]:
                custom["category_name"] = custom["expense_name"]
        services.generate_budget_plans(g.current_user.id, month_id,
                                       selected=request.form.getlist("suggestion"),
                                       values=_suggested_values(), custom=custom,
                                       savings_target=request.form.get("savings_target"))
    except BudgetError as exc:
        if custom:
            return _extra_error(month, form, exc)
        return _workspace(month, setup_error=str(exc)), 409 if isinstance(exc, services.BudgetConflict) else 400
    return redirect(url_for("budgets.month", month_id=month_id, _anchor="compare"))


@bp.get("/budget/<uuid:month_id>/plans/<uuid:plan_id>")
@login_required
def plan(month_id, plan_id):
    saved_plan = services.get_plan(g.current_user.id, month_id, plan_id)
    return render_template(
        "budgets/plan.html", plan=saved_plan, month=saved_plan.budget_month,
        locked=any(p.status == "CONFIRMED" for p in services.list_plans(g.current_user.id, month_id)),
        action_form=BudgetActionForm(),
        breakdown=services.plan_breakdown(g.current_user.id, month_id, plan_id),
        confirm_snapshot=services.plan_draft_fingerprint(saved_plan),
    )


@bp.route("/budget/<uuid:month_id>/plans/<uuid:plan_id>/customize", methods=("GET", "POST"))
@login_required
def customize(month_id, plan_id):
    month = services.get_month(g.current_user.id, month_id)
    candidate = services.get_plan(g.current_user.id, month_id, plan_id)
    if any(p.status == "CONFIRMED" for p in services.list_plans(g.current_user.id, month_id)):
        raise services.BudgetConflict("This budget month is already confirmed.")
    if candidate.status != "GENERATED":
        raise services.BudgetConflict("Only unconfirmed plans can be customized.")
    display = dict(
        month=month, plan=candidate, action_form=BudgetActionForm(),
        submitted_values={}, validation_error=None,
        plan_snapshot=services.customization_fingerprint(g.current_user.id, month.id, candidate.id),
    )
    if request.method == "GET":
        return render_template("budgets/customize.html", **display)
    _require_action()
    editable = {str(a.budget_expense_id) for a in candidate.allocations
                if a.budget_expense.priority in ("P1", "P2")}
    fields = {"allocation_" + expense_id for expense_id in editable}
    posted_fields = {key for key in request.form if key.startswith("allocation_")}
    display["submitted_values"] = request.form.to_dict(flat=True)
    # Never replace the submitted token on an error: retrying an old form must
    # still conflict, even when the first submission failed field validation.
    display["plan_snapshot"] = request.form.get("plan_snapshot", "")
    if (posted_fields != fields or
            any(len(request.form.getlist(field)) != 1 for field in fields) or
            len(request.form.getlist("plan_snapshot")) != 1):
        display["validation_error"] = "Submit exactly one amount for each P1 and P2 expense."
        return render_template("budgets/customize.html", **display), 400
    try:
        customized = services.save_manual_plan(
            g.current_user.id, month_id, plan_id,
            {expense_id: request.form.get("allocation_" + expense_id) for expense_id in editable},
            expected_fingerprint=request.form.get("plan_snapshot"),
        )
    except BudgetError as exc:
        display["validation_error"] = str(exc)
        return render_template("budgets/customize.html", **display), (
            409 if isinstance(exc, services.BudgetConflict) else 400
        )
    flash("Manual draft saved. Review the allocations before confirming.", "success")
    return redirect(url_for("budgets.plan", month_id=month.id, plan_id=customized.id))


@bp.post("/budget/<uuid:month_id>/plans/<uuid:plan_id>/confirm")
@login_required
def confirm(month_id, plan_id):
    _require_action()
    selected = services.get_plan(g.current_user.id, month_id, plan_id)
    snapshot = None
    if selected.status == "GENERATED" and selected.plan_type == "MANUAL":
        snapshots = request.form.getlist("confirm_snapshot")
        if len(snapshots) != 1 or not snapshots[0]:
            raise services.BudgetConflict("Review the latest manual plan before confirming.")
        snapshot = snapshots[0]
    services.confirm_and_schedule(g.current_user.id, month_id, plan_id, expected_fingerprint=snapshot)
    flash("Đã xác nhận và tạo lịch chi tiêu." if get_ui_language()=="vi" else "Plan confirmed and scheduled.", "success")
    return redirect(url_for("expenses.index", budget_month_id=month_id, view="month"))


@bp.errorhandler(services.BudgetNotFound)
def not_found(error):
    return render_template("budgets/error.html", message=str(error)), 404


@bp.errorhandler(BudgetError)
def invalid_budget(error):
    return render_template("budgets/error.html", message=str(error)), 409 if isinstance(error, services.BudgetConflict) else 400
