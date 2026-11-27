"""Optional monthly planning choices. Existing months retain their original setup."""
from alembic import op
import sqlalchemy as sa

revision = "19a01e000004"
down_revision = "19a01e000003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("budget_months", sa.Column("savings_target", sa.BigInteger(), nullable=True))
    op.add_column("budget_months", sa.Column("setup_reuse_mode", sa.String(12), nullable=True))


def downgrade():
    op.drop_column("budget_months", "setup_reuse_mode")
    op.drop_column("budget_months", "savings_target")
