"""Illustrative inputs for the browser-local budget and dashboard UI previews.

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


def workspace_context(page="budget"):
    locale = g.ui_locale
    month = selected_month(request.args.get("month"))
    year, month_number = map(int, month.split("-"))
    copy = {
        key: value for key, value in MESSAGES[locale].items()
        if key.startswith(("ws_", "budget_", "group_", "cat_", "dash_"))
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
    context = {
        "active_page": page,
        "workspace_data": {
            "page": page, "locale": locale, "month": month,
            "defaultPlan": plan,
            "budgetUrl": url_for("budgets.index"),
        },
        "workspace_copy": copy,
        "month_label": month_label,
        "totals": totals,
        "group_labels": {group: copy[f"group_{group}"] for group in ("p0", "p1", "p2")},
        "category_labels": category_labels,
    }
    if page == "dashboard":
        dashboard_data, dashboard_view = dashboard_preview(month, locale, copy, plan)
        context["workspace_data"]["dashboard"] = dashboard_data
        context["dashboard_view"] = dashboard_view
    return context


def dashboard_preview(month, locale, copy, plan):
    """One explicit sample snapshot, separate from actual expense module records."""
    sample_rows = (
        ("rent", "dash_record_rent", "rent", "p0", 1, 2_000_000),
        ("utilities", "dash_record_utilities", "utilities", "p0", 3, 400_000),
        ("food", "dash_record_food", "food", "p1", 5, 395_000),
        ("transport", "dash_record_transport", "transport", "p1", 8, 50_000),
        ("bus", "dash_record_bus", "transport", "p1", 10, 100_000),
        ("groceries", "dash_record_groceries", "food", "p1", 10, 160_000),
        ("lunch", "dash_record_lunch", "food", "p1", 11, 45_000),
        ("study", "dash_record_study", "study", "p1", 7, 50_000),
        ("social", "dash_record_social", "social", "p2", 6, 150_000),
        ("shopping", "dash_record_shopping", "shopping", "p2", 4, 50_000),
    )
    records = [
        {"id": f"demo_{row_id}", "titleKey": title_key, "categoryId": category,
         "group": group, "date": f"{month}-{day:02}", "amount": amount}
        for row_id, title_key, category, group, day, amount in sample_rows
    ] if month == DEFAULT_MONTH else []

    def percent(value, whole, digits=1):
        result = f"{(value / whole * 100) if whole else 0:.{digits}f}"
        return f"{result.replace('.', ',') if locale == 'vi' else result}%"

    def date_label(iso_date):
        year, number, day = map(int, iso_date.split("-"))
        return f"{day} thg {number}" if locale == "vi" else f"{day} {ENGLISH_MONTHS[number - 1][:3]}"

    spent = sum(record["amount"] for record in records)
    planned = sum(category["amount"] for category in plan["categories"])
    groups = []
    for group in ("p0", "p1", "p2"):
        used = sum(record["amount"] for record in records if record["group"] == group)
        group_plan = sum(category["amount"] for category in plan["categories"] if category["group"] == group)
        groups.append({"id": group, "label": copy[f"group_{group}"], "spent": used,
                       "planned": group_plan, "percent": percent(used, group_plan, 0)})

    breakdown = []
    for category, label_key, color, icon in (
        ("rent", "cat_rent", "#6358d5", "home"),
        ("utilities", "cat_utilities", "#b9b1ed", "wifi"),
        ("food", "cat_food", "#e8a18e", "utensils"),
        ("other", "dash_other", "#95c9b8", "bag"),
    ):
        amount = sum(record["amount"] for record in records if (
            record["categoryId"] == category if category != "other"
            else record["categoryId"] not in {"rent", "utilities", "food"}
        ))
        breakdown.append({"id": category, "labelKey": label_key, "amount": amount,
                          "percent": percent(amount, spent), "color": color, "icon": icon})

    icons = {"rent": "home", "utilities": "wifi", "food": "utensils", "transport": "bus",
             "study": "book", "social": "users", "shopping": "bag"}
    # Later same-date entries stay later in the illustrative feed.
    recent = sorted(enumerate(records), key=lambda item: (item[1]["date"], item[0]), reverse=True)
    visible_records = [{**record, "dateLabel": date_label(record["date"]),
                        "icon": icons.get(record["categoryId"], "receipt")}
                       for _, record in recent]
    snapshot_date = f"{month}-12"
    updated_through = f"{month}-11"
    return {
        "sampleMonth": DEFAULT_MONTH, "snapshotDate": snapshot_date,
        "updatedThrough": updated_through, "defaultRecords": records,
        "defaultNoExpenseDates": [], "budgetUrl": url_for("budgets.index"),
        "dashboardUrl": url_for("dashboard.index"),
    }, {
        "planned": planned, "spent": spent, "remaining": planned - spent,
        "spent_share": percent(spent, planned), "updated_label": date_label(updated_through),
        "snapshot_label": date_label(snapshot_date), "groups": groups,
        "breakdown": breakdown, "recent": visible_records[:3], "records": visible_records,
        "unallocated": plan["available"] - planned, "available": plan["available"],
    }
