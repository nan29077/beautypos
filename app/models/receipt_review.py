"""
Receipt Review models for QR/NFC-based receipt review system.
"""
from datetime import datetime
import uuid
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base


class ReceiptReviewConfig(Base):
    """매장별 영수증 리뷰 설정 (QR코드/NFC 태그 발급용)"""
    __tablename__ = "receipt_review_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, unique=True, index=True)
    # 고유 토큰: QR/NFC 스캔 시 URL에 포함되는 식별자
    token = Column(String(64), nullable=False, unique=True, index=True)
    # 플레이스 URL (고객이 리뷰 작성 후 이동하는 주소)
    place_url = Column(String(500), nullable=True)
    # 안내 문구
    welcome_message = Column(Text, nullable=True, default="방문해주셔서 감사합니다! 영수증 리뷰를 남겨주세요.")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant")

    @staticmethod
    def generate_token():
        return uuid.uuid4().hex[:16]


class ReceiptReview(Base):
    """고객이 제출한 영수증 리뷰 기록"""
    __tablename__ = "receipt_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("receipt_review_configs.id"), nullable=False)
    # 고객 정보 (선택)
    customer_phone = Column(String(30), nullable=True)
    customer_name = Column(String(100), nullable=True)
    # 영수증 이미지 경로/URL
    receipt_image_url = Column(String(500), nullable=True)
    # 상태: pending(제출됨), approved(승인됨), rejected(반려됨)
    status = Column(String(20), default="pending", nullable=False)
    # 리뷰 완료 여부 (플레이스에 리뷰를 남겼는지)
    review_completed = Column(Boolean, default=False)
    # 메모
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant")
    config = relationship("ReceiptReviewConfig")
