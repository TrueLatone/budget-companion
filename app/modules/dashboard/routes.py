from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__)


@bp.get("/dashboard")
def index():
    return render_template("pages/placeholder.html", module_name="Dashboard & Reports")
