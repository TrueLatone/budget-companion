import re
from datetime import datetime

from wtforms import DateField, IntegerField, StringField, SubmitField
from wtforms.validators import InputRequired, NumberRange, Optional, ValidationError

from app.forms import LocalizedForm
from app.i18n import translate


MAX_VND = 9_223_372_036_854_775_807


def valid_calendar_month(form, field):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", field.data or ""):
        raise ValidationError(translate("validation_calendar_month"))
    try:
        datetime.strptime(field.data, "%Y-%m")
    except ValueError as exc:
        raise ValidationError(translate("validation_calendar_month")) from exc


def tracking_date_within_month(form, field):
    if field.data is None:
        return  # DateField reports malformed dates.
    try:
        month_start = datetime.strptime(form.month.data, "%Y-%m").date()
    except (TypeError, ValueError):
        return  # The month field reports its own validation error.
    if field.data.replace(day=1) != month_start:
        raise ValidationError(translate("validation_tracking_start_date"))


class BudgetMonthCreateForm(LocalizedForm):
    label_keys = {
        "month": "budget_month_field",
        "tracking_start_date": "tracking_start_date_field",
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
    tracking_start_date = DateField(
        "Tracking start date", validators=[Optional(), tracking_date_within_month],
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
