from functools import wraps
from uuid import UUID

from flask import flash, g, redirect, request, session, url_for

from app.extensions import db
from app.i18n import translate
from app.models import User


def load_current_user():
    g.current_user = None
    raw_user_id = session.get("user_id")
    if raw_user_id is None:
        return

    try:
        user_id = UUID(raw_user_id)
    except (TypeError, ValueError, AttributeError):
        session.clear()
        return

    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        session.clear()
        return

    g.current_user = user


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            flash(translate("login_required"), "warning")
            return redirect(url_for("accounts.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped_view
