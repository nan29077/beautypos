"""매장별 광고 집행 키워드 테이블 추가 (승인 절차 포함)

매장(원장)과 최고관리자가 등록하는 상시 키워드를 담는다.
매장이 등록한 키워드는 status='pending' 으로 들어가 관리자 승인을 받아야
자동 집행에 쓰인다.

멱등하다: 테이블이 이미 있으면 아무것도 하지 않는다.

Revision ID: d3b6e91a47c2
Revises: c8a1f0d54e39
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3b6e91a47c2"
down_revision: Union[str, None] = "c8a1f0d54e39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "merchant_ad_keywords"


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=60), nullable=False),
        sa.Column("ad_type", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_by_role", sa.String(length=20), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", "ad_type", "keyword", name="uq_merchant_ad_keyword"),
    )
    op.create_index("ix_merchant_ad_keywords_merchant_id", TABLE, ["merchant_id"])
    op.create_index("ix_merchant_ad_keywords_status", TABLE, ["merchant_id", "status"])


def downgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table(TABLE):
        return
    op.drop_index("ix_merchant_ad_keywords_status", table_name=TABLE)
    op.drop_index("ix_merchant_ad_keywords_merchant_id", table_name=TABLE)
    op.drop_table(TABLE)
