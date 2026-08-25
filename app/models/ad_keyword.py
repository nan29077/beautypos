"""매장별 광고 집행 키워드.

기존 키워드와의 차이:
  AdPlaceProfile.analysis_keyword          — 순위 '분석'용 키워드 1개
  AdOrderPlaceTrafficDetail.search_keywords_json — 그 주문 1건에만 쓰이는 키워드
  MerchantAdKeyword (이 파일)              — 매장에 상시 등록되어 매일 자동 집행에 쓰이는 키워드

매장(원장)과 최고관리자가 모두 등록할 수 있고, 매장이 등록한 것은
관리자 승인을 받아야 집행에 쓰인다. 관리자가 등록한 것은 즉시 승인 상태가 된다.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.database import Base


# 승인 상태
KEYWORD_PENDING = "pending"
KEYWORD_APPROVED = "approved"
KEYWORD_REJECTED = "rejected"
KEYWORD_STATUSES = [
    (KEYWORD_PENDING, "승인 대기"),
    (KEYWORD_APPROVED, "승인됨"),
    (KEYWORD_REJECTED, "반려됨"),
]
KEYWORD_STATUS_CODES = [code for code, _ in KEYWORD_STATUSES]
KEYWORD_STATUS_LABELS = dict(KEYWORD_STATUSES)

# ad_type 이 빈 문자열이면 '모든 광고 공통'을 뜻한다.
# NULL 을 쓰지 않는 이유: 유니크 제약에서 NULL 은 서로 다른 값으로 취급돼
# 같은 키워드를 몇 번이든 중복 등록할 수 있게 되기 때문이다.
AD_TYPE_ALL = ""

# 매장 한 곳이 등록할 수 있는 키워드 수 상한.
# 너무 많으면 집행이 분산돼 효과가 흐려지고, 검수 부담도 커진다.
MAX_KEYWORDS_PER_MERCHANT = 20

KEYWORD_MAX_LENGTH = 60


class MerchantAdKeyword(Base):
    """매장에 상시 등록되는 광고 집행 키워드."""

    __tablename__ = "merchant_ad_keywords"
    __table_args__ = (
        UniqueConstraint("merchant_id", "ad_type", "keyword", name="uq_merchant_ad_keyword"),
        Index("ix_merchant_ad_keywords_status", "merchant_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    keyword = Column(String(KEYWORD_MAX_LENGTH), nullable=False)

    # AD_EXECUTION_TYPE_CODES 중 하나, 또는 빈 문자열(모든 광고 공통)
    ad_type = Column(String(30), nullable=False, default=AD_TYPE_ALL, server_default="")

    # 낮을수록 먼저 쓰인다. 자동 집행은 이 순서로 날짜에 따라 순환한다.
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    status = Column(String(20), nullable=False, default=KEYWORD_PENDING, server_default=KEYWORD_PENDING)
    reject_reason = Column(String(255), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_role = Column(String(20), nullable=True)  # owner / admin
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
    creator = relationship("User", foreign_keys=[created_by])
    approver = relationship("User", foreign_keys=[approved_by])

    @property
    def is_usable(self) -> bool:
        """자동 집행에 쓸 수 있는 상태인지."""
        return self.is_active and self.status == KEYWORD_APPROVED

    @property
    def status_label(self) -> str:
        return KEYWORD_STATUS_LABELS.get(self.status, self.status)
