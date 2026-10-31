"""HTML forms use the application's existing Flask-WTF CSRF protection."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, Optional


class ExpenseForm(FlaskForm):
    expense_name = StringField("Expense name", validators=[InputRequired(), Length(max=120)], filters=[lambda value: value.strip() if value else value])
    category_id = SelectField("Existing category", choices=[])
    category_name = StringField("Or new category", validators=[Optional(), Length(max=100)])
    priority = SelectField("Priority", choices=[("P0", "P0 — mandatory"), ("P1", "P1 — essential"), ("P2", "P2 — flexible")])
    estimated_amount = StringField("Estimated monthly amount (VND)", filters=[lambda value: value.strip() if value else value])
    minimum_amount = StringField("P1 minimum (VND, optional)", filters=[lambda value: value.strip() if value else value])
    allocation_frequency = SelectField("Frequency", choices=[("DAILY", "Daily"), ("WEEKLY", "Weekly"), ("MONTHLY", "Monthly")], default="MONTHLY")
    due_day = StringField("Monthly due day (optional)")
    is_recurring = BooleanField("Recurring expense")
    submit = SubmitField("Save expense")


class BudgetActionForm(FlaskForm):
    submit = SubmitField("Continue")
