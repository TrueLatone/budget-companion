"""Calendar/display helpers selectively reused from KAN-8 c382f6c.

These adapters use canonical models; there is no alternate persistence layer.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import uuid

from app.models import AssignedExpenseTask, ExpenseCategory, ExpenseRecord
from app.modules.budgets.rules import meal_breakdown
from app.modules.expenses.validators import parse_optional_date

VN_TZ = timezone(timedelta(hours=7))
STATUS_PENDING = "PENDING"
STATUS_UNRECORDED = "UNRECORDED"
STATUS_NO_EXPENSE = "NO_EXPENSE"
STATUS_WITHIN_BUDGET = "WITHIN_BUDGET"
STATUS_OVER_BUDGET = "OVER_BUDGET"
RECORD_PLANNED = "PLANNED"
CONFIRMED_STATUSES = (STATUS_NO_EXPENSE, STATUS_WITHIN_BUDGET, STATUS_OVER_BUDGET)
VIEWS = ("day", "week", "month", "year")
UI_VIEWS = ("day", "month", "year")


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
    records = [r for r in raw_task.records if r.record_type == RECORD_PLANNED]
    if raw_task.task_status == STATUS_NO_EXPENSE:
        return STATUS_UNRECORDED if records else STATUS_NO_EXPENSE
    if records:
        total = sum(r.amount for r in records)
        limit = raw_task.current_limit
        return STATUS_WITHIN_BUDGET if total <= limit else STATUS_OVER_BUDGET
    if raw_task.task_status == "RECORDED":
        return STATUS_UNRECORDED  # Missing transactions remain unknown.

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
    def meal_guidance(self) -> dict[str, int] | None:
        """Optional display subdivisions of this Food task, never new tasks."""
        expense = self._task.allocation.budget_expense
        if expense.expense_name.strip().casefold() == "food" and expense.allocation_frequency == "DAILY":
            return meal_breakdown(self._task.current_limit)
        return None

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
        end = date.fromordinal(min(date.max.toordinal(), start.toordinal() + 6))
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
    daily_names: tuple[str, ...] = ()
    period_starts: tuple[str, ...] = ()
    continuing_count: int = 0
    due_count: int = 0
    record_count: int = 0
    no_expense_count: int = 0


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
    continuing_count: int = 0


def build_month_calendar(
    tasks: list[ExpenseTaskAdapter],
    records: list[ExpenseRecordAdapter],
    year: int,
    month: int,
) -> list[list[CalendarDay | None]]:
    """Display starts, active periods, due dates and actuals independently.

    plan_total and task_count count assignments once, on their start date.
    Repeated period/status indicators never repeat a financial allocation.
    """
    tasks_by_day: dict[date, list[ExpenseTaskAdapter]] = defaultdict(list)
    active_by_day: dict[date, list[ExpenseTaskAdapter]] = defaultdict(list)
    due_by_day: dict[date, list[ExpenseTaskAdapter]] = defaultdict(list)
    records_by_day: dict[date, list[ExpenseRecordAdapter]] = defaultdict(list)
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    for task in tasks:
        if task.assigned_date.year == year and task.assigned_date.month == month:
            tasks_by_day[task.assigned_date].append(task)
        begin, finish = max(first, task.assigned_date), min(last, task.period_end)
        for offset in range(max(0, (finish - begin).days + 1)):
            active_by_day[begin + timedelta(days=offset)].append(task)
        if task.payment_due_date and first <= task.payment_due_date <= last:
            due_by_day[task.payment_due_date].append(task)
    for record in records:
        if record.record_type in ("PLANNED", "UNEXPECTED") and first <= record.expense_date <= last:
            records_by_day[record.expense_date].append(record)

    weeks: list[list[CalendarDay | None]] = []
    week: list[CalendarDay | None] = [None] * first.weekday()

    for day_number in range(1, last_day + 1):
        day = date(year, month, day_number)
        day_tasks = tasks_by_day[day]
        day_records = records_by_day[day]
        visible = {str(task.id): task for task in active_by_day[day] + due_by_day[day]}
        statuses = [get_task_status(task) for task in visible.values()]
        week.append(
            CalendarDay(
                day=day,
                task_count=len(day_tasks),
                plan_total=sum(task.current_limit for task in day_tasks),
                actual_total=sum(record.amount for record in day_records),
                pending_count=statuses.count(STATUS_PENDING),
                unrecorded_count=statuses.count(STATUS_UNRECORDED),
                confirmed_count=sum(status in CONFIRMED_STATUSES for status in statuses),
                daily_names=tuple(task.title for task in day_tasks if task.schedule_tag == "DAILY"),
                period_starts=tuple(
                    f"{task.title}: {task.assigned_date.isoformat()} - {task.period_end.isoformat()}"
                    for task in day_tasks if task.schedule_tag != "DAILY"
                ),
                continuing_count=sum(task.assigned_date < day for task in active_by_day[day]),
                due_count=len(due_by_day[day]),
                record_count=len(day_records),
                no_expense_count=statuses.count(STATUS_NO_EXPENSE),
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
    summary: dict[str, object], selected_date: date, *, covering_tasks=(),
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

    # A continuing period is discoverable, but its full weekly/monthly limit
    # is not a new assignment to this day and does not enter the day total.
    for task in covering_tasks:
        if str(task.id) not in seen and task.assigned_date <= selected_date <= task.period_end:
            items.append(TaskEntry(task=task, assigned_in_period=False,
                                   due_in_period=task.payment_due_date == selected_date))
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
        continuing_count=sum(not entry.assigned_in_period and not entry.due_in_period for entry in items),
    )


def build_month_items(summary: dict[str, object]) -> list[TaskEntry]:
    """Return all assigned tasks once, including daily Food, plus due-only bills."""
    items: list[TaskEntry] = []
    seen: set[str] = set()

    for task in summary["tasks"]:  # type: ignore[union-attr]
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

    return sorted(items, key=lambda entry: (entry.task.priority, entry.task.title, entry.task.assigned_date))


@dataclass(frozen=True)
class MonthCard:
    """A month summary used by the year view."""

    month: int
    label: str
    start: date
    plan_total: int | None
    actual_total: int
    difference: int | None
    task_count: int
    daily_count: int
    confirmed: int
    unconfirmed: int
    highlights: list[ExpenseTaskAdapter]


def shift_month(anchor: date, delta: int) -> date:
    """Move by calendar months, clamping the day to the target month's last day."""
    total = max(0, min(9999 * 12 - 1, (anchor.year - 1) * 12 + (anchor.month - 1) + delta))
    year, month_index = divmod(total, 12)
    year += 1
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def shift_year(anchor: date, delta: int) -> date:
    """Move by calendar years, clamping 29 February to 28 February when needed."""
    year = max(1, min(9999, anchor.year + delta))
    last_day = calendar.monthrange(year, anchor.month)[1]
    return date(year, anchor.month, min(anchor.day, last_day))


def build_navigation(period: Period) -> dict[str, date]:
    """Return prev/next anchors for the active view and its calendar header."""
    anchor = period.anchor
    if period.view == "day":
        prev_anchor = date.fromordinal(max(1, anchor.toordinal() - 1))
        next_anchor = date.fromordinal(min(date.max.toordinal(), anchor.toordinal() + 1))
    elif period.view == "week":
        prev_anchor = date.fromordinal(max(1, anchor.toordinal() - 7))
        next_anchor = date.fromordinal(min(date.max.toordinal(), anchor.toordinal() + 7))
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
                plan_total=plan_total if month_tasks else None,
                actual_total=actual_total,
                difference=(plan_total - actual_total) if summary.get("month_complete", {}).get(month, False) else None,
                task_count=len(month_tasks),
                daily_count=daily_count,
                confirmed=confirmed,
                unconfirmed=len(month_tasks) - confirmed,
                highlights=highlights,
            )
        )
    return cards
