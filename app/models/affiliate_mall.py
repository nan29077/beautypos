"""
제휴중개몰 모델
- AffiliateMall: 제휴 중개몰 정보 (로고 포함)
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text
)
from app.database import Base


class AffiliateMall(Base):
    """제휴 중개몰"""
    __tablename__ = "affiliate_malls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    logo_url = Column(String(500), nullable=True)
    website_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)       # 카테고리 (예: 패션, 리빙, 식품 등)
    commission_rate = Column(String(50), nullable=True)  # 커미션율 안내 (예: "최대 5%")
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
