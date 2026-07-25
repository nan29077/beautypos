import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text,
    Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.database import Base


class FeePolicy(Base):
    __tablename__ = "fee_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, unique=True)
    pg_fee_rate = Column(Numeric(5, 4), default=0.035)  # 3.5% (VAT 별도, VAT 포함 3.85%)
    vat_inclusive_rate = Column(Numeric(5, 4), default=0.0385)  # 3.85% (VAT 포함)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant")


class MerchantSalesAssignment(Base):
    __tablename__ = "merchant_sales_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    sales_manager_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    commission_rate = Column(Numeric(5, 4), default=0.01)  # 3.5% 내에서 영업관리자 수익률 (VAT 별도)
    memo = Column(Text, nullable=True)  # 배정 메모
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("Merchant")
    sales_manager = relationship("User")


class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    gross_amount = Column(Numeric(14, 2), default=0)
    pg_fee_amount = Column(Numeric(14, 2), default=0)
    net_amount = Column(Numeric(14, 2), default=0)
    commission_amount = Column(Numeric(14, 2), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("Merchant")


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
