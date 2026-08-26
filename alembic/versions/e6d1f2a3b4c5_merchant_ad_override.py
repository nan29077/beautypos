"""가맹점별 광고 수량 오버라이드 테이블 추가

플랜 기본값과 별도로 가맹점마다 광고 종류별 월 목표 건수를 개별 설정할 수 있도록
merchant_ad_overrides 테이블을 추가한다.

멱등하다: CREATE TABLE IF NOT EXISTS 패턴 사용.

Revision ID: e6d1f2a3b4c5
Revises: c8a1f0d54e39
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6d1f2a3b4c5'
down_revision = 'a9d3f42b8c17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'merchant_ad_overrides' in inspector.get_table_names():
        return  # 멱등: 이미 존재하면 건너뜀

    op.create_table(
        'merchant_ad_overrides',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('ad_type', sa.String(30), nullable=False),
        sa.Column('monthly_override', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('merchant_id', 'ad_type', name='uq_merchant_ad_override'),
    )
    op.create_index(
        'ix_merchant_ad_overrides_merchant_id',
        'merchant_ad_overrides',
        ['merchant_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_merchant_ad_overrides_merchant_id', table_name='merchant_ad_overrides')
    op.drop_table('merchant_ad_overrides')
