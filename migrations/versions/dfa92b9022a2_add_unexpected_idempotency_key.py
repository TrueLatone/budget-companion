"""add unexpected idempotency key

Revision ID: dfa92b9022a2
Revises: b5187cd44b85
Create Date: 2026-10-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dfa92b9022a2'
down_revision = 'b5187cd44b85'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'expense_records',
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'uq_expense_records_idempotency',
        'expense_records',
        ['user_id', 'idempotency_key'],
        unique=True,
        postgresql_where=sa.text('idempotency_key IS NOT NULL'),
        sqlite_where=sa.text('idempotency_key IS NOT NULL'),
    )


def downgrade():
    op.drop_index(
        'uq_expense_records_idempotency',
        table_name='expense_records',
    )
    with op.batch_alter_table('expense_records', schema=None) as batch_op:
        batch_op.drop_column('idempotency_key')
