"""매장 광고비 크레딧 — 잔액 · 원장 · 환불 신청.

플랜에 포함된 집행량을 넘겨 광고를 더 하고 싶은 매장이 광고비를 충전해 쓴다.

세 테이블의 역할
    MerchantAdCredit — 매장당 1행. 지금 남은 잔액.
    AdCreditLedger   — 모든 증감 이력. **잔액은 캐시이고 원장이 진실이다.**
                       amount 는 잔액 기준 증감(충전 +, 차감 −)이며 합계가 곧 잔액이어야 한다.
    AdCreditRefund   — 환불 신청과 처리 이력.

선점(hold) 개념을 두지 않는 이유
    추가 주문은 관리자 승인 없이 바로 집행되므로 주문 시점과 확정 시점 사이에
    간격이 없다. 주문할 때 바로 차감하고, 집행이 실패하면 되돌린다.
    선점 상태를 따로 관리하면 잔액이 어긋날 여지만 늘어난다.

CRM 의 고객 포인트와는 완전히 다른 개념이다. 그쪽은 매장이 고객에게 주는 적립금이고,
이쪽은 매장이 ADPAY 에 미리 넣어두는 광고비다.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Numeric, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ─── 원장 항목 종류 ─────────────────────────────────────────
ENTRY_CHARGE = "charge"    # 충전 (+) — 관리자가 입금 확인 후 반영
ENTRY_USE = "use"          # 주문 차감 (−)
ENTRY_REVERSE = "reverse"  # 주문 취소·집행 실패로 되돌림 (+)
ENTRY_REFUND = "refund"    # 환불 지급 (−)
ENTRY_ADJUST = "adjust"    # 관리자 수동 조정 (±) — 사유 필수

CREDIT_ENTRIES = [
    (ENTRY_CHARGE, "충전"),
    (ENTRY_USE, "주문 차감"),
    (ENTRY_REVERSE, "차감 취소"),
    (ENTRY_REFUND, "환불"),
    (ENTRY_ADJUST, "수동 조정"),
]
CREDIT_ENTRY_LABELS = dict(CREDIT_ENTRIES)

# ─── 환불 ───────────────────────────────────────────────────
REFUND_PENDING = "pending"
REFUND_APPROVED = "approved"
REFUND_REJECTED = "rejected"

REFUND_STATUSES = [
    (REFUND_PENDING, "처리 대기"),
    (REFUND_APPROVED, "환불 완료"),
    (REFUND_REJECTED, "반려됨"),
]
REFUND_STATUS_LABELS = dict(REFUND_STATUSES)

# 환불 최소 금액. 잔액이 이보다 적으면 환불 신청을 받지 않는다.
MIN_REFUND_AMOUNT = 10000

# ─── 주문 결제 출처 ─────────────────────────────────────────
PAYMENT_PLAN = "plan"      # 플랜 한도 안 — 추가 비용 없음
PAYMENT_CREDIT = "credit"  # 한도 초과 — 충전 크레딧에서 차감


class MerchantAdCredit(Base):
    """매장별 광고비 잔액. 원장을 합산한 결과를 빠르게 읽기 위한 캐시다."""

    __tablename__ = "merchant_ad_credits"
    __table_args__ = (
        UniqueConstraint("merchant_id", name="uq_merchant_ad_credit"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    balance = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")


class AdCreditLedger(Base):
    """크레딧 증감 이력. 지워지지 않으며 잔액 검증의 근거가 된다."""

    __tablename__ = "ad_credit_ledgers"
    __table_args__ = (
        Index("ix_ad_credit_ledgers_merchant_created", "merchant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    entry_type = Column(String(20), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False, default=0)        # 증가 +, 감소 −
    balance_after = Column(Numeric(14, 2), nullable=False, default=0)

    ad_order_id = Column(Integer, ForeignKey("ad_orders.id"), nullable=True)
    memo = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
    creator = relationship("User", foreign_keys=[created_by])

    @property
    def entry_label(self) -> str:
        return CREDIT_ENTRY_LABELS.get(self.entry_type, self.entry_type)


class AdCreditRefund(Base):
    """환불 신청. 매장이 넣고 관리자가 승인·송금한 뒤 완료 처리한다."""

    __tablename__ = "ad_credit_refunds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    status = Column(String(20), nullable=False, default=REFUND_PENDING,
                    server_default=REFUND_PENDING, index=True)
    reason = Column(String(255), nullable=True)        # 매장이 적는 사유
    admin_memo = Column(String(255), nullable=True)    # 관리자 처리 메모 / 반려 사유

    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    processed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
    requester = relationship("User", foreign_keys=[requested_by])
    processor = relationship("User", foreign_keys=[processed_by])

    @property
    def status_label(self) -> str:
        return REFUND_STATUS_LABELS.get(self.status, self.status)
