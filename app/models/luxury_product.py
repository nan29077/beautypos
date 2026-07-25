"""
명품스토어 상품 모델
- LuxuryCategory: 상품 카테고리 (세분화)
- LuxuryProduct: 관리자가 등록하는 명품 상품
- LuxuryProductOrder: 원장(골드회원)이 선택/주문하는 상품
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Enum as SAEnum, Text,
    ForeignKey, Float
)
from sqlalchemy.orm import relationship
from app.database import Base


class LuxuryCategoryEnum(str, enum.Enum):
    """명품 카테고리 (세분화)"""
    BAG = "bag"                         # 가방
    WALLET = "wallet"                   # 지갑
    WATCH = "watch"                     # 시계
    JEWELRY = "jewelry"                 # 주얼리
    CLOTHING = "clothing"               # 의류
    SHOES = "shoes"                     # 신발
    ACCESSORY = "accessory"             # 액세서리
    PERFUME = "perfume"                 # 향수
    COSMETICS = "cosmetics"             # 화장품
    SUNGLASSES = "sunglasses"           # 선글라스
    BELT = "belt"                       # 벨트
    SCARF = "scarf"                     # 스카프/머플러
    ELECTRONICS = "electronics"         # 전자기기
    OTHER = "other"                     # 기타


LUXURY_CATEGORY_LABELS = {
    "bag": "가방",
    "wallet": "지갑",
    "watch": "시계",
    "jewelry": "주얼리",
    "clothing": "의류",
    "shoes": "신발",
    "accessory": "액세서리",
    "perfume": "향수",
    "cosmetics": "화장품",
    "sunglasses": "선글라스",
    "belt": "벨트",
    "scarf": "스카프/머플러",
    "electronics": "전자기기",
    "other": "기타",
}


class LuxuryProductStatus(str, enum.Enum):
    ACTIVE = "active"
    SOLD_OUT = "sold_out"
    HIDDEN = "hidden"


class LuxuryProduct(Base):
    """관리자가 등록하는 명품 상품"""
    __tablename__ = "luxury_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    brand = Column(String(100), nullable=False)         # 브랜드명 (구찌, 루이비통 등)
    category = Column(SAEnum(LuxuryCategoryEnum), nullable=False, default=LuxuryCategoryEnum.OTHER)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False, default=0)           # 정가 (원)
    discount_price = Column(Integer, nullable=True)              # 할인가 (원)
    image_url = Column(String(500), nullable=True)               # 상품 이미지 URL
    status = Column(SAEnum(LuxuryProductStatus), nullable=False, default=LuxuryProductStatus.ACTIVE)
    stock = Column(Integer, nullable=False, default=0)           # 재고
    is_featured = Column(Boolean, default=False)                 # 추천상품 여부
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 등록한 관리자
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def category_label(self):
        return LUXURY_CATEGORY_LABELS.get(self.category.value if self.category else "", "기타")

    @property
    def display_price(self):
        return self.discount_price if self.discount_price else self.price


class LuxuryOrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class LuxuryProductOrder(Base):
    """원장(골드회원)이 선택/주문하는 명품 상품"""
    __tablename__ = "luxury_product_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("luxury_products.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    total_price = Column(Integer, nullable=False, default=0)
    status = Column(SAEnum(LuxuryOrderStatus), nullable=False, default=LuxuryOrderStatus.PENDING)
    memo = Column(Text, nullable=True)
    shipping_address = Column(String(500), nullable=True)
    shipping_phone = Column(String(30), nullable=True)
    admin_memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("LuxuryProduct", lazy="joined")
