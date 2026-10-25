"""Illustrative inputs for the browser-local My budget UI preview.

These are not confirmed plans, financial records, or Budget Planning APIs.
The feature owner can replace this presentation data when integration is ready.
"""

from copy import deepcopy
from datetime import date
import re

from flask import g, request, url_for

from app.translations import MESSAGES


DEFAULT_MONTH = "2026-11"
DEFAULT_PLAN = {
    "available": 6_000_000,
    "categories": [
        {"id": "rent", "labelKey": "cat_rent", "group": "p0", "amount": 2_000_000},
        {"id": "utilities", "labelKey": "cat_utilities", "group": "p0", "amount": 400_000},
        {"id": "food", "labelKey": "cat_food", "group": "p1", "amount": 1_500_000},
        {"id": "transport", "labelKey": "cat_transport", "group": "p1", "amount": 300_000},
        {"id": "study", "labelKey": "cat_study", "group": "p1", "amount": 200_000},
        {"id": "social", "labelKey": "cat_social", "group": "p2", "amount": 300_000},
        {"id": "shopping", "labelKey": "cat_shopping", "group": "p2", "amount": 200_000},
    ],
}
ENGLISH_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def selected_month(value):
    """Accept a calendar month only; malformed query values stay out of the UI."""
    if not value or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        return DEFAULT_MONTH
    try:
        date.fromisoformat(f"{value}-01")
    except ValueError:
        return DEFAULT_MONTH
    return value


def workspace_context():
    locale = g.ui_locale
    month = selected_month(request.args.get("month"))
    year, month_number = map(int, month.split("-"))
    copy = {
        key: value for key, value in MESSAGES[locale].items()
        if key.startswith(("ws_", "budget_", "group_", "cat_"))
    }
    plan = deepcopy(DEFAULT_PLAN)
    totals = {
        group: sum(item["amount"] for item in plan["categories"] if item["group"] == group)
        for group in ("p0", "p1", "p2")
    }
    totals["available"] = plan["available"]
    totals["planned"] = sum(totals[group] for group in ("p0", "p1", "p2"))
    totals["unallocated"] = plan["available"] - totals["planned"]
    category_labels = {}
    for item in plan["categories"]:
        category_labels[item["id"]] = copy[item["labelKey"]]
        category_labels[item["labelKey"]] = copy[item["labelKey"]]
    month_label = (
        f"Tháng {month_number} năm {year}" if locale == "vi"
        else f"{ENGLISH_MONTHS[month_number - 1]} {year}"
    )
    return {
        "active_page": "budget",
        "workspace_data": {
            "page": "budget", "locale": locale, "month": month,
            "defaultPlan": plan,
            "budgetUrl": url_for("budgets.index"),
        },
        "workspace_copy": copy,
        "month_label": month_label,
        "totals": totals,
        "group_labels": {group: copy[f"group_{group}"] for group in ("p0", "p1", "p2")},
        "category_labels": category_labels,
    }
