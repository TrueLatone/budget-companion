"""create users and budget months

Revision ID: de12e989405f
Revises: 
Create Date: 2026-10-23 14:57:24.277517

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'de12e989405f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # EXTRACT is native on PostgreSQL; STRFTIME keeps disposable SQLite
    # migration checks usable for local development.
    if op.get_bind().dialect.name == "postgresql":
        month_starts_first_day = "EXTRACT(DAY FROM month_start) = 1"
    else:
        month_starts_first_day = "CAST(STRFTIME('%d', month_start) AS INTEGER) = 1"

    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('email = lower(trim(email))', name=op.f('ck_users_email_normalized')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('budget_months',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('month_start', sa.Date(), nullable=False),
    sa.Column('available_vnd', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint(month_starts_first_day, name=op.f('ck_budget_months_month_starts_first_day')),
    sa.CheckConstraint('available_vnd >= 0', name=op.f('ck_budget_months_available_vnd_nonnegative')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_budget_months_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_months')),
    sa.UniqueConstraint('user_id', 'month_start', name='uq_budget_months_user_id_month_start')
    )


def downgrade():
    op.drop_table('budget_months')
    op.drop_table('users')
