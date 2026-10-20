from flask import Blueprint, render_template

bp = Blueprint("expenses", __name__)


@bp.get("/expenses")
def index():
    # Day-1 placeholder only. Feature implementation belongs to its Jira tickets.
    return render_template("pages/placeholder.html", module_name="Expense & Smart Check-in")
