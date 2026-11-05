"""Server-side validation helpers for the expenses module.

HTML inputs are only a convenience; every value that reaches the service layer
is validated again here.
"""

import re
from datetime import date, datetime
from typing import Mapping

PRIORITIES = ("P0", "P1", "P2")
MAX_AMOUNT = 9_223_372_036_854_775_807
MAX_TITLE = 120
MAX_CATEGORY = 100


class ValidationError(ValueError):
    """Raised when user input or a state transition is invalid."""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_amount(raw: object, field: str = "Amount") -> int:
    """Parse a positive integer VND amount."""
    text = _text(raw)
    if not text:
        raise ValidationError(f"{field} is required.")
    if not re.fullmatch(r"[0-9]+", text):
        raise ValidationError(f"{field} must be a positive whole number (VND).")
    text = text.lstrip("0") or "0"
    if len(text) > 19:
        raise ValidationError(f"{field} exceeds the allowed limit.")
    value = int(text)
    if value <= 0:
        raise ValidationError(f"{field} must be greater than 0.")
    if value > MAX_AMOUNT:
        raise ValidationError(f"{field} exceeds the allowed limit.")
    return value


def parse_date(raw: object, field: str = "Date", required: bool = True) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date."""
    text = _text(raw)
    if not text:
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise ValidationError(f"{field} must use YYYY-MM-DD.")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid YYYY-MM-DD date.") from exc


def parse_optional_date(raw: object, field: str = "Date") -> date | None:
    return parse_date(raw, field=field, required=False)


def parse_choice(raw: object, allowed: tuple[str, ...], field: str) -> str:
    text = _text(raw).upper()
    if text not in allowed:
        raise ValidationError(f"{field} is invalid.")
    return text


def validate_record_form(
    form: Mapping[str, object], *, require_title: bool = False
) -> dict[str, object]:
    """Validate an actual/unexpected expense form."""
    title = _text(form.get("title"))
    if require_title and not title:
        raise ValidationError("A transaction title is required.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"The transaction title must be at most {MAX_TITLE} characters.")

    category = _text(form.get("category"))
    if len(category) > MAX_CATEGORY:
        raise ValidationError(f"The category must be at most {MAX_CATEGORY} characters.")

    note = _text(form.get("note"))
    if len(note) > 2000:
        raise ValidationError("The note must be at most 2000 characters.")

    return {
        "amount": parse_amount(form.get("amount"), "Actual amount"),
        "expense_date": parse_date(form.get("expense_date"), "Expense date"),
        "title": title or None,
        "category": category or None,
        "note": note or None,
    }
