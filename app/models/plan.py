"""플랜(요금제) 관리 모델.

Plan          — 베이직/스탠다드/프리미엄 3종 플랜 카탈로그 (수수료율 + 5종 광고 목표 건수)
MerchantPlan  — 가맹점에 배정된 플랜 (배정 이력이 쌓이며, 최신 1건이 현재 플랜)
AdExecution   — 광고 집행 기록 (가맹점 × 광고종류 × 날짜)
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey, Text, Numeric,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


# 5종 광고 타입 — (code, 표시명) 순서가 화면 노출 순서다.
AD_EXECUTION_TYPES = [
    ("blog_review", "블로그 리뷰"),
    ("receipt_review", "영수증 리뷰"),
    ("place_traffic", "플레이스 트래픽"),
    ("place_save", "플레이스 저장"),
    ("shorts", "쇼츠"),
]
AD_EXECUTION_TYPE_CODES = [code for code, _ in AD_EXECUTION_TYPES]
AD_EXECUTION_TYPE_LABELS = dict(AD_EXECUTION_TYPES)

# 플랜 코드 → 표시명
PLAN_CODES = [("basic", "베이직"), ("standard", "스탠다드"), ("premium", "프리미엄")]


class Plan(Base):
    """플랜 카탈로그. 3종 고정 (basic / standard / premium)."""
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)                    # 베이직 / 스탠다드 / 프리미엄
    code = Column(String(20), nullable=False, unique=True, index=True)  # basic / standard / premium

    # 가맹점 수수료율. FeePolicy 는 비율(0.055)로 저장하지만 플랜은 화면 입력값 그대로
    # 퍼센트(5.50)로 저장한다. 부가세 별도 공급가이며 정산 시 0.055 × 1.1로 적용된다.
    merchant_fee_rate = Column(Numeric(5, 2), nullable=False, default=0)

    # 5종 광고 목표 건수. *_monthly 가 기준이며 *_daily 는 기존 DB 호환용 평균값이다.
    blog_review_daily = Column(Integer, nullable=False, default=0)
    blog_review_monthly = Column(Integer, nullable=False, default=0)
    receipt_review_daily = Column(Integer, nullable=False, default=0)
    receipt_review_monthly = Column(Integer, nullable=False, default=0)
    place_traffic_daily = Column(Integer, nullable=False, default=0)
    place_traffic_monthly = Column(Integer, nullable=False, default=0)
    place_save_daily = Column(Integer, nullable=False, default=0)
    place_save_monthly = Column(Integer, nullable=False, default=0)
    shorts_daily = Column(Integer, nullable=False, default=0)
    shorts_monthly = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def target(self, ad_type: str, period: str) -> int:
        """ad_type('blog_review') + period('daily'|'monthly') 의 목표 건수."""
        return int(getattr(self, f"{ad_type}_{period}", 0) or 0)


class MerchantPlan(Base):
    """가맹점-플랜 배정. 가장 최근 assigned_at(동률이면 id) 레코드가 현재 플랜이다."""
    __tablename__ = "merchant_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 어드민 ID (시드 배정 시 NULL)

    merchant = relationship("Merchant")
    plan = relationship("Plan")
    assigner = relationship("User", foreign_keys=[assigned_by])


class AdExecution(Base):
    """광고 집행 기록. 가맹점 × 광고종류 × 날짜 조합당 1건으로 관리한다."""
    __tablename__ = "ad_executions"
    __table_args__ = (
        UniqueConstraint("merchant_id", "ad_type", "execution_date", name="uq_ad_exec_merchant_type_date"),
        Index("ix_ad_executions_date", "execution_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    ad_type = Column(String(30), nullable=False)  # AD_EXECUTION_TYPE_CODES 중 하나
    executed_count = Column(Integer, nullable=False, default=0)
    execution_date = Column(Date, nullable=False)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
    creator = relationship("User", foreign_keys=[created_by])
