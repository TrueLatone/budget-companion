from dotenv import load_dotenv
from flask import Flask

from app.extensions import db, migrate


def create_app(test_config=None):
    """Application factory: register extensions and independent feature blueprints."""
    load_dotenv()
    from app.config import Config

    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    # Ensure future models imported by app.models are visible to Alembic.
    from app import models  # noqa: F401
    migrate.init_app(app, db)

    from app.modules.core.routes import bp as core_bp
    from app.modules.accounts.routes import bp as accounts_bp
    from app.modules.budgets.routes import bp as budgets_bp
    from app.modules.expenses.routes import bp as expenses_bp
    from app.modules.dashboard.routes import bp as dashboard_bp
    from app.modules.recommendations.routes import bp as recommendations_bp

    for blueprint in (
        core_bp, accounts_bp, budgets_bp, expenses_bp,
        dashboard_bp, recommendations_bp,
    ):
        app.register_blueprint(blueprint)

    return app
