"""광고 집행 원장(ad_dispatches) 테이블 추가

리워드팝에 보낸 요청 1건 = 1행. 멱등키로 같은 날 중복 집행을 DB 가 막는다.
집계용 ad_executions 와는 분리해, 실패·보류 이력이 진도표를 오염시키지 않게 한다.

멱등하다: 테이블이 이미 있으면 아무것도 하지 않는다.

Revision ID: e5c2a80f39d4
Revises: d3b6e91a47c2
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5c2a80f39d4"
down_revision: Union[str, None] = "d3b6e91a47c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "ad_dispatches"


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("ad_type", sa.String(length=30), nullable=False),
        sa.Column("execution_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("ad_order_id", sa.Integer(), nullable=True),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("keyword", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("skip_reason", sa.String(length=40), nullable=True),
        sa.Column("external_order_id", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=150), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=True),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("cost_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.ForeignKeyConstraint(["ad_order_id"], ["ad_orders.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ad_dispatch_idempotency"),
    )
    op.create_index("ix_ad_dispatches_merchant_id", TABLE, ["merchant_id"])
    op.create_index("ix_ad_dispatches_execution_date", TABLE, ["execution_date"])
    op.create_index("ix_ad_dispatches_external_order_id", TABLE, ["external_order_id"])
    op.create_index("ix_ad_dispatches_date_status", TABLE, ["execution_date", "status"])


def downgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table(TABLE):
        return
    for name in ("ix_ad_dispatches_date_status", "ix_ad_dispatches_external_order_id",
                 "ix_ad_dispatches_execution_date", "ix_ad_dispatches_merchant_id"):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
