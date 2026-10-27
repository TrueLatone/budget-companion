"""Language choice must follow the visitor across public pages, not API calls."""

from html.parser import HTMLParser
from http.cookies import SimpleCookie

import pytest


class LanguageMarkup(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.locale = None
        self.selected_languages = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.locale = attrs.get("lang")
        if tag == "a" and attrs.get("hreflang") in {"en", "vi"}:
            if attrs.get("aria-current") == "true":
                self.selected_languages.append(attrs["hreflang"])


def assert_page_language(response, locale):
    assert response.status_code == 200
    markup = LanguageMarkup(response.get_data(as_text=True))
    assert markup.locale == locale
    assert markup.selected_languages == [locale]


def language_cookie(response):
    cookies = SimpleCookie()
    for header in response.headers.getlist("Set-Cookie"):
        cookies.load(header)
    return cookies.get("bc_language")


def test_english_is_default_without_persisting_an_unmade_choice(client):
    response = client.get("/")
    assert_page_language(response, "en")
    assert "Live independently," in response.get_data(as_text=True)
    assert language_cookie(response) is None


def test_vietnamese_choice_is_remembered_across_pages_and_refreshes(client):
    response = client.get("/?lang=vi")
    assert_page_language(response, "vi")
    assert "Đăng nhập" in response.get_data(as_text=True)
    cookie = language_cookie(response)
    assert cookie is not None
    assert cookie.value == "vi"
    assert int(cookie["max-age"]) == 365 * 24 * 60 * 60
    assert cookie["path"] == "/"

    assert_page_language(client.get("/budget"), "vi")
    assert_page_language(client.get("/"), "vi")


def test_explicit_choice_takes_precedence_and_can_switch_back_to_english(client):
    client.set_cookie("bc_language", "vi")

    response = client.get("/?lang=en")
    assert_page_language(response, "en")
    assert language_cookie(response).value == "en"
    assert_page_language(client.get("/expenses"), "en")


@pytest.mark.parametrize("path", ["/account", "/budget", "/expenses", "/dashboard", "/recommendations"])
def test_remembered_language_applies_to_all_module_pages(client, path):
    client.set_cookie("bc_language", "vi")
    response = client.get(path)
    assert_page_language(response, "vi")
    # Workspace pages share the language switch; unfinished modules use the public menu.
    translated_label = "Ngân sách của tôi" if path in {"/budget", "/dashboard"} else "Đăng nhập"
    assert translated_label in response.get_data(as_text=True)


@pytest.mark.parametrize("query", ["fr", "VI", "", "<script>alert(1)</script>"])
def test_unsupported_query_uses_existing_preference_without_overwriting_it(client, query):
    client.set_cookie("bc_language", "vi")
    response = client.get("/", query_string={"lang": query})
    assert_page_language(response, "vi")
    assert language_cookie(response) is None


@pytest.mark.parametrize("cookie_value", ["fr", "EN", "arbitrary-unsupported-language"])
def test_unsupported_cookie_falls_back_to_english(client, cookie_value):
    client.set_cookie("bc_language", cookie_value)
    response = client.get("/", query_string={"lang": "unsupported"})
    assert_page_language(response, "en")
    assert language_cookie(response) is None


@pytest.mark.parametrize("path", ["/api/health", "/api/health/database"])
def test_api_requests_do_not_change_language_preference(client, path):
    client.set_cookie("bc_language", "en")
    baseline = client.get(path)
    response = client.get(path, query_string={"lang": "vi"})
    assert response.status_code == baseline.status_code == 200
    assert response.json == baseline.json
    assert language_cookie(response) is None
    assert_page_language(client.get("/"), "en")


def test_api_query_does_not_create_a_preference_for_a_new_visitor(client):
    response = client.get("/api/health?lang=vi")
    assert response.json == {"status": "ok", "service": "budget-companion"}
    assert language_cookie(response) is None
    assert_page_language(client.get("/"), "en")
