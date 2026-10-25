"""merge expense planning and budget foundation heads

Revision ID: a8c32b643be1
Revises: de12e989405f, dfa92b9022a2
Create Date: 2026-10-25 17:47:46.774786

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c32b643be1'
down_revision = ('de12e989405f', 'dfa92b9022a2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
