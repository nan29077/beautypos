import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Numeric,
    Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class TransactionStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("terminal_id", "approval_code", name="uq_terminal_approval"),
    )

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
    status = Column(
        SAEnum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.APPROVED,
        server_default=TransactionStatus.APPROVED.value,
        nullable=False,
        index=True,
    )
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    merchant = relationship("Merchant")
    terminal = relationship("TerminalDevice")
    staff = relationship("Staff")
    owner = relationship("User", foreign_keys=[owner_user_id])
