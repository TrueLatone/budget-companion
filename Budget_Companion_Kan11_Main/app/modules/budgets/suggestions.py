"""KAN-11 setup hints, never automatically seeded financial records."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SuggestedExpense:
    key: str
    name: str
    priority: str
    category: str
    frequency: str
    selected: bool = True
    example_amount: int | None = None
    example_due_day: int | None = None


# Amounts/due days come from KAN-11's loadSample(), not researched prices.
SUGGESTED_EXPENSES = (
    SuggestedExpense("rent", "Rent", "P0", "Housing", "MONTHLY", example_amount=1_500_000, example_due_day=5),
    SuggestedExpense("electricity", "Electricity", "P0", "Utilities", "MONTHLY", example_amount=200_000, example_due_day=12),
    SuggestedExpense("water", "Water", "P0", "Utilities", "MONTHLY", example_amount=100_000, example_due_day=12),
    SuggestedExpense("internet", "Internet", "P0", "Utilities", "MONTHLY", selected=False, example_amount=100_000, example_due_day=1),
    SuggestedExpense("food", "Food", "P1", "Food", "DAILY"),
    SuggestedExpense("transportation", "Transportation", "P1", "Transportation", "WEEKLY"),
)
