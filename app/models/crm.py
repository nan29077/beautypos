"""
미용실 CRM (고객관리프로그램) 데이터 모델.

- CrmCustomer         : 고객(회원) 상세 프로필 + 메모/태그/포인트
- CrmService          : 시술 메뉴(카테고리/가격/소요시간)
- CrmServicePrice     : 디자이너별 시술 단가 오버라이드
- CrmVisit            : 방문/시술 이력 (매출 귀속 포함)
- CrmReservation      : 예약 관리 (충돌 방지용 종료시각 포함)
- CrmPointLog         : 포인트 적립/사용 이력
- CrmMessageTemplate  : 알림톡/문자 템플릿
- CrmMessageLog       : 메시지 발송 내역 (목업 발송)
- CrmCoupon           : 쿠폰 발급/사용

원장(미용실)과 그 미용실에 귀속된 디자이너가 함께 사용한다.
모든 레코드는 merchant_id 로 미용실에 귀속된다.
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey,
    Text, Numeric, Boolean, Enum as SAEnum,
)
from app.database import Base


class ReservationStatus(str, enum.Enum):
    BOOKED = "booked"        # 예약접수
    CONFIRMED = "confirmed"  # 예약확정
    DONE = "done"            # 방문완료
    CANCELLED = "cancelled"  # 취소
    NOSHOW = "noshow"        # 노쇼


RESERVATION_STATUS_KR = {
    "booked": "예약접수",
    "confirmed": "예약확정",
    "done": "방문완료",
    "cancelled": "취소",
    "noshow": "노쇼",
}


class MessageChannel(str, enum.Enum):
    SMS = "sms"
    ALIMTALK = "alimtalk"


class MessageStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"
    QUEUED = "queued"


class CouponStatus(str, enum.Enum):
    ISSUED = "issued"
    USED = "used"
    EXPIRED = "expired"


class CrmCustomer(Base):
    __tablename__ = "crm_customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=True, index=True)
    gender = Column(String(10), nullable=True)        # male / female / none
    birthday = Column(Date, nullable=True)
    anniversary = Column(Date, nullable=True)         # 기념일
    memo = Column(Text, nullable=True)                # 고객 메모
    allergy_memo = Column(Text, nullable=True)        # 알레르기/주의사항
    hair_memo = Column(Text, nullable=True)           # 모발 상태/이력
    photo_url = Column(String(500), nullable=True)    # 고객 사진 URL
    tags = Column(String(300), nullable=True)         # 콤마 구분 태그
    assigned_staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True, index=True)
    preferred_staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)  # 선호 디자이너
    preferred_service = Column(String(200), nullable=True)  # 선호 시술
    points = Column(Integer, default=0, nullable=False)
    last_message_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CrmService(Base):
    __tablename__ = "crm_services"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)      # 컷/펌/염색/클리닉/스타일링 등
    price = Column(Numeric(12, 0), default=0, nullable=False)
    duration_min = Column(Integer, default=60, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmServicePrice(Base):
    """디자이너별 시술 단가 오버라이드 (없으면 시술 기본가 사용)."""
    __tablename__ = "crm_service_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("crm_services.id"), nullable=False, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False, index=True)
    price = Column(Numeric(12, 0), default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmVisit(Base):
    __tablename__ = "crm_visits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("crm_customers.id"), nullable=False, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True, index=True)
    service_name = Column(String(200), nullable=True)
    amount = Column(Numeric(12, 0), default=0, nullable=False)
    memo = Column(Text, nullable=True)
    visit_date = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmReservation(Base):
    __tablename__ = "crm_reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("crm_customers.id"), nullable=True, index=True)
    customer_name = Column(String(100), nullable=True)   # 비회원/워크인 예약 대비
    phone = Column(String(30), nullable=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True, index=True)
    service_name = Column(String(200), nullable=True)
    reserved_at = Column(DateTime, nullable=False, index=True)
    end_at = Column(DateTime, nullable=True)             # 종료 예정 시각(충돌 방지용)
    duration_min = Column(Integer, default=60, nullable=True)
    status = Column(SAEnum(ReservationStatus), default=ReservationStatus.BOOKED, nullable=False)
    memo = Column(Text, nullable=True)
    reminder_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmPointLog(Base):
    __tablename__ = "crm_point_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("crm_customers.id"), nullable=False, index=True)
    delta = Column(Integer, nullable=False)
    reason = Column(String(200), nullable=True)
    balance_after = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmMessageTemplate(Base):
    __tablename__ = "crm_message_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    channel = Column(SAEnum(MessageChannel), default=MessageChannel.SMS, nullable=False)
    category = Column(String(50), nullable=True)   # reminder/birthday/dormant/thanks/custom
    body = Column(Text, nullable=False)            # {고객명}, {매장명}, {예약일시} 치환변수 지원
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmMessageLog(Base):
    __tablename__ = "crm_message_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("crm_customers.id"), nullable=True, index=True)
    template_id = Column(Integer, ForeignKey("crm_message_templates.id"), nullable=True)
    channel = Column(SAEnum(MessageChannel), default=MessageChannel.SMS, nullable=False)
    to_phone = Column(String(30), nullable=True)
    content = Column(Text, nullable=False)
    status = Column(SAEnum(MessageStatus), default=MessageStatus.SENT, nullable=False)
    campaign = Column(String(50), nullable=True)   # reminder/birthday/dormant/manual
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmCoupon(Base):
    __tablename__ = "crm_coupons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("crm_customers.id"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    discount_type = Column(String(20), default="amount", nullable=False)  # amount / percent
    value = Column(Integer, default=0, nullable=False)
    status = Column(SAEnum(CouponStatus), default=CouponStatus.ISSUED, nullable=False)
    expires_at = Column(Date, nullable=True)
    used_at = Column(DateTime, nullable=True)
    memo = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
