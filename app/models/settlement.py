import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text,
    Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


class FeePolicy(Base):
    """수수료 정책.

    merchant_id = NULL  → 전역 기본값 (플랫폼 공통 적용)
    merchant_id = <id>  → 해당 가맹점 오버라이드
    """
    __tablename__ = "fee_policies"
    __table_args__ = (UniqueConstraint("merchant_id", name="uq_fee_policies_merchant_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True)  # NULL = 전역 기본값
    merchant_fee_rate = Column(Numeric(5, 4), default=0.05)   # 미용실 부과 총 수수료율 (5%)
    pg_fee_rate = Column(Numeric(5, 4), default=0.03)          # PG사 실비용 (3%)
    vat_inclusive_rate = Column(Numeric(5, 4), default=0.033)  # 하위 호환용 (미사용 시 pg_fee_rate 기준)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant", foreign_keys=[merchant_id])


class SalesCommissionPolicy(Base):
    """영업관리자 커미션 정책.

    sales_manager_user_id = NULL  → 전역 기본값
    sales_manager_user_id = <id>  → 해당 영업관리자 오버라이드
    """
    __tablename__ = "sales_commission_policies"
    __table_args__ = (UniqueConstraint("sales_manager_user_id", name="uq_scp_sales_manager"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    sales_manager_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = 전역 기본값
    commission_rate = Column(Numeric(5, 4), default=0.01)  # 영업 커미션율 (1%)
    created_at = Column(DateTime, default=datetime.utcnow)

    sales_manager = relationship("User", foreign_keys=[sales_manager_user_id])


class MerchantSalesAssignment(Base):
    """가맹점-영업관리자 배정. 한 가맹점에 활성 배정은 1개만 허용 (앱 레이어에서 검증)."""
    __tablename__ = "merchant_sales_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    sales_manager_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    commission_rate = Column(Numeric(5, 4), default=0.01)  # 이 배정의 커미션율 (SalesCommissionPolicy 없을 때 폴백)
    memo = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("Merchant")
    sales_manager = relationship("User")


class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    sales_manager_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 정산 시점 스냅샷
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    gross_amount = Column(Numeric(14, 2), default=0)
    merchant_fee_amount = Column(Numeric(14, 2), default=0)   # 미용실이 낸 수수료
    pg_fee_amount = Column(Numeric(14, 2), default=0)          # PG 실비용
    net_amount = Column(Numeric(14, 2), default=0)             # 미용실 실수령액 (gross - merchant_fee)
    commission_amount = Column(Numeric(14, 2), default=0)      # 영업 커미션
    company_profit_amount = Column(Numeric(14, 2), default=0)  # 회사 순수익
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("Merchant")
    sales_manager = relationship("User", foreign_keys=[sales_manager_user_id])


class PayoutStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PayoutRequest(Base):
    __tablename__ = "payout_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requester_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    bank_info = Column(Text, nullable=True)
    memo = Column(Text, nullable=True)
    status = Column(SAEnum(PayoutStatus), default=PayoutStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    requester = relationship("User", foreign_keys=[requester_user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
