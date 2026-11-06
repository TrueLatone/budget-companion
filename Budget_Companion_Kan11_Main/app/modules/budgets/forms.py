"""HTML forms use the application's existing Flask-WTF CSRF protection."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, Optional
from app.i18n import translate


class ExpenseForm(FlaskForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self:
            if field.name != "csrf_token":
                field.label.text = translate("live_field_" + field.name)
        self.priority.choices = [(key, key + " — " + translate("group_" + key.lower())) for key in ("P0", "P1", "P2")]
        self.allocation_frequency.choices = [(key, translate("live_frequency_" + key)) for key in ("DAILY", "WEEKLY", "MONTHLY")]

    expense_name = StringField("Expense name", validators=[InputRequired(), Length(max=120)], filters=[lambda value: value.strip() if value else value])
    category_id = SelectField("Existing category", choices=[])
    category_name = StringField("Or new category", validators=[Optional(), Length(max=100)])
    priority = SelectField("Priority", choices=[("P0", "P0 — mandatory"), ("P1", "P1 — essential"), ("P2", "P2 — flexible")], default="P2")
    # WTForms also filters values loaded from obj=expense. Stored VND amounts
    # are integers; leave them (and None/zero) intact when rendering edits.
    estimated_amount = StringField("Estimated monthly amount (VND)", filters=[lambda value: value.strip() if isinstance(value, str) else value])
    minimum_amount = StringField("P1 minimum (VND, optional)", filters=[lambda value: value.strip() if isinstance(value, str) else value])
    allocation_frequency = SelectField("Frequency", choices=[("DAILY", "Daily"), ("WEEKLY", "Weekly"), ("MONTHLY", "Monthly")], default="MONTHLY")
    due_day = StringField("Monthly due day (optional)")
    is_recurring = BooleanField("Recurring expense")
    submit = SubmitField("Save expense")


class BudgetActionForm(FlaskForm):
    submit = SubmitField("Continue")
