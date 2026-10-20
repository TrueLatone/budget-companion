from flask import Blueprint, render_template

bp = Blueprint("accounts", __name__)


@bp.get("/account")
def index():
    # Day-1 placeholder only. Feature implementation belongs to its Jira tickets.
    return render_template("pages/placeholder.html", module_name="Account Management")
