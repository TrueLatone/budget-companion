"""KAN-27 HTML destination plus predictable F16/F18/F19 JSON routes."""

from functools import wraps

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for

from app.modules.accounts.auth import login_required
from app.modules.budget_periods.services import list_budget_months
from app.modules.budgets import services as budgets
from . import services

bp = Blueprint("recommendations", __name__, url_prefix="/recommendations")


def _json_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None:
            return jsonify(error="Authentication required"), 401
        return view(*args, **kwargs)
    return wrapped


def _payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise services.RecommendationServiceError("A JSON object is required")
    return payload


@bp.get("")
@login_required
def index():
    months = list_budget_months(g.current_user.id)
    if request.args.get("budget_month_id"):
        try:
            month = budgets.get_month(g.current_user.id, request.args["budget_month_id"])
        except budgets.BudgetNotFound:
            raise services.RecommendationServiceError("Budget month not found", 404) from None
    elif request.args.get("month"):
        month = services.get_budget_month(g.current_user.id, request.args["month"])
    elif session.get("active_budget_month_id"):
        try:
            month = budgets.get_month(g.current_user.id, session["active_budget_month_id"])
        except budgets.BudgetNotFound:
            raise services.RecommendationServiceError("Budget month not found", 404) from None
    else:
        month = months[0] if months else None
    result = services.analyze_spending(g.current_user.id, month.month_start.strftime("%Y-%m"), request.args.get("as_of")) if month else None
    return render_template("recommendations/index.html", month=month, months=months, result=result, today=services.today_vn())


@bp.post("/analyze")
@login_required
def analyze():
    result = services.generate_recommendations(g.current_user, request.form.get("month"), request.form.get("as_of"))
    flash("Insufficient data: baseline guidance only." if result["status"] == "SKIPPED_INSUFFICIENT_DATA"
          else "Analysis saved. Financial adjustments remain disabled.", "info")
    # A future month defaults to today's cutoff before tracking starts. Preserve
    # that baseline result through GET defaults rather than submitting a cutoff
    # outside the selected month back into the explicit-date validator.
    cutoff = result["as_of"] if result["as_of"][:7] == result["month"] else None
    return redirect(url_for("recommendations.index", month=result["month"], as_of=cutoff))


@bp.post("/<uuid:recommendation_id>/dismiss")
@login_required
def dismiss(recommendation_id):
    detail = services.get_recommendation(g.current_user.id, recommendation_id)
    services.decide_recommendation(g.current_user.id, recommendation_id, "REJECT")
    return redirect(url_for("recommendations.index", budget_month_id=detail["budget_month_id"]))


@bp.get("/analysis")
@_json_login_required
def analysis():
    return jsonify(services.analyze_spending(g.current_user.id, request.args.get("month"), request.args.get("as_of")))


@bp.get("/completeness")
@_json_login_required
def completeness():
    return jsonify(services.get_completeness(g.current_user.id, request.args.get("month"), request.args.get("as_of")))


@bp.post("/generate")
@_json_login_required
def generate():
    payload = _payload()
    result = services.generate_recommendations(g.current_user, payload.get("month"), payload.get("as_of"))
    return jsonify(result), 201 if result["status"] == "GENERATED" else 200


@bp.get("/<uuid:recommendation_id>")
@_json_login_required
def explain(recommendation_id):
    return jsonify(services.get_recommendation(g.current_user.id, recommendation_id))


@bp.post("/<uuid:recommendation_id>/decision")
@_json_login_required
def decide(recommendation_id):
    payload = _payload()
    return jsonify(services.decide_recommendation(g.current_user.id, recommendation_id, payload.get("decision"), payload.get("as_of")))


@bp.get("/monthly-review")
@_json_login_required
def monthly_review():
    return jsonify(services.get_monthly_review(g.current_user.id, request.args.get("month"), request.args.get("as_of")))


@bp.post("/monthly-review/feedback")
@_json_login_required
def monthly_feedback():
    if request.is_json:
        payload = _payload()
        return jsonify(services.save_monthly_feedback(
            g.current_user.id, payload.get("month"), payload.get("rating"), payload.get("comment")
        ))
    month = request.form.get("month")
    raw_rating = request.form.get("rating", "").strip()
    if raw_rating and not raw_rating.isdecimal():
        raise services.RecommendationServiceError("rating must be an integer from 1 to 5")
    rating = int(raw_rating) if raw_rating else None
    services.save_monthly_feedback(g.current_user.id, month, rating, request.form.get("comment"))
    flash("Đã lưu đánh giá tháng của bạn.", "info")
    return redirect(url_for("recommendations.index", month=month))


@bp.errorhandler(services.RecommendationServiceError)
def invalid_recommendation(error):
    if request.endpoint in {"recommendations.index", "recommendations.analyze", "recommendations.dismiss"}:
        return render_template("recommendations/error.html", message=str(error)), error.status_code
    return jsonify(error=str(error)), error.status_code
