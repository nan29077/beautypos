import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey, Text, Numeric,
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


# ─── Ad Orders ──────────────────────────────────────────────

class AdOrderType(str, enum.Enum):
    BLOG = "blog"
    PLACE_TRAFFIC = "place_traffic"


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
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("AdOrder", backref="place_traffic_detail")
