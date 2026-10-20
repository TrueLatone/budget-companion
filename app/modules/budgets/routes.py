from flask import Blueprint, render_template

bp = Blueprint("budgets", __name__)


@bp.get("/budget")
def index():
    return render_template("pages/placeholder.html", module_name="Budget Planning")
