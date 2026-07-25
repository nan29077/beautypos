from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean, Numeric, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    staff_code = Column(String(50), nullable=False)
    # 디자이너 분배율: (결제액 - PG수수료 - 영업수수료) 잔액 중 디자이너 몫 비율.
    # 나머지 (1 - share_rate) 는 원장(사장님) 몫. 디자이너마다 다르게 설정 가능.
    share_rate = Column(Numeric(5, 4), default=0.5, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="staff_members")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("merchant_id", "staff_code", name="uq_merchant_staff_code"),
    )
