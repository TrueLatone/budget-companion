"""Shared form behavior for the manually translated server-rendered UI."""

from flask_wtf import FlaskForm

from app.i18n import translate


WTForms_MESSAGE_KEYS = {
    "This field is required.": "validation_required",
    "Invalid email address.": "validation_email",
    "Not a valid integer value.": "validation_integer",
    "Number must be between %(min)s and %(max)s.": "validation_number_range",
    "Field cannot be longer than %(max)d character.": "validation_length_max",
    "Field cannot be longer than %(max)d characters.": "validation_length_max",
    "Field must be between %(min)d and %(max)d characters long.": "validation_length_between",
    "Field must be equal to %(other_name)s.": "validation_equal",
    "Invalid input.": "validation_invalid",
    "The CSRF token is missing.": "validation_csrf_missing",
    "The CSRF token is invalid.": "validation_csrf_invalid",
    "The CSRF token has expired.": "validation_csrf_expired",
}


class _UITranslations:
    def gettext(self, message):
        key = WTForms_MESSAGE_KEYS.get(str(message))
        return translate(key) if key else str(message)

    def ngettext(self, singular, plural, number):
        message = singular if number == 1 else plural
        return self.gettext(message)


class LocalizedForm(FlaskForm):
    """Flask-WTF form whose labels and built-in errors use the active UI language."""

    label_keys = {}

    class Meta(FlaskForm.Meta):
        def get_translations(self, form):
            return _UITranslations()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, translation_key in self.label_keys.items():
            self[field_name].label.text = translate(translation_key)
