"""Small, server-rendered language preferences for the current web UI."""

from urllib.parse import urlencode

from flask import g, has_request_context, request

from app.translations import MESSAGES


SUPPORTED_LANGUAGES = ("en", "vi")
DEFAULT_LANGUAGE = "en"
LANGUAGE_COOKIE = "bc_language"


def get_ui_language():
    """Return the selected UI language, or English outside a request."""

    if has_request_context():
        return getattr(g, "ui_locale", DEFAULT_LANGUAGE)
    return DEFAULT_LANGUAGE


def translate(key, language=None):
    """Translate one application message with an English fallback."""

    locale = language if language in SUPPORTED_LANGUAGES else get_ui_language()
    return MESSAGES[locale].get(key, MESSAGES[DEFAULT_LANGUAGE].get(key, key))


def format_money(amount, language=None):
    grouped = f"{amount:,}"
    locale = language if language in SUPPORTED_LANGUAGES else get_ui_language()
    return grouped.replace(",", ".") if locale == "vi" else grouped


def format_month(value, language=None):
    """Format a date-like value as a localized month and year."""

    return f"{translate(f'month_{value.month}', language)} {value.year}"


def register_ui_languages(app):
    """Expose translations to templates without changing feature/API routes."""

    @app.before_request
    def select_ui_language():
        requested = request.args.get("lang")
        remembered = request.cookies.get(LANGUAGE_COOKIE)
        g.ui_locale = (
            requested if requested in SUPPORTED_LANGUAGES
            else remembered if remembered in SUPPORTED_LANGUAGES
            else DEFAULT_LANGUAGE
        )

    @app.context_processor
    def ui_language_context():
        def language_url(language):
            # Use only the current local path; keep existing query parameters.
            parameters = request.args.to_dict(flat=False)
            parameters["lang"] = [language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE]
            return f"{request.path}?{urlencode(parameters, doseq=True)}"

        return {
            "ui_locale": g.ui_locale,
            "t": translate,
            "language_url": language_url,
            "money": format_money,
            "month_name": format_month,
        }

    @app.after_request
    def remember_ui_language(response):
        requested = request.args.get("lang")
        if (
            request.method == "GET"
            and not request.path.startswith("/api/")
            and requested in SUPPORTED_LANGUAGES
            and response.mimetype == "text/html"
            and 200 <= response.status_code < 400
        ):
            response.set_cookie(
                LANGUAGE_COOKIE,
                requested,
                max_age=365 * 24 * 60 * 60,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
            )
        return response
