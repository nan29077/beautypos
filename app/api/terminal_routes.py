"""
Terminal transaction ingest API.
Authenticates via terminal API key in X-Terminal-Key header.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.database import get_db
from app.models.terminal import TerminalDevice
from app.models.transaction import Transaction
from app.models.staff import Staff
from app.models.merchant import Merchant
from app.schemas.schemas import TerminalTransactionCreate

router = APIRouter(prefix="/api/terminal", tags=["terminal"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _auth_terminal(api_key: str, db: Session) -> TerminalDevice:
    """Authenticate terminal by API key."""
    # For MVP, we check against all active terminals
    terminals = db.query(TerminalDevice).filter(TerminalDevice.is_active == True).all()
    for t in terminals:
        if pwd_context.verify(api_key, t.api_key_hash):
            return t
    raise HTTPException(status_code=401, detail="Invalid terminal API key")


@router.post("/transactions")
def ingest_transaction(
    req: TerminalTransactionCreate,
    x_terminal_key: str = Header(..., alias="X-Terminal-Key"),
    db: Session = Depends(get_db),
):
    """
    Receive a payment from a terminal device.
    - Authenticates via X-Terminal-Key header.
    - If staff_code is valid for the merchant, assigns to that staff.
    - Otherwise assigns to the merchant owner.
    """
    terminal = _auth_terminal(x_terminal_key, db)

    # Validate merchant
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=400, detail="Merchant not found")

    # Ensure terminal belongs to merchant
    if terminal.merchant_id != merchant.id:
        raise HTTPException(status_code=403, detail="Terminal does not belong to this merchant")

    # Staff code resolution
    staff_id = None
    owner_user_id = merchant.owner_user_id
    log_note = None

    if req.staff_code:
        staff = db.query(Staff).filter(
            Staff.merchant_id == merchant.id,
            Staff.staff_code == req.staff_code,
            Staff.is_active == True,
        ).first()
        if staff:
            staff_id = staff.id
        else:
            log_note = f"Invalid staff_code '{req.staff_code}' — assigned to owner"
    else:
        log_note = "No staff_code — assigned to owner"

    txn = Transaction(
        merchant_id=merchant.id,
        terminal_id=terminal.id,
        staff_id=staff_id,
        owner_user_id=owner_user_id,
        amount=req.amount,
        installment_months=req.installment_months,
        card_brand=req.card_brand,
        approval_code=req.approval_code,
        staff_code_input=req.staff_code,
        approved_at=req.approved_at or datetime.utcnow(),
        raw_payload_json=json.dumps(req.model_dump(), default=str),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    return {
        "id": txn.id,
        "merchant_id": txn.merchant_id,
        "staff_id": txn.staff_id,
        "amount": float(txn.amount),
        "assigned_to": "staff" if staff_id else "owner",
        "note": log_note,
    }
