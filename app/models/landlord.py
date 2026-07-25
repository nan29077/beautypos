"""
BangGutPay (방긋페이) — Landlord Rent Payment Models
임대인이 임차인에게 QR코드를 발급하여 월세를 카드결제/정기결제로 받을 수 있는 서비스.
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float,
    ForeignKey, Text, Enum as SAEnum
)
from app.database import Base


class PropertyType(str, enum.Enum):
    APARTMENT = "apartment"
    OFFICETEL = "officetel"
    COMMERCIAL = "commercial"
    VILLA = "villa"
    OTHER = "other"


PROPERTY_TYPE_KR = {
    "apartment": "아파트",
    "officetel": "오피스텔",
    "commercial": "상가",
    "villa": "빌라",
    "other": "기타",
}


class RentPaymentStatus(str, enum.Enum):
    PAID = "paid"
    PENDING = "pending"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class RentPaymentMethod(str, enum.Enum):
    CARD_ONCE = "card_once"      # 일반결제
    CARD_RECURRING = "card_recurring"  # 정기결제
    ONGI_BANK = "ongi_bank"      # ONGI 내통장 결제


class LandlordProfile(Base):
    """임대인 프로필 (1 user ↔ 1 profile)"""
    __tablename__ = "landlord_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    building_name = Column(String(200), nullable=True)  # 대표 건물명
    property_names_list = Column(Text, nullable=True)  # 임대물건명 목록 (JSON array)
    business_no = Column(String(30), nullable=True)
    address = Column(String(300), nullable=True)
    phone = Column(String(30), nullable=True)
    bank_name = Column(String(50), nullable=True)
    bank_account = Column(String(50), nullable=True)
    bank_holder = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tenant(Base):
    """임차인 (임대인이 등록)"""
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    landlord_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=True)
    email = Column(String(200), nullable=True)
    property_type = Column(SAEnum(PropertyType), default=PropertyType.OFFICETEL)
    property_name = Column(String(200), nullable=False)  # e.g. "강남 센트럴 오피스텔"
    unit_number = Column(String(50), nullable=False)      # e.g. "301호"
    monthly_rent = Column(Float, nullable=False, default=0)
    deposit = Column(Float, nullable=True, default=0)     # 보증금
    rent_due_day = Column(Integer, default=25)             # 매달 납부일
    qr_token = Column(String(100), unique=True, nullable=False, default=lambda: uuid.uuid4().hex[:16])
    is_recurring = Column(Boolean, default=False)          # 정기결제 여부
    memo = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    contract_start = Column(DateTime, nullable=True)
    contract_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RentPayment(Base):
    """월세 결제 내역"""
    __tablename__ = "rent_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    landlord_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(SAEnum(RentPaymentMethod), default=RentPaymentMethod.CARD_ONCE)
    status = Column(SAEnum(RentPaymentStatus), default=RentPaymentStatus.PAID)
    card_brand = Column(String(50), nullable=True)
    approval_code = Column(String(100), nullable=True)
    payment_month = Column(String(7), nullable=True)  # e.g. "2025-02"
    memo = Column(Text, nullable=True)
    # ONGI 연동: payment_code가 ONGI 측 대외 식별자 — 멱등 처리 키로 사용
    ongi_payment_code = Column(String(100), unique=True, nullable=True, index=True)
    ongi_auth_no = Column(String(100), nullable=True)
    ongi_tr_no = Column(String(100), nullable=True)
    payer_name = Column(String(100), nullable=True)
    payer_phone = Column(String(30), nullable=True)
    paid_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class LandlordSalesAssignment(Base):
    """방긋페이 영업관리자 <-> 임대인 연결 (ADPAY의 MerchantSalesAssignment과 별도)"""
    __tablename__ = "landlord_sales_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    landlord_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sales_manager_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    commission_rate = Column(Float, default=0.01)  # e.g. 0.01 = 1%
    memo = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
