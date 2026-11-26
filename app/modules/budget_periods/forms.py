import re
from datetime import datetime

from wtforms import DateField, IntegerField, StringField, SubmitField
from wtforms.validators import InputRequired, NumberRange, Optional, ValidationError

from app.forms import LocalizedForm
from app.i18n import get_ui_language, translate
from app.modules.expenses.presentation import today_vn


MAX_VND = 9_223_372_036_854_775_807


def valid_calendar_month(form, field):
    if re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", field.data or ""):
        field.data = field.data[3:] + "-" + field.data[:2]
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
    tracking_start_day = IntegerField("Start day", validators=[Optional(), NumberRange(min=1, max=31)])

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        raw = self.tracking_start_day.raw_data
        if raw and (len(raw) != 1 or not raw[0].strip()):
            self.tracking_start_day.errors.append(translate("validation_tracking_start_date"))
            return False
        return valid

    def validate_tracking_start_day(self, field):
        if field.data is None or self.month.errors:
            return
        try:
            start = datetime.strptime(self.month.data, "%Y-%m").date().replace(day=field.data)
        except ValueError as exc:
            raise ValidationError(translate("validation_tracking_start_date")) from exc
        if self.tracking_start_date.data and start != self.tracking_start_date.data:
            raise ValidationError(translate("validation_tracking_start_date"))
        if start < today_vn():
            raise ValidationError("Ngày bắt đầu không được trước hôm nay." if get_ui_language() == "vi"
                                  else "Select today or a later tracking day.")
        self.tracking_start_date.data = start

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
