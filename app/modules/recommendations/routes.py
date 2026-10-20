from flask import Blueprint, render_template

bp = Blueprint("recommendations", __name__)


@bp.get("/recommendations")
def index():
    return render_template("pages/placeholder.html", module_name="Adaptive Recommendations")
