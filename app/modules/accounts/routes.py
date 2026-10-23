from urllib.parse import urlsplit

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from app.modules.accounts.auth import login_required
from app.modules.accounts.forms import LoginForm, LogoutForm, RegistrationForm
from app.modules.accounts.services import (
    DuplicateEmailError,
    authenticate_user,
    register_user,
)

bp = Blueprint("accounts", __name__)


@bp.get("/account")
@login_required
def index():
    return render_template(
        "accounts/account.html",
        logout_form=LogoutForm(),
    )


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.current_user is not None:
        return redirect(url_for("accounts.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            register_user(form.email.data, form.password.data)
        except DuplicateEmailError:
            form.email.errors.append("An account with this email already exists.")
        else:
            flash("Account created. Please sign in.", "success")
            return redirect(url_for("accounts.login"))

    return render_template("accounts/register.html", form=form)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.current_user is not None:
        return redirect(url_for("accounts.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate_user(form.email.data, form.password.data)
        if user is None:
            form.password.errors.append("Invalid email or password.")
        else:
            session.clear()
            session["user_id"] = str(user.id)
            session.permanent = bool(form.remember.data)

            next_url = request.args.get("next")
            if _is_safe_local_url(next_url):
                return redirect(next_url)
            return redirect(url_for("accounts.index"))

    return render_template("accounts/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    form = LogoutForm()
    if form.validate_on_submit():
        session.clear()
        flash("You have signed out.", "success")
        return redirect(url_for("accounts.login"))
    return redirect(url_for("accounts.index"))


def _is_safe_local_url(target):
    if not target:
        return False
    parsed = urlsplit(target)
    return (
        not parsed.scheme
        and not parsed.netloc
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
    )
