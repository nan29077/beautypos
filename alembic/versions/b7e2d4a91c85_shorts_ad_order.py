"""shorts ad order — ad_order_shorts_details + AdOrderType.SHORTS

Revision ID: b7e2d4a91c85
Revises: a3f1c9e27b40
Create Date: 2026-07-30

앱 기동 시 Base.metadata.create_all 로 이미 테이블이 만들어진 환경이 있으므로,
존재 여부를 확인해 멱등하게 동작하도록 작성한다.

- ad_order_shorts_details 테이블 생성
- MariaDB/MySQL 은 ad_orders.type 이 네이티브 ENUM 이라 'SHORTS' 값을 추가한다.
  (SQLite 는 VARCHAR 이므로 변경할 것이 없다)
- 쇼츠 기능 스위치(ad_shorts_enabled) 기본값을 ON 으로 넣어 광고 주문이
  켜져 있는 환경에서 바로 쇼츠 탭이 보이게 한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7e2d4a91c85'
down_revision: Union[str, None] = 'a3f1c9e27b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AD_ORDER_TYPE_VALUES = ('BLOG', 'PLACE_TRAFFIC', 'SHORTS')


def _existing_tables() -> set:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _is_mysql() -> bool:
    return op.get_bind().dialect.name in ('mysql', 'mariadb')


def upgrade() -> None:
    tables = _existing_tables()

    if 'ad_order_shorts_details' not in tables:
        op.create_table(
            'ad_order_shorts_details',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),

            # 브랜드 · 캠페인 기본 정보
            sa.Column('campaign_name', sa.String(length=300), nullable=False),
            sa.Column('brand_name', sa.String(length=200), nullable=True),
            sa.Column('industry', sa.String(length=50), nullable=True),
            sa.Column('website_url', sa.String(length=500), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),

            # 캠페인 설정
            sa.Column('campaign_type', sa.String(length=40), nullable=False),
            sa.Column('distribution_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('video_production_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('video_duration_tier', sa.String(length=10), nullable=True),
            sa.Column('platforms_json', sa.Text(), nullable=True),
            sa.Column('platform_counts_json', sa.Text(), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('target_keywords_json', sa.Text(), nullable=True),
            sa.Column('reference_links_json', sa.Text(), nullable=True),
            sa.Column('uploaded_video_url', sa.Text(), nullable=True),

            # 영상 제작 브리프
            sa.Column('brief_product_name', sa.String(length=300), nullable=True),
            sa.Column('brief_product_detail', sa.Text(), nullable=True),
            sa.Column('brief_categories_json', sa.Text(), nullable=True),
            sa.Column('brief_tone', sa.String(length=100), nullable=True),
            sa.Column('brief_style', sa.String(length=100), nullable=True),
            sa.Column('brief_target_audience', sa.Text(), nullable=True),
            sa.Column('brief_key_messages', sa.Text(), nullable=True),
            sa.Column('brief_avoid', sa.Text(), nullable=True),
            sa.Column('brief_hashtags_json', sa.Text(), nullable=True),

            # 크리에이터 자격 요건
            sa.Column('creator_min_followers', sa.String(length=20), nullable=True),
            sa.Column('creator_gender', sa.String(length=20), nullable=True),
            sa.Column('creator_age_group', sa.String(length=20), nullable=True),
            sa.Column('creator_requirements', sa.Text(), nullable=True),

            # 브랜드 세이프티
            sa.Column('brand_forbidden_words', sa.Text(), nullable=True),
            sa.Column('brand_no_competitor', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('brand_no_adult', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('brand_no_violence', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('brand_no_political', sa.Boolean(), nullable=False, server_default=sa.false()),

            # 성과 추적
            sa.Column('track_utm', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('track_promo_code', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('kpi_goals_json', sa.Text(), nullable=True),

            # 예상 집행 비용 (원, 부가세 별도)
            sa.Column('est_distribution_cost', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
            sa.Column('est_production_cost', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
            sa.Column('est_total_cost', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),

            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['order_id'], ['ad_orders.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('order_id'),
        )

    # ad_orders.type ENUM 확장 (MariaDB/MySQL 전용)
    if _is_mysql() and 'ad_orders' in tables:
        values = ', '.join(f"'{value}'" for value in AD_ORDER_TYPE_VALUES)
        op.execute(f"ALTER TABLE ad_orders MODIFY COLUMN type ENUM({values}) NOT NULL")

    # 쇼츠 기능 스위치 기본값 ON (없을 때만 추가)
    if 'system_configs' in tables:
        bind = op.get_bind()
        exists = bind.execute(
            sa.text("SELECT 1 FROM system_configs WHERE config_key = :key"),
            {"key": "ad_shorts_enabled"},
        ).first()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO system_configs (config_key, is_enabled, description) "
                    "VALUES (:key, :enabled, :description)"
                ),
                {
                    "key": "ad_shorts_enabled",
                    "enabled": True,
                    "description": "쇼츠(숏폼) 배포 광고 ON/OFF",
                },
            )


def downgrade() -> None:
    tables = _existing_tables()

    if 'ad_order_shorts_details' in tables:
        op.drop_table('ad_order_shorts_details')

    if 'system_configs' in tables:
        op.execute("DELETE FROM system_configs WHERE config_key = 'ad_shorts_enabled'")

    if _is_mysql() and 'ad_orders' in tables:
        op.execute("DELETE FROM ad_orders WHERE type = 'SHORTS'")
        op.execute("ALTER TABLE ad_orders MODIFY COLUMN type ENUM('BLOG', 'PLACE_TRAFFIC') NOT NULL")
