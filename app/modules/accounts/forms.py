from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length

from app.forms import LocalizedForm


def _normalize_email(value):
    return value.strip().lower() if value else value


class RegistrationForm(LocalizedForm):
    label_keys = {
        "email": "form_email",
        "password": "form_password",
        "confirm_password": "form_confirm_password",
        "submit": "register_submit",
    }

    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=320)],
        filters=[_normalize_email],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password")],
    )
    submit = SubmitField("Create account")


class LoginForm(LocalizedForm):
    label_keys = {
        "email": "form_email",
        "password": "form_password",
        "remember": "login_remember",
        "submit": "login_submit",
    }

    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=320)],
        filters=[_normalize_email],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(max=128)],
    )
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class LogoutForm(LocalizedForm):
    label_keys = {"submit": "logout_submit"}

    submit = SubmitField("Sign out")
