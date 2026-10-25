"""The My budget preview is bilingual and stays separate from feature APIs."""

from html.parser import HTMLParser
import json

import pytest


class WorkspaceData(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.capture = False
        self.parts = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.capture = dict(attrs).get("id") == "workspace-data"

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False

    @property
    def value(self):
        return json.loads("".join(self.parts))


def test_budget_page_has_a_consistent_illustrative_plan(client):
    response = client.get("/budget")
    assert response.status_code == 200
    markup = response.get_data(as_text=True)
    data = WorkspaceData(markup).value
    assert data["page"] == "budget"
    assert data["month"] == "2026-11"
    plan = data["defaultPlan"]
    assert plan["available"] == 6_000_000
    assert sum(row["amount"] for row in plan["categories"]) == 4_900_000
    assert {row["group"] for row in plan["categories"]} == {"p0", "p1", "p2"}
    assert "Save budget" in markup
    assert "1,100,000" in markup


@pytest.mark.parametrize("language,label", [("en", "Set up your monthly budget"), ("vi", "Lập ngân sách cho tháng của bạn")])
def test_budget_uses_the_same_language_as_the_rest_of_the_site(client, language, label):
    response = client.get(f"/budget?lang={language}&month=2026-12")
    markup = response.get_data(as_text=True)
    data = WorkspaceData(markup).value
    assert response.status_code == 200
    assert data["locale"] == language
    assert data["month"] == "2026-12"
    assert label in markup
    assert f'lang="{language}"' in markup
    assert "month=2026-12" in markup


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "0000-01", "<script>alert(1)</script>"])
def test_bad_month_queries_fall_back_to_a_valid_month(client, month):
    response = client.get("/budget", query_string={"month": month})
    assert response.status_code == 200
    assert WorkspaceData(response.get_data(as_text=True)).value["month"] == "2026-11"


def test_budget_preview_does_not_accept_server_side_writes(client):
    assert client.post("/budget", json={"available": 1_000_000}).status_code == 405
