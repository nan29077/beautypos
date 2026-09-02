"""광고 집행 원장 — 리워드팝에 보낸 요청 1건 = 1행.

AdExecution 과의 차이:
    AdExecution — "며칠에 몇 건 나갔다" 는 결과 집계. 화면의 진도표가 이걸 읽는다.
    AdDispatch  — "어떤 요청을 보내 무슨 응답을 받았다" 는 연동 원장.

둘을 한 테이블로 합치면 실패·보류 이력이 집계에 섞여 진도표가 오염된다.
집행이 성공했을 때만 AdExecution 을 갱신한다.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ─── 집행 출처 ──────────────────────────────────────────────
SOURCE_AUTO = "auto"    # 스케줄러(또는 관리자 수동 실행)가 플랜 목표대로 집행
SOURCE_ORDER = "order"  # 매장이 크레딧으로 넣은 추가 주문

# ─── 상태 ───────────────────────────────────────────────────
STATUS_PENDING = "pending"    # 행만 만들고 아직 전송 전
STATUS_DRY_RUN = "dry_run"    # 드라이런 — 실제로 보내지 않고 요청 내용만 기록
STATUS_SENT = "sent"          # 리워드팝이 접수함
STATUS_RUNNING = "running"    # 진행 중
STATUS_DONE = "done"          # 완료
STATUS_FAILED = "failed"      # 실패 (재시도 대상일 수 있음)
STATUS_SKIPPED = "skipped"    # 사전 점검에서 건너뜀 (호출하지 않음)

DISPATCH_STATUSES = [
    (STATUS_PENDING, "전송 대기"),
    (STATUS_DRY_RUN, "드라이런"),
    (STATUS_SENT, "접수됨"),
    (STATUS_RUNNING, "진행 중"),
    (STATUS_DONE, "완료"),
    (STATUS_FAILED, "실패"),
    (STATUS_SKIPPED, "보류"),
]
DISPATCH_STATUS_CODES = [code for code, _ in DISPATCH_STATUSES]
DISPATCH_STATUS_LABELS = dict(DISPATCH_STATUSES)

# 집행이 실제로 이뤄진 것으로 볼 상태 (AdExecution 에 반영되는 상태)
EXECUTED_STATUSES = {STATUS_SENT, STATUS_RUNNING, STATUS_DONE}

# ─── 보류 사유 ──────────────────────────────────────────────
SKIP_NO_KEYWORD = "no_keyword"
SKIP_NO_PLAN = "no_plan"
SKIP_ZERO_TARGET = "zero_target"
SKIP_ALREADY_DONE = "already_done"
SKIP_INTEGRATION_OFF = "integration_off"
SKIP_NO_PRICE = "no_price"
SKIP_LOW_BALANCE = "low_balance"
SKIP_NO_CONFIG = "no_config"      # 매장별 리워드팝 집행 설정 미등록
SKIP_NO_PLACE_CODE = "no_place_code"  # 네이버 플레이스 코드 미등록
SKIP_INVALID_CONFIG = "invalid_config"  # 공식 API 규격과 맞지 않는 설정

SKIP_REASON_LABELS = {
    SKIP_NO_KEYWORD: "승인된 키워드 없음",
    SKIP_NO_PLAN: "플랜 미배정",
    SKIP_ZERO_TARGET: "오늘 목표 없음",
    SKIP_ALREADY_DONE: "오늘 이미 집행됨",
    SKIP_INTEGRATION_OFF: "리워드팝 연동 꺼짐",
    SKIP_NO_PRICE: "단가 미설정",
    SKIP_LOW_BALANCE: "포인트 잔액 부족",
    SKIP_NO_CONFIG: "리워드팝 집행 설정 미등록",
    SKIP_NO_PLACE_CODE: "네이버 플레이스 코드 미등록",
    SKIP_INVALID_CONFIG: "리워드팝 집행 설정 오류",
}

# 재시도 상한과 간격(분). 지수 백오프 — 무한 재시도는 포인트를 태운다.
MAX_RETRY = 3
RETRY_BACKOFF_MINUTES = [10, 30, 120]


class AdDispatch(Base):
    __tablename__ = "ad_dispatches"
    __table_args__ = (
        # 멱등의 핵심. 같은 날 같은 가맹점·광고에 두 번 나가는 것을 DB 가 막는다.
        UniqueConstraint("idempotency_key", name="uq_ad_dispatch_idempotency"),
        Index("ix_ad_dispatches_date_status", "execution_date", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    ad_type = Column(String(30), nullable=False)
    execution_date = Column(Date, nullable=False, index=True)

    source = Column(String(20), nullable=False, default=SOURCE_AUTO, server_default=SOURCE_AUTO)
    ad_order_id = Column(Integer, ForeignKey("ad_orders.id"), nullable=True)

    requested_count = Column(Integer, nullable=False, default=0)
    keyword = Column(String(200), nullable=True)  # 이번 집행에 쓴 키워드 (쉼표 구분)

    status = Column(String(20), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING)
    skip_reason = Column(String(40), nullable=True)

    external_order_id = Column(String(100), nullable=True, index=True)
    # "auto:12:place_traffic:2026-08-25" 형태. 재실행해도 같은 값이 나와야 한다.
    idempotency_key = Column(String(150), nullable=False)

    request_json = Column(Text, nullable=True)   # 보낸 값 원본 — 분쟁·디버깅용
    response_json = Column(Text, nullable=True)  # 받은 값 원본

    error_message = Column(String(500), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    next_retry_at = Column(DateTime, nullable=True)

    cost_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    dry_run = Column(Boolean, nullable=False, default=False, server_default="0")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 수동 실행자
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
    creator = relationship("User", foreign_keys=[created_by])

    @property
    def status_label(self) -> str:
        return DISPATCH_STATUS_LABELS.get(self.status, self.status)

    @property
    def skip_reason_label(self) -> str:
        return SKIP_REASON_LABELS.get(self.skip_reason or "", self.skip_reason or "")

    @property
    def counts_as_executed(self) -> bool:
        """이 건을 집행 실적(AdExecution)으로 볼 수 있는지."""
        return self.status in EXECUTED_STATUSES and not self.dry_run

    @property
    def retryable(self) -> bool:
        return self.status == STATUS_FAILED and self.retry_count < MAX_RETRY


def build_idempotency_key(source: str, merchant_id: int, ad_type: str,
                          execution_date, order_id=None) -> str:
    """재실행해도 같은 값이 나오는 키. 자동 집행은 하루 한 번으로 고정된다."""
    if source == SOURCE_ORDER and order_id:
        return f"order:{order_id}:{ad_type}"
    return f"auto:{merchant_id}:{ad_type}:{execution_date}"
