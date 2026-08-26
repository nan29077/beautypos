"""OngiTransaction — 온기(ONGI) QR 결제 내역 로컬 사본.

온기 결제 서버에서 폴링(ongi_sync)으로 받아온 결제 1건 = 1행.
온기 쪽 결제 id(ongi_payment_id)가 멱등 키라서 몇 번을 다시 받아도 중복되지 않고,
상태가 바뀐 건(완료 → 취소)은 같은 행이 갱신된다.

단말기 결제(transactions)와 스키마가 달라(QR·주문코드·PG 거래번호 중심) 별도
테이블로 둔다. 대시보드는 이 테이블만 읽으므로 온기 서버 장애와 무관하게 뜬다.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text

from app.database import Base

# 온기 결제 상태 (온기 응답의 status 필드 그대로)
ONGI_STATUS_COMPLETED = "완료"
ONGI_STATUS_CANCELLED = "취소"


class OngiTransaction(Base):
    __tablename__ = "ongi_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ─── 온기 쪽 식별자 ───
    ongi_payment_id = Column(Integer, unique=True, nullable=False)  # 온기 결제 id (멱등 키)
    payment_code = Column(String(100), nullable=True, index=True)   # 온기 결제 코드 (노티 멱등 키와 동일)
    order_code = Column(String(100), nullable=True, index=True)     # 가맹점 주문번호
    organization_id = Column(Integer, nullable=True)                # 온기 조직(가맹점) PK
    api_mid = Column(String(50), nullable=True)

    # ─── 결제 내용 ───
    status = Column(String(20), nullable=False, index=True)         # 완료 | 취소
    amount = Column(Numeric(12, 2), nullable=True)                  # 요청 금액(원)
    pay_price = Column(Numeric(12, 2), nullable=True)               # 실결제 금액(원)
    discount_price = Column(Numeric(12, 2), nullable=True)
    payment_type = Column(String(50), nullable=True)                # 카드, 계좌이체 등
    division = Column(String(50), nullable=True)                    # 일시기부, 주문 등 결제 구분
    payment_words = Column(String(200), nullable=True)
    member_name = Column(String(100), nullable=True)                # 결제자 이름
    ongi_member_id = Column(Integer, nullable=True)

    # ─── QR ───
    qr_id = Column(Integer, nullable=True, index=True)              # 온기 QR id
    qr_name = Column(String(200), nullable=True)                    # 동기화 시점의 QR 이름 (표시용)

    # ─── PG 거래 정보 ───
    auth_no = Column(String(50), nullable=True)                     # 승인번호
    transaction_no = Column(String(100), nullable=True)             # PG 거래번호
    pg_merchant_id = Column(String(100), nullable=True)             # 온기 응답의 merchantId (PG MID)
    result_code = Column(String(20), nullable=True)
    result_message = Column(String(200), nullable=True)

    # ─── 시각 ───
    paid_at = Column(DateTime, nullable=True, index=True)           # 결제 시각 (온기 응답 그대로, KST)
    ongi_updated_at = Column(String(30), nullable=True)             # 온기 updatedAt 원문 — 변경 감지용
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)  # 마지막 동기화(UTC)

    raw_json = Column(Text, nullable=True)                          # 온기 응답 원문 (감사·재파싱용)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
