import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric,
    Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


# ─── Place Profile & Competitors ────────────────────────────

class AdPlaceProfile(Base):
    __tablename__ = "ad_place_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    place_url = Column(String(500), nullable=True)
    place_id = Column(String(200), nullable=True)
    nickname = Column(String(200), nullable=True)
    analysis_keyword = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdCompetitor(Base):
    __tablename__ = "ad_competitors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    competitor_place_url = Column(String(500), nullable=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Metrics ────────────────────────────────────────────────

class AdMetric(Base):
    __tablename__ = "ad_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    place_url = Column(String(500), nullable=False)
    date = Column(Date, nullable=False)
    blog_review_count = Column(Integer, default=0)
    visitor_review_count = Column(Integer, default=0)
    place_rank = Column(Integer, nullable=True)
    search_keyword = Column(String(200), nullable=True)
    source = Column(String(50), default="manual")  # manual / api
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("merchant_id", "place_url", "date", name="uq_metric_merchant_place_date"),
    )


class PlaceMetricSnapshot(Base):
    """네이버 플레이스 자동 수집 결과의 일 단위 스냅샷."""

    __tablename__ = "place_metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    place_id = Column(String(50), nullable=False, index=True)
    place_url = Column(String(500), nullable=True)
    place_name = Column(String(300), nullable=True)
    kind = Column(String(20), default="my")  # my / competitor
    blog_count = Column(Integer, nullable=True)
    visitor_count = Column(Integer, nullable=True)
    rank = Column(Integer, nullable=True)
    keyword = Column(String(200), nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("merchant_id", "place_id", "date", name="uq_snapshot_merchant_place_date"),
    )


# ─── Ad Orders ──────────────────────────────────────────────

class AdOrderType(str, enum.Enum):
    BLOG = "blog"
    PLACE_TRAFFIC = "place_traffic"
    SHORTS = "shorts"


class AdOrderStatus(str, enum.Enum):
    REQUESTED = "requested"
    REVIEWING = "reviewing"
    RUNNING = "running"
    DONE = "done"
    REJECTED = "rejected"


class AdOrder(Base):
    __tablename__ = "ad_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    type = Column(SAEnum(AdOrderType), nullable=False)
    status = Column(SAEnum(AdOrderStatus), default=AdOrderStatus.REQUESTED)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("User", foreign_keys=[created_by])
    merchant = relationship("Merchant")


class AdOrderBlogDetail(Base):
    __tablename__ = "ad_order_blog_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("ad_orders.id"), nullable=False, unique=True)
    campaign_name = Column(String(300), nullable=False)
    address = Column(String(500), nullable=True)
    contact = Column(String(100), nullable=True)
    links_json = Column(Text, nullable=True)           # JSON array of URLs
    main_keywords_json = Column(Text, nullable=True)   # JSON array max 5
    hashtags_json = Column(Text, nullable=True)         # JSON array max 5
    description = Column(Text, nullable=True)
    extra_image_link = Column(Text, nullable=True)
    order_count = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    est_total_cost = Column(Numeric(14, 2), nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("AdOrder", backref="blog_detail")


class AdOrderBlogImage(Base):
    __tablename__ = "ad_order_blog_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("ad_orders.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("AdOrder", backref="blog_images")


class AdOrderPlaceTrafficDetail(Base):
    __tablename__ = "ad_order_place_traffic_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("ad_orders.id"), nullable=False, unique=True)
    place_name_or_id = Column(String(300), nullable=False)
    search_keywords_json = Column(Text, nullable=True)  # JSON array max 3
    order_count = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    est_total_cost = Column(Numeric(14, 2), nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("AdOrder", backref="place_traffic_detail")


# ─── 쇼츠 배포 주문 옵션 · 단가 ──────────────────────────────
# 원장(가맹점)이 숏폼(쇼츠) 제작·배포를 주문할 때 선택하는 옵션 카탈로그.
# (code, 표시명) 순서가 화면 노출 순서다. 금액은 모두 "원 / 부가세 별도" 기준이다.

# 캠페인 유형 — (code, 표시명, 설명, 배포 사용, 제작 사용)
SHORTS_CAMPAIGN_TYPES = [
    ("production_distribution", "영상 제작 + 배포", "크리에이터가 직접 제작하고 자신의 채널에 배포합니다.", True, True),
    ("own_video_distribution", "자체 영상 배포", "매장이 제공한 영상을 크리에이터 채널에서 배포합니다.", True, False),
    ("existing_video_distribution", "기존 영상 기반 배포", "기존 제작 영상 URL을 기반으로 크리에이터가 배포합니다.", True, False),
    ("production_only", "단순 영상 제작", "영상 배포 없이 제작만 의뢰합니다.", False, True),
]
SHORTS_CAMPAIGN_TYPE_CODES = [code for code, _, _, _, _ in SHORTS_CAMPAIGN_TYPES]
SHORTS_CAMPAIGN_TYPE_LABELS = {code: label for code, label, _, _, _ in SHORTS_CAMPAIGN_TYPES}
# 유형별 배포/제작 건수 사용 여부
SHORTS_CAMPAIGN_TYPE_USES = {
    code: {"distribution": uses_dist, "production": uses_prod}
    for code, _, _, uses_dist, uses_prod in SHORTS_CAMPAIGN_TYPES
}

# 영상 길이 등급 — (code, 표시명, 제작 단가/건)
SHORTS_DURATION_TIERS = [
    ("15s", "15초 이하", 10000),
    ("30s", "30초 이하", 15000),
    ("60s", "60초 이하", 25000),
    ("90s", "90초 이하", 35000),
]
SHORTS_DURATION_TIER_CODES = [code for code, _, _ in SHORTS_DURATION_TIERS]
SHORTS_DURATION_TIER_PRICES = {code: price for code, _, price in SHORTS_DURATION_TIERS}

# 배포 플랫폼
SHORTS_PLATFORMS = [
    ("youtube", "YouTube"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("facebook", "Facebook"),
]
SHORTS_PLATFORM_CODES = [code for code, _ in SHORTS_PLATFORMS]

# 배포 단가 (1건 = 크리에이터 채널 1건 게시)
SHORTS_DISTRIBUTION_UNIT_PRICE = 15000

# 주문 1건당 허용하는 최대 건수 (배포/제작 각각)
SHORTS_MAX_COUNT = 1000


def shorts_estimate(campaign_type: str, distribution_count: int, video_production_count: int,
                    video_duration_tier: str | None) -> dict:
    """쇼츠 주문의 예상 집행 비용(원, 부가세 별도)을 계산한다.

    배포비 = 배포 건수 × 15,000원, 제작비 = 제작 건수 × 영상 길이 등급 단가.
    캠페인 유형이 사용하지 않는 항목은 0원으로 계산한다.
    """
    uses = SHORTS_CAMPAIGN_TYPE_USES.get(campaign_type, {"distribution": True, "production": True})
    dist_count = int(distribution_count or 0) if uses["distribution"] else 0
    prod_count = int(video_production_count or 0) if uses["production"] else 0
    unit_price = SHORTS_DURATION_TIER_PRICES.get(video_duration_tier or "", 0)

    distribution_cost = dist_count * SHORTS_DISTRIBUTION_UNIT_PRICE
    production_cost = prod_count * unit_price
    return {
        "distribution_count": dist_count,
        "production_count": prod_count,
        "distribution_unit_price": SHORTS_DISTRIBUTION_UNIT_PRICE,
        "production_unit_price": unit_price,
        "distribution_cost": distribution_cost,
        "production_cost": production_cost,
        "total_cost": distribution_cost + production_cost,
    }


class AdOrderShortsDetail(Base):
    """쇼츠(숏폼) 제작·배포 주문 상세.

    원장이 입력하는 5단계(브랜드 정보 / 캠페인 설정 / 영상 브리프 /
    크리에이터 자격 / 확인)의 값을 한 행에 보관한다.
    리스트·맵 형태의 값은 다른 광고 주문과 동일하게 `*_json` 컬럼에 JSON 문자열로 저장한다.
    """

    __tablename__ = "ad_order_shorts_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("ad_orders.id"), nullable=False, unique=True)

    # 1) 브랜드 · 캠페인 기본 정보
    campaign_name = Column(String(300), nullable=False)
    brand_name = Column(String(200), nullable=True)
    industry = Column(String(50), nullable=True)
    website_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)

    # 2) 캠페인 설정
    campaign_type = Column(String(40), nullable=False)
    distribution_count = Column(Integer, nullable=False, default=0)
    video_production_count = Column(Integer, nullable=False, default=0)
    video_duration_tier = Column(String(10), nullable=True)
    platforms_json = Column(Text, nullable=True)         # JSON array: ["youtube", ...]
    platform_counts_json = Column(Text, nullable=True)   # JSON object: {"youtube": 10}
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    target_keywords_json = Column(Text, nullable=True)   # JSON array
    reference_links_json = Column(Text, nullable=True)   # JSON array
    uploaded_video_url = Column(Text, nullable=True)

    # 3) 영상 제작 브리프
    brief_product_name = Column(String(300), nullable=True)
    brief_product_detail = Column(Text, nullable=True)
    brief_categories_json = Column(Text, nullable=True)  # JSON object: {"youtube": "뷰티 / 메이크업"}
    brief_tone = Column(String(100), nullable=True)
    brief_style = Column(String(100), nullable=True)
    brief_target_audience = Column(Text, nullable=True)
    brief_key_messages = Column(Text, nullable=True)
    brief_avoid = Column(Text, nullable=True)
    brief_hashtags_json = Column(Text, nullable=True)    # JSON array

    # 4) 크리에이터 자격 요건
    creator_min_followers = Column(String(20), nullable=True)
    creator_gender = Column(String(20), nullable=True)
    creator_age_group = Column(String(20), nullable=True)
    creator_requirements = Column(Text, nullable=True)

    # 4) 브랜드 세이프티
    brand_forbidden_words = Column(Text, nullable=True)
    brand_no_competitor = Column(Boolean, nullable=False, default=False)
    brand_no_adult = Column(Boolean, nullable=False, default=False)
    brand_no_violence = Column(Boolean, nullable=False, default=False)
    brand_no_political = Column(Boolean, nullable=False, default=False)

    # 4) 성과 추적
    track_utm = Column(Boolean, nullable=False, default=False)
    track_promo_code = Column(Boolean, nullable=False, default=False)
    kpi_goals_json = Column(Text, nullable=True)         # JSON array

    # 5) 예상 집행 비용 (원, 부가세 별도) — 주문 시점 단가로 서버에서 산출해 보관한다.
    est_distribution_cost = Column(Numeric(12, 2), nullable=False, default=0)
    est_production_cost = Column(Numeric(12, 2), nullable=False, default=0)
    est_total_cost = Column(Numeric(12, 2), nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("AdOrder", backref="shorts_detail")
