"""HTTP entry points for Expense Planning & Smart Check-in."""

import calendar
from datetime import date, timedelta, timezone
from uuid import uuid4

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.modules.expenses import duplicates, services
from app.modules.accounts.auth import login_required
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets.rules import BudgetError
from app.modules.expenses.services import (
    NotFoundError,
    STATUS_NO_EXPENSE,
    STATUS_OVER_BUDGET,
    STATUS_PENDING,
    STATUS_UNRECORDED,
    STATUS_WITHIN_BUDGET,
)
from app.modules.expenses.validators import (
    SCHEDULE_TAGS,
    ValidationError,
    parse_optional_date,
)

bp = Blueprint("expenses", __name__)

VN_TZ = timezone(timedelta(hours=7))

VIEW_LABELS = {
    "day": "Ngày",
    "month": "Tháng",
    "year": "Năm",
}
WEEKDAY_LABELS = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ nhật",
)

STATUS_LABELS = {
    STATUS_PENDING: "Chưa xác nhận",
    STATUS_UNRECORDED: "Chưa ghi nhận (quá hạn)",
    STATUS_NO_EXPENSE: "Không phát sinh",
    STATUS_WITHIN_BUDGET: "Trong kế hoạch",
    STATUS_OVER_BUDGET: "Vượt kế hoạch",
}

STATUS_CLASSES = {
    STATUS_PENDING: "secondary",
    STATUS_UNRECORDED: "danger",
    STATUS_NO_EXPENSE: "secondary",
    STATUS_WITHIN_BUDGET: "success",
    STATUS_OVER_BUDGET: "danger",
}

PRIORITY_LABELS = {"P0": "P0 — bắt buộc", "P1": "P1 — thiết yếu", "P2": "P2 — linh hoạt"}

SCHEDULE_LABELS = {
    "DAILY": "Hằng ngày",
    "WEEKLY": "Hằng tuần",
    "MONTHLY": "Cuối mỗi tháng",
    "DAY_OF_MONTH": "Ngày cố định trong tháng",
}


@bp.app_template_filter("vnd")
def format_vnd(value) -> str:
    if type(value) is not int:
        return "—"
    return f"{value:,}".replace(",", ".") + " ₫"


@bp.app_template_filter("date_vn")
def format_date(value) -> str:
    if not value:
        return "-"
    return value.strftime("%d/%m/%Y")


@bp.app_template_filter("weekday_vn")
def weekday_vn(value) -> str:
    if not value:
        return ""
    return WEEKDAY_LABELS[value.weekday()]


@bp.app_template_filter("datetime_vn")
def format_datetime(value) -> str:
    """Convert a naive UTC timestamp to Vietnam time for display."""
    if not value:
        return "—"
    utc_value = value.replace(tzinfo=timezone.utc)
    return utc_value.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M")


@bp.app_template_filter("difference")
def difference(planned, actual):
    """Return ``planned - actual`` for display, or None when data is missing."""
    if planned is None or actual is None:
        return None
    return int(planned) - int(actual)


@bp.app_template_filter("status_label")
def status_label(value) -> str:
    if isinstance(value, (services.AssignedExpenseTask, services.ExpenseTaskAdapter)):
        value = services.get_task_status(value)
    elif hasattr(value, "display_status"):
        value = value.display_status
    return STATUS_LABELS.get(value, str(value))


@bp.app_template_filter("status_class")
def status_class(value) -> str:
    if isinstance(value, (services.AssignedExpenseTask, services.ExpenseTaskAdapter)):
        value = services.get_task_status(value)
    elif hasattr(value, "display_status"):
        value = value.display_status
    return STATUS_CLASSES.get(value, "secondary")


@bp.app_template_filter("priority_label")
def priority_label(value) -> str:
    return PRIORITY_LABELS.get(value, value)


@bp.app_template_filter("schedule_label")
def schedule_label(value) -> str:
    return SCHEDULE_LABELS.get(value, value)


def _user_id() -> str:
    return services.resolve_current_user_id()


def _back_url(fields=None):
    """Redirect back to the current view/date after a POST (POST-Redirect-GET)."""
    source, fallback = (request.form, request.args) if fields is None else (fields, {})
    if (source.get("page") or fallback.get("page")) == "history":
        return redirect(url_for("expenses.history", **{
            key: source.get(key) or fallback.get(key) for key in ("start", "end")
            if source.get(key) or fallback.get(key)
        }))
    view = source.get("view") or fallback.get("view") or "day"
    raw_date = source.get("date") or fallback.get("date")
    values = {"view": view}
    if raw_date:
        values["date"] = raw_date
    tag = source.get("tag") or fallback.get("tag")
    if tag:
        values["tag"] = tag
    return redirect(url_for("expenses.index", **values))


def _back_fields():
    return {name: value[:64] for name in ("page", "start", "end", "view", "date", "tag")
            if (value := request.form.get(name))}


def _prompt_duplicate(user_id, *, flow, target, action=None):
    token = request.form.get(duplicates.TOKEN_FIELD)
    if not token:
        return None  # Preserve the legacy idempotency_key API's silent safe retry.
    if flow == "checkin":
        task = services.get_task(user_id, target)
        month_id = task.raw_task.allocation.plan.budget_month_id
    else:
        month_id = target
    record = services.get_submission(user_id, month_id, token)
    if record is None:
        return None
    if ((flow == "checkin" and str(record.raw_record.task_id) != str(target)) or
            (flow == "unexpected" and record.record_type != "UNEXPECTED")):
        raise services.ExpenseConflict("This retry token belongs to a different transaction.")
    pending_id = duplicates.add_pending(
        flow=flow, target=target, action=action, back=_back_fields(),
        record_id=record.id, user_id=user_id,
    )
    return redirect(url_for("expenses.duplicate_submission", pending_id=pending_id))


@bp.get("/expenses/duplicates/<pending_id>")
@login_required
def duplicate_submission(pending_id):
    pending = duplicates.peek_pending(pending_id)
    if pending is None or pending["user_id"] != str(_user_id()):
        flash("This duplicate confirmation is no longer available.", "warning")
        return redirect(url_for("expenses.index"))
    return render_template(
        "pages/duplicate_submission.html", pending_id=pending_id,
        record=services.get_record(_user_id(), pending["record_id"]),
        token=duplicates.confirmation_token(pending_id, _user_id()),
        can_duplicate=pending["flow"] == "unexpected" or pending["action"] == "actual",
    )


@bp.post("/expenses/duplicates/<pending_id>/confirm")
@login_required
def confirm_duplicate(pending_id):
    user_id = _user_id()
    pending = duplicates.peek_pending(pending_id)
    if pending is None or pending["user_id"] != str(user_id):
        flash("This duplicate confirmation was already used or has expired. Nothing was saved again.", "warning")
        return _back_url()
    record = services.get_record(user_id, pending["record_id"])
    key = duplicates.confirmation_token(pending_id, user_id)
    if pending["flow"] == "checkin":
        if pending["action"] != "actual":
            raise ValidationError("A planned check-in can only be recorded once per task.")
        services.checkin_task(
            user_id, pending["target"], action="actual", amount_raw=record.amount,
            expense_date_raw=record.expense_date.isoformat(), category=str(record.category_id),
            note=record.note, title=record.title, idempotency_key=key,
        )
    else:
        services.create_unexpected_record(user_id, dict(
            budget_month_id=pending["target"], title=record.title, amount=record.amount,
            expense_date=record.expense_date.isoformat(), category=str(record.category_id),
            priority=record.priority, budget_impact_scope=record.budget_impact_scope,
            note=record.note, idempotency_key=key,
        ))
    duplicates.take_pending(pending_id)
    flash("A second identical transaction was saved.", "success")
    return _back_url(pending["back"])


@bp.post("/expenses/duplicates/<pending_id>/dismiss")
@login_required
def dismiss_duplicate(pending_id):
    pending = duplicates.peek_pending(pending_id)
    if pending is None or pending["user_id"] != str(_user_id()):
        return _back_url()
    duplicates.take_pending(pending_id)
    flash("Only the first transaction was kept. Nothing else was saved.", "info")
    return _back_url(pending["back"])


def _flash_error(exc: Exception) -> None:
    if hasattr(exc, "messages") and isinstance(exc.messages, (list, tuple)):
        for message in exc.messages:
            flash(message, "danger")
    else:
        flash(str(exc), "danger")


def _month_picker_date(raw_month: str, raw_date: str | None) -> str:
    """Keep the current day when possible, clamping to the picked month."""
    base = parse_optional_date(raw_date, "Ngày xem") or services.today_vn()
    try:
        year_text, month_text = raw_month.split("-", 1)
        year, month = int(year_text), int(month_text)
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(base.day, last_day)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValidationError("Tháng không hợp lệ.") from exc


def _year_picker_date(raw_year: str, raw_date: str | None) -> str:
    """Keep the current month/day when possible, clamping for leap-year changes."""
    base = parse_optional_date(raw_date, "Ngày xem") or services.today_vn()
    try:
        year = int(raw_year)
        last_day = calendar.monthrange(year, base.month)[1]
        return date(year, base.month, min(base.day, last_day)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValidationError("Năm không hợp lệ.") from exc


@bp.get("/expenses")
@login_required
def index():
    user_id = _user_id()
    raw_view = (request.args.get("view") or "day").lower()
    if raw_view not in services.UI_VIEWS:
        raw_view = "day"
    raw_tag = (request.args.get("tag") or "").upper()
    if raw_tag not in ("", *SCHEDULE_TAGS):
        raw_tag = ""

    raw_date = request.args.get("date")
    raw_month = request.args.get("month")
    raw_year = request.args.get("year")
    explicit_month_id = request.args.get("budget_month_id")
    month_id = explicit_month_id or session.get("active_budget_month_id")
    if month_id:
        active_month = services.get_month(user_id, month_id)
        if explicit_month_id:
            # An explicit owned month selection wins over stale navigation
            # fields. Date-only navigation can still leave the session month.
            selected_date = parse_optional_date(raw_date)
            if not selected_date or selected_date.replace(day=1) != active_month.month_start:
                raw_date = active_month.tracking_start_date.isoformat()
            raw_month = raw_year = None
        elif not (raw_date or raw_month or raw_year):
            today = services.today_vn()
            raw_date = (today if today.replace(day=1) == active_month.month_start else active_month.tracking_start_date).isoformat()

    try:
        if raw_view == "month" and raw_month:
            raw_date = _month_picker_date(raw_month, raw_date)
        elif raw_view == "year" and raw_year:
            raw_date = _year_picker_date(raw_year, raw_date)
        period = services.resolve_period(raw_view, raw_date)
    except ValidationError as exc:
        _flash_error(exc)
        period = services.resolve_period("day", None)

    services.refresh_unrecorded(user_id)
    schedule_filter = raw_tag if period.view == "year" else ""
    summary = services.build_summary(
        user_id,
        period,
        schedule_tag=schedule_filter or None,
    )

    calendar_weeks = []
    day_items = []
    month_items = []
    month_cards = []
    month_summary = None

    if period.view in ("day", "month"):
        month_period = services.resolve_period("month", period.anchor.isoformat())
        month_summary = services.build_summary(user_id, month_period)
        calendar_weeks = services.build_month_calendar(
            month_summary["tasks"],
            month_summary["records"],
            period.anchor.year,
            period.anchor.month,
        )
        if period.view == "month":
            summary = month_summary
            period = month_period
            month_items = services.build_month_items(month_summary)
        else:
            day_items = services.build_day_items(summary, period.anchor, covering_tasks=month_summary["tasks"])
    else:
        month_cards = services.build_year_months(
            summary,
            period.anchor.year,
            schedule_tag=schedule_filter or None,
        )

    day_totals = services.summarize_day_items(day_items)
    visible_items = day_items or month_items
    planned_by_task = summary["planned_by_task"]
    if visible_items and isinstance(planned_by_task, dict):
        planned_by_task.update(
            services.planned_records_for_tasks(
                user_id,
                [entry.task.task_id for entry in visible_items]
            )
        )

    navigation = services.build_navigation(period)
    plan_items = []

    modal_records = []
    if period.view != "year":
        seen_record_ids = set()
        linked = [record for spending in planned_by_task.values() for record in spending.records]
        for record in list(summary["records"]) + linked:
            if record.record_id not in seen_record_ids:
                modal_records.append(record)
                seen_record_ids.add(record.record_id)

    selected_month = services.find_month(user_id, period.anchor)
    schedule_state = services.get_schedule_state(user_id, selected_month.id) if selected_month else None
    return render_template(
        "pages/expenses.html",
        summary=summary,
        period=period,
        plan_items=plan_items,
        today=services.today_vn(),
        unexpected_token=uuid4().hex,
        checkin_tokens={entry.task.task_id: uuid4().hex for entry in day_items},
        selected_month=selected_month,
        budget_months=list_budget_months(user_id),
        schedule_state=schedule_state,
        can_schedule=bool(schedule_state and schedule_state.can_schedule),
        calendar=calendar_weeks,
        day_items=day_items,
        day_totals=day_totals,
        month_items=month_items,
        month_cards=month_cards,
        navigation=navigation,
        modal_records=modal_records,
        categories=services.list_categories(_user_id()),
        mode_label=VIEW_LABELS.get(period.view, "Ngày"),
        selected_day_label=(
            f"{WEEKDAY_LABELS[period.anchor.weekday()]}, "
            f"{period.anchor:%d/%m/%Y}"
        ),
        month_title=f"Tháng {period.anchor.month}/{period.anchor.year}",
        tag=schedule_filter,
        tag_label=SCHEDULE_LABELS.get(schedule_filter, "Tất cả"),
        schedule_labels=SCHEDULE_LABELS,
        priority_labels=PRIORITY_LABELS,
        weekday_labels=WEEKDAY_LABELS,
    )


@bp.get("/expenses/history")
@login_required
def history():
    user_id = _user_id()
    today = services.today_vn()
    try:
        start = parse_optional_date(request.args.get("start"), "Từ ngày") or today.replace(day=1)
        end = parse_optional_date(request.args.get("end"), "Đến ngày") or today
    except ValidationError as exc:
        _flash_error(exc)
        start = today.replace(day=1)
        end = today
    if end < start:
        start, end = end, start

    services.refresh_unrecorded(user_id)
    period = services.Period(
        view="custom",
        anchor=end,
        start=start,
        end=end,
        label=f"{start:%d/%m/%Y} - {end:%d/%m/%Y}",
    )
    summary = services.build_summary(user_id, period)
    return render_template(
        "pages/expense_history.html",
        summary=summary,
        records=summary["records"],
        start=start,
        end=end,
        total=summary["actual_total"],
        selected_month=services.find_month(user_id, end),
        categories=services.list_categories(user_id), priority_labels=PRIORITY_LABELS,
    )


@bp.post("/expenses/tasks/<uuid:task_id>/checkin")
@login_required
def checkin(task_id: str):
    action = request.form.get("action", "")
    if action not in {"actual", "planned", "no_expense"}:
        raise ValidationError("Choose planned, actual or no_expense.")
    if action != "no_expense":
        prompt = _prompt_duplicate(_user_id(), flow="checkin", target=task_id, action=action)
        if prompt is not None:
            return prompt
    services.checkin_task(
        _user_id(), task_id, action=action,
        amount_raw=request.form.get("amount"), expense_date_raw=request.form.get("expense_date"),
        category=request.form.get("category"), note=request.form.get("note"),
        title=request.form.get("title"),
        idempotency_key=request.form.get("submission_token") or request.form.get("idempotency_key"),
    )
    flash("Đã ghi nhận check-in.", "success")
    return _back_url()


@bp.post("/expenses/tasks/<uuid:task_id>/payment-status")
@login_required
def set_payment_status(task_id: str):
    services.set_payment_status(_user_id(), task_id, request.form.get("payment_status"))
    flash("Đã cập nhật trạng thái thanh toán tự ghi nhận.", "success")
    return _back_url()


@bp.post("/expenses/records")
@login_required
def create_record():
    prompt = _prompt_duplicate(_user_id(), flow="unexpected", target=request.form.get("budget_month_id"))
    if prompt is not None:
        return prompt
    form = request.form.to_dict()
    form["idempotency_key"] = form.get("submission_token") or form.get("idempotency_key")
    services.create_unexpected_record(_user_id(), form)
    flash("Đã ghi nhận khoản chi bất ngờ.", "success")
    return _back_url()


@bp.post("/expenses/records/<uuid:record_id>/edit")
@login_required
def edit_record(record_id: str):
    services.update_record(_user_id(), record_id, request.form)
    flash("Đã cập nhật giao dịch.", "success")
    return _back_url()


@bp.post("/expenses/records/<uuid:record_id>/delete")
@login_required
def delete_record(record_id: str):
    services.delete_record(_user_id(), record_id)
    flash("Đã xóa giao dịch.", "success")
    return _back_url()


@bp.post("/expenses/months/<uuid:month_id>/schedule")
@login_required
def schedule(month_id):
    month = services.get_month(_user_id(), month_id)
    services.ensure_tasks_for_month(_user_id(), month.id)
    flash("Spending schedule saved. Repeating this action preserves existing tasks and check-ins.", "success")
    return redirect(url_for("expenses.index", budget_month_id=month.id, view="month", date=month.tracking_start_date.isoformat()))


@bp.errorhandler(NotFoundError)
def not_found(error):
    return "Expense resource not found.", 404


@bp.errorhandler(ValidationError)
@bp.errorhandler(BudgetError)
def invalid_expense(error):
    return render_template("expenses/error.html", message=str(error)), 409 if isinstance(error, services.ExpenseConflict) else 400
