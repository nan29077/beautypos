"""매장 광고비 크레딧 — 잔액·원장·환불 신청 테이블과 주문 결제 출처 컬럼

플랜 한도를 넘겨 광고를 더 하려는 매장이 광고비를 충전해 쓰는 구조.
잔액은 캐시이고 원장(ad_credit_ledgers)이 진실이다.

멱등하다: 이미 있는 테이블·컬럼은 건너뛴다.

Revision ID: f7a3c19e5b28
Revises: e5c2a80f39d4
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a3c19e5b28"
down_revision: Union[str, None] = "e5c2a80f39d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("merchant_ad_credits"):
        op.create_table(
            "merchant_ad_credits",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("merchant_id", sa.Integer(), nullable=False),
            sa.Column("balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("merchant_id", name="uq_merchant_ad_credit"),
        )
        op.create_index("ix_merchant_ad_credits_merchant_id", "merchant_ad_credits", ["merchant_id"])

    if not inspector.has_table("ad_credit_ledgers"):
        op.create_table(
            "ad_credit_ledgers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("merchant_id", sa.Integer(), nullable=False),
            sa.Column("entry_type", sa.String(length=20), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("balance_after", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("ad_order_id", sa.Integer(), nullable=True),
            sa.Column("memo", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
            sa.ForeignKeyConstraint(["ad_order_id"], ["ad_orders.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ad_credit_ledgers_merchant_id", "ad_credit_ledgers", ["merchant_id"])
        op.create_index(
            "ix_ad_credit_ledgers_merchant_created", "ad_credit_ledgers",
            ["merchant_id", "created_at"],
        )

    if not inspector.has_table("ad_credit_refunds"):
        op.create_table(
            "ad_credit_refunds",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("merchant_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("admin_memo", sa.String(length=255), nullable=True),
            sa.Column("requested_by", sa.Integer(), nullable=True),
            sa.Column("processed_by", sa.Integer(), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["processed_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ad_credit_refunds_merchant_id", "ad_credit_refunds", ["merchant_id"])
        op.create_index("ix_ad_credit_refunds_status", "ad_credit_refunds", ["status"])

    if inspector.has_table("ad_orders"):
        cols = _columns(conn, "ad_orders")
        if "payment_source" not in cols:
            op.add_column("ad_orders", sa.Column(
                "payment_source", sa.String(length=20), nullable=False, server_default="plan"))
        if "credit_amount" not in cols:
            op.add_column("ad_orders", sa.Column(
                "credit_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("ad_orders"):
        cols = _columns(conn, "ad_orders")
        if "credit_amount" in cols:
            op.drop_column("ad_orders", "credit_amount")
        if "payment_source" in cols:
            op.drop_column("ad_orders", "payment_source")
    for table in ("ad_credit_refunds", "ad_credit_ledgers", "merchant_ad_credits"):
        if inspector.has_table(table):
            op.drop_table(table)
