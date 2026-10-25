"""Server-side validation helpers for the expenses module.

HTML inputs are only a convenience; every value that reaches the service layer
is validated again here.
"""

import re
from datetime import date, datetime
from typing import Mapping

SCHEDULE_TAGS = ("DAILY", "WEEKLY", "MONTHLY", "DAY_OF_MONTH", "DATE")
PRIORITIES = ("P0", "P1", "P2")
AMOUNT_SOURCES = ("BUDGET_DEFAULT", "USER_ENTERED")
MAX_AMOUNT = 10**12
MAX_TITLE = 200
MAX_CATEGORY = 80


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


def parse_schedule_fields(
    schedule_tag: str,
    raw_day_of_week: object,
    raw_day_of_month: object,
    raw_specific_date: object,
) -> dict[str, object]:
    """Validate that only the fields relevant to the schedule tag are set."""
    day_of_week = None
    day_of_month = None
    specific_date = None

    if schedule_tag == "WEEKLY":
        text = _text(raw_day_of_week)
        if not re.fullmatch(r"[1-7]", text):
            raise ValidationError("Thứ trong tuần phải là 1 (thứ Hai) đến 7 (Chủ nhật).")
        day_of_week = int(text)
    elif schedule_tag == "DAY_OF_MONTH":
        text = _text(raw_day_of_month)
        if not re.fullmatch(r"([1-9]|[12][0-9]|3[01])", text):
            raise ValidationError("Ngày trong tháng phải nằm trong khoảng 1-31.")
        day_of_month = int(text)
    elif schedule_tag == "DATE":
        specific_date = parse_date(raw_specific_date, field="Ngày cụ thể")
    elif schedule_tag not in ("DAILY", "MONTHLY"):
        raise ValidationError("Kiểu lịch không hợp lệ.")

    return {
        "day_of_week": day_of_week,
        "day_of_month": day_of_month,
        "specific_date": specific_date,
    }


def validate_plan_item_form(form: Mapping[str, object]) -> dict[str, object]:
    """Validate the demo/source expense form and return normalized values."""
    title = _text(form.get("title"))
    if not title:
        raise ValidationError("Tên khoản chi không được để trống.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Tên khoản chi tối đa {MAX_TITLE} ký tự.")

    schedule_tag = parse_choice(form.get("schedule_tag"), SCHEDULE_TAGS, "Kiểu lịch")
    schedule_fields = parse_schedule_fields(
        schedule_tag,
        form.get("day_of_week"),
        form.get("day_of_month"),
        form.get("specific_date"),
    )

    return {
        "title": title,
        "planned_amount": parse_amount(form.get("planned_amount"), "Số tiền kế hoạch"),
        "amount_source": parse_choice(
            form.get("amount_source") or "USER_ENTERED",
            AMOUNT_SOURCES,
            "Nguồn số tiền",
        ),
        "priority": parse_choice(form.get("priority") or "P1", PRIORITIES, "Mức ưu tiên"),
        "schedule_tag": schedule_tag,
        **schedule_fields,
        "is_active": str(form.get("is_active", "1")).strip().lower()
        in ("1", "true", "on", "yes"),
    }


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

    return {
        "amount": parse_amount(form.get("amount"), "Số tiền thực tế"),
        "expense_date": parse_date(form.get("expense_date"), "Ngày phát sinh"),
        "title": title or None,
        "category": category or None,
        "note": note or None,
    }
