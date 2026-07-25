import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean,
    Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.database import Base


class PGProvider(Base):
    __tablename__ = "pg_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)   # seedpayments / kiwoompay / toss
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PGConfigStatus(str, enum.Enum):
    CONNECTED = "connected"
    TESTED = "tested"
    DISABLED = "disabled"


class MerchantPGConfig(Base):
    __tablename__ = "merchant_pg_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("pg_providers.id"), nullable=False)
    mid = Column(String(200), nullable=False)
    secret_encrypted = Column(Text, nullable=False)
    status = Column(SAEnum(PGConfigStatus), default=PGConfigStatus.CONNECTED)
    last_tested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant")
    provider = relationship("PGProvider")
