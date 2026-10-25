from flask import Blueprint, render_template

from app.ui_demo import workspace_context

bp = Blueprint("budgets", __name__)


@bp.get("/budget")
def index():
    return render_template("pages/budget.html", **workspace_context())
