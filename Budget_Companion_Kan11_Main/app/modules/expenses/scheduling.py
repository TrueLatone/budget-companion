"""Confirmed monthly totals become periods, not repeated per-occurrence amounts."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.modules.budgets.rules import split_integer
from app.modules.expenses.validators import ValidationError, parse_amount


@dataclass(frozen=True)
class ScheduledPeriod:
    assigned_date: date
    period_end: date
    original_limit: int
    payment_due_date: date | None


def build_task_schedule(allocation, tracking_start_date):
    """Distribute the complete allocation over the tracked part of its month.

    Weeks run Monday–Sunday, clipped at tracking/month boundaries. A monthly
    bill keeps its actual due date, including an overdue date before tracking.
    is_recurring means future-month reuse; frequency defines these periods.
    """
    month = allocation.plan.budget_month
    expense = allocation.budget_expense
    if allocation.plan.status != "CONFIRMED" or expense.budget_month_id != month.id:
        raise ValidationError("Only confirmed allocations in the same month may be scheduled.")
    start = tracking_start_date
    if not isinstance(start, date) or start.replace(day=1) != month.month_start:
        raise ValidationError("Tracking must start within the allocation's month.")
    last_day = calendar.monthrange(start.year, start.month)[1]
    end = date(start.year, start.month, last_day)
    amount = parse_amount(allocation.allocated_amount, "Monthly allocation")
    periods = []
    cursor = start
    frequency = expense.allocation_frequency
    while cursor <= end:
        if frequency == "DAILY":
            period_end = cursor
        elif frequency == "WEEKLY":
            period_end = cursor + timedelta(days=min(6 - cursor.weekday(), (end - cursor).days))
        elif frequency == "MONTHLY":
            period_end = end
        else:
            raise ValidationError("Invalid canonical allocation frequency.")
        periods.append((cursor, period_end))
        if period_end == end:
            break
        cursor = period_end + timedelta(days=1)
    weights = [(finish - begin).days + 1 for begin, finish in periods]
    amounts = split_integer(amount, weights)
    due = None
    if frequency == "MONTHLY" and expense.due_day is not None:
        due = date(start.year, start.month, min(expense.due_day, last_day))
    return [ScheduledPeriod(begin, finish, limit, due) for (begin, finish), limit in zip(periods, amounts)]
