"""Data-source adapters for expense plan items.

The demo adapter reads module-owned rows flagged ``is_demo``. When Budget/M1
publishes a real interface, implement ``M1BudgetSource`` and switch
``get_expense_source`` without changing scheduling/check-in business logic.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional, Protocol

from app.models.expense_planning import ExpensePlanItem

ScheduleTag = Literal["DAILY", "WEEKLY", "MONTHLY", "DAY_OF_MONTH", "DATE"]


@dataclass(frozen=True)
class SourceExpense:
    """Normalized input contract shared by the demo and M1 adapters."""

    user_id: str
    expense_id: str
    title: str
    amount_source: str
    amount: int
    priority: str
    schedule_tag: ScheduleTag
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    specific_date: Optional[date] = None
    plan_item_id: Optional[str] = None


class ExpenseSource(Protocol):
    def list_expenses(
        self, user_id: str, period_start: date, period_end: date
    ) -> list[SourceExpense]: ...


class DemoExpenseSource:
    """Read active demo plan items owned by the current user."""

    def list_expenses(
        self, user_id: str, period_start: date, period_end: date
    ) -> list[SourceExpense]:
        items = (
            ExpensePlanItem.query.filter_by(
                user_id=user_id, is_active=True, is_demo=True
            )
            .order_by(ExpensePlanItem.created_at.asc())
            .all()
        )
        return [
            SourceExpense(
                user_id=item.user_id,
                expense_id=item.source_expense_id or item.plan_item_id,
                title=item.title,
                amount_source=item.amount_source,
                amount=item.planned_amount,
                priority=item.priority,
                schedule_tag=item.schedule_tag,
                day_of_week=item.day_of_week,
                day_of_month=item.day_of_month,
                specific_date=item.specific_date,
                plan_item_id=item.plan_item_id,
            )
            for item in items
        ]


class M1BudgetSource:
    """Placeholder for the real Budget/M1 adapter.

    Do not fake network calls: M1 has not published an API yet
    (docs/api-contracts.md is still a proposal).
    """

    def list_expenses(
        self, user_id: str, period_start: date, period_end: date
    ) -> list[SourceExpense]:
        raise NotImplementedError(
            "M1 Budget API chưa sẵn sàng; dùng nguồn demo trong MVP."
        )


def get_expense_source() -> ExpenseSource:
    """Return the active source. MVP uses the isolated demo adapter."""
    return DemoExpenseSource()
