"""OngiQrMapping — 온기(ONGI) QR ↔ 가맹점 매핑.

온기 결제 사본(ongi_transactions)에는 우리 쪽 가맹점 정보가 없고 온기 QR id만
있다. 관리자가 QR을 가맹점에 연결해두면 사장님(OWNER)은 자기 매장에 매핑된
QR의 결제 내역만 조회할 수 있다. QR 1개는 가맹점 1곳에만 속하고(qr_id unique),
가맹점 1곳은 QR 여러 개를 가질 수 있다.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class OngiQrMapping(Base):
    __tablename__ = "ongi_qr_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    qr_id = Column(Integer, unique=True, nullable=False)    # 온기 QR id
    qr_name = Column(String(200), nullable=True)            # 매핑 시점의 QR 이름 (표시용)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
