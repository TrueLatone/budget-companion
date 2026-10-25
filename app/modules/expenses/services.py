"""Business logic for Expense Planning & Smart Check-in (F07-F13).

All rules live here; routes only translate HTTP <-> service calls, and Jinja
templates only render data.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.expense_planning import (
    AssignedExpenseTask,
    ExpensePlanItem,
    ExpenseRecord,
)
from app.modules.expenses.idgen import new_id
from app.modules.expenses.sources import (
    ExpenseSource,
    SourceExpense,
    get_expense_source,
)
from app.modules.expenses.validators import (
    ValidationError,
    parse_amount,
    parse_optional_date,
    validate_plan_item_form,
    validate_record_form,
)

VN_TZ = timezone(timedelta(hours=7))

DEMO_USER_ID = "demo-user"

STATUS_PENDING = "PENDING"
STATUS_UNRECORDED = "UNRECORDED"
STATUS_NO_EXPENSE = "NO_EXPENSE"
STATUS_WITHIN_BUDGET = "WITHIN_BUDGET"
STATUS_OVER_BUDGET = "OVER_BUDGET"

CONFIRMED_STATUSES = (
    STATUS_NO_EXPENSE,
    STATUS_WITHIN_BUDGET,
    STATUS_OVER_BUDGET,
)

RECORD_PLANNED = "PLANNED"
RECORD_UNEXPECTED = "UNEXPECTED"

VIEWS = ("day", "week", "month", "year")
UI_VIEWS = ("day", "month", "year")


class NotFoundError(Exception):
    """Raised when an entity does not exist or belongs to another user."""


# ---------------------------------------------------------------------------
# Time helpers (Vietnam calendar dates, naive UTC timestamps)
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def today_vn() -> date:
    return vn_now().date()


def deadline_for(assigned_date: date) -> datetime:
    """23:59:59 Vietnam time on the assigned date, stored as naive UTC."""
    local = datetime.combine(assigned_date, time(23, 59, 59), tzinfo=VN_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def resolve_current_user_id() -> str:
    """Single integration point for identity.

    Authentication is not implemented yet (see doc-technical.md section 11).
    Replace this function when the Accounts module ships a session user.

    TODO(auth): replace DEMO_USER_ID with the authenticated session user and
    remove the demo-only assumption in one place, not across routes/templates.
    """
    return DEMO_USER_ID


# ---------------------------------------------------------------------------
# Plan items
# ---------------------------------------------------------------------------


def list_plan_items(user_id: str, *, demo_only: bool = False) -> list[ExpensePlanItem]:
    query = ExpensePlanItem.query.filter_by(user_id=user_id)
    if demo_only:
        query = query.filter_by(is_demo=True)
    return query.order_by(ExpensePlanItem.created_at.desc()).all()


def _get_plan_item(
    item_id: str, user_id: str, *, demo_only: bool = False
) -> ExpensePlanItem:
    item = db.session.get(ExpensePlanItem, item_id)
    if (
        item is None
        or item.user_id != user_id
        or (demo_only and not item.is_demo)
    ):
        raise NotFoundError("Không tìm thấy khoản chi.")
    return item


def create_plan_item(
    user_id: str, form, *, is_demo: bool = True
) -> ExpensePlanItem:
    data = validate_plan_item_form(form)
    item = ExpensePlanItem(
        plan_item_id=new_id(),
        user_id=user_id,
        is_demo=is_demo,
        **data,
    )
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValidationError("Không thể lưu khoản chi do dữ liệu bị trùng.") from exc
    return item


def update_plan_item(user_id: str, item_id: str, form) -> ExpensePlanItem:
    item = _get_plan_item(item_id, user_id, demo_only=True)
    data = validate_plan_item_form(form)
    schedule_keys = ("schedule_tag", "day_of_week", "day_of_month", "specific_date")
    if item.tasks and any(getattr(item, key) != data[key] for key in schedule_keys):
        raise ValidationError(
            "Không thể đổi lịch khi khoản chi đã có task. Hãy ngừng dùng khoản chi này và tạo khoản chi mới nếu cần lịch khác."
        )
    for field, value in data.items():
        setattr(item, field, value)

    # Only today/future tasks that are still pending and before their deadline may
    # follow a template edit. Confirmed, checked, overdue, or UNRECORDED tasks keep
    # the amount/priority snapshot that was used for their history.
    now = now_utc()
    today = today_vn()
    for task in item.tasks:
        if (
            task.task_status != STATUS_PENDING
            or task.checked_at is not None
            or task.records
            or task.assigned_date < today
            or task.checkin_deadline_at < now
        ):
            continue
        task.planned_amount = item.planned_amount
        task.priority = item.priority

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValidationError("Không thể cập nhật khoản chi do dữ liệu bị trùng.") from exc
    return item


def set_plan_item_active(user_id: str, item_id: str, active: bool) -> ExpensePlanItem:
    item = _get_plan_item(item_id, user_id, demo_only=True)
    item.is_active = active
    db.session.commit()
    return item


def delete_plan_item(user_id: str, item_id: str) -> None:
    item = _get_plan_item(item_id, user_id, demo_only=True)
    has_history = any(
        task.records or task.task_status in CONFIRMED_STATUSES for task in item.tasks
    )
    if has_history:
        raise ValidationError(
            "Khoản chi đã có check-in/giao dịch. Hãy ngừng sử dụng thay vì xóa để giữ lịch sử."
        )
    for task in list(item.tasks):
        db.session.delete(task)
    db.session.delete(item)
    db.session.commit()


# ---------------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------------


def _month_starts(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield date(year, month, 1)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


def occurrence_dates(
    schedule_tag: str,
    start: date,
    end: date,
    *,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    specific_date: date | None = None,
) -> list[date]:
    """Return every date a plan item occurs between start and end (inclusive)."""
    if end < start:
        raise ValidationError("Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.")

    dates: list[date] = []
    if schedule_tag == "DAILY":
        cursor = start
        while cursor <= end:
            dates.append(cursor)
            cursor += timedelta(days=1)
    elif schedule_tag == "WEEKLY":
        if day_of_week not in range(1, 8):
            raise ValidationError("Thứ trong tuần không hợp lệ.")
        cursor = start
        while cursor <= end:
            if cursor.isoweekday() == day_of_week:
                dates.append(cursor)
            cursor += timedelta(days=1)
    elif schedule_tag == "MONTHLY":
        for month_start in _month_starts(start, end):
            last_day = calendar.monthrange(month_start.year, month_start.month)[1]
            candidate = date(month_start.year, month_start.month, last_day)
            if start <= candidate <= end:
                dates.append(candidate)
    elif schedule_tag == "DAY_OF_MONTH":
        if not day_of_month or not 1 <= day_of_month <= 31:
            raise ValidationError("Ngày trong tháng không hợp lệ.")
        for month_start in _month_starts(start, end):
            last_day = calendar.monthrange(month_start.year, month_start.month)[1]
            candidate = date(
                month_start.year, month_start.month, min(day_of_month, last_day)
            )
            if start <= candidate <= end:
                dates.append(candidate)
    elif schedule_tag == "DATE":
        if specific_date is None:
            raise ValidationError("Ngày cụ thể không được để trống.")
        if start <= specific_date <= end:
            dates.append(specific_date)
    else:
        raise ValidationError("Kiểu lịch không hợp lệ.")

    return dates


def _materialize_plan_item(
    source_item: SourceExpense, user_id: str
) -> ExpensePlanItem:
    """Return the module-owned row for an adapter item, creating it for M1 items."""
    if source_item.plan_item_id:
        item = db.session.get(ExpensePlanItem, source_item.plan_item_id)
        if item is not None and item.user_id == user_id:
            return item

    if source_item.expense_id:
        existing = ExpensePlanItem.query.filter_by(
            user_id=user_id, source_expense_id=source_item.expense_id
        ).first()
        if existing is not None:
            return existing

    item = ExpensePlanItem(
        plan_item_id=new_id(),
        source_expense_id=source_item.expense_id or None,
        user_id=user_id,
        title=source_item.title,
        amount_source=source_item.amount_source,
        planned_amount=source_item.amount,
        priority=source_item.priority,
        schedule_tag=source_item.schedule_tag,
        day_of_week=source_item.day_of_week,
        day_of_month=source_item.day_of_month,
        specific_date=source_item.specific_date,
        is_active=True,
        is_demo=source_item.plan_item_id is not None,
    )
    db.session.add(item)
    db.session.flush()
    return item


def generate_tasks(
    user_id: str,
    period_start: date,
    period_end: date,
    *,
    source: ExpenseSource | None = None,
) -> int:
    """Generate idempotent assigned tasks for the period. Returns created count."""
    if period_end < period_start:
        raise ValidationError("Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.")

    active_source = source or get_expense_source()
    source_items = active_source.list_expenses(user_id, period_start, period_end)

    existing_pairs = {
        (task.plan_item_id, task.assigned_date)
        for task in AssignedExpenseTask.query.filter(
            AssignedExpenseTask.user_id == user_id,
            AssignedExpenseTask.assigned_date >= period_start,
            AssignedExpenseTask.assigned_date <= period_end,
        ).all()
    }

    created = 0
    for source_item in source_items:
        item = _materialize_plan_item(source_item, user_id)
        for assigned_date in occurrence_dates(
            source_item.schedule_tag,
            period_start,
            period_end,
            day_of_week=source_item.day_of_week,
            day_of_month=source_item.day_of_month,
            specific_date=source_item.specific_date,
        ):
            pair = (item.plan_item_id, assigned_date)
            if pair in existing_pairs:
                continue
            db.session.add(
                AssignedExpenseTask(
                    task_id=new_id(),
                    plan_item_id=item.plan_item_id,
                    user_id=user_id,
                    assigned_date=assigned_date,
                    planned_amount=item.planned_amount,
                    priority=item.priority,
                    checkin_deadline_at=deadline_for(assigned_date),
                    task_status=STATUS_PENDING,
                    is_demo=item.is_demo,
                )
            )
            existing_pairs.add(pair)
            created += 1

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValidationError(
            "Không thể tạo lịch do task đã tồn tại; hãy tải lại trang."
        ) from exc
    return created


# ---------------------------------------------------------------------------
# Tasks and check-in
# ---------------------------------------------------------------------------


def _get_task(task_id: str, user_id: str) -> AssignedExpenseTask:
    task = db.session.get(AssignedExpenseTask, task_id)
    if task is None or task.user_id != user_id:
        raise NotFoundError("Không tìm thấy task.")
    return task


def list_tasks(
    user_id: str,
    start: date,
    end: date,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> list[AssignedExpenseTask]:
    query = AssignedExpenseTask.query.filter(
        AssignedExpenseTask.user_id == user_id,
        AssignedExpenseTask.assigned_date >= start,
        AssignedExpenseTask.assigned_date <= end,
    )
    if demo_only:
        query = query.filter(AssignedExpenseTask.is_demo.is_(True))
    if schedule_tag:
        query = query.join(
            ExpensePlanItem,
            AssignedExpenseTask.plan_item_id == ExpensePlanItem.plan_item_id,
        ).filter(ExpensePlanItem.schedule_tag == schedule_tag)
    return (
        query
        .order_by(
            AssignedExpenseTask.assigned_date.asc(),
            AssignedExpenseTask.priority.asc(),
        )
        .all()
    )


def list_due_tasks(
    user_id: str,
    start: date,
    end: date,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> list[AssignedExpenseTask]:
    query = AssignedExpenseTask.query.filter(
        AssignedExpenseTask.user_id == user_id,
        AssignedExpenseTask.payment_due_date.isnot(None),
        AssignedExpenseTask.payment_due_date >= start,
        AssignedExpenseTask.payment_due_date <= end,
    )
    if demo_only:
        query = query.filter(AssignedExpenseTask.is_demo.is_(True))
    if schedule_tag:
        query = query.join(
            ExpensePlanItem,
            AssignedExpenseTask.plan_item_id == ExpensePlanItem.plan_item_id,
        ).filter(ExpensePlanItem.schedule_tag == schedule_tag)
    return (
        query
        .order_by(AssignedExpenseTask.payment_due_date.asc())
        .all()
    )


def _planned_record(task: AssignedExpenseTask) -> ExpenseRecord | None:
    return ExpenseRecord.query.filter_by(
        task_id=task.task_id, record_type=RECORD_PLANNED
    ).first()


def _comparison_status(amount: int, planned_amount: int) -> str:
    return STATUS_WITHIN_BUDGET if amount <= planned_amount else STATUS_OVER_BUDGET


def refresh_unrecorded(user_id: str, *, now: datetime | None = None) -> int:
    """Move overdue PENDING tasks to UNRECORDED. Idempotent, no background job."""
    current = now or now_utc()
    tasks = AssignedExpenseTask.query.filter(
        AssignedExpenseTask.user_id == user_id,
        AssignedExpenseTask.is_demo.is_(True),
        AssignedExpenseTask.task_status == STATUS_PENDING,
        AssignedExpenseTask.checkin_deadline_at < current,
    ).all()
    for task in tasks:
        task.task_status = STATUS_UNRECORDED
    if tasks:
        db.session.commit()
    return len(tasks)


def checkin_task(
    user_id: str,
    task_id: str,
    *,
    action: str,
    amount_raw: object = None,
    expense_date_raw: object = None,
    category: str | None = None,
    note: str | None = None,
) -> AssignedExpenseTask:
    """Handle the three check-in actions: planned, actual, no_expense."""
    task = _get_task(task_id, user_id)
    record = _planned_record(task)

    if action == "no_expense":
        if record is not None:
            raise ValidationError(
                "Task đã có giao dịch thực tế. Hãy xóa hoặc sửa giao dịch trước khi chọn 'Không phát sinh'."
            )
        task.task_status = STATUS_NO_EXPENSE
        task.checked_at = now_utc()
        db.session.commit()
        return task

    if action == "planned":
        amount = task.planned_amount
        amount_source = RECORD_PLANNED
    elif action == "actual":
        amount = parse_amount(amount_raw, "Số tiền thực tế")
        amount_source = "USER_ENTERED"
    else:
        raise ValidationError("Thao tác check-in không hợp lệ.")

    expense_date = parse_optional_date(expense_date_raw, "Ngày phát sinh")
    if expense_date is None:
        expense_date = task.assigned_date

    category_text = (category or "").strip()
    if len(category_text) > 80:
        raise ValidationError("Danh mục tối đa 80 ký tự.")

    if record is None:
        record = ExpenseRecord(
            record_id=new_id(),
            user_id=user_id,
            task_id=task.task_id,
            record_type=RECORD_PLANNED,
            is_demo=task.is_demo,
        )
        db.session.add(record)

    record.amount = amount
    record.expense_date = expense_date
    record.actual_amount_source = amount_source
    record.title = task.plan_item.title if task.plan_item else None
    record.category = category_text or None
    record.note = (note or "").strip() or None

    task.task_status = _comparison_status(amount, task.planned_amount)
    task.checked_at = now_utc()
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValidationError(
            "Giao dịch cho task này đã được ghi nhận. Hãy tải lại trang để xem kết quả."
        ) from exc
    return task


def set_payment_due_date(
    user_id: str, task_id: str, raw_date: object
) -> AssignedExpenseTask:
    task = _get_task(task_id, user_id)
    task.payment_due_date = parse_optional_date(raw_date, "Hạn thanh toán")
    db.session.commit()
    return task


# ---------------------------------------------------------------------------
# Actual records
# ---------------------------------------------------------------------------


def list_records(
    user_id: str,
    start: date,
    end: date,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> list[ExpenseRecord]:
    query = ExpenseRecord.query.filter(
        ExpenseRecord.user_id == user_id,
        ExpenseRecord.expense_date >= start,
        ExpenseRecord.expense_date <= end,
    )
    if demo_only:
        query = query.filter(ExpenseRecord.is_demo.is_(True))
    if schedule_tag:
        query = query.join(
            AssignedExpenseTask,
            ExpenseRecord.task_id == AssignedExpenseTask.task_id,
        ).join(
            ExpensePlanItem,
            AssignedExpenseTask.plan_item_id == ExpensePlanItem.plan_item_id,
        ).filter(ExpensePlanItem.schedule_tag == schedule_tag)
    return (
        query
        .order_by(ExpenseRecord.expense_date.desc(), ExpenseRecord.created_at.desc())
        .all()
    )


def planned_records_for_tasks(task_ids: list[str]) -> dict[str, ExpenseRecord]:
    """Return linked planned records for any task ids, including due-only tasks."""
    if not task_ids:
        return {}
    records = ExpenseRecord.query.filter(
        ExpenseRecord.task_id.in_(task_ids),
        ExpenseRecord.record_type == RECORD_PLANNED,
    ).all()
    return {record.task_id: record for record in records}


def _get_record(record_id: str, user_id: str) -> ExpenseRecord:
    record = db.session.get(ExpenseRecord, record_id)
    if record is None or record.user_id != user_id:
        raise NotFoundError("Không tìm thấy giao dịch.")
    return record


def _idempotency_key(form) -> str | None:
    key = str(form.get("idempotency_key") or "").strip()
    if len(key) > 64:
        raise ValidationError("Mã chống trùng giao dịch tối đa 64 ký tự.")
    return key or None


def find_unexpected_by_idempotency(
    user_id: str, idempotency_key: str | None
) -> ExpenseRecord | None:
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 64:
        return None
    return ExpenseRecord.query.filter_by(
        user_id=user_id,
        idempotency_key=key,
        record_type=RECORD_UNEXPECTED,
    ).first()


def create_unexpected_record(user_id: str, form) -> ExpenseRecord:
    """Create an unexpected record once per client form token.

    The token is deliberately independent of amount/date so two legitimate
    same-day expenses with the same amount are still allowed. A retried request
    carrying the same token returns the original row instead of inserting again.
    """
    data = validate_record_form(form, require_title=True)
    key = _idempotency_key(form)
    if key:
        existing = find_unexpected_by_idempotency(user_id, key)
        if existing is not None:
            return existing

    record = ExpenseRecord(
        record_id=new_id(),
        user_id=user_id,
        task_id=None,
        record_type=RECORD_UNEXPECTED,
        actual_amount_source="USER_ENTERED",
        idempotency_key=key,
        is_demo=True,
        **data,
    )
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if key:
            existing = find_unexpected_by_idempotency(user_id, key)
            if existing is not None:
                return existing
        raise ValidationError("Không thể lưu giao dịch do dữ liệu bị trùng.") from exc
    return record


def update_record(user_id: str, record_id: str, form) -> ExpenseRecord:
    record = _get_record(record_id, user_id)
    data = validate_record_form(
        form, require_title=record.record_type == RECORD_UNEXPECTED
    )
    record.amount = data["amount"]
    record.expense_date = data["expense_date"]
    record.category = data["category"]
    record.note = data["note"]
    if record.record_type == RECORD_UNEXPECTED:
        record.title = data["title"]

    if record.task is not None:
        record.task.task_status = _comparison_status(
            record.amount, record.task.planned_amount
        )
        record.task.checked_at = now_utc()
    db.session.commit()
    return record


def delete_record(user_id: str, record_id: str) -> None:
    record = _get_record(record_id, user_id)
    task = record.task
    if task is not None:
        task.checked_at = None
        task.task_status = (
            STATUS_UNRECORDED
            if task.checkin_deadline_at < now_utc()
            else STATUS_PENDING
        )
    db.session.delete(record)
    db.session.commit()


# ---------------------------------------------------------------------------
# Period summary / history
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    view: str
    anchor: date
    start: date
    end: date
    label: str


def resolve_period(view: str | None, raw_date: str | None) -> Period:
    view = (view or "month").lower()
    if view not in VIEWS:
        view = "month"
    anchor = parse_optional_date(raw_date, "Ngày xem") or today_vn()

    if view == "day":
        start = end = anchor
        label = anchor.strftime("%d/%m/%Y")
    elif view == "week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        label = f"{start.strftime('%d/%m')} - {end.strftime('%d/%m/%Y')}"
    elif view == "year":
        start = date(anchor.year, 1, 1)
        end = date(anchor.year, 12, 31)
        label = f"Năm {anchor.year}"
    else:
        start = anchor.replace(day=1)
        end = anchor.replace(
            day=calendar.monthrange(anchor.year, anchor.month)[1]
        )
        label = anchor.strftime("%m/%Y")

    return Period(view=view, anchor=anchor, start=start, end=end, label=label)


@dataclass(frozen=True)
class CalendarDay:
    """One real day in a month calendar, with small aggregate indicators."""

    day: date
    task_count: int = 0
    plan_total: int = 0
    actual_total: int = 0
    pending_count: int = 0
    unrecorded_count: int = 0
    confirmed_count: int = 0

    @property
    def has_tasks(self) -> bool:
        return self.task_count > 0


@dataclass(frozen=True)
class TaskEntry:
    """A task shown in a day/month list and why it belongs there."""

    task: AssignedExpenseTask
    assigned_in_period: bool
    due_in_period: bool


@dataclass(frozen=True)
class DayTotals:
    """Split planned money for assigned tasks and due-only tasks in a day."""

    assigned_count: int
    due_only_count: int
    assigned_plan_total: int
    due_only_plan_total: int


@dataclass(frozen=True)
class MonthCard:
    """A month summary used by the year view."""

    month: int
    label: str
    start: date
    plan_total: int
    actual_total: int
    difference: int
    task_count: int
    daily_count: int
    confirmed: int
    unconfirmed: int
    highlights: list[AssignedExpenseTask]


def shift_month(anchor: date, delta: int) -> date:
    """Move by calendar months, clamping the day to the target month's last day."""
    total = anchor.year * 12 + (anchor.month - 1) + delta
    year, month_index = divmod(total, 12)
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def shift_year(anchor: date, delta: int) -> date:
    """Move by calendar years, clamping 29 February to 28 February when needed."""
    year = anchor.year + delta
    last_day = calendar.monthrange(year, anchor.month)[1]
    return date(year, anchor.month, min(anchor.day, last_day))


def build_navigation(period: Period) -> dict[str, date]:
    """Return prev/next anchors for the active view and its calendar header."""
    anchor = period.anchor
    if period.view == "day":
        prev_anchor = anchor - timedelta(days=1)
        next_anchor = anchor + timedelta(days=1)
    elif period.view == "week":
        prev_anchor = anchor - timedelta(days=7)
        next_anchor = anchor + timedelta(days=7)
    elif period.view == "month":
        prev_anchor = shift_month(anchor, -1)
        next_anchor = shift_month(anchor, 1)
    else:
        prev_anchor = shift_year(anchor, -1)
        next_anchor = shift_year(anchor, 1)

    return {
        "prev": prev_anchor,
        "next": next_anchor,
        "prev_month": shift_month(anchor, -1),
        "next_month": shift_month(anchor, 1),
        "prev_year": shift_year(anchor, -1),
        "next_year": shift_year(anchor, 1),
    }


def build_month_calendar(
    tasks: list[AssignedExpenseTask],
    records: list[ExpenseRecord],
    year: int,
    month: int,
) -> list[list[CalendarDay | None]]:
    """Build real calendar weeks for a month, with none-padded leading/trailing cells."""
    tasks_by_day: dict[date, list[AssignedExpenseTask]] = defaultdict(list)
    records_by_day: dict[date, list[ExpenseRecord]] = defaultdict(list)

    for task in tasks:
        if task.assigned_date.year == year and task.assigned_date.month == month:
            tasks_by_day[task.assigned_date].append(task)
    for record in records:
        if record.expense_date.year == year and record.expense_date.month == month:
            records_by_day[record.expense_date].append(record)

    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    weeks: list[list[CalendarDay | None]] = []
    week: list[CalendarDay | None] = [None] * first.weekday()

    for day_number in range(1, last_day + 1):
        day = date(year, month, day_number)
        day_tasks = tasks_by_day[day]
        day_records = records_by_day[day]
        week.append(
            CalendarDay(
                day=day,
                task_count=len(day_tasks),
                plan_total=sum(task.planned_amount for task in day_tasks),
                actual_total=sum(record.amount for record in day_records),
                pending_count=sum(
                    1 for task in day_tasks if task.task_status == STATUS_PENDING
                ),
                unrecorded_count=sum(
                    1 for task in day_tasks if task.task_status == STATUS_UNRECORDED
                ),
                confirmed_count=sum(
                    1
                    for task in day_tasks
                    if task.task_status in CONFIRMED_STATUSES
                ),
            )
        )
        if len(week) == 7:
            weeks.append(week)
            week = []

    if week:
        week.extend([None] * (7 - len(week)))
        weeks.append(week)
    return weeks


def build_day_items(
    summary: dict[str, object], selected_date: date
) -> list[TaskEntry]:
    """Tasks assigned on the selected day plus tasks due that day, de-duplicated."""
    items: list[TaskEntry] = []
    seen: set[str] = set()

    for task in summary["tasks"]:  # type: ignore[union-attr]
        items.append(
            TaskEntry(
                task=task,
                assigned_in_period=True,
                due_in_period=task.payment_due_date == selected_date,
            )
        )
        seen.add(task.task_id)

    for task in summary["due_tasks"]:  # type: ignore[union-attr]
        if task.task_id not in seen:
            items.append(
                TaskEntry(
                    task=task,
                    assigned_in_period=False,
                    due_in_period=True,
                )
            )
            seen.add(task.task_id)

    return items


def summarize_day_items(items: list[TaskEntry]) -> DayTotals:
    """Separate assigned totals from due-only totals, without double counting."""
    assigned = [entry for entry in items if entry.assigned_in_period]
    due_only = [entry for entry in items if not entry.assigned_in_period]
    return DayTotals(
        assigned_count=len(assigned),
        due_only_count=len(due_only),
        assigned_plan_total=sum(entry.task.planned_amount for entry in assigned),
        due_only_plan_total=sum(entry.task.planned_amount for entry in due_only),
    )


def build_month_items(summary: dict[str, object]) -> list[TaskEntry]:
    """Non-daily obligations for a month, plus due-only tasks, de-duplicated."""
    items: list[TaskEntry] = []
    seen: set[str] = set()
    due_ids = {task.task_id for task in summary["due_tasks"]}  # type: ignore[union-attr]
    period = summary["period"]

    for task in summary["tasks"]:  # type: ignore[union-attr]
        if task.plan_item and task.plan_item.schedule_tag == "DAILY":
            continue
        items.append(
            TaskEntry(
                task=task,
                assigned_in_period=True,
                due_in_period=task.task_id in due_ids,
            )
        )
        seen.add(task.task_id)

    for task in summary["due_tasks"]:  # type: ignore[union-attr]
        if task.task_id in seen:
            continue
        items.append(
            TaskEntry(
                task=task,
                assigned_in_period=period.start <= task.assigned_date <= period.end,
                due_in_period=True,
            )
        )
        seen.add(task.task_id)

    return items


def build_year_months(
    summary: dict[str, object],
    year: int,
    *,
    schedule_tag: str | None = None,
) -> list[MonthCard]:
    """Group a filtered year summary into month cards without re-querying."""
    tasks_by_month: dict[int, list[AssignedExpenseTask]] = defaultdict(list)
    records_by_month: dict[int, list[ExpenseRecord]] = defaultdict(list)

    for task in summary["tasks"]:  # type: ignore[union-attr]
        if task.assigned_date.year == year:
            tasks_by_month[task.assigned_date.month].append(task)
    for record in summary["records"]:  # type: ignore[union-attr]
        if record.expense_date.year == year:
            records_by_month[record.expense_date.month].append(record)

    cards: list[MonthCard] = []
    for month in range(1, 13):
        month_tasks = tasks_by_month[month]
        month_records = records_by_month[month]
        plan_total = sum(task.planned_amount for task in month_tasks)
        actual_total = sum(record.amount for record in month_records)
        daily_count = sum(
            1
            for task in month_tasks
            if task.plan_item and task.plan_item.schedule_tag == "DAILY"
        )
        confirmed = sum(
            1
            for task in month_tasks
            if task.task_status in CONFIRMED_STATUSES
        )

        if schedule_tag == "DAILY":
            highlights: list[AssignedExpenseTask] = []
        elif schedule_tag:
            highlights = list(month_tasks)
        else:
            highlights = [
                task
                for task in month_tasks
                if not (task.plan_item and task.plan_item.schedule_tag == "DAILY")
            ]

        cards.append(
            MonthCard(
                month=month,
                label=f"Tháng {month}",
                start=date(year, month, 1),
                plan_total=plan_total,
                actual_total=actual_total,
                difference=plan_total - actual_total,
                task_count=len(month_tasks),
                daily_count=daily_count,
                confirmed=confirmed,
                unconfirmed=len(month_tasks) - confirmed,
                highlights=highlights,
            )
        )
    return cards


def build_summary(
    user_id: str,
    period: Period,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> dict[str, object]:
    tasks = list_tasks(
        user_id,
        period.start,
        period.end,
        demo_only=demo_only,
        schedule_tag=schedule_tag,
    )
    records = list_records(
        user_id,
        period.start,
        period.end,
        demo_only=demo_only,
        schedule_tag=schedule_tag,
    )

    plan_total = sum(task.planned_amount for task in tasks)
    actual_total = sum(record.amount for record in records)
    planned_by_task = {}
    task_ids = [task.task_id for task in tasks]
    if task_ids:
        linked_records = ExpenseRecord.query.filter(
            ExpenseRecord.task_id.in_(task_ids),
            ExpenseRecord.record_type == RECORD_PLANNED,
        ).all()
        planned_by_task = {
            record.task_id: record for record in linked_records
        }
    counts = {
        "pending": sum(1 for task in tasks if task.task_status == STATUS_PENDING),
        "unrecorded": sum(1 for task in tasks if task.task_status == STATUS_UNRECORDED),
        "no_expense": sum(1 for task in tasks if task.task_status == STATUS_NO_EXPENSE),
        "within": sum(
            1 for task in tasks if task.task_status == STATUS_WITHIN_BUDGET
        ),
        "over": sum(1 for task in tasks if task.task_status == STATUS_OVER_BUDGET),
    }

    return {
        "period": period,
        "tasks": tasks,
        "records": records,
        "due_tasks": list_due_tasks(
            user_id,
            period.start,
            period.end,
            demo_only=demo_only,
            schedule_tag=schedule_tag,
        ),
        "plan_total": plan_total,
        "actual_total": actual_total,
        "difference": plan_total - actual_total,
        "counts": counts,
        "confirmed": counts["no_expense"] + counts["within"] + counts["over"],
        "unconfirmed": counts["pending"] + counts["unrecorded"],
        "unexpected_records": [
            record
            for record in records
            if record.record_type == RECORD_UNEXPECTED
        ],
        "planned_by_task": planned_by_task,
    }


def clear_demo_data(user_id: str) -> dict[str, int]:
    """Delete only rows flagged as demo for this user, in FK-safe order."""
    demo_records = ExpenseRecord.query.filter_by(user_id=user_id, is_demo=True).all()
    demo_tasks = AssignedExpenseTask.query.filter_by(user_id=user_id, is_demo=True).all()
    demo_items = ExpensePlanItem.query.filter_by(user_id=user_id, is_demo=True).all()

    for record in demo_records:
        db.session.delete(record)
    for task in demo_tasks:
        db.session.delete(task)
    for item in demo_items:
        db.session.delete(item)
    db.session.commit()
    return {
        "records": len(demo_records),
        "tasks": len(demo_tasks),
        "items": len(demo_items),
    }
