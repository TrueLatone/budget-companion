"""KAN-19: expand budget months with an optional tracking start date.

Revision ID: 19a01e000001
Revises: de12e989405f

Old application versions may continue inserting NULL during this expansion.
The next revision backfills and enforces the final contract.
"""

from alembic import op
import sqlalchemy as sa


revision = "19a01e000001"
down_revision = "de12e989405f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("budget_months", sa.Column("tracking_start_date", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("budget_months") as batch_op:
        batch_op.drop_column("tracking_start_date")
