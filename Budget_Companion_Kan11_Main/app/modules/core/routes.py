from flask import Blueprint, jsonify, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

bp = Blueprint("core", __name__)


@bp.get("/")
def home():
    return render_template("pages/home.html")


@bp.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "budget-companion"})


@bp.get("/api/health/database")
def database_health():
    """Check connectivity without exposing credentials or SQL errors to clients."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"})
    except SQLAlchemyError:
        return jsonify({"status": "unavailable", "database": "disconnected"}), 503
