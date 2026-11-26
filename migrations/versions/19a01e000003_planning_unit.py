"""Keep previous distributions exact without changing existing financial data."""
from alembic import op
import sqlalchemy as sa

revision = "19a01e000003"
down_revision = "19a01e000002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("budget_months", sa.Column("planning_unit", sa.Integer(), nullable=False, server_default="1000"))
    op.execute("UPDATE budget_months SET planning_unit = 1")
    # Available funds can legitimately differ from an older confirmed snapshot.
    # A unit migration must preserve both amounts; it cannot infer a correction.


def downgrade():
    op.drop_column("budget_months", "planning_unit")
