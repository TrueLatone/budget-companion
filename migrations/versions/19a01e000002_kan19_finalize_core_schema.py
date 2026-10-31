"""KAN-19: finalize tracking and create the 13-entity shared core.

Revision ID: 19a01e000002
Revises: 19a01e000001

Extends the KAN-15 lineage only. KAN-8's independent table-creation history
must not be replayed against this schema without an integration migration.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "19a01e000002"
down_revision = "19a01e000001"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve legacy full-month interpretation, IDs, funds, and audit values.
    op.execute(sa.text(
        "UPDATE budget_months SET tracking_start_date = month_start "
        "WHERE tracking_start_date IS NULL"
    ))
    # Do this before introducing new incoming FKs, including on SQLite.
    with op.batch_alter_table("budget_months") as batch_op:
        batch_op.alter_column("tracking_start_date", existing_type=sa.Date(), nullable=False)
        batch_op.create_check_constraint(
            op.f("ck_budget_months_tracking_within_month"),
            sa.and_(
                sa.extract("year", sa.column("tracking_start_date"))
                == sa.extract("year", sa.column("month_start")),
                sa.extract("month", sa.column("tracking_start_date"))
                == sa.extract("month", sa.column("month_start")),
            ),
        )
    op.create_table('expense_categories',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('category_name', sa.String(length=100), nullable=False),
    sa.CheckConstraint('length(trim(category_name)) > 0', name=op.f('ck_expense_categories_category_name_nonempty')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_expense_categories_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_expense_categories'))
    )
    with op.batch_alter_table('expense_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expense_categories_user_id'), ['user_id'], unique=False)
        # SQLite autogenerate cannot reflect expression indexes; keep these explicit.
        batch_op.create_index(
            'uq_expense_categories_owned_name',
            ['user_id', sa.text('lower(trim(category_name))')], unique=True,
            postgresql_where=sa.text('user_id IS NOT NULL'),
            sqlite_where=sa.text('user_id IS NOT NULL'),
        )
        batch_op.create_index(
            'uq_expense_categories_builtin_name',
            [sa.text('lower(trim(category_name))')], unique=True,
            postgresql_where=sa.text('user_id IS NULL'),
            sqlite_where=sa.text('user_id IS NULL'),
        )

    op.create_table('user_preferences',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('preferred_plan_type', sa.String(length=20), nullable=True),
    sa.Column('budget_alerts_enabled', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('payment_reminders_enabled', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.CheckConstraint("preferred_plan_type IS NULL OR preferred_plan_type IN ('SAVING', 'BALANCED', 'LIFESTYLE', 'MANUAL')", name=op.f('ck_user_preferences_preferred_plan_type_valid')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_preferences_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_preferences')),
    sa.UniqueConstraint('user_id', name=op.f('uq_user_preferences_user_id'))
    )
    op.create_table('budget_expenses',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('budget_month_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.Column('expense_name', sa.String(length=120), nullable=False),
    sa.Column('priority', sa.String(length=2), nullable=False),
    sa.Column('estimated_amount', sa.BigInteger(), nullable=True),
    sa.Column('minimum_amount', sa.BigInteger(), nullable=True),
    sa.Column('allocation_frequency', sa.String(length=10), nullable=False),
    sa.Column('is_recurring', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('due_day', sa.SmallInteger(), nullable=True),
    sa.CheckConstraint("allocation_frequency IN ('DAILY', 'WEEKLY', 'MONTHLY')", name=op.f('ck_budget_expenses_allocation_frequency_valid')),
    sa.CheckConstraint("priority IN ('P0', 'P1', 'P2')", name=op.f('ck_budget_expenses_priority_valid')),
    sa.CheckConstraint('due_day IS NULL OR due_day BETWEEN 1 AND 31', name=op.f('ck_budget_expenses_due_day_valid')),
    sa.CheckConstraint('estimated_amount IS NULL OR estimated_amount >= 0', name=op.f('ck_budget_expenses_estimated_amount_nonnegative')),
    sa.CheckConstraint('minimum_amount IS NULL OR minimum_amount > 0', name=op.f('ck_budget_expenses_minimum_amount_positive')),
    sa.ForeignKeyConstraint(['budget_month_id'], ['budget_months.id'], name=op.f('fk_budget_expenses_budget_month_id_budget_months'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_id'], ['expense_categories.id'], name=op.f('fk_budget_expenses_category_id_expense_categories'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_expenses'))
    )
    with op.batch_alter_table('budget_expenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_budget_expenses_budget_month_id'), ['budget_month_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_expenses_category_id'), ['category_id'], unique=False)

    op.create_table('budget_plans',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('budget_month_id', sa.Uuid(), nullable=False),
    sa.Column('plan_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='GENERATED', nullable=False),
    sa.Column('planned_savings', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.CheckConstraint("plan_type IN ('SAVING', 'BALANCED', 'LIFESTYLE', 'MANUAL')", name=op.f('ck_budget_plans_plan_type_valid')),
    sa.CheckConstraint("status IN ('GENERATED', 'CONFIRMED')", name=op.f('ck_budget_plans_status_valid')),
    sa.CheckConstraint('planned_savings >= 0', name=op.f('ck_budget_plans_planned_savings_nonnegative')),
    sa.ForeignKeyConstraint(['budget_month_id'], ['budget_months.id'], name=op.f('fk_budget_plans_budget_month_id_budget_months'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_plans'))
    )
    with op.batch_alter_table('budget_plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_budget_plans_budget_month_id'), ['budget_month_id'], unique=False)
        batch_op.create_index('uq_budget_plans_confirmed_month', ['budget_month_id'], unique=True, postgresql_where=sa.text("status = 'CONFIRMED'"), sqlite_where=sa.text("status = 'CONFIRMED'"))

    op.create_table('monthly_reviews',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('budget_month_id', sa.Uuid(), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.CheckConstraint('rating IS NULL OR rating BETWEEN 1 AND 5', name=op.f('ck_monthly_reviews_rating_valid')),
    sa.ForeignKeyConstraint(['budget_month_id'], ['budget_months.id'], name=op.f('fk_monthly_reviews_budget_month_id_budget_months'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monthly_reviews')),
    sa.UniqueConstraint('budget_month_id', name=op.f('uq_monthly_reviews_budget_month_id'))
    )
    op.create_table('recommendations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('budget_month_id', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('expected_impact', sa.Text(), nullable=False),
    sa.Column('proposed_changes', sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'REJECTED')", name=op.f('ck_recommendations_status_valid')),
    sa.ForeignKeyConstraint(['budget_month_id'], ['budget_months.id'], name=op.f('fk_recommendations_budget_month_id_budget_months'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recommendations'))
    )
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recommendations_budget_month_id'), ['budget_month_id'], unique=False)

    op.create_table('budget_adjustments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('recommendation_id', sa.Uuid(), nullable=True),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('adjustment_type', sa.String(length=24), nullable=False),
    sa.CheckConstraint('length(trim(adjustment_type)) > 0', name=op.f('ck_budget_adjustments_adjustment_type_nonempty')),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], name=op.f('fk_budget_adjustments_recommendation_id_recommendations'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_adjustments')),
    sa.UniqueConstraint('recommendation_id', name=op.f('uq_budget_adjustments_recommendation_id'))
    )
    op.create_table('budget_allocations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('plan_id', sa.Uuid(), nullable=False),
    sa.Column('budget_expense_id', sa.Uuid(), nullable=False),
    sa.Column('allocated_amount', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('allocated_amount > 0', name=op.f('ck_budget_allocations_allocated_amount_positive')),
    sa.ForeignKeyConstraint(['budget_expense_id'], ['budget_expenses.id'], name=op.f('fk_budget_allocations_budget_expense_id_budget_expenses'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['plan_id'], ['budget_plans.id'], name=op.f('fk_budget_allocations_plan_id_budget_plans'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_allocations')),
    sa.UniqueConstraint('plan_id', 'budget_expense_id', name=op.f('uq_budget_allocations_plan_id'))
    )
    with op.batch_alter_table('budget_allocations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_budget_allocations_budget_expense_id'), ['budget_expense_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_allocations_plan_id'), ['plan_id'], unique=False)

    op.create_table('assigned_expense_tasks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('allocation_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_date', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('original_limit', sa.BigInteger(), nullable=False),
    sa.Column('current_limit', sa.BigInteger(), nullable=False),
    sa.Column('task_status', sa.String(length=20), server_default='PENDING', nullable=False),
    sa.Column('payment_due_date', sa.Date(), nullable=True),
    sa.Column('payment_status', sa.String(length=20), nullable=True),
    sa.CheckConstraint("payment_status IS NULL OR payment_status IN ('PAID', 'UNPAID')", name=op.f('ck_assigned_expense_tasks_payment_status_valid')),
    sa.CheckConstraint("task_status IN ('PENDING', 'RECORDED', 'NO_EXPENSE')", name=op.f('ck_assigned_expense_tasks_task_status_valid')),
    sa.CheckConstraint('current_limit >= 0', name=op.f('ck_assigned_expense_tasks_current_limit_nonnegative')),
    sa.CheckConstraint('original_limit >= 0', name=op.f('ck_assigned_expense_tasks_original_limit_nonnegative')),
    sa.CheckConstraint('period_end >= assigned_date', name=op.f('ck_assigned_expense_tasks_period_order_valid')),
    sa.ForeignKeyConstraint(['allocation_id'], ['budget_allocations.id'], name=op.f('fk_assigned_expense_tasks_allocation_id_budget_allocations'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assigned_expense_tasks')),
    sa.UniqueConstraint('allocation_id', 'assigned_date', name=op.f('uq_assigned_expense_tasks_allocation_id'))
    )
    with op.batch_alter_table('assigned_expense_tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_assigned_expense_tasks_allocation_id'), ['allocation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_assigned_expense_tasks_payment_due_date'), ['payment_due_date'], unique=False)

    op.create_table('budget_adjustment_details',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('adjustment_id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('previous_limit', sa.BigInteger(), nullable=False),
    sa.Column('new_limit', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('new_limit >= 0', name=op.f('ck_budget_adjustment_details_new_limit_nonnegative')),
    sa.CheckConstraint('previous_limit >= 0', name=op.f('ck_budget_adjustment_details_previous_limit_nonnegative')),
    sa.ForeignKeyConstraint(['adjustment_id'], ['budget_adjustments.id'], name=op.f('fk_budget_adjustment_details_adjustment_id_budget_adjustments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['task_id'], ['assigned_expense_tasks.id'], name=op.f('fk_budget_adjustment_details_task_id_assigned_expense_tasks'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_adjustment_details')),
    sa.UniqueConstraint('adjustment_id', 'task_id', name=op.f('uq_budget_adjustment_details_adjustment_id'))
    )
    with op.batch_alter_table('budget_adjustment_details', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_budget_adjustment_details_adjustment_id'), ['adjustment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_adjustment_details_task_id'), ['task_id'], unique=False)

    op.create_table('expense_records',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('budget_month_id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=True),
    sa.Column('category_id', sa.Uuid(), nullable=True),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.Column('expense_date', sa.Date(), nullable=False),
    sa.Column('record_type', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.String(length=2), nullable=True),
    sa.Column('title', sa.String(length=120), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('budget_impact_scope', sa.String(length=10), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.CheckConstraint("(record_type = 'PLANNED' AND task_id IS NOT NULL) OR (record_type IN ('UNEXPECTED', 'FUNDS_ADDED') AND task_id IS NULL)", name=op.f('ck_expense_records_task_matches_record_type')),
    sa.CheckConstraint("(record_type = 'UNEXPECTED' AND priority IS NOT NULL) OR (record_type = 'FUNDS_ADDED' AND priority IS NULL) OR record_type = 'PLANNED'", name=op.f('ck_expense_records_priority_matches_record_type')),
    sa.CheckConstraint("(record_type IN ('PLANNED', 'UNEXPECTED') AND category_id IS NOT NULL) OR (record_type = 'FUNDS_ADDED' AND category_id IS NULL)", name=op.f('ck_expense_records_category_matches_record_type')),
    sa.CheckConstraint("budget_impact_scope IS NULL OR (record_type = 'UNEXPECTED' AND budget_impact_scope IN ('DAILY', 'WEEKLY', 'MONTHLY'))", name=op.f('ck_expense_records_budget_impact_scope_valid')),
    sa.CheckConstraint("priority IS NULL OR priority IN ('P0', 'P1', 'P2')", name=op.f('ck_expense_records_priority_valid')),
    sa.CheckConstraint("record_type IN ('PLANNED', 'UNEXPECTED', 'FUNDS_ADDED')", name=op.f('ck_expense_records_record_type_valid')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_expense_records_amount_positive')),
    sa.ForeignKeyConstraint(['budget_month_id'], ['budget_months.id'], name=op.f('fk_expense_records_budget_month_id_budget_months'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_id'], ['expense_categories.id'], name=op.f('fk_expense_records_category_id_expense_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['task_id'], ['assigned_expense_tasks.id'], name=op.f('fk_expense_records_task_id_assigned_expense_tasks'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_expense_records')),
    sa.UniqueConstraint('budget_month_id', 'idempotency_key', name=op.f('uq_expense_records_budget_month_id'))
    )
    with op.batch_alter_table('expense_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expense_records_budget_month_id'), ['budget_month_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_records_category_id'), ['category_id'], unique=False)
        batch_op.create_index('ix_expense_records_month_date', ['budget_month_id', 'expense_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_records_task_id'), ['task_id'], unique=False)



def downgrade():
    with op.batch_alter_table('expense_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_expense_records_task_id'))
        batch_op.drop_index('ix_expense_records_month_date')
        batch_op.drop_index(batch_op.f('ix_expense_records_category_id'))
        batch_op.drop_index(batch_op.f('ix_expense_records_budget_month_id'))

    op.drop_table('expense_records')
    with op.batch_alter_table('budget_adjustment_details', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_budget_adjustment_details_task_id'))
        batch_op.drop_index(batch_op.f('ix_budget_adjustment_details_adjustment_id'))

    op.drop_table('budget_adjustment_details')
    with op.batch_alter_table('assigned_expense_tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_assigned_expense_tasks_payment_due_date'))
        batch_op.drop_index(batch_op.f('ix_assigned_expense_tasks_allocation_id'))

    op.drop_table('assigned_expense_tasks')
    with op.batch_alter_table('budget_allocations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_budget_allocations_plan_id'))
        batch_op.drop_index(batch_op.f('ix_budget_allocations_budget_expense_id'))

    op.drop_table('budget_allocations')
    op.drop_table('budget_adjustments')
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recommendations_budget_month_id'))

    op.drop_table('recommendations')
    op.drop_table('monthly_reviews')
    with op.batch_alter_table('budget_plans', schema=None) as batch_op:
        batch_op.drop_index('uq_budget_plans_confirmed_month', postgresql_where=sa.text("status = 'CONFIRMED'"), sqlite_where=sa.text("status = 'CONFIRMED'"))
        batch_op.drop_index(batch_op.f('ix_budget_plans_budget_month_id'))

    op.drop_table('budget_plans')
    with op.batch_alter_table('budget_expenses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_budget_expenses_category_id'))
        batch_op.drop_index(batch_op.f('ix_budget_expenses_budget_month_id'))

    op.drop_table('budget_expenses')
    op.drop_table('user_preferences')
    with op.batch_alter_table('expense_categories', schema=None) as batch_op:
        batch_op.drop_index('uq_expense_categories_builtin_name')
        batch_op.drop_index('uq_expense_categories_owned_name')
        batch_op.drop_index(batch_op.f('ix_expense_categories_user_id'))

    op.drop_table('expense_categories')

    with op.batch_alter_table("budget_months") as batch_op:
        batch_op.drop_constraint(op.f("ck_budget_months_tracking_within_month"), type_="check")
        batch_op.alter_column("tracking_start_date", existing_type=sa.Date(), nullable=True)
