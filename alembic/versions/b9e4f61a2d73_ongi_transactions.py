"""온기(ONGI) 결제 내역 로컬 사본(ongi_transactions) 테이블 추가

온기 결제 서버에서 폴링으로 받아온 결제 1건 = 1행. 온기 결제 id 유니크 제약이
멱등 키 역할을 해 같은 기간을 몇 번 다시 받아도 중복되지 않는다.

멱등하다: 테이블이 이미 있으면 아무것도 하지 않는다.

Revision ID: b9e4f61a2d73
Revises: f3a4b5c6d7e8
Create Date: 2026-08-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9e4f61a2d73"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "ongi_transactions"

# ongi_payment_id 는 유니크 제약이 인덱스를 겸하므로 별도 인덱스를 만들지 않는다.
INDEXES = (
    ("ix_ongi_transactions_payment_code", ["payment_code"]),
    ("ix_ongi_transactions_order_code", ["order_code"]),
    ("ix_ongi_transactions_status", ["status"]),
    ("ix_ongi_transactions_qr_id", ["qr_id"]),
    ("ix_ongi_transactions_paid_at", ["paid_at"]),
)


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ongi_payment_id", sa.Integer(), nullable=False),
        sa.Column("payment_code", sa.String(length=100), nullable=True),
        sa.Column("order_code", sa.String(length=100), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("api_mid", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("pay_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_type", sa.String(length=50), nullable=True),
        sa.Column("division", sa.String(length=50), nullable=True),
        sa.Column("payment_words", sa.String(length=200), nullable=True),
        sa.Column("member_name", sa.String(length=100), nullable=True),
        sa.Column("ongi_member_id", sa.Integer(), nullable=True),
        sa.Column("qr_id", sa.Integer(), nullable=True),
        sa.Column("qr_name", sa.String(length=200), nullable=True),
        sa.Column("auth_no", sa.String(length=50), nullable=True),
        sa.Column("transaction_no", sa.String(length=100), nullable=True),
        sa.Column("pg_merchant_id", sa.String(length=100), nullable=True),
        sa.Column("result_code", sa.String(length=20), nullable=True),
        sa.Column("result_message", sa.String(length=200), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("ongi_updated_at", sa.String(length=30), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ongi_payment_id", name="uq_ongi_transactions_payment_id"),
    )
    for name, cols in INDEXES:
        op.create_index(name, TABLE, cols)


def downgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table(TABLE):
        return
    for name, _cols in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
