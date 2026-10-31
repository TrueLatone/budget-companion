from flask import Blueprint, g, jsonify, request

from . import services

bp = Blueprint("recommendations", __name__, url_prefix="/recommendations")


def _current_user():
    user = getattr(g, "current_user", None)
    if user is None:
        return None, (jsonify({"error": "Authentication required"}), 401)
    return user, None


def _error_response(error):
    return jsonify({"error": str(error)}), getattr(error, "status_code", 400)


@bp.get("/completeness")
def completeness():
    user, error = _current_user()
    if error:
        return error
    try:
        result = services.get_completeness(user.id, request.args.get("month"), request.args.get("as_of"))
        return jsonify(result)
    except services.RecommendationServiceError as exc:
        return _error_response(exc)


@bp.post("/generate")
def generate():
    user, error = _current_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        result = services.generate_recommendations(user, payload.get("month"), payload.get("as_of"))
        return jsonify(result), 201 if result.get("status") == "GENERATED" else 200
    except services.RecommendationServiceError as exc:
        return _error_response(exc)


@bp.get("/<uuid:recommendation_id>")
def explain(recommendation_id):
    user, error = _current_user()
    if error:
        return error
    try:
        return jsonify(services.get_recommendation(user.id, recommendation_id))
    except services.RecommendationServiceError as exc:
        return _error_response(exc)


@bp.post("/<uuid:recommendation_id>/decision")
def decide(recommendation_id):
    user, error = _current_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        result = services.decide_recommendation(
            user.id,
            recommendation_id,
            payload.get("decision"),
            payload.get("as_of"),
        )
        return jsonify(result)
    except services.RecommendationServiceError as exc:
        return _error_response(exc)


@bp.get("/monthly-review")
def monthly_review():
    user, error = _current_user()
    if error:
        return error
    try:
        result = services.get_monthly_review(user.id, request.args.get("month"), request.args.get("as_of"))
        return jsonify(result)
    except services.RecommendationServiceError as exc:
        return _error_response(exc)


@bp.post("/monthly-review/feedback")
def monthly_feedback():
    user, error = _current_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        result = services.save_monthly_feedback(
            user.id,
            payload.get("month"),
            payload.get("rating"),
            payload.get("comment"),
        )
        return jsonify(result), 201
    except services.RecommendationServiceError as exc:
        return _error_response(exc)
