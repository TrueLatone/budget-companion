"""Data-source adapters for budget expense plan items.

Reads confirmed budget allocations and expenses from the shared database schema.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional, Protocol

from app.models import (
    BudgetAllocation,
    BudgetExpense,
    BudgetMonth,
    BudgetPlan,
)

ScheduleTag = Literal["DAILY", "WEEKLY", "MONTHLY", "DAY_OF_MONTH", "DATE"]


@dataclass(frozen=True)
class SourceExpense:
    """Normalized input contract representing an assigned budget expense."""

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
        self, user_id: object, period_start: date, period_end: date
    ) -> list[SourceExpense]: ...


class SharedBudgetSource:
    """Read active confirmed budget allocations owned by the user from shared models."""

    def list_expenses(
        self, user_id: object, period_start: date, period_end: date
    ) -> list[SourceExpense]:
        from app.modules.expenses.services import to_uuid

        user_uuid = to_uuid(user_id)
        allocations = (
            BudgetAllocation.query.join(
                BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id
            )
            .join(BudgetMonth, BudgetPlan.budget_month_id == BudgetMonth.id)
            .join(
                BudgetExpense,
                BudgetAllocation.budget_expense_id == BudgetExpense.id,
            )
            .filter(
                BudgetMonth.user_id == user_uuid,
                BudgetPlan.status == "CONFIRMED",
            )
            .all()
        )
        results: list[SourceExpense] = []
        for alloc in allocations:
            exp = alloc.budget_expense
            tag: ScheduleTag = "MONTHLY"
            if exp.allocation_frequency in ("DAILY", "WEEKLY", "MONTHLY"):
                tag = exp.allocation_frequency  # type: ignore[assignment]
            results.append(
                SourceExpense(
                    user_id=str(user_uuid),
                    expense_id=str(exp.id),
                    title=exp.expense_name,
                    amount_source="ALLOCATION",
                    amount=alloc.allocated_amount,
                    priority=exp.priority,
                    schedule_tag=tag,
                    day_of_month=exp.due_day,
                    plan_item_id=str(alloc.id),
                )
            )
        return results


def get_expense_source() -> ExpenseSource:
    """Return the active source backed by canonical shared database models."""
    return SharedBudgetSource()
