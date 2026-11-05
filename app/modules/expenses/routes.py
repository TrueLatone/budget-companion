"""HTTP entry points for Expense Planning & Smart Check-in."""

import calendar
from datetime import date, timedelta, timezone

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
from app.modules.expenses.validators import ValidationError, parse_optional_date

bp = Blueprint("expenses", __name__)

VN_TZ = timezone(timedelta(hours=7))

VIEW_LABELS = {
    "day": "Day",
    "month": "Month",
    "year": "Year",
}
WEEKDAY_LABELS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

STATUS_LABELS = {
    STATUS_PENDING: "Pending",
    STATUS_UNRECORDED: "Unrecorded (overdue)",
    STATUS_NO_EXPENSE: "No expense",
    STATUS_WITHIN_BUDGET: "Within budget",
    STATUS_OVER_BUDGET: "Over budget",
}

STATUS_CLASSES = {
    STATUS_PENDING: "secondary",
    STATUS_UNRECORDED: "danger",
    STATUS_NO_EXPENSE: "secondary",
    STATUS_WITHIN_BUDGET: "success",
    STATUS_OVER_BUDGET: "danger",
}

PRIORITY_LABELS = {"P0": "P0 — required", "P1": "P1 — essential", "P2": "P2 — flexible"}


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


def _user_id() -> str:
    return services.resolve_current_user_id()


def _back_url(fields=None):
    """Redirect back to the current view after a POST (POST-Redirect-GET).

    ``fields`` replays the hidden navigation fields of an earlier submission
    (used by the duplicate-confirmation flow); by default the current form and
    query string are read instead.
    """
    source, fallback = (request.form, request.args) if fields is None else (fields, {})
    page = source.get("page") or fallback.get("page")
    if page == "history":
        values = {}
        start = source.get("start") or fallback.get("start")
        end = source.get("end") or fallback.get("end")
        if start:
            values["start"] = start
        if end:
            values["end"] = end
        return redirect(url_for("expenses.history", **values))
    view = source.get("view") or fallback.get("view") or "day"
    if view not in services.UI_VIEWS:
        view = "day"
    raw_date = source.get("date") or fallback.get("date")
    values = {"view": view}
    if raw_date:
        values["date"] = raw_date
    month_id = source.get("budget_month_id") or fallback.get("budget_month_id")
    if month_id:
        values["budget_month_id"] = month_id
    return redirect(url_for("expenses.index", **values))


_BACK_FIELDS = ("page", "start", "end", "view", "date", "budget_month_id")


def _back_fields():
    """Capture the navigation fields of the current submission for a replay."""
    return {name: value for name in _BACK_FIELDS if (value := request.form.get(name))}


CHECKIN_FORM_FIELDS = {
    "action": "action",
    "amount_raw": "amount",
    "expense_date_raw": "expense_date",
    "category": "category",
    "note": "note",
    "title": "title",
}
UNEXPECTED_FORM_FIELDS = (
    "budget_month_id", "title", "amount", "expense_date", "category",
    "priority", "budget_impact_scope", "note",
)


def _checkin_kwargs(form):
    return {key: form.get(name) for key, name in CHECKIN_FORM_FIELDS.items()}


def _submit_checkin(user_id, task_id, kwargs, token):
    def remember(record_id):
        duplicates.remember(token, record_id, flow="checkin", target=str(task_id), user_id=str(user_id))

    services.checkin_task(user_id, task_id, **kwargs, on_created=remember)


def _submit_unexpected(user_id, form, token):
    def remember(record_id):
        duplicates.remember(token, record_id, flow="unexpected",
                            target=str(form.get("budget_month_id")), user_id=str(user_id))

    services.create_unexpected_record(user_id, form, on_created=remember)


def _replayed(user_id, *, flow, target, token):
    """Return the committed write for a reused token of this flow and target."""
    entry = duplicates.remembered(token)
    if (
        entry is None
        or entry.get("flow") != flow
        or entry.get("target") != str(target)
        or entry.get("user_id") != str(user_id)
    ):
        return None
    return entry


def _prompt_duplicate(user_id, *, flow, target, payload, back, record_id):
    pending_id = duplicates.add_pending(
        flow=flow, target=target, payload=payload, back=back,
        record_id=record_id, user_id=user_id,
    )
    return redirect(url_for("expenses.duplicate_submission", pending_id=pending_id))


@bp.app_template_global("new_submission_token")
def new_submission_token():
    return duplicates.new_token()



def _flash_error(exc: Exception) -> None:
    if hasattr(exc, "messages") and isinstance(exc.messages, (list, tuple)):
        for message in exc.messages:
            flash(message, "danger")
    else:
        flash(str(exc), "danger")


def _month_picker_date(raw_month: str, raw_date: str | None) -> str:
    """Keep the current day when possible, clamping to the picked month."""
    base = parse_optional_date(raw_date, "View date") or services.today_vn()
    try:
        year_text, month_text = raw_month.split("-", 1)
        year, month = int(year_text), int(month_text)
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(base.day, last_day)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid month.") from exc


def _year_picker_date(raw_year: str, raw_date: str | None) -> str:
    """Keep the current month/day when possible, clamping for leap-year changes."""
    base = parse_optional_date(raw_date, "View date") or services.today_vn()
    try:
        year = int(raw_year)
        last_day = calendar.monthrange(year, base.month)[1]
        return date(year, base.month, min(base.day, last_day)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid year.") from exc


@bp.get("/expenses")
@login_required
def index():
    user_id = _user_id()
    raw_view = (request.args.get("view") or "day").lower()
    if raw_view not in services.UI_VIEWS:
        raw_view = "day"

    raw_date = request.args.get("date")
    raw_month = request.args.get("month")
    raw_year = request.args.get("year")
    explicit_month_id = request.args.get("budget_month_id")
    month_id = explicit_month_id or session.get("active_budget_month_id")
    if month_id:
        active_month = services.get_month(user_id, month_id)
        if explicit_month_id:
            # An explicit owned month selection becomes the session month so
            # subsequent check-ins and transactions stay in the same month.
            session["active_budget_month_id"] = str(active_month.id)
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
    summary = services.build_summary(user_id, period)

    calendar_weeks = []
    day_items = []
    due_items = []
    month_items = []
    month_due_items = []
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
            month_due_items = services.build_due_items(month_summary)
        else:
            day_items = services.build_day_items(summary, period.anchor)
            due_items = services.build_due_items(summary, period.anchor)
    else:
        month_cards = services.build_year_months(summary, period.anchor.year)

    day_totals = services.summarize_day_items(day_items, due_items)
    visible_items = day_items or due_items or month_items
    planned_by_task = dict(summary["planned_by_task"])
    if visible_items:
        planned_by_task.update(
            services.planned_records_for_tasks(
                user_id,
                [entry.task.task_id for entry in visible_items]
            )
        )

    navigation = services.build_navigation(period)
    selected_month = services.find_month(user_id, period.anchor)
    if selected_month is None and month_summary is not None:
        selected_month = services.find_month(user_id, month_summary["period"].anchor)
    schedule_state = services.get_schedule_state(user_id, selected_month.id) if selected_month else None

    modal_records = []
    if period.view != "year":
        seen_record_ids = set()
        linked = [record for spending in planned_by_task.values() for record in spending.records]
        for record in list(summary["records"]) + linked:
            if record.record_id not in seen_record_ids:
                modal_records.append(record)
                seen_record_ids.add(record.record_id)

    modal_tasks = list(day_items) + list(due_items)
    return render_template(
        "pages/expenses.html",
        summary=summary,
        period=period,
        today=services.today_vn(),
        selected_month=selected_month,
        budget_months=list_budget_months(user_id),
        schedule_state=schedule_state,
        calendar=calendar_weeks,
        day_items=day_items,
        due_items=due_items,
        day_totals=day_totals,
        month_items=month_items,
        month_due_items=month_due_items,
        month_cards=month_cards,
        navigation=navigation,
        modal_records=modal_records,
        modal_tasks=modal_tasks,
        categories=services.list_categories(user_id),
        mode_label=VIEW_LABELS.get(period.view, "Day"),
        selected_day_label=(
            f"{WEEKDAY_LABELS[period.anchor.weekday()]}, "
            f"{period.anchor:%d/%m/%Y}"
        ),
        month_title=f"Month {period.anchor.month:02d}/{period.anchor.year}",
        priority_labels=PRIORITY_LABELS,
        weekday_labels=WEEKDAY_LABELS,
    )


@bp.get("/expenses/history")
@login_required
def history():
    user_id = _user_id()
    today = services.today_vn()
    try:
        start = parse_optional_date(request.args.get("start"), "Start date") or today.replace(day=1)
        end = parse_optional_date(request.args.get("end"), "End date") or today
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
        categories=services.list_categories(user_id),
        priority_labels=PRIORITY_LABELS,
    )


@bp.post("/expenses/tasks/<uuid:task_id>/checkin")
@login_required
def checkin(task_id: str):
    user_id = _user_id()
    token = request.form.get(duplicates.TOKEN_FIELD)
    kwargs = _checkin_kwargs(request.form)
    if kwargs["action"] != "no_expense":
        entry = _replayed(user_id, flow="checkin", target=task_id, token=token)
        if entry is not None:
            try:
                services.get_record(user_id, entry["record_id"])
            except NotFoundError:
                # The first transaction was deleted; this submission is no longer a duplicate.
                duplicates.forget(token)
            else:
                return _prompt_duplicate(
                    user_id, flow="checkin", target=task_id,
                    payload={"kwargs": kwargs}, back=_back_fields(),
                    record_id=entry["record_id"],
                )
    _submit_checkin(user_id, task_id, kwargs, token)
    flash("Check-in recorded.", "success")
    return _back_url()


@bp.post("/expenses/tasks/<uuid:task_id>/payment-status")
@login_required
def set_payment_status(task_id: str):
    services.set_payment_status(_user_id(), task_id, request.form.get("payment_status"))
    flash("Payment status updated.", "success")
    return _back_url()


@bp.post("/expenses/records")
@login_required
def create_record():
    user_id = _user_id()
    token = request.form.get(duplicates.TOKEN_FIELD)
    form = {name: request.form.get(name) for name in UNEXPECTED_FORM_FIELDS}
    entry = _replayed(user_id, flow="unexpected", target=form["budget_month_id"], token=token)
    if entry is not None:
        try:
            services.get_record(user_id, entry["record_id"])
        except NotFoundError:
            duplicates.forget(token)
        else:
            return _prompt_duplicate(
                user_id, flow="unexpected", target=form["budget_month_id"],
                payload={"form": form}, back=_back_fields(),
                record_id=entry["record_id"],
            )
    _submit_unexpected(user_id, form, token)
    flash("Unexpected expense recorded.", "success")
    return _back_url()


@bp.get("/expenses/duplicates/<pending_id>")
@login_required
def duplicate_submission(pending_id: str):
    user_id = _user_id()
    pending = duplicates.peek_pending(pending_id)
    if pending is None or pending.get("user_id") != str(user_id):
        flash("This duplicate confirmation is no longer available.", "warning")
        return redirect(url_for("expenses.index"))
    try:
        record = services.get_record(user_id, pending["record_id"])
    except (NotFoundError, ValidationError):
        duplicates.take_pending(pending_id)
        flash("The first transaction can no longer be shown, so nothing was saved again.", "info")
        return _back_url(pending.get("back"))
    payload = pending.get("payload") or {}
    action = (payload.get("kwargs") or {}).get("action")
    return render_template(
        "pages/duplicate_submission.html",
        record=record,
        pending_id=pending_id,
        token=duplicates.new_token(),
        can_duplicate=pending.get("flow") != "checkin" or action == "actual",
    )


@bp.post("/expenses/duplicates/<pending_id>/confirm")
@login_required
def confirm_duplicate(pending_id: str):
    user_id = _user_id()
    pending = duplicates.take_pending(pending_id)
    if pending is None or pending.get("user_id") != str(user_id):
        flash("This duplicate confirmation was already used or has expired. Nothing was saved again.", "warning")
        return _back_url()
    token = request.form.get(duplicates.TOKEN_FIELD)
    payload = pending.get("payload") or {}
    try:
        if pending.get("flow") == "checkin":
            kwargs = dict(payload.get("kwargs") or {})
            if kwargs.get("action") != "actual":
                raise ValidationError("A planned check-in can only be recorded once per task.")
            _submit_checkin(user_id, pending["target"], kwargs, token)
        elif pending.get("flow") == "unexpected":
            _submit_unexpected(user_id, dict(payload.get("form") or {}), token)
        else:
            raise ValidationError("This duplicate confirmation is not valid.")
    except (ValidationError, NotFoundError) as exc:
        _flash_error(exc)
        return _back_url(pending.get("back"))
    flash("A second identical transaction was saved.", "success")
    return _back_url(pending.get("back"))


@bp.post("/expenses/duplicates/<pending_id>/dismiss")
@login_required
def dismiss_duplicate(pending_id: str):
    pending = duplicates.take_pending(pending_id)
    if pending is None or pending.get("user_id") != str(_user_id()):
        flash("This duplicate confirmation was already used or has expired.", "warning")
        return _back_url()
    flash("Only the first transaction was kept. Nothing else was saved.", "info")
    return _back_url(pending.get("back"))


@bp.post("/expenses/records/<uuid:record_id>/edit")
@login_required
def edit_record(record_id: str):
    services.update_record(_user_id(), record_id, request.form)
    flash("Transaction updated.", "success")
    return _back_url()


@bp.post("/expenses/records/<uuid:record_id>/delete")
@login_required
def delete_record(record_id: str):
    services.delete_record(_user_id(), record_id)
    flash("Transaction deleted.", "success")
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
