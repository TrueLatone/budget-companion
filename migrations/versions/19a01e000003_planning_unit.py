"""Keep previous distributions exact and restore the funding of confirmed months."""
from alembic import op
import sqlalchemy as sa

revision = "19a01e000003"
down_revision = "19a01e000002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("budget_months", sa.Column("planning_unit", sa.Integer(), nullable=False, server_default="1000"))
    op.execute("UPDATE budget_months SET planning_unit = 1")
    op.execute("""UPDATE budget_months SET available_vnd = (
        SELECT p.planned_savings + COALESCE(SUM(a.allocated_amount),0)
        FROM budget_plans p JOIN budget_allocations a ON a.plan_id = p.id
        WHERE p.budget_month_id = budget_months.id AND p.status = 'CONFIRMED'
        GROUP BY p.id, p.planned_savings)
        WHERE EXISTS (SELECT 1 FROM budget_plans p JOIN budget_allocations a ON a.plan_id=p.id
                      WHERE p.budget_month_id=budget_months.id AND p.status='CONFIRMED')""")


def downgrade():
    op.drop_column("budget_months", "planning_unit")
