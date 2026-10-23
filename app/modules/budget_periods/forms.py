from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Regexp


MAX_VND = 9_223_372_036_854_775_807


class BudgetMonthCreateForm(FlaskForm):
    month = StringField(
        "Calendar month",
        validators=[
            DataRequired(),
            Regexp(
                r"^\d{4}-(0[1-9]|1[0-2])$",
                message="Use a calendar month in YYYY-MM format.",
            ),
        ],
    )
    available_vnd = IntegerField(
        "Available funds (VND)",
        validators=[InputRequired(), NumberRange(min=0, max=MAX_VND)],
    )
    submit = SubmitField("Create budget month")


class BudgetMonthUpdateForm(FlaskForm):
    available_vnd = IntegerField(
        "Available funds (VND)",
        validators=[InputRequired(), NumberRange(min=0, max=MAX_VND)],
    )
    submit = SubmitField("Save changes")
