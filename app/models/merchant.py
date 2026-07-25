from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base


# 업종별 직원매출 관리 필요 여부
STAFF_MANAGED_CATEGORIES = ['hair_salon', 'nail_shop', 'waxing_shop', 'massage_shop', 'other_staff']

class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    business_no = Column(String(50), nullable=True)
    address = Column(String(500), nullable=True)
    phone = Column(String(30), nullable=True)
    category = Column(String(50), nullable=True, default=None)  # hair_salon, nail_shop, restaurant, cafe, etc.
    category_custom = Column(String(100), nullable=True, default=None)  # 직접입력 시 값
    place_url = Column(String(500), nullable=True, default=None)  # 네이버 플레이스 URL
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", foreign_keys=[owner_user_id])
    staff_members = relationship("Staff", back_populates="merchant")
    terminals = relationship("TerminalDevice", back_populates="merchant")

    @property
    def needs_staff_management(self):
        """이 업종이 직원별 매출 관리가 필요한지"""
        return self.category in STAFF_MANAGED_CATEGORIES

    @property
    def display_category(self):
        """사람이 읽을 수 있는 업종명"""
        cats = {
            'hair_salon': '미용실',
            'nail_shop': '네일샵',
            'waxing_shop': '왁싱샵',
            'massage_shop': '마사지샵',
            'restaurant': '식당',
            'cafe': '카페',
            'bakery': '베이커리',
            'gym': '헬스장',
            'other_staff': '기타(직원관리)',
            'other': '기타',
        }
        if self.category == 'custom' and self.category_custom:
            return self.category_custom
        return cats.get(self.category, '미설정')
