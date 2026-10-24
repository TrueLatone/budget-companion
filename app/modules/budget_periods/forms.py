import re

from wtforms import IntegerField, StringField, SubmitField
from wtforms.validators import InputRequired, NumberRange, ValidationError

from app.forms import LocalizedForm
from app.i18n import translate


MAX_VND = 9_223_372_036_854_775_807


def valid_calendar_month(form, field):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", field.data or ""):
        raise ValidationError(translate("validation_calendar_month"))


class BudgetMonthCreateForm(LocalizedForm):
    label_keys = {
        "month": "budget_month_field",
        "available_vnd": "available_funds_field",
        "submit": "budget_create_submit",
    }

    month = StringField(
        "Calendar month",
        validators=[InputRequired(), valid_calendar_month],
    )
    available_vnd = IntegerField(
        "Available funds (VND)",
        validators=[InputRequired(), NumberRange(min=0, max=MAX_VND)],
    )
    submit = SubmitField("Create budget month")


class BudgetMonthUpdateForm(LocalizedForm):
    label_keys = {
        "available_vnd": "available_funds_field",
        "submit": "budget_save_submit",
    }

    available_vnd = IntegerField(
        "Available funds (VND)",
        validators=[InputRequired(), NumberRange(min=0, max=MAX_VND)],
    )
    submit = SubmitField("Save changes")
