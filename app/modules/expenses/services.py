"""Business logic for Expense Planning & Smart Check-in (F07-F13).

All business rules live here; routes translate HTTP <-> service calls, and Jinja
templates render view data.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
import uuid

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AssignedExpenseTask,
    BudgetAllocation,
    BudgetExpense,
    BudgetMonth,
    BudgetPlan,
    ExpenseCategory,
    ExpenseRecord,
    User,
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
    validate_record_form,
)

VN_TZ = timezone(timedelta(hours=7))

DEMO_USER_ID = "demo-user"
DEMO_USER_UUID = uuid.uuid5(uuid.NAMESPACE_DNS, DEMO_USER_ID)

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
RECORD_FUNDS_ADDED = "FUNDS_ADDED"

VIEWS = ("day", "week", "month", "year")
UI_VIEWS = ("day", "month", "year")


class NotFoundError(Exception):
    """Raised when an entity does not exist or belongs to another user."""


# ---------------------------------------------------------------------------
# Identity and UUID helpers
# ---------------------------------------------------------------------------


def to_uuid(value: object) -> uuid.UUID:
    """Safely convert any identifier (UUID, hex string, or arbitrary name) to a UUID."""
    if isinstance(value, uuid.UUID):
        return value
    val_str = str(value)
    try:
        return uuid.UUID(val_str)
    except (ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, val_str)


def resolve_current_user_id() -> uuid.UUID:
    """Return the active user identifier as a UUID."""
    from flask import g

    current_user = getattr(g, "current_user", None)
    if current_user is not None and getattr(current_user, "id", None) is not None:
        return current_user.id
    return DEMO_USER_UUID


def _ensure_user(user_uuid: uuid.UUID) -> User:
    """Ensure a backing User row exists for foreign key references."""
    user = db.session.get(User, user_uuid)
    if user is None:
        user = User(
            id=user_uuid,
            email=f"user-{user_uuid.hex[:8]}@example.com",
            password_hash="not-a-real-hash",
        )
        db.session.add(user)
        db.session.flush()
    return user


# ---------------------------------------------------------------------------
# Time helpers (Vietnam calendar dates, naive UTC timestamps)
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def today_vn() -> date:
    return vn_now().date()


def deadline_for(target_date: date) -> datetime:
    """23:59:59 Vietnam time on the given calendar date, stored as naive UTC."""
    local = datetime.combine(target_date, time(23, 59, 59), tzinfo=VN_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Derived task status and model compatibility adapters (no monkey-patching)
# ---------------------------------------------------------------------------


def get_task_status(
    task: AssignedExpenseTask | "ExpenseTaskAdapter",
    now: datetime | None = None,
) -> str:
    """Derive display status: PENDING, UNRECORDED, NO_EXPENSE, WITHIN_BUDGET, OVER_BUDGET.

    Note on check-in deadline:
    The canonical database schema AssignedExpenseTask does not define a contractual
    `checkin_deadline_at` column. As an application convention, Expense evaluates
    `UNRECORDED` when now > deadline_for(task.period_end or task.assigned_date).
    Pre-tracking dates (before BudgetMonth.tracking_start_date) are excluded from
    becoming UNRECORDED.
    """
    raw_task: AssignedExpenseTask = getattr(task, "raw_task", task)  # type: ignore[assignment]
    if raw_task.task_status == STATUS_NO_EXPENSE:
        return STATUS_NO_EXPENSE

    records = [r for r in raw_task.records if r.record_type == RECORD_PLANNED]
    if records:
        total = sum(r.amount for r in records)
        limit = raw_task.current_limit
        return STATUS_WITHIN_BUDGET if total <= limit else STATUS_OVER_BUDGET

    # Exclude dates before tracking_start_date
    if (
        raw_task.allocation
        and raw_task.allocation.plan
        and raw_task.allocation.plan.budget_month
    ):
        tracking_start = raw_task.allocation.plan.budget_month.tracking_start_date
        if tracking_start and raw_task.assigned_date < tracking_start:
            return STATUS_PENDING

    current = now or now_utc()
    deadline = deadline_for(raw_task.period_end or raw_task.assigned_date)
    if deadline < current:
        return STATUS_UNRECORDED
    return STATUS_PENDING


class _PlanItemShim:
    """Shim exposing title, schedule_tag, and priority from the shared schema."""

    def __init__(self, task: AssignedExpenseTask):
        self._task = task

    @property
    def title(self) -> str:
        if self._task.allocation and self._task.allocation.budget_expense:
            return self._task.allocation.budget_expense.expense_name
        return ""

    @property
    def schedule_tag(self) -> str:
        if self._task.allocation and self._task.allocation.budget_expense:
            expense = self._task.allocation.budget_expense
            if not getattr(expense, "is_recurring", True):
                return "DATE"
            if expense.allocation_frequency == "MONTHLY" and getattr(expense, "due_day", None):
                return "DAY_OF_MONTH"
            return expense.allocation_frequency or "DAILY"
        return "DAILY"

    @property
    def priority(self) -> str:
        if self._task.allocation and self._task.allocation.budget_expense:
            return self._task.allocation.budget_expense.priority
        return "P1"

    @property
    def is_active(self) -> bool:
        return True


class ExpenseCategoryAdapter:
    """Read-only adapter for ExpenseCategory."""

    def __init__(self, category: ExpenseCategory | None):
        self._category = category

    @property
    def id(self) -> uuid.UUID | None:
        return self._category.id if self._category else None

    @property
    def category_name(self) -> str:
        return self._category.category_name if self._category else ""

    def __str__(self) -> str:
        return self.category_name

    def __bool__(self) -> bool:
        return self._category is not None

    def __getattr__(self, name: str):
        if self._category is not None:
            return getattr(self._category, name)
        raise AttributeError(name)


class ExpenseRecordAdapter:
    """Read-only DTO/adapter wrapping ExpenseRecord for Expense views and routes."""

    def __init__(self, record: ExpenseRecord):
        self._record = record

    @property
    def id(self) -> uuid.UUID:
        return self._record.id

    @property
    def record_id(self) -> str:
        return str(self._record.id)

    @property
    def task_id(self) -> uuid.UUID | None:
        return self._record.task_id

    @property
    def budget_month_id(self) -> uuid.UUID:
        return self._record.budget_month_id

    @property
    def category_id(self) -> uuid.UUID | None:
        return self._record.category_id

    @property
    def amount(self) -> int:
        return self._record.amount

    @property
    def expense_date(self) -> date:
        return self._record.expense_date

    @property
    def record_type(self) -> str:
        return self._record.record_type

    @property
    def priority(self) -> str | None:
        if self._record.priority:
            return self._record.priority
        if (
            self._record.task
            and self._record.task.allocation
            and self._record.task.allocation.budget_expense
        ):
            return self._record.task.allocation.budget_expense.priority
        return None

    @property
    def title(self) -> str | None:
        if self._record.title:
            return self._record.title
        if (
            self._record.task
            and self._record.task.allocation
            and self._record.task.allocation.budget_expense
        ):
            return self._record.task.allocation.budget_expense.expense_name
        return None

    @property
    def note(self) -> str | None:
        return self._record.note

    @property
    def budget_impact_scope(self) -> str | None:
        return self._record.budget_impact_scope

    @property
    def idempotency_key(self) -> str | None:
        return self._record.idempotency_key

    @property
    def actual_amount_source(self) -> str:
        if self._record.record_type == RECORD_PLANNED:
            if (
                self._record.task
                and self._record.amount == self._record.task.current_limit
            ):
                return "PLANNED"
            return "USER_ENTERED"
        return "USER_ENTERED"

    @property
    def category(self) -> ExpenseCategoryAdapter:
        return ExpenseCategoryAdapter(self._record.category)

    @property
    def category_name(self) -> str:
        return self._record.category.category_name if self._record.category else ""

    @property
    def user_id(self) -> str | None:
        if self._record.budget_month:
            return str(self._record.budget_month.user_id)
        return None

    @property
    def task(self) -> "ExpenseTaskAdapter | None":
        return ExpenseTaskAdapter(self._record.task) if self._record.task else None

    @property
    def raw_record(self) -> ExpenseRecord:
        return self._record

    def __getattr__(self, name: str):
        return getattr(self._record, name)


class ExpenseTaskAdapter:
    """Read-only DTO/adapter wrapping AssignedExpenseTask for Expense views and routes."""

    def __init__(self, task: AssignedExpenseTask, now: datetime | None = None):
        self._task = task
        self._now = now

    @property
    def id(self) -> uuid.UUID:
        return self._task.id

    @property
    def task_id(self) -> str:
        return str(self._task.id)

    @property
    def assigned_date(self) -> date:
        return self._task.assigned_date

    @property
    def period_end(self) -> date:
        return self._task.period_end

    @property
    def payment_due_date(self) -> date | None:
        return self._task.payment_due_date

    @property
    def payment_status(self) -> str | None:
        return self._task.payment_status

    @property
    def original_limit(self) -> int:
        return self._task.original_limit

    @property
    def current_limit(self) -> int:
        return self._task.current_limit

    @property
    def planned_amount(self) -> int:
        return self._task.current_limit

    @property
    def task_status(self) -> str:
        return self._task.task_status

    @property
    def display_status(self) -> str:
        return get_task_status(self._task, self._now)

    @property
    def title(self) -> str:
        if self._task.allocation and self._task.allocation.budget_expense:
            return self._task.allocation.budget_expense.expense_name
        return ""

    @property
    def priority(self) -> str:
        if self._task.allocation and self._task.allocation.budget_expense:
            return self._task.allocation.budget_expense.priority
        return "P1"

    @property
    def schedule_tag(self) -> str:
        if self._task.allocation and self._task.allocation.budget_expense:
            expense = self._task.allocation.budget_expense
            if not getattr(expense, "is_recurring", True):
                return "DATE"
            if expense.allocation_frequency == "MONTHLY" and getattr(expense, "due_day", None):
                return "DAY_OF_MONTH"
            return expense.allocation_frequency or "DAILY"
        return "DAILY"

    @property
    def plan_item(self) -> _PlanItemShim:
        return _PlanItemShim(self._task)

    @property
    def checkin_deadline_at(self) -> datetime:
        return deadline_for(self._task.period_end or self._task.assigned_date)

    @property
    def user_id(self) -> str | None:
        if (
            self._task.allocation
            and self._task.allocation.plan
            and self._task.allocation.plan.budget_month
        ):
            return str(self._task.allocation.plan.budget_month.user_id)
        return None

    @property
    def records(self) -> list[ExpenseRecordAdapter]:
        return [ExpenseRecordAdapter(r) for r in self._task.records]

    @property
    def raw_task(self) -> AssignedExpenseTask:
        return self._task

    def __getattr__(self, name: str):
        return getattr(self._task, name)


def adapt_task(
    task: AssignedExpenseTask | ExpenseTaskAdapter,
    now: datetime | None = None,
) -> ExpenseTaskAdapter:
    if isinstance(task, ExpenseTaskAdapter):
        return task
    return ExpenseTaskAdapter(task, now=now)


def adapt_record(
    record: ExpenseRecord | ExpenseRecordAdapter,
) -> ExpenseRecordAdapter:
    if isinstance(record, ExpenseRecordAdapter):
        return record
    return ExpenseRecordAdapter(record)


# ---------------------------------------------------------------------------
# Scheduling helper
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
    """Return every date a recurring rule occurs between start and end (inclusive)."""
    if end < start:
        return []

    dates: list[date] = []

    if schedule_tag == "DAILY":
        cur = start
        while cur <= end:
            dates.append(cur)
            cur += timedelta(days=1)
    elif schedule_tag == "WEEKLY":
        if day_of_week is None or not (1 <= day_of_week <= 7):
            raise ValidationError("Thứ trong tuần phải từ 1 đến 7.")
        cur = start
        while cur <= end:
            if cur.isoweekday() == day_of_week:
                dates.append(cur)
            cur += timedelta(days=1)
    elif schedule_tag == "MONTHLY":
        for m_start in _month_starts(start, end):
            last_day = calendar.monthrange(m_start.year, m_start.month)[1]
            candidate = date(m_start.year, m_start.month, last_day)
            if start <= candidate <= end:
                dates.append(candidate)
    elif schedule_tag == "DAY_OF_MONTH":
        if day_of_month is None or not (1 <= day_of_month <= 31):
            raise ValidationError("Ngày trong tháng phải từ 1 đến 31.")
        for m_start in _month_starts(start, end):
            max_day = calendar.monthrange(m_start.year, m_start.month)[1]
            candidate = date(
                m_start.year, m_start.month, min(day_of_month, max_day)
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


# ---------------------------------------------------------------------------
# Tasks and check-in
# ---------------------------------------------------------------------------


def _get_task(task_id: object, user_id: object) -> AssignedExpenseTask:
    task_uuid = to_uuid(task_id)
    user_uuid = to_uuid(user_id)
    task = db.session.get(AssignedExpenseTask, task_uuid)
    if (
        task is None
        or not task.allocation
        or not task.allocation.plan
        or not task.allocation.plan.budget_month
        or task.allocation.plan.budget_month.user_id != user_uuid
    ):
        raise NotFoundError("Không tìm thấy task.")
    return task


def get_task(user_id: object, task_id: object) -> ExpenseTaskAdapter:
    return ExpenseTaskAdapter(_get_task(task_id, user_id))


def _apply_schedule_filter(query, schedule_tag: str):
    if schedule_tag == "DATE":
        return query.filter(BudgetExpense.is_recurring.is_(False))
    elif schedule_tag == "DAY_OF_MONTH":
        return query.filter(
            BudgetExpense.is_recurring.is_(True),
            BudgetExpense.allocation_frequency == "MONTHLY",
            BudgetExpense.due_day.isnot(None),
        )
    elif schedule_tag == "MONTHLY":
        return query.filter(
            BudgetExpense.is_recurring.is_(True),
            BudgetExpense.allocation_frequency == "MONTHLY",
            BudgetExpense.due_day.is_(None),
        )
    elif schedule_tag in ("DAILY", "WEEKLY"):
        return query.filter(
            BudgetExpense.is_recurring.is_(True),
            BudgetExpense.allocation_frequency == schedule_tag,
        )
    return query.filter(BudgetExpense.allocation_frequency == schedule_tag)


def list_tasks(
    user_id: object,
    start: date,
    end: date,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> list[ExpenseTaskAdapter]:
    user_uuid = to_uuid(user_id)
    query = (
        AssignedExpenseTask.query.join(
            BudgetAllocation,
            AssignedExpenseTask.allocation_id == BudgetAllocation.id,
        )
        .join(BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id)
        .join(BudgetMonth, BudgetPlan.budget_month_id == BudgetMonth.id)
        .join(
            BudgetExpense,
            BudgetAllocation.budget_expense_id == BudgetExpense.id,
        )
        .filter(
            BudgetMonth.user_id == user_uuid,
            AssignedExpenseTask.assigned_date >= start,
            AssignedExpenseTask.assigned_date <= end,
        )
    )
    if schedule_tag:
        query = _apply_schedule_filter(query, schedule_tag)
    tasks = (
        query.order_by(
            AssignedExpenseTask.assigned_date.asc(),
            BudgetExpense.priority.asc(),
        ).all()
    )
    return [ExpenseTaskAdapter(t) for t in tasks]


def list_due_tasks(
    user_id: object,
    start: date,
    end: date,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> list[ExpenseTaskAdapter]:
    user_uuid = to_uuid(user_id)
    query = (
        AssignedExpenseTask.query.join(
            BudgetAllocation,
            AssignedExpenseTask.allocation_id == BudgetAllocation.id,
        )
        .join(BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id)
        .join(BudgetMonth, BudgetPlan.budget_month_id == BudgetMonth.id)
        .join(
            BudgetExpense,
            BudgetAllocation.budget_expense_id == BudgetExpense.id,
        )
        .filter(
            BudgetMonth.user_id == user_uuid,
            AssignedExpenseTask.payment_due_date.isnot(None),
            AssignedExpenseTask.payment_due_date >= start,
            AssignedExpenseTask.payment_due_date <= end,
        )
    )
    if schedule_tag:
        query = _apply_schedule_filter(query, schedule_tag)
    tasks = query.order_by(AssignedExpenseTask.payment_due_date.asc()).all()
    return [ExpenseTaskAdapter(t) for t in tasks]


def _find_or_create_category(user_uuid: uuid.UUID, category_name: str) -> ExpenseCategory:
    cleaned = category_name.strip()
    if not cleaned:
        cleaned = "Khác"
    # 1. Check user-owned categories
    cats = ExpenseCategory.query.filter_by(user_id=user_uuid).all()
    for c in cats:
        if c.category_name.strip().lower() == cleaned.lower():
            return c
    # 2. Check built-in categories (user_id is None)
    builtins = ExpenseCategory.query.filter(ExpenseCategory.user_id.is_(None)).all()
    for c in builtins:
        if c.category_name.strip().lower() == cleaned.lower():
            return c
    # 3. Create user-owned category
    cat = ExpenseCategory(user_id=user_uuid, category_name=cleaned)
    db.session.add(cat)
    db.session.flush()
    return cat


def _planned_record(task: AssignedExpenseTask) -> ExpenseRecord | None:
    return ExpenseRecord.query.filter_by(
        task_id=task.id, record_type=RECORD_PLANNED
    ).first()


def refresh_unrecorded(user_id: object, *, now: datetime | None = None) -> int:
    """Derive how many pending tasks have passed their check-in deadline."""
    user_uuid = to_uuid(user_id)
    current = now or now_utc()
    tasks = (
        AssignedExpenseTask.query.join(
            BudgetAllocation,
            AssignedExpenseTask.allocation_id == BudgetAllocation.id,
        )
        .join(BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id)
        .join(BudgetMonth, BudgetPlan.budget_month_id == BudgetMonth.id)
        .filter(
            BudgetMonth.user_id == user_uuid,
            AssignedExpenseTask.task_status == STATUS_PENDING,
        )
        .all()
    )
    count = 0
    for task in tasks:
        tracking_start = task.allocation.plan.budget_month.tracking_start_date
        if tracking_start and task.assigned_date < tracking_start:
            continue
        if deadline_for(task.period_end or task.assigned_date) < current:
            count += 1
    return count


def checkin_task(
    user_id: object,
    task_id: object,
    *,
    action: str,
    amount_raw: object = None,
    expense_date_raw: object = None,
    category: str | None = None,
    note: str | None = None,
) -> ExpenseTaskAdapter:
    """Handle the three check-in actions: planned, actual, no_expense."""
    task = _get_task(task_id, user_id)
    user_uuid = to_uuid(user_id)
    record = _planned_record(task)

    if action == "no_expense":
        existing_planned = [r for r in task.records if r.record_type == RECORD_PLANNED]
        if existing_planned:
            raise ValidationError(
                "Task đã có giao dịch thực tế. Hãy xóa hoặc sửa giao dịch trước khi chọn 'Không phát sinh'."
            )
        task.task_status = STATUS_NO_EXPENSE
        db.session.commit()
        return ExpenseTaskAdapter(task)

    if action == "planned":
        amount = task.current_limit
    elif action == "actual":
        amount = parse_amount(amount_raw, "Số tiền thực tế")
    else:
        raise ValidationError("Thao tác check-in không hợp lệ.")

    expense_date = parse_optional_date(expense_date_raw, "Ngày phát sinh")
    if expense_date is None:
        expense_date = task.assigned_date

    category_text = (category or "").strip()
    if len(category_text) > 80:
        raise ValidationError("Danh mục tối đa 80 ký tự.")

    # Resolve category: custom category name or task's default category
    if category_text:
        cat = _find_or_create_category(user_uuid, category_text)
        category_id = cat.id
    else:
        category_id = task.allocation.budget_expense.category_id

    budget_month_id = task.allocation.plan.budget_month_id

    if record is None:
        record = ExpenseRecord(
            id=uuid.uuid4(),
            budget_month_id=budget_month_id,
            task_id=task.id,
            category_id=category_id,
            amount=amount,
            expense_date=expense_date,
            record_type=RECORD_PLANNED,
            priority=(
                task.allocation.budget_expense.priority
                if task.allocation and task.allocation.budget_expense
                else None
            ),
            title=(
                task.allocation.budget_expense.expense_name
                if task.allocation and task.allocation.budget_expense
                else None
            ),
            note=(note or "").strip() or None,
        )
        db.session.add(record)
    else:
        record.amount = amount
        record.expense_date = expense_date
        record.category_id = category_id
        record.note = (note or "").strip() or None

    task.task_status = "RECORDED"
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValidationError(
            "Giao dịch cho task này đã được ghi nhận. Hãy tải lại trang để xem kết quả."
        ) from exc
    return ExpenseTaskAdapter(task)


def set_payment_status(
    user_id: object, task_id: object, status: str | None
) -> ExpenseTaskAdapter:
    """Update self-reported bill payment status (PAID or UNPAID) without touching payment_due_date."""
    task = _get_task(task_id, user_id)
    if status is not None:
        status_norm = str(status).strip().upper()
        if not status_norm:
            task.payment_status = None
        elif status_norm in ("PAID", "UNPAID"):
            task.payment_status = status_norm
        else:
            raise ValidationError("Trạng thái thanh toán phải là PAID hoặc UNPAID.")
    else:
        task.payment_status = None
    db.session.commit()
    return ExpenseTaskAdapter(task)


# ---------------------------------------------------------------------------
# Actual records
# ---------------------------------------------------------------------------


def list_records(
    user_id: object,
    start: date,
    end: date,
    *,
    demo_only: bool = True,
    schedule_tag: str | None = None,
) -> list[ExpenseRecordAdapter]:
    user_uuid = to_uuid(user_id)
    query = (
        ExpenseRecord.query.join(
            BudgetMonth, ExpenseRecord.budget_month_id == BudgetMonth.id
        )
        .filter(
            BudgetMonth.user_id == user_uuid,
            ExpenseRecord.expense_date >= start,
            ExpenseRecord.expense_date <= end,
            ExpenseRecord.record_type.in_([RECORD_PLANNED, RECORD_UNEXPECTED]),
        )
    )
    if schedule_tag:
        query = (
            query.join(AssignedExpenseTask, ExpenseRecord.task_id == AssignedExpenseTask.id)
            .join(BudgetAllocation, AssignedExpenseTask.allocation_id == BudgetAllocation.id)
            .join(BudgetExpense, BudgetAllocation.budget_expense_id == BudgetExpense.id)
        )
        query = _apply_schedule_filter(query, schedule_tag)
    records = (
        query.order_by(
            ExpenseRecord.expense_date.desc(),
            ExpenseRecord.id.desc(),
        ).all()
    )
    return [ExpenseRecordAdapter(r) for r in records]


def planned_records_for_tasks(task_ids: list[object]) -> dict[str, ExpenseRecordAdapter]:
    """Return linked planned records for any task ids, including due-only tasks."""
    if not task_ids:
        return {}
    uuids = [to_uuid(tid) for tid in task_ids]
    records = ExpenseRecord.query.filter(
        ExpenseRecord.task_id.in_(uuids),
        ExpenseRecord.record_type == RECORD_PLANNED,
    ).all()
    return {str(record.task_id): ExpenseRecordAdapter(record) for record in records}


def _get_record(record_id: object, user_id: object) -> ExpenseRecord:
    rec_uuid = to_uuid(record_id)
    user_uuid = to_uuid(user_id)
    record = db.session.get(ExpenseRecord, rec_uuid)
    if (
        record is None
        or not record.budget_month
        or record.budget_month.user_id != user_uuid
    ):
        raise NotFoundError("Không tìm thấy giao dịch.")
    return record


def get_record(user_id: object, record_id: object) -> ExpenseRecordAdapter:
    return ExpenseRecordAdapter(_get_record(record_id, user_id))


def _idempotency_key(form) -> str | None:
    key = str(form.get("idempotency_key") or "").strip()
    if len(key) > 64:
        raise ValidationError("Mã chống trùng giao dịch tối đa 64 ký tự.")
    return key or None


def find_unexpected_by_idempotency(
    user_id: object, idempotency_key: str | None
) -> ExpenseRecordAdapter | None:
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 64:
        return None
    user_uuid = to_uuid(user_id)
    rec = (
        ExpenseRecord.query.join(
            BudgetMonth, ExpenseRecord.budget_month_id == BudgetMonth.id
        )
        .filter(
            BudgetMonth.user_id == user_uuid,
            ExpenseRecord.idempotency_key == key,
            ExpenseRecord.record_type == RECORD_UNEXPECTED,
        )
        .first()
    )
    return ExpenseRecordAdapter(rec) if rec is not None else None


def create_unexpected_record(user_id: object, form) -> ExpenseRecordAdapter:
    """Create an unexpected record once per client form token."""
    data = validate_record_form(form, require_title=True)
    key = _idempotency_key(form)
    if key:
        existing = find_unexpected_by_idempotency(user_id, key)
        if existing is not None:
            return existing

    user_uuid = to_uuid(user_id)
    _ensure_user(user_uuid)

    expense_date = data["expense_date"]
    month_start = date(expense_date.year, expense_date.month, 1)
    month = BudgetMonth.query.filter_by(
        user_id=user_uuid, month_start=month_start
    ).first()
    if month is None:
        month = BudgetMonth(
            user_id=user_uuid,
            month_start=month_start,
            tracking_start_date=month_start,
            available_vnd=0,
        )
        db.session.add(month)
        db.session.flush()

    cat_name = data["category"] or "Khác"
    cat = _find_or_create_category(user_uuid, cat_name)

    scope = str(form.get("budget_impact_scope") or "").strip().upper() or None
    if scope and scope not in ("DAILY", "WEEKLY", "MONTHLY"):
        scope = None

    priority = str(form.get("priority") or "").strip().upper() or "P1"
    if priority not in ("P0", "P1", "P2"):
        priority = "P1"

    record = ExpenseRecord(
        id=uuid.uuid4(),
        budget_month_id=month.id,
        task_id=None,
        category_id=cat.id,
        amount=data["amount"],
        expense_date=expense_date,
        record_type=RECORD_UNEXPECTED,
        priority=priority,
        title=data["title"],
        note=data["note"],
        budget_impact_scope=scope,
        idempotency_key=key,
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
    return ExpenseRecordAdapter(record)


def update_record(user_id: object, record_id: object, form) -> ExpenseRecordAdapter:
    record = _get_record(record_id, user_id)
    data = validate_record_form(
        form, require_title=record.record_type == RECORD_UNEXPECTED
    )
    user_uuid = to_uuid(user_id)
    new_date = data["expense_date"]

    # Re-link budget month if transaction date moved across calendar months
    if (new_date.year, new_date.month) != (
        record.expense_date.year,
        record.expense_date.month,
    ):
        target_month_start = date(new_date.year, new_date.month, 1)
        target_month = BudgetMonth.query.filter_by(
            user_id=user_uuid, month_start=target_month_start
        ).first()
        if target_month is None:
            target_month = BudgetMonth(
                user_id=user_uuid,
                month_start=target_month_start,
                tracking_start_date=target_month_start,
                available_vnd=0,
            )
            db.session.add(target_month)
            db.session.flush()
        record.budget_month_id = target_month.id

    record.amount = data["amount"]
    record.expense_date = new_date
    record.note = data["note"]
    if record.record_type == RECORD_UNEXPECTED:
        record.title = data["title"]

    if data["category"]:
        cat = _find_or_create_category(user_uuid, data["category"])
        record.category_id = cat.id

    if record.task is not None:
        record.task.task_status = "RECORDED"
    db.session.commit()
    return ExpenseRecordAdapter(record)


def delete_record(user_id: object, record_id: object) -> None:
    record = _get_record(record_id, user_id)
    task = record.task
    db.session.delete(record)
    if task is not None:
        remaining = [
            r
            for r in task.records
            if r.id != record.id and r.record_type == RECORD_PLANNED
        ]
        if not remaining:
            task.task_status = STATUS_PENDING
        else:
            task.task_status = "RECORDED"
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
        start = date(anchor.year, anchor.month, 1)
        last_day = calendar.monthrange(anchor.year, anchor.month)[1]
        end = date(anchor.year, anchor.month, last_day)
        label = f"Tháng {anchor.month:02d}/{anchor.year}"

    return Period(
        view=view, anchor=anchor, start=start, end=end, label=label
    )


@dataclass(frozen=True)
class CalendarDay:
    day: date
    task_count: int
    plan_total: int
    actual_total: int
    pending_count: int
    unrecorded_count: int
    confirmed_count: int


@dataclass(frozen=True)
class TaskEntry:
    task: ExpenseTaskAdapter
    assigned_in_period: bool
    due_in_period: bool


@dataclass(frozen=True)
class DayItemTotals:
    assigned_count: int
    due_only_count: int
    assigned_plan_total: int
    due_only_plan_total: int


def build_month_calendar(
    tasks: list[ExpenseTaskAdapter],
    records: list[ExpenseRecordAdapter],
    year: int,
    month: int,
) -> list[list[CalendarDay | None]]:
    """Build a standard Monday-to-Sunday matrix of real days in (year, month)."""
    tasks_by_day: dict[date, list[ExpenseTaskAdapter]] = defaultdict(list)
    records_by_day: dict[date, list[ExpenseRecordAdapter]] = defaultdict(list)
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
                plan_total=sum(task.current_limit for task in day_tasks),
                actual_total=sum(record.amount for record in day_records),
                pending_count=sum(
                    1 for task in day_tasks if get_task_status(task) == STATUS_PENDING
                ),
                unrecorded_count=sum(
                    1 for task in day_tasks if get_task_status(task) == STATUS_UNRECORDED
                ),
                confirmed_count=sum(
                    1
                    for task in day_tasks
                    if get_task_status(task) in CONFIRMED_STATUSES
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
        seen.add(str(task.id))

    for task in summary["due_tasks"]:  # type: ignore[union-attr]
        if str(task.id) not in seen:
            items.append(
                TaskEntry(
                    task=task,
                    assigned_in_period=False,
                    due_in_period=True,
                )
            )
            seen.add(str(task.id))

    def sort_key(entry: TaskEntry):
        due_only = 1 if (not entry.assigned_in_period and entry.due_in_period) else 0
        return (due_only, entry.task.priority, entry.task.title)

    return sorted(items, key=sort_key)


def summarize_day_items(items: list[TaskEntry]) -> DayItemTotals:
    assigned = [entry for entry in items if entry.assigned_in_period]
    due_only = [
        entry
        for entry in items
        if not entry.assigned_in_period and entry.due_in_period
    ]
    return DayItemTotals(
        assigned_count=len(assigned),
        due_only_count=len(due_only),
        assigned_plan_total=sum(entry.task.current_limit for entry in assigned),
        due_only_plan_total=sum(entry.task.current_limit for entry in due_only),
    )


def build_month_items(summary: dict[str, object]) -> list[TaskEntry]:
    """Return non-daily tasks and due-only obligations for month view."""
    items: list[TaskEntry] = []
    seen: set[str] = set()

    for task in summary["tasks"]:  # type: ignore[union-attr]
        if task.plan_item and task.plan_item.schedule_tag == "DAILY":
            continue
        items.append(
            TaskEntry(
                task=task,
                assigned_in_period=True,
                due_in_period=task.payment_due_date is not None,
            )
        )
        seen.add(str(task.id))

    for task in summary["due_tasks"]:  # type: ignore[union-attr]
        if str(task.id) not in seen:
            items.append(
                TaskEntry(
                    task=task,
                    assigned_in_period=False,
                    due_in_period=True,
                )
            )
            seen.add(str(task.id))

    return sorted(items, key=lambda entry: (entry.task.priority, entry.task.title))


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
    highlights: list[ExpenseTaskAdapter]


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


def build_year_months(
    summary: dict[str, object],
    year: int,
    *,
    schedule_tag: str | None = None,
) -> list[MonthCard]:
    """Group a filtered year summary into month cards without re-querying."""
    tasks_by_month: dict[int, list[ExpenseTaskAdapter]] = defaultdict(list)
    records_by_month: dict[int, list[ExpenseRecordAdapter]] = defaultdict(list)

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
        plan_total = sum(task.current_limit for task in month_tasks)
        actual_total = sum(record.amount for record in month_records)
        daily_count = sum(
            1
            for task in month_tasks
            if task.plan_item and task.plan_item.schedule_tag == "DAILY"
        )
        confirmed = sum(
            1
            for task in month_tasks
            if get_task_status(task) in CONFIRMED_STATUSES
        )

        if schedule_tag == "DAILY":
            highlights: list[ExpenseTaskAdapter] = []
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
    user_id: object,
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

    plan_total = sum(task.current_limit for task in tasks)
    actual_total = sum(record.amount for record in records)
    planned_by_task = {}
    task_uuids = [task.id for task in tasks]
    if task_uuids:
        linked_records = ExpenseRecord.query.filter(
            ExpenseRecord.task_id.in_(task_uuids),
            ExpenseRecord.record_type == RECORD_PLANNED,
        ).all()
        planned_by_task = {
            str(record.task_id): ExpenseRecordAdapter(record)
            for record in linked_records
        }

    counts = {
        "pending": sum(1 for task in tasks if get_task_status(task) == STATUS_PENDING),
        "unrecorded": sum(1 for task in tasks if get_task_status(task) == STATUS_UNRECORDED),
        "no_expense": sum(1 for task in tasks if get_task_status(task) == STATUS_NO_EXPENSE),
        "within": sum(
            1 for task in tasks if get_task_status(task) == STATUS_WITHIN_BUDGET
        ),
        "over": sum(1 for task in tasks if get_task_status(task) == STATUS_OVER_BUDGET),
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


def clear_demo_data(user_id: object) -> dict[str, int]:
    """Delete expense records owned by this user."""
    user_uuid = to_uuid(user_id)
    records = (
        ExpenseRecord.query.join(
            BudgetMonth, ExpenseRecord.budget_month_id == BudgetMonth.id
        )
        .filter(BudgetMonth.user_id == user_uuid)
        .all()
    )
    for record in records:
        db.session.delete(record)
    db.session.commit()
    return {
        "records": len(records),
        "tasks": 0,
        "items": 0,
    }
