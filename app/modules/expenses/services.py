"""KAN-23: canonical Budget → schedule → transaction/check-in services.

All writes lock the owned BudgetMonth and commit atomically. Presentation and
calendar code is selectively reused from KAN-8; legacy models are never loaded.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import threading
import uuid

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AssignedExpenseTask, BudgetAllocation, BudgetExpense, BudgetMonth, BudgetPlan,
    ExpenseCategory, ExpenseRecord,
)
from app.modules.budgets import services as budgets
from app.modules.expenses.presentation import (
    CONFIRMED_STATUSES, UI_VIEWS, STATUS_PENDING, STATUS_UNRECORDED,
    STATUS_NO_EXPENSE, STATUS_WITHIN_BUDGET, STATUS_OVER_BUDGET,
    ExpenseRecordAdapter, ExpenseTaskAdapter, Period, build_day_items,
    build_due_items, build_month_calendar, build_month_items, build_navigation,
    build_year_months, get_task_status, now_utc, resolve_period,
    summarize_day_items, today_vn,
)
from app.modules.expenses.scheduling import build_task_schedule
from app.modules.expenses.validators import (
    ValidationError, parse_amount, parse_choice, parse_optional_date,
    validate_record_form,
)

RECORD_PLANNED = "PLANNED"
RECORD_UNEXPECTED = "UNEXPECTED"


class NotFoundError(LookupError):
    """Missing, malformed or unauthorized canonical resource."""


class ExpenseConflict(ValidationError):
    """A replay or saved schedule conflicts with current financial data."""


_inflight_lock = threading.Lock()
_inflight_keys: set[tuple] = set()


@contextmanager
def _single_flight(key):
    """Reject a concurrent identical write, while allowing later legitimate repeats."""
    with _inflight_lock:
        if key in _inflight_keys:
            raise ExpenseConflict(
                "This action is already being processed. Wait for it to finish before submitting again."
            )
        _inflight_keys.add(key)
    try:
        yield
    finally:
        with _inflight_lock:
            _inflight_keys.discard(key)


def _payload_key(*values):
    return tuple("" if value is None else str(value).strip() for value in values)


def to_uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise NotFoundError("Expense resource not found.") from None


def resolve_current_user_id():
    from flask import abort, g

    user = getattr(g, "current_user", None)
    if user is None:
        abort(401)
    return user.id


def get_month(user_id, month_id):
    try:
        return budgets.get_month(to_uuid(user_id), to_uuid(month_id))
    except budgets.BudgetNotFound:
        raise NotFoundError("Budget month not found.") from None


def find_month(user_id, anchor):
    return db.session.scalar(db.select(BudgetMonth).where(
        BudgetMonth.user_id == to_uuid(user_id), BudgetMonth.month_start == anchor.replace(day=1),
    ))


@contextmanager
def _write_month(user_id, month_id):
    try:
        month = budgets.get_month(to_uuid(user_id), to_uuid(month_id), lock=True)
        yield month
        db.session.commit()
    except budgets.BudgetNotFound:
        db.session.rollback()
        raise NotFoundError("Budget month not found.") from None
    except IntegrityError as exc:
        db.session.rollback()
        raise ExpenseConflict("A concurrent write changed the expense data. Reload and retry using the same token.") from exc
    except Exception:
        db.session.rollback()
        raise


def ensure_tasks_for_month(user_id, month_id):
    """Repeat-safe scheduling; never overwrite actuals, adjustments or statuses."""
    with _write_month(user_id, month_id) as month:
        allocations = budgets.get_confirmed_allocations(user_id, month.id)
        if not allocations:
            raise ValidationError("Confirm a budget plan before creating its spending schedule.")
        tasks = []
        for allocation in allocations:
            expected = build_task_schedule(allocation, month.tracking_start_date)
            existing = list(db.session.scalars(db.select(AssignedExpenseTask).where(
                AssignedExpenseTask.allocation_id == allocation.id,
            ).execution_options(populate_existing=True)))
            by_date = {task.assigned_date: task for task in existing}
            if set(by_date) - {item.assigned_date for item in expected}:
                raise ExpenseConflict("Existing task dates differ from this confirmed schedule.")
            for item in expected:
                task = by_date.get(item.assigned_date)
                if task is not None:
                    if (task.period_end, task.original_limit, task.payment_due_date) != (
                        item.period_end, item.original_limit, item.payment_due_date,
                    ):
                        raise ExpenseConflict("Existing task limits or periods differ; original schedules cannot be overwritten.")
                else:
                    task = AssignedExpenseTask(
                        allocation_id=allocation.id, assigned_date=item.assigned_date,
                        period_end=item.period_end, original_limit=item.original_limit,
                        current_limit=item.original_limit, task_status="PENDING",
                        payment_due_date=item.payment_due_date,
                        payment_status="UNPAID" if item.payment_due_date else None,
                    )
                    db.session.add(task)
                tasks.append(task)
            if sum(item.original_limit for item in expected) != allocation.allocated_amount:
                raise ExpenseConflict("The schedule must conserve its complete monthly allocation.")
        db.session.flush()
    return tasks


@dataclass(frozen=True)
class ScheduleState:
    code: str
    message: str
    can_schedule: bool = False
    plan_id: uuid.UUID | None = None


def get_schedule_state(user_id, month_id):
    """Read-only diagnosis of the owned month's Budget-to-Expense handoff."""
    month = get_month(user_id, month_id)
    expenses = budgets.list_expenses(user_id, month.id)
    plans = budgets.list_plans(user_id, month.id)
    confirmed = next((plan for plan in plans if plan.status == "CONFIRMED"), None)
    if confirmed is None:
        if not expenses:
            return ScheduleState("NO_EXPENSES", "No budget expenses or plan exist. Add expenses in Budget setup first.")
        if not plans:
            return ScheduleState("NO_PLAN", "No budget plan exists. Generate plans in Budget setup first.")
        return ScheduleState("UNCONFIRMED", "No confirmed plan exists. Review and confirm a saved Budget plan first.")
    allocations = budgets.get_confirmed_allocations(user_id, month.id)
    if not allocations:
        return ScheduleState("NO_ALLOCATIONS", "The confirmed plan has no allocations to schedule. Review the saved Budget plan.", plan_id=confirmed.id)
    # Allocation IDs have already been authorized through the confirmed Budget
    # service. Inspect stored rows so filtering cannot make a conflicting
    # schedule look like one that has never been created. This is a read-only
    # conservation check; Expense never rebuilds recurrence schedules.
    tasks = list(db.session.scalars(db.select(AssignedExpenseTask).where(
        AssignedExpenseTask.allocation_id.in_([allocation.id for allocation in allocations]),
    )))
    if not tasks:
        return ScheduleState("NOT_SCHEDULED", "Your plan is confirmed, but no AssignedExpenseTask exists yet. Budget must create the spending schedule upstream; Expense only displays existing tasks.", plan_id=confirmed.id)
    if any(task.assigned_date < month.tracking_start_date for task in tasks):
        return ScheduleState("CONFLICT", "Saved task dates or original limits differ from the confirmed plan. Expense will not overwrite them; review the saved plan.", plan_id=confirmed.id)
    totals = {}
    for task in tasks:
        totals[task.allocation_id] = totals.get(task.allocation_id, 0) + task.original_limit
    for allocation in allocations:
        total = totals.get(allocation.id, 0)
        if total > allocation.allocated_amount:
            return ScheduleState("CONFLICT", "Saved task dates or original limits differ from the confirmed plan. Expense will not overwrite them; review the saved plan.", plan_id=confirmed.id)
        if total < allocation.allocated_amount:
            return ScheduleState("INCOMPLETE", "Some scheduled tasks are missing. Budget must complete the schedule; Expense will not generate missing tasks.", plan_id=confirmed.id)
    return ScheduleState("READY", "Spending schedule ready. Select a calendar date for daily expenses and active weekly/monthly periods.", True, confirmed.id)


def _task_statement(user_id):
    return (
        db.select(AssignedExpenseTask)
        .join(BudgetAllocation, AssignedExpenseTask.allocation_id == BudgetAllocation.id)
        .join(BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id)
        .join(BudgetMonth, BudgetPlan.budget_month_id == BudgetMonth.id)
        .join(BudgetExpense, BudgetAllocation.budget_expense_id == BudgetExpense.id)
        .join(ExpenseCategory, BudgetExpense.category_id == ExpenseCategory.id)
        .where(
            BudgetMonth.user_id == to_uuid(user_id), BudgetPlan.status == "CONFIRMED",
            BudgetExpense.budget_month_id == BudgetMonth.id,
            AssignedExpenseTask.assigned_date >= BudgetMonth.tracking_start_date,
            db.extract("year", AssignedExpenseTask.period_end) == db.extract("year", BudgetMonth.month_start),
            db.extract("month", AssignedExpenseTask.period_end) == db.extract("month", BudgetMonth.month_start),
            db.or_(ExpenseCategory.user_id == BudgetMonth.user_id, ExpenseCategory.user_id.is_(None)),
        )
    )


def _get_task(task_id, user_id):
    task = db.session.scalar(_task_statement(user_id).where(
        AssignedExpenseTask.id == to_uuid(task_id),
    ).execution_options(populate_existing=True))
    if task is None:
        raise NotFoundError("Task not found.")
    db.session.expire(task, ["records"])
    return task


def get_task(user_id, task_id):
    return ExpenseTaskAdapter(_get_task(task_id, user_id))


def list_tasks(user_id, start, end):
    statement = _task_statement(user_id).where(
        AssignedExpenseTask.assigned_date >= start, AssignedExpenseTask.assigned_date <= end,
    )
    return [ExpenseTaskAdapter(task) for task in db.session.scalars(statement.order_by(
        AssignedExpenseTask.assigned_date, BudgetExpense.priority, AssignedExpenseTask.id,
    ))]


def list_due_tasks(user_id, start, end):
    statement = _task_statement(user_id).where(
        AssignedExpenseTask.payment_due_date >= start, AssignedExpenseTask.payment_due_date <= end,
    )
    return [ExpenseTaskAdapter(task) for task in db.session.scalars(statement.order_by(
        AssignedExpenseTask.payment_due_date, AssignedExpenseTask.id,
    ))]


def _valid_date(month, expense_date, task=None):
    if expense_date.replace(day=1) != month.month_start or expense_date < month.tracking_start_date:
        raise ValidationError("The transaction date must belong to this month's tracking interval.")
    if expense_date > today_vn():
        raise ValidationError("Future spending cannot be recorded.")
    if task and not task.assigned_date <= expense_date <= task.period_end:
        raise ValidationError("The transaction date must be within the task's assigned period.")


def list_categories(user_id):
    """Read-only list of categories this user may reference."""
    return budgets.list_categories(to_uuid(user_id))


def _category(user_id, value, *, default_id=None):
    """Resolve an existing owned/built-in category. Expense never creates categories."""
    owner = to_uuid(user_id)
    text = str(value or "").strip()
    if not text:
        if default_id is None:
            raise ValidationError("Choose an existing category.")
        category = db.session.get(ExpenseCategory, default_id)
    else:
        try:
            category = db.session.get(ExpenseCategory, uuid.UUID(text))
        except (ValueError, TypeError, AttributeError):
            category = db.session.scalar(db.select(ExpenseCategory).where(
                db.or_(ExpenseCategory.user_id == owner, ExpenseCategory.user_id.is_(None)),
                db.func.lower(db.func.trim(ExpenseCategory.category_name)) == text.lower(),
            ))
    if category is None or category.user_id not in (None, owner):
        raise ValidationError("Choose an existing category.")
    return category


def _recalculate_task_status(task):
    """Persist only canonical task_status values after record changes."""
    total = db.session.scalar(db.select(db.func.count(ExpenseRecord.id)).where(
        ExpenseRecord.task_id == task.id, ExpenseRecord.record_type == "PLANNED",
    ))
    task.task_status = "RECORDED" if total else "PENDING"
    return task.task_status


def checkin_task(user_id, task_id, *, action, amount_raw=None, expense_date_raw=None,
                 category=None, note=None, title=None, on_created=None):
    key = ("checkin", str(user_id), str(task_id)) + _payload_key(
        action, amount_raw, expense_date_raw, category, note, title,
    )
    created_id = None
    with _single_flight(key):
        task = _get_task(task_id, user_id)
        month_id = task.allocation.plan.budget_month_id
        with _write_month(user_id, month_id) as month:
            task = _get_task(task_id, user_id)
            if task.assigned_date > today_vn():
                raise ValidationError("Future tasks cannot be checked in.")
            if action == "no_expense":
                if any(record.record_type == "PLANNED" for record in task.records):
                    raise ExpenseConflict("This task has actual transactions. Remove or correct them before confirming NO_EXPENSE.")
                task.task_status = "NO_EXPENSE"
            else:
                if action not in {"planned", "actual"}:
                    raise ValidationError("Choose planned, actual or no_expense.")
                if action == "planned":
                    if any(record.record_type == "PLANNED" for record in task.records):
                        raise ExpenseConflict("This task already has spending. Add a separate actual purchase or edit a transaction.")
                    if task.current_limit <= 0:
                        raise ValidationError("CurrentLimit is zero. Enter a positive actual amount or choose no expense.")
                amount = parse_amount(task.current_limit if action == "planned" else amount_raw)
                expense_date = parse_optional_date(expense_date_raw) or task.assigned_date
                _valid_date(month, expense_date, task)
                category_row = _category(user_id, category, default_id=task.allocation.budget_expense.category_id)
                clean_note = str(note or "").strip() or None
                if clean_note and len(clean_note) > 2000:
                    raise ValidationError("Notes must be at most 2000 characters.")
                clean_title = str(title or "").strip() or task.allocation.budget_expense.expense_name
                if len(clean_title) > 120:
                    raise ValidationError("Titles must be at most 120 characters.")
                record = ExpenseRecord(
                    budget_month_id=month.id, task_id=task.id, record_type="PLANNED",
                    amount=amount, expense_date=expense_date, category_id=category_row.id,
                    priority=None, title=clean_title,
                    note=clean_note, budget_impact_scope=None,
                )
                db.session.add(record)
                db.session.flush()
                created_id = record.id
                task.task_status = "RECORDED"
    if created_id is not None and on_created is not None:
        on_created(created_id)
    return ExpenseTaskAdapter(task)


def set_payment_status(user_id, task_id, status):
    task = _get_task(task_id, user_id)
    with _write_month(user_id, task.allocation.plan.budget_month_id):
        task = _get_task(task_id, user_id)
        if task.payment_due_date is None:
            raise ValidationError("Only bill tasks have a payment status.")
        task.payment_status = parse_choice(status, ("PAID", "UNPAID"), "Payment status")
    return ExpenseTaskAdapter(task)


def _get_record(record_id, user_id):
    record = db.session.scalar(db.select(ExpenseRecord).join(BudgetMonth).where(
        ExpenseRecord.id == to_uuid(record_id), BudgetMonth.user_id == to_uuid(user_id),
        ExpenseRecord.record_type.in_(("PLANNED", "UNEXPECTED")),
    ).execution_options(populate_existing=True))
    if record is None:
        raise NotFoundError("Spending record not found.")
    if record.category is None or record.category.user_id not in (None, to_uuid(user_id)):
        raise NotFoundError("Spending category not found.")
    if record.task_id is not None:
        task = _get_task(record.task_id, user_id)
        if task.allocation.plan.budget_month_id != record.budget_month_id:
            raise ExpenseConflict("A transaction and its task must belong to the same month.")
    _valid_date(record.budget_month, record.expense_date, record.task)
    return record


def get_record(user_id, record_id):
    return ExpenseRecordAdapter(_get_record(record_id, user_id))


def list_records(user_id, start, end):
    statement = db.select(ExpenseRecord).join(BudgetMonth).where(
        BudgetMonth.user_id == to_uuid(user_id), ExpenseRecord.expense_date >= start,
        ExpenseRecord.expense_date <= end, ExpenseRecord.record_type.in_(("PLANNED", "UNEXPECTED")),
    )
    records = []
    for record in db.session.scalars(statement.order_by(ExpenseRecord.expense_date, ExpenseRecord.id)):
        record = _get_record(record.id, user_id)
        records.append(ExpenseRecordAdapter(record))
    return records


def _parse_scope(raw):
    scope = str(raw or "").strip().upper() or None
    if scope is not None and scope not in {"DAILY", "WEEKLY", "MONTHLY"}:
        raise ValidationError("Invalid budget impact scope.")
    return scope


def create_unexpected_record(user_id, form, *, on_created=None):
    key = ("unexpected", str(user_id)) + _payload_key(
        form.get("budget_month_id"), form.get("amount"), form.get("expense_date"),
        form.get("title"), form.get("category"), form.get("priority"),
        form.get("budget_impact_scope"), form.get("note"),
    )
    created_id = None
    with _single_flight(key):
        month_id = form.get("budget_month_id")
        with _write_month(user_id, month_id) as month:
            data = validate_record_form(form, require_title=True)
            _valid_date(month, data["expense_date"])
            priority = parse_choice(form.get("priority"), ("P0", "P1", "P2"), "Priority")
            scope = _parse_scope(form.get("budget_impact_scope"))
            category = _category(user_id, data["category"])
            record = ExpenseRecord(
                budget_month_id=month.id, task_id=None, record_type="UNEXPECTED",
                amount=data["amount"], expense_date=data["expense_date"], title=data["title"],
                note=data["note"], category_id=category.id, priority=priority,
                budget_impact_scope=scope,
            )
            db.session.add(record)
            db.session.flush()
            created_id = record.id
    if on_created is not None:
        on_created(created_id)
    return ExpenseRecordAdapter(record)


def update_record(user_id, record_id, form):
    key = ("update", str(user_id), str(record_id)) + _payload_key(
        form.get("amount"), form.get("expense_date"), form.get("title"),
        form.get("category"), form.get("priority"), form.get("budget_impact_scope"),
        form.get("note"),
    )
    with _single_flight(key):
        record = _get_record(record_id, user_id)
        with _write_month(user_id, record.budget_month_id) as month:
            record = _get_record(record_id, user_id)
            data = validate_record_form(form, require_title=record.record_type == "UNEXPECTED")
            _valid_date(month, data["expense_date"], record.task)
            category = _category(user_id, data["category"], default_id=record.category_id)
            record.amount = data["amount"]
            record.expense_date = data["expense_date"]
            record.note = data["note"]
            record.category_id = category.id
            if record.record_type == "UNEXPECTED":
                record.title = data["title"]
                record.priority = parse_choice(form.get("priority"), ("P0", "P1", "P2"), "Priority")
                record.budget_impact_scope = _parse_scope(form.get("budget_impact_scope"))
            elif data["title"]:
                record.title = data["title"]
            if record.task:
                _recalculate_task_status(record.task)
    return ExpenseRecordAdapter(record)


def delete_record(user_id, record_id):
    record = _get_record(record_id, user_id)
    with _write_month(user_id, record.budget_month_id):
        record = _get_record(record_id, user_id)
        task = record.task if record.task_id else None
        db.session.delete(record)
        db.session.flush()
        if task is not None:
            db.session.expire(task, ["records"])
            _recalculate_task_status(task)


@dataclass
class TaskSpending:
    """Aggregate all task transactions; delegate edit metadata to the latest."""
    records: list

    @property
    def amount(self):
        return sum(record.amount for record in self.records)

    def __getattr__(self, name):
        return getattr(self.records[-1], name)


def planned_records_for_tasks(user_id, task_ids):
    grouped = {}
    for task_id in task_ids:
        task = _get_task(task_id, user_id)
        records = sorted([ExpenseRecordAdapter(_get_record(record.id, user_id)) for record in task.records if record.record_type == "PLANNED"],
                         key=lambda record: (record.expense_date, record.id))
        if records:
            grouped[str(task.id)] = TaskSpending(records)
    return grouped


def refresh_unrecorded(user_id, *, now=None):
    return sum(get_task_status(task, now=now) == STATUS_UNRECORDED
               for task in db.session.scalars(_task_statement(user_id)))


def _complete_period(user_id, period, tasks, records):
    """A known balance requires complete schedules and matching date coverage."""
    if not tasks or any(get_task_status(task) not in CONFIRMED_STATUSES for task in tasks):
        return False
    task_ids = {task.id for task in tasks}
    if any(record.task_id and record.task_id not in task_ids for record in records):
        return False
    if any(not period.start <= record.expense_date <= period.end for task in tasks
           for record in task.records if record.record_type == "PLANNED"):
        return False
    months = list(db.session.scalars(db.select(BudgetMonth).where(
        BudgetMonth.user_id == to_uuid(user_id), BudgetMonth.month_start >= period.start.replace(day=1),
        BudgetMonth.month_start <= period.end.replace(day=1),
    )))
    month_count = (period.end.year - period.start.year) * 12 + period.end.month - period.start.month + 1
    if len(months) != month_count:
        return False
    for month in months:
        allocations = budgets.get_confirmed_allocations(user_id, month.id)
        if not allocations:
            return False
        month_tasks = [
            task for task in tasks
            if task.assigned_date.year == month.month_start.year
            and task.assigned_date.month == month.month_start.month
        ]
        totals = {}
        for task in month_tasks:
            allocation_id = task.raw_task.allocation_id
            totals[allocation_id] = totals.get(allocation_id, 0) + task.original_limit
        if any(totals.get(allocation.id, 0) != allocation.allocated_amount for allocation in allocations):
            return False
    return True


def build_summary(user_id, period):
    tasks = list_tasks(user_id, period.start, period.end)
    due_tasks = list_due_tasks(user_id, period.start, period.end)
    records = list_records(user_id, period.start, period.end)
    counts = {name: sum(get_task_status(task) == status for task in tasks) for name, status in (
        ("pending", STATUS_PENDING), ("unrecorded", STATUS_UNRECORDED),
        ("no_expense", STATUS_NO_EXPENSE), ("within", STATUS_WITHIN_BUDGET), ("over", STATUS_OVER_BUDGET),
    )}
    plan_total = sum(task.current_limit for task in tasks) if tasks else None
    actual_total = sum(record.amount for record in records)  # Observed spending only.
    complete = _complete_period(user_id, period, tasks, records)
    month_complete = {}
    if period.view == "year":
        for number in range(1, 13):
            monthly = resolve_period("month", date(period.anchor.year, number, 1).isoformat())
            month_complete[number] = _complete_period(user_id, monthly,
                [task for task in tasks if task.assigned_date.month == number],
                [record for record in records if record.expense_date.month == number])
    return dict(
        period=period, tasks=tasks, due_tasks=due_tasks, records=records, plan_total=plan_total,
        actual_total=actual_total, difference=plan_total - actual_total if complete else None,
        counts=counts, confirmed=counts["no_expense"] + counts["within"] + counts["over"],
        unconfirmed=counts["pending"] + counts["unrecorded"], data_complete=complete,
        month_complete=month_complete,
        unexpected_records=[record for record in records if record.record_type == "UNEXPECTED"],
        planned_by_task=planned_records_for_tasks(user_id, [task.id for task in tasks]),
    )
