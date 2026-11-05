"""Routes and copy for the calendar-period UI, isolated from financial APIs."""
import json
import re
import pytest
from app.translations import PERIOD_MESSAGES


@pytest.mark.parametrize("locale,heading", [("en", "Create a monthly budget period"), ("vi", "Tạo kỳ ngân sách tháng")])
def test_period_creation_page_is_bilingual_and_keeps_workspace_navigation(client, locale, heading):
    response = client.get("/budget-periods", query_string={"lang": locale, "month": "2028-02"})
    assert response.status_code == 200
    markup = response.get_data(as_text=True)
    assert heading in markup
    assert 'id="period-month"' in markup and 'id="period-error"' in markup
    assert 'id="period-success"' in markup
    assert '/dashboard?month=2028-02' in markup
    match = re.search(r'id="workspace-data">(.*?)</script>', markup, re.S)
    data = json.loads(match.group(1))
    assert data["page"] == "periods" and data["month"] == "2028-02"
    assert data["dashboardUrl"] == "/dashboard"


def test_calendar_period_creation_does_not_add_a_mutating_feature_api(client):
    assert client.post("/budget-periods", json={"month": "2028-02"}).status_code == 405
    assert client.post("/api/budgets", json={"month": "2028-02"}).status_code == 404


def test_period_translation_pairs_are_complete():
    assert PERIOD_MESSAGES["en"].keys() == PERIOD_MESSAGES["vi"].keys()
