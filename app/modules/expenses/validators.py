"""Server-side validation helpers for the expenses module.

HTML inputs are only a convenience; every value that reaches the service layer
is validated again here.
"""

import re
from datetime import date, datetime
from typing import Mapping

SCHEDULE_TAGS = ("DAILY", "WEEKLY", "MONTHLY", "DAY_OF_MONTH")
PRIORITIES = ("P0", "P1", "P2")
MAX_AMOUNT = 9_223_372_036_854_775_807
MAX_TITLE = 120
MAX_CATEGORY = 100


class ValidationError(ValueError):
    """Raised when user input or a state transition is invalid."""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_amount(raw: object, field: str = "Số tiền") -> int:
    """Parse a positive integer VND amount."""
    text = _text(raw)
    if not text:
        raise ValidationError(f"{field} không được để trống.")
    if not re.fullmatch(r"[0-9]+", text):
        raise ValidationError(f"{field} phải là số nguyên dương (VND).")
    text = text.lstrip("0") or "0"
    if len(text) > 19:
        raise ValidationError(f"{field} vượt giới hạn cho phép.")
    value = int(text)
    if value <= 0:
        raise ValidationError(f"{field} phải lớn hơn 0.")
    if value > MAX_AMOUNT:
        raise ValidationError(f"{field} vượt giới hạn cho phép.")
    return value


def parse_date(raw: object, field: str = "Ngày", required: bool = True) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date."""
    text = _text(raw)
    if not text:
        if required:
            raise ValidationError(f"{field} không được để trống.")
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise ValidationError(f"{field} phải dùng YYYY-MM-DD.")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError(f"{field} không đúng định dạng YYYY-MM-DD.") from exc


def parse_optional_date(raw: object, field: str = "Ngày") -> date | None:
    return parse_date(raw, field=field, required=False)


def parse_choice(raw: object, allowed: tuple[str, ...], field: str) -> str:
    text = _text(raw).upper()
    if text not in allowed:
        raise ValidationError(f"{field} không hợp lệ.")
    return text


def validate_record_form(
    form: Mapping[str, object], *, require_title: bool = False
) -> dict[str, object]:
    """Validate an actual/unexpected expense form."""
    title = _text(form.get("title"))
    if require_title and not title:
        raise ValidationError("Tên khoản chi không được để trống.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Tên khoản chi tối đa {MAX_TITLE} ký tự.")

    category = _text(form.get("category"))
    if len(category) > MAX_CATEGORY:
        raise ValidationError(f"Danh mục tối đa {MAX_CATEGORY} ký tự.")

    note = _text(form.get("note"))
    if len(note) > 2000:
        raise ValidationError("Ghi chú tối đa 2000 ký tự.")

    return {
        "amount": parse_amount(form.get("amount"), "Số tiền thực tế"),
        "expense_date": parse_date(form.get("expense_date"), "Ngày phát sinh"),
        "title": title or None,
        "category": category or None,
        "note": note or None,
    }
