"""merchant_ad_configs 에 블로그 자동 접수 전용 필드 추가

리워드팝 POST /ads/cloblog 호출에 필요한 파라미터를 매장·광고타입 설정에 저장한다.
blog_review 타입 행에 채워두면 매월 첫 평일에 자동 접수된다.

멱등하다: 이미 있는 컬럼은 건너뛴다.

Revision ID: b9f3c1d5e7a2
Revises: c4e9b71fa2d5
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9f3c1d5e7a2"
down_revision: Union[str, None] = "c4e9b71fa2d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("merchant_ad_configs"):
        return

    cols = _columns(conn, "merchant_ad_configs")

    if "blog_place_url" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_place_url", sa.String(length=500), nullable=True))
    if "blog_place_name" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_place_name", sa.String(length=100), nullable=True))
    if "blog_main_keyword" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_main_keyword", sa.String(length=100), nullable=True))
    if "blog_work_keywords" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_work_keywords", sa.Text(), nullable=True))
    if "blog_tags" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_tags", sa.Text(), nullable=True))
    if "blog_post_type" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_post_type", sa.String(length=10), nullable=True))
    if "blog_store_address" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_store_address", sa.String(length=200), nullable=True))
    if "blog_store_phone" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_store_phone", sa.String(length=30), nullable=True))
    if "blog_extra_link" not in cols:
        op.add_column("merchant_ad_configs", sa.Column(
            "blog_extra_link", sa.String(length=500), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("merchant_ad_configs"):
        return

    cols = _columns(conn, "merchant_ad_configs")
    for col in (
        "blog_extra_link", "blog_store_phone", "blog_store_address",
        "blog_post_type", "blog_tags", "blog_work_keywords",
        "blog_main_keyword", "blog_place_name", "blog_place_url",
    ):
        if col in cols:
            op.drop_column("merchant_ad_configs", col)
