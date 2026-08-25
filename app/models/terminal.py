from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


class TerminalDevice(Base):
    __tablename__ = "terminal_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    terminal_serial = Column(String(100), unique=True, nullable=False)
    api_key_hash = Column(String(255), nullable=False)
    # 조회용 지문 — HMAC-SHA256(JWT_SECRET_KEY, 평문 키).
    # 인증 때 전체 단말기를 bcrypt 로 순회하지 않고 이 값으로 후보 한 행만 찾는다.
    # 레거시 행은 비어 있을 수 있어 nullable 이다 (첫 인증 성공 시 채워진다).
    api_key_fingerprint = Column(String(64), nullable=True, index=True)
    memo = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="terminals")
