import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Enum as SAEnum, Text
)
from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SALES = "sales"
    OWNER = "owner"
    DESIGNER = "designer"


class BusinessType(str, enum.Enum):
    BEAUTY = "beauty"
    GENERAL = "general"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # nullable for OAuth-only users
    name = Column(String(100), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.OWNER)
    # String 타입으로 저장: MariaDB ENUM 매핑 충돌 방지
    business_type = Column(String(20), nullable=False, default="beauty", server_default="beauty")
    oauth_provider = Column(String(50), nullable=True)  # kakao / naver / google
    oauth_sub = Column(String(255), nullable=True)       # provider's user id
    phone = Column(String(30), nullable=True)
    referral_code = Column(String(50), nullable=True, unique=True, index=True)  # SALES 전용 추천 코드
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
