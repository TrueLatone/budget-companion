from dotenv import load_dotenv
from flask import Flask

from app.extensions import csrf, db, migrate


def create_app(test_config=None):
    """Application factory: register extensions and independent feature blueprints."""
    load_dotenv()
    from app.config import Config

    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    from app.i18n import register_ui_languages
    register_ui_languages(app)

    db.init_app(app)
    # Ensure models are visible to Alembic.
    from app import models  
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app.modules.core.routes import bp as core_bp
    from app.modules.accounts.auth import load_current_user
    from app.modules.accounts.routes import bp as accounts_bp
    from app.modules.budget_periods.routes import bp as budget_periods_bp
    from app.modules.budgets.routes import bp as budgets_bp
    from app.modules.expenses.routes import bp as expenses_bp
    from app.modules.dashboard.routes import bp as dashboard_bp
    from app.modules.recommendations.routes import bp as recommendations_bp

    for blueprint in (
        core_bp, accounts_bp, budget_periods_bp, budgets_bp, expenses_bp,
        dashboard_bp, recommendations_bp,
    ):
        app.register_blueprint(blueprint)

    app.before_request(load_current_user)

    from app.workspace import register_workspace
    register_workspace(app)

    from werkzeug.exceptions import HTTPException
    from flask import request, render_template
    from app.i18n import get_ui_language

    @app.errorhandler(HTTPException)
    def localized_http_error(error):
        if get_ui_language() != "vi" or request.path.startswith("/api/"):
            return error
        messages = {400:"Biểu mẫu không hợp lệ hoặc đã hết hạn. Hãy tải lại trang và thử lại.",
                    403:"Bạn không có quyền thực hiện thao tác này.", 404:"Không tìm thấy trang hoặc dữ liệu.",
                    405:"Thao tác này không được hỗ trợ."}
        return render_template("pages/request_error.html", message=messages.get(error.code, "Không thể thực hiện yêu cầu.")), error.code

    @app.cli.command("complete-schedules")
    def complete_schedules():
        """Fill schedules for budgets confirmed before automatic scheduling."""
        from app.models import BudgetPlan, BudgetMonth
        from app.modules.expenses.services import get_schedule_state, ensure_tasks_for_month
        months = db.session.execute(db.select(BudgetMonth.user_id, BudgetMonth.id).join(
            BudgetPlan, BudgetPlan.budget_month_id == BudgetMonth.id
        ).where(BudgetPlan.status == "CONFIRMED")).all()
        for user_id, month_id in months:
            if get_schedule_state(user_id, month_id).code in ("NOT_SCHEDULED", "INCOMPLETE"):
                ensure_tasks_for_month(user_id, month_id)
    return app
