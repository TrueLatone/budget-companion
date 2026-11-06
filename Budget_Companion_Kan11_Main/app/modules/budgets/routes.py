from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for, session
from uuid import uuid4
from datetime import date, timedelta
import calendar

from app.modules.accounts.auth import login_required
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets import services
from app.modules.budgets.forms import BudgetActionForm, ExpenseForm
from app.modules.budgets.rules import BudgetError, ExpenseInput, money, validate_setup
from app.modules.budgets.suggestions import SUGGESTED_EXPENSES
from app.modules.budgets.ai_service import suggest_priority
from app.modules.budgets.ui_copy import budget_copy
from app.workspace import select_month
from app.i18n import translate

bp = Blueprint("budgets", __name__)


@bp.get("/budget")
@login_required
def index():
    months = list_budget_months(g.current_user.id)
    month = select_month(g.current_user.id)
    return _workspace(month, months)


@bp.get("/budget/<uuid:month_id>")
@login_required
def month(month_id):
    return _workspace(services.get_month(g.current_user.id, month_id))



def _safe_custom_rows():
    try:
        return _submitted_custom_rows()
    except BudgetError:
        return []


def _submitted_custom_rows():
    """Extract uncommitted additional rows for both POST validation and rerender."""
    ids = request.form.getlist("custom_id") if request.method == "POST" else []
    if len(ids) > 40 or len(ids) != len(set(ids)) or any(
        not key.isascii() or not key.isdigit() or len(key) > 5 for key in ids
    ):
        raise BudgetError("Danh sách khoản chi thêm không hợp lệ (tối đa 40 khoản).")
    fields = ("expense_name", "priority", "estimated_amount", "minimum_amount",
              "allocation_frequency", "due_day")
    rows = []
    for index in ids:
        prefix = f"custom_{index}_"
        if any(len(request.form.getlist(prefix + field)) != 1 for field in fields):
            raise BudgetError("Hãy nhập đầy đủ các trường cho khoản chi thêm.")
        rows.append({"id": index, **{field: request.form.get(prefix + field, "") for field in fields},
                     "is_recurring": prefix + "is_recurring" in request.form})
    # Block submission of injected custom_* fields not represented by a row.
    posted_fields = {key for key in request.form if key.startswith("custom_") and key != "custom_id"}
    allowed_fields = {f"custom_{index}_{field}" for index in ids for field in fields + ("is_recurring",)}
    if posted_fields != (posted_fields & allowed_fields):
        raise BudgetError("Danh sách khoản chi thêm không hợp lệ.")
    return rows

def _workspace(month, months=None, *, form_error=None, suggestion_errors=None, submitted_values=None, custom_form_error=None):
    expenses = services.list_expenses(g.current_user.id, month.id) if month else []
    plans = services.list_plans(g.current_user.id, month.id) if month else []
    form = ExpenseForm()
    _category_choices(form)
    summary_plan = next((plan for plan in plans if plan.status == "CONFIRMED"), None)
    summary_plan = summary_plan or next((plan for plan in plans if plan.plan_type == "BALANCED"), None)
    generated = [plan for plan in plans if plan.status == "GENERATED" and plan.plan_type in {"SAVING", "BALANCED", "LIFESTYLE"}]
    def _signature(plan):
        return (plan.planned_savings,
                tuple(sorted((str(a.budget_expense_id), a.allocated_amount) for a in plan.allocations)))
    choices_identical = len(generated) == 3 and len({_signature(plan) for plan in generated}) == 1
    return render_template(
        "budgets/index.html", month=month, expenses=expenses, plans=plans,
        months=months if months is not None else list_budget_months(g.current_user.id),
        locked=any(plan.status == "CONFIRMED" for plan in plans), action_form=BudgetActionForm(),
        expense_form=form, suggestions=SUGGESTED_EXPENSES,
        summary_plan=summary_plan,
        existing_names={expense.expense_name.strip().casefold() for expense in expenses},
        breakdowns={plan.id: services.plan_breakdown(g.current_user.id, month.id, plan.id) for plan in plans},
        bp=budget_copy(getattr(g, "ui_locale", "vi")),
        ai_explanations=(session.get("budget_plan_explanations", {}).get("explanations", {})
                         if session.get("budget_plan_explanations", {}).get("month_id") == str(month.id)
                         else {}) if month else {},
        choices_identical=choices_identical,
        form_error=form_error, suggestion_errors=suggestion_errors or {},
        submitted_values=submitted_values or {},
        selected_keys=set(request.form.getlist("suggestion")) if request.method == "POST" else set(),
        custom_form_error=custom_form_error,
        custom_drafts=(_safe_custom_rows() if request.method == "POST" else []),
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
        try:
            services.save_expense(g.current_user.id, month.id, form.data, expense_id=expense_id)
        except BudgetError as exc:
            error = _friendly_budget_error(exc)
        else:
            flash("Đã lưu khoản chi.", "success")
            return redirect(url_for("budgets.month", month_id=month.id, _anchor="add-expense" if not expense_id else "setup"))
    elif request.method == "POST":
        messages = [err for field in form for err in field.errors]
        error = "Kiểm tra lại các trường bắt buộc: " + "; ".join(messages) if messages else "Dữ liệu chưa hợp lệ. Hãy kiểm tra lại."
    else:
        error = None
    if not expense_id and error:
        return _workspace(month, custom_form_error=error), 400
    return render_template("budgets/expense_form.html", month=month, form=form, expense=expense,
                           form_error=error, bp=budget_copy(getattr(g, "ui_locale", "vi"))), 400 if error else 200

def _category_choices(form):
    form.category_id.choices = [("", translate("live_enter_category"))] + [
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
    flash(f"Đã thêm {len(created)} khoản chi gợi ý.", "success")
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


def _friendly_budget_error(error):
    """Friendly Vietnamese errors in the same Budget screen; no backend rule weakening."""
    message = str(error)
    lower = message.lower()
    if 'enter an expense name' in lower or 'invalid additional expense' in lower:
        return 'Hãy nhập tên hợp lệ cho khoản chi mới (tối đa 100 ký tự).'
    if 'only p1 expenses may specify a minimum' in lower:
        return 'Chỉ khoản thiết yếu mới cần mức tối thiểu. Hãy kiểm tra lại khoản chi mới.'
    if 'too many additional expenses' in lower:
        return 'Bạn có thể thêm tối đa 40 khoản chi trong một lần.'
    if 'Budget shortfall' in message or 'insufficient funds' in lower or 'not enough funds' in lower:
        return 'Nguồn tiền chưa đủ cho các khoản bắt buộc và mức chi tối thiểu. Hãy điều chỉnh số tiền trước khi tiếp tục.'
    if 'Required P0 expenses' in message:
        return 'Cần có tiền thuê trọ, tiền điện và tiền nước trước khi tạo kế hoạch.'
    if 'unique' in lower or 'duplicate' in lower:
        return 'Đã có khoản chi cùng tên trong tháng này. Hãy đặt một tên khác.'
    if 'amount' in lower and ('integer' in lower or 'positive' in lower or 'nonnegative' in lower):
        return 'Số tiền phải là số nguyên hợp lệ, không âm. Khoản chi bắt buộc cần lớn hơn 0.'
    if 'minimum' in lower:
        return 'Khoản chi thiết yếu không được thấp hơn mức tối thiểu đã chọn.'
    if 'exceed available funds' in lower or 'allocations plus planned savings' in lower or 'must exactly equal available' in lower:
        return 'Tổng tiền phân bổ và tiết kiệm phải bằng số tiền hiện có.'
    if 'each expense' in lower or 'exactly one' in lower:
        return 'Danh sách khoản chi không hợp lệ. Hãy tải lại trang và thử lại.'
    if 'confirmed' in lower or 'locked' in lower:
        return 'Kế hoạch tháng này đã được xác nhận và không thể chỉnh sửa.'
    if 'due day' in lower:
        return 'Ngày đến hạn cần nằm trong khoảng 1 đến 31 và chỉ dùng cho khoản hằng tháng.'
    if 'another tab' in lower or 'changed while' in lower:
        return 'Kế hoạch đã thay đổi. Hãy tải lại trang trước khi điều chỉnh.'
    if message and all(ord(c) < 128 for c in message):
        return 'Thông tin ngân sách chưa hợp lệ. Vui lòng kiểm tra các số tiền và thử lại.'
    return message


def _preview_suggestions(user_id, month_id, keys, values):
    """Preflight all input before saving any new suggested expense."""
    existing = services.list_expenses(user_id, month_id)
    seen = {e.expense_name.strip().casefold() for e in existing}
    candidates = [ExpenseInput(e.id, e.expense_name, e.priority,
                               e.estimated_amount, e.minimum_amount) for e in existing]
    known = {item.key: item for item in SUGGESTED_EXPENSES}
    if len(keys) != len(set(keys)) or any(key not in known for key in keys):
        raise BudgetError("Các khoản đã chọn không hợp lệ. Vui lòng tải lại trang.")
    for key in keys:
        item = known[key]
        if item.name.casefold() in seen:
            continue
        fields = values[key]
        estimate = money(fields.get('estimated_amount'), 'Số tiền dự kiến', optional=True)
        minimum = money(fields.get('minimum_amount'), 'Số tiền tối thiểu', optional=True, positive=True)
        frequency = fields.get('allocation_frequency')
        if frequency not in ('DAILY', 'WEEKLY', 'MONTHLY'):
            raise BudgetError(f'Chu kỳ phân bổ của {item.name} không hợp lệ.')
        if minimum is not None and item.priority != 'P1':
            raise BudgetError('Chỉ khoản thiết yếu mới có mức tối thiểu.')
        due = fields.get('due_day')
        if due not in (None,''):
            day = money(due, 'Ngày đến hạn', positive=True)
            if day > 31 or frequency != 'MONTHLY':
                raise BudgetError('Ngày đến hạn phải từ 1 đến 31 và chỉ dành cho khoản hằng tháng.')
        if item.priority == 'P0' and (estimate is None or estimate == 0):
            raise BudgetError('Hãy nhập số tiền lớn hơn 0 cho ' + {'rent':'tiền thuê trọ','electricity':'tiền điện','water':'tiền nước','internet':'Internet'}.get(key, item.name) + '.')
        candidates.append(ExpenseInput(uuid4(), item.name, item.priority, estimate, minimum))
        seen.add(item.name.casefold())
    month = services.get_month(user_id, month_id)
    validate_setup(month.available_vnd, candidates)


@bp.post("/budget/<uuid:month_id>/plans/generate")
@login_required
def generate(month_id):
    _require_action()
    user_id = g.current_user.id
    chosen = request.form.getlist("suggestion")
    fields = {
        item.key: {
            "estimated_amount": request.form.get(f"{item.key}_estimated_amount"),
            "minimum_amount": request.form.get(f"{item.key}_minimum_amount"),
            "allocation_frequency": request.form.get(f"{item.key}_allocation_frequency", item.frequency),
            "due_day": request.form.get(f"{item.key}_due_day"),
        }
        for item in SUGGESTED_EXPENSES
    }
    try:
        draft_rows = _submitted_custom_rows()
        # Never persist any expense until every row and the generated plans
        # have passed validation; the service owns the single transaction.
        custom_expenses = [{
            "expense_name": row["expense_name"],
            "priority": row["priority"],
            "estimated_amount": row["estimated_amount"],
            "minimum_amount": row["minimum_amount"],
            "allocation_frequency": row["allocation_frequency"],
            "due_day": row["due_day"],
            "is_recurring": row["is_recurring"],
        } for row in draft_rows]
        plans, source, explanations = services.generate_budget_plans_from_setup(
            user_id, month_id, chosen, fields, custom_expenses,
            use_ai=request.form.get("budget_ai_weights") == "1",
        )
    except BudgetError as exc:
        return _workspace(services.get_month(user_id, month_id),
                          form_error=_friendly_budget_error(exc),
                          submitted_values=request.form.to_dict(flat=True)), 400
    session["budget_plan_explanations"] = {"month_id": str(month_id), "explanations": explanations}
    flash("Đã tạo ba phương án. Hãy xem và chọn kế hoạch phù hợp.", "success")
    if request.form.get("budget_ai_weights") == "1":
        flash("Gemini đã hỗ trợ gợi ý phân bổ." if source == "Gemini" else
              "Chưa dùng được Gemini. Kế hoạch đã được tạo theo quy tắc an toàn.", "info")
    return redirect(url_for("budgets.month", month_id=month_id, _anchor="compare"))

@bp.get("/budget/<uuid:month_id>/plans/<uuid:plan_id>")
@login_required
def plan(month_id, plan_id):
    saved_plan = services.get_plan(g.current_user.id, month_id, plan_id)
    schedule_state = None
    if saved_plan.status == "CONFIRMED":
        # KAN-23 owns schedule creation. Budget only shows the correct next step.
        from app.modules.expenses.services import get_schedule_state
        schedule_state = get_schedule_state(g.current_user.id, month_id)
    return render_template(
        "budgets/plan.html", plan=saved_plan, month=saved_plan.budget_month,
        action_form=BudgetActionForm(),
        breakdown=services.plan_breakdown(g.current_user.id, month_id, plan_id),
        schedule_state=schedule_state,
        confirm_snapshot=services.plan_draft_fingerprint(saved_plan) if saved_plan.status == "GENERATED" else None,
        bp=budget_copy(getattr(g, "ui_locale", "vi")),
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
    display = {"month": month, "plan": candidate, "action_form": BudgetActionForm(),
               "bp": budget_copy(getattr(g, "ui_locale", "vi")), "submitted_values": {},
               "validation_error": None,
               "plan_snapshot": services.customization_fingerprint(g.current_user.id, month.id, candidate.id)}
    if request.method == "GET":
        return render_template("budgets/customize.html", **display)
    _require_action()
    editable = {str(a.budget_expense_id) for a in candidate.allocations
                if a.budget_expense.priority in ("P1", "P2")}
    expected_fields = {"allocation_" + expense_id for expense_id in editable}
    posted_fields = {key for key in request.form if key.startswith("allocation_")}
    if (posted_fields != expected_fields or
            any(len(request.form.getlist(field)) != 1 for field in expected_fields) or
            len(request.form.getlist("plan_snapshot")) != 1):
        display["validation_error"] = "Hãy nhập số tiền hợp lệ cho từng khoản sinh hoạt."
        display["submitted_values"] = request.form.to_dict(flat=True)
        return render_template("budgets/customize.html", **display), 400
    values = {expense_id: request.form.get("allocation_" + expense_id)
              for expense_id in editable}
    try:
        customized = services.save_manual_plan(
            g.current_user.id, month_id, plan_id, values,
            expected_fingerprint=request.form.get("plan_snapshot"), auto_savings=True,
        )
    except BudgetError as exc:
        display["validation_error"] = _friendly_budget_error(exc)
        display["submitted_values"] = request.form.to_dict(flat=True)
        if isinstance(exc, services.BudgetConflict):
            # Keep the submitted stale token so retrying an old form cannot
            # silently overwrite a newer draft. A fresh GET is required.
            display["plan_snapshot"] = request.form.get("plan_snapshot", "")
        return render_template("budgets/customize.html", **display), (409 if isinstance(exc, services.BudgetConflict) else 400)
    flash("Đã lưu điều chỉnh. Hãy xem lại trước khi xác nhận.", "success")
    return redirect(url_for("budgets.plan", month_id=month.id, plan_id=customized.id))


@bp.post("/budget/<uuid:month_id>/ai/priority")
@login_required
def priority_suggestion(month_id):
    _require_action()
    services.get_month(g.current_user.id, month_id)
    if any(p.status == "CONFIRMED" for p in services.list_plans(g.current_user.id, month_id)):
        return jsonify(error="Kế hoạch đã được xác nhận, không thể đổi mức ưu tiên."), 409
    name = request.form.get("expense_name", "")
    if not name.strip() or len(name) > 120:
        return jsonify(error="Hãy nhập tên khoản chi (tối đa 120 ký tự)."), 400
    try:
        return jsonify(suggest_priority(name))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/budget/<uuid:month_id>/plans/<uuid:plan_id>/confirm")
@login_required
def confirm(month_id, plan_id):
    """Persist the selected generated/MANUAL plan; scheduling is KAN-23's POST.

    Build 1 explicitly separated these transactions. A successful confirmation
    remains immutable even if scheduling cannot be completed immediately.
    Expense Planning reads ONLY the saved CONFIRMED allocations, and its
    idempotent POST creates/verifies tasks without overwriting check-ins.
    """
    _require_action()
    try:
        selected = services.get_plan(g.current_user.id, month_id, plan_id)
        if selected.status == "GENERATED" and selected.plan_type == "MANUAL":
            snapshots = request.form.getlist("confirm_snapshot")
            if len(snapshots) != 1 or not snapshots[0]:
                raise services.BudgetConflict("The manual plan changed in another tab. Review it before confirming.")
            snapshot = snapshots[0]
        else:
            snapshot = None
        services.confirm_plan(g.current_user.id, month_id, plan_id,
                              expected_fingerprint=snapshot)
    except BudgetError as exc:
        plan = services.get_plan(g.current_user.id, month_id, plan_id)
        return render_template(
            "budgets/plan.html", plan=plan, month=plan.budget_month,
            action_form=BudgetActionForm(),
            confirm_snapshot=services.plan_draft_fingerprint(plan) if plan.status == "GENERATED" else None,
            breakdown=services.plan_breakdown(g.current_user.id, month_id, plan_id),
            error_message=_friendly_budget_error(exc),
        ), 409 if isinstance(exc, services.BudgetConflict) else 400
    flash("Kế hoạch đã được xác nhận. Bước tiếp theo: tạo lịch chi tiêu.", "success")
    return redirect(url_for("budgets.plan", month_id=month_id, plan_id=plan_id))


@bp.get("/budget/<uuid:month_id>/schedule")
@login_required
def schedule(month_id):
    """Budget's read-only day/week/month planning view over canonical KAN-23 tasks.

    No duplicate schedule generator or new tables. Assigned task limits are
    counted once, on their assignment day; active periods are informational.
    """
    from app.modules.expenses import services as expense_services
    from app.modules.expenses.presentation import today_vn

    month = services.get_month(g.current_user.id, month_id)
    confirmed = next((p for p in services.list_plans(g.current_user.id, month.id)
                      if p.status == "CONFIRMED"), None)
    if confirmed is None:
        flash("Hãy xác nhận một kế hoạch trước khi xem lịch phân bổ.", "warning")
        return redirect(url_for("budgets.month", month_id=month.id))

    view = request.args.get("view", "day")
    if view not in {"day", "week", "month"}:
        view = "day"
    first = month.tracking_start_date
    last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    today = today_vn()
    default = today if first <= today <= last else first
    try:
        anchor = date.fromisoformat(request.args.get("date", "")) if request.args.get("date") else default
    except ValueError:
        anchor = default
    if not first <= anchor <= last:
        anchor = default
    if view == "week":
        start = max(first, anchor - timedelta(days=anchor.weekday()))
        end = min(last, anchor + timedelta(days=6-anchor.weekday()))
    elif view == "month":
        start, end = first, last
    else:
        start = end = anchor
    state = expense_services.get_schedule_state(g.current_user.id, month.id)
    tasks = expense_services.list_tasks(g.current_user.id, month.tracking_start_date, last) if state.code == "READY" else []
    assigned = [task for task in tasks if start <= task.assigned_date <= end]
    continuing = [task for task in tasks if task.assigned_date < start <= task.period_end or
                  (task.payment_due_date is not None and start <= task.payment_due_date <= end
                   and task.assigned_date < start)] if view != "month" else []
    # Budget Planning's initial schedule is an immutable allocation snapshot.
    # Current limits/check-in statuses belong to Expense Planning and may later
    # change; they must not alter the initial plan displayed on this page.
    total = sum(task.original_limit for task in assigned)
    from app.modules.budgets.rules import meal_breakdown
    initial_meals = {task.id: meal_breakdown(task.original_limit)
                     for task in assigned
                     if task.title.strip().casefold() == "food" and task.schedule_tag == "DAILY"}
    step = timedelta(days=7 if view == "week" else 1)
    prev_day, next_day = anchor - step, anchor + step
    return render_template("budgets/schedule.html", month=month, plan=confirmed,
                           view=view, anchor=anchor, start=start, end=end, last=last,
                           assigned=assigned, continuing=continuing, total=total,
                           initial_meals=initial_meals,
                           prev_day=prev_day if first <= prev_day <= last else None,
                           next_day=next_day if first <= next_day <= last else None,
                           state=state, month_total=sum(a.allocated_amount for a in confirmed.allocations),
                           allocations=confirmed.allocations)


@bp.errorhandler(services.BudgetNotFound)
def not_found(error):
    return "Budget resource not found.", 404


@bp.errorhandler(BudgetError)
def invalid_budget(error):
    return render_template("budgets/error.html", message=str(error)), 409 if isinstance(error, services.BudgetConflict) else 400
