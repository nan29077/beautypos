"""온기 QR ↔ 가맹점 매핑 테이블

관리자가 온기 QR을 가맹점에 연결해두면 사장님(OWNER)이 자기 매장 QR의
결제 내역만 조회할 수 있다.

멱등하다: 이미 있는 테이블은 건너뛴다.

Revision ID: a9d4e7f1c3b5
Revises: c1d2e3f4a5b6
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d4e7f1c3b5"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("ongi_qr_mappings"):
        op.create_table(
            "ongi_qr_mappings",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("qr_id", sa.Integer(), nullable=False),
            sa.Column("qr_name", sa.String(200), nullable=True),
            sa.Column("merchant_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("qr_id", name="uq_ongi_qr_mapping_qr_id"),
        )
        op.create_index(
            "ix_ongi_qr_mappings_merchant_id", "ongi_qr_mappings", ["merchant_id"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("ongi_qr_mappings"):
        op.drop_table("ongi_qr_mappings")
