from flask import Blueprint, render_template

from app.ui_demo import workspace_context

bp = Blueprint("dashboard", __name__)


@bp.get("/dashboard")
def index():
    return render_template("pages/dashboard.html", **workspace_context(page="dashboard"))
