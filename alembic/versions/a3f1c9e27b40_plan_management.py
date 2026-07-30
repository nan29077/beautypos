"""plan management — plans / merchant_plans / ad_executions

Revision ID: a3f1c9e27b40
Revises: cd1d80f67c8d
Create Date: 2026-07-30

앱 기동 시 Base.metadata.create_all 로 이미 테이블이 만들어진 환경이 있으므로,
존재 여부를 확인해 멱등하게 동작하도록 작성한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3f1c9e27b40'
down_revision: Union[str, None] = 'cd1d80f67c8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    tables = _existing_tables()

    if 'plans' not in tables:
        op.create_table(
            'plans',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(length=50), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=False),
            sa.Column('merchant_fee_rate', sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column('blog_review_daily', sa.Integer(), nullable=False),
            sa.Column('blog_review_monthly', sa.Integer(), nullable=False),
            sa.Column('receipt_review_daily', sa.Integer(), nullable=False),
            sa.Column('receipt_review_monthly', sa.Integer(), nullable=False),
            sa.Column('place_traffic_daily', sa.Integer(), nullable=False),
            sa.Column('place_traffic_monthly', sa.Integer(), nullable=False),
            sa.Column('place_save_daily', sa.Integer(), nullable=False),
            sa.Column('place_save_monthly', sa.Integer(), nullable=False),
            sa.Column('shorts_daily', sa.Integer(), nullable=False),
            sa.Column('shorts_monthly', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_plans_code'), 'plans', ['code'], unique=True)

    if 'merchant_plans' not in tables:
        op.create_table(
            'merchant_plans',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('merchant_id', sa.Integer(), nullable=False),
            sa.Column('plan_id', sa.Integer(), nullable=False),
            sa.Column('assigned_at', sa.DateTime(), nullable=False),
            sa.Column('assigned_by', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['assigned_by'], ['users.id']),
            sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id']),
            sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_merchant_plans_merchant_id'), 'merchant_plans', ['merchant_id'])
        op.create_index(op.f('ix_merchant_plans_plan_id'), 'merchant_plans', ['plan_id'])

    if 'ad_executions' not in tables:
        op.create_table(
            'ad_executions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('merchant_id', sa.Integer(), nullable=False),
            sa.Column('ad_type', sa.String(length=30), nullable=False),
            sa.Column('executed_count', sa.Integer(), nullable=False),
            sa.Column('execution_date', sa.Date(), nullable=False),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('merchant_id', 'ad_type', 'execution_date',
                                name='uq_ad_exec_merchant_type_date'),
        )
        op.create_index(op.f('ix_ad_executions_merchant_id'), 'ad_executions', ['merchant_id'])
        op.create_index('ix_ad_executions_date', 'ad_executions', ['execution_date'])


def downgrade() -> None:
    tables = _existing_tables()
    if 'ad_executions' in tables:
        op.drop_index('ix_ad_executions_date', table_name='ad_executions')
        op.drop_index(op.f('ix_ad_executions_merchant_id'), table_name='ad_executions')
        op.drop_table('ad_executions')
    if 'merchant_plans' in tables:
        op.drop_index(op.f('ix_merchant_plans_plan_id'), table_name='merchant_plans')
        op.drop_index(op.f('ix_merchant_plans_merchant_id'), table_name='merchant_plans')
        op.drop_table('merchant_plans')
    if 'plans' in tables:
        op.drop_index(op.f('ix_plans_code'), table_name='plans')
        op.drop_table('plans')
