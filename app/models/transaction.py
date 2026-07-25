from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Numeric
)
from sqlalchemy.orm import relationship
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    terminal_id = Column(Integer, ForeignKey("terminal_devices.id"), nullable=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    installment_months = Column(Integer, default=0)
    card_brand = Column(String(50), nullable=True)
    approval_code = Column(String(100), nullable=True)
    staff_code_input = Column(String(50), nullable=True)  # raw input
    approved_at = Column(DateTime, nullable=True)
    raw_payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    merchant = relationship("Merchant")
    terminal = relationship("TerminalDevice")
    staff = relationship("Staff")
    owner = relationship("User", foreign_keys=[owner_user_id])
