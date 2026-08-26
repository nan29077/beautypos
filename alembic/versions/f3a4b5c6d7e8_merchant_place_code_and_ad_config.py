"""매장 placeCode 필드 추가 및 광고 집행 설정 테이블 추가

리워드팝 POST /ads 호출에 필요한 placeCode(네이버 플레이스 숫자 코드)를
merchants 테이블에 추가하고, 매장별 광고 타입별 집행 설정(missionCategory,
missionAction, keywordMode 등)을 저장하는 merchant_ad_configs 테이블을 추가한다.

멱등하다: 컬럼/테이블 존재 여부를 확인하고 건너뜀.

Revision ID: f3a4b5c6d7e8
Revises: e6d1f2a3b4c5
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'f3a4b5c6d7e8'
down_revision = 'e6d1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. merchants.place_code 컬럼 추가
    merchant_cols = [c["name"] for c in inspector.get_columns("merchants")]
    if "place_code" not in merchant_cols:
        op.add_column("merchants", sa.Column("place_code", sa.String(30), nullable=True))

    # 2. merchant_ad_configs 테이블 생성
    if "merchant_ad_configs" not in inspector.get_table_names():
        op.create_table(
            "merchant_ad_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("merchant_id", sa.Integer(), nullable=False),
            sa.Column("ad_type", sa.String(30), nullable=False),
            sa.Column("mission_category", sa.String(20), nullable=True),
            sa.Column("mission_action", sa.String(30), nullable=True),
            sa.Column("keyword_mode", sa.String(10), nullable=False, server_default="MANUAL"),
            sa.Column("auto_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("merchant_id", "ad_type", name="uq_merchant_ad_config"),
        )
        op.create_index(
            "ix_merchant_ad_configs_merchant_id",
            "merchant_ad_configs",
            ["merchant_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_merchant_ad_configs_merchant_id", table_name="merchant_ad_configs")
    op.drop_table("merchant_ad_configs")
    op.drop_column("merchants", "place_code")
