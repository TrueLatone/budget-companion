"""The dashboard is a coherent UI preview, not a new expense service."""

import json
import re
from datetime import date

import pytest

from app.translations import DASHBOARD_MESSAGES


def workspace_data(response):
    markup = response.get_data(as_text=True)
    match = re.search(r'<script type="application/json" id="workspace-data">(.*?)</script>', markup, re.S)
    assert match, "Missing safe workspace data payload"
    return json.loads(match.group(1))


def test_dashboard_illustration_reconciles_plan_and_recorded_expenses(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    data = workspace_data(response)
    records = data["dashboard"]["defaultRecords"]
    plan = data["defaultPlan"]
    planned = sum(row["amount"] for row in plan["categories"])
    spent = sum(row["amount"] for row in records)
    assert (planned, spent, planned - spent) == (4_900_000, 3_400_000, 1_500_000)
    assert plan["available"] - planned == 1_100_000
    assert len({row["id"] for row in records}) == len(records)
    assert {group: sum(row["amount"] for row in records if row["group"] == group)
            for group in ("p0", "p1", "p2")} == {"p0": 2_400_000, "p1": 800_000, "p2": 200_000}
    assert all(date.fromisoformat(row["date"]) < date.fromisoformat(data["dashboard"]["snapshotDate"])
               for row in records)
    assert data["dashboard"]["defaultNoExpenseDates"] == []
    markup = response.get_data(as_text=True)
    for percentage in ("58.8%", "11.8%", "17.6%"):
        assert percentage in markup
    assert "Remaining in plan" in markup


@pytest.mark.parametrize("month", ["2026-12", "2027-01"])
def test_other_months_never_inherit_november_expenses(client, month):
    response = client.get("/dashboard", query_string={"month": month})
    data = workspace_data(response)
    assert data["month"] == month
    assert data["dashboard"]["defaultRecords"] == []
    assert data["dashboard"]["snapshotDate"] == f"{month}-12"
    assert "3,400,000" not in response.get_data(as_text=True)


@pytest.mark.parametrize("locale,label", [("en", "Your month, at a glance."), ("vi", "Bạn đã chi vào đâu?")])
def test_dashboard_keeps_language_and_month_in_workspace_links(client, locale, label):
    response = client.get("/dashboard", query_string={"lang": locale, "month": "2026-12"})
    markup = response.get_data(as_text=True)
    assert label in markup
    assert f'lang="{locale}"' in markup
    assert 'href="/budget?month=2026-12"' in markup
    assert 'href="/dashboard?month=2026-12"' in markup
    assert 'id="db-donut"' in markup
    assert "dash_error_" not in re.sub(r"<script.*?</script>", "", markup, flags=re.S)


def test_invalid_month_query_is_not_reflected_in_dashboard_dates(client):
    response = client.get("/dashboard", query_string={"month": "<script>bad</script>"})
    assert response.status_code == 200
    assert workspace_data(response)["month"] == "2026-11"
    assert "<script>bad</script>" not in response.get_data(as_text=True)


def test_dashboard_remains_read_only_on_the_server(client):
    assert client.post("/dashboard", json={"amount": 100_000}).status_code == 405
    assert client.post("/api/expenses", json={"amount": 100_000}).status_code == 404


def test_dashboard_has_complete_translation_pairs():
    assert DASHBOARD_MESSAGES["en"].keys() == DASHBOARD_MESSAGES["vi"].keys()
