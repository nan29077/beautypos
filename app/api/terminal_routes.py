"""
Terminal transaction ingest API.
Authenticates via terminal API key in X-Terminal-Key header.
"""
import json
from datetime import datetime, timezone
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


def _auth_terminal(api_key: str, db: Session, serial: str = None) -> TerminalDevice:
    """Authenticate terminal by API key.

    M-6: serial 이 있으면 해당 단말기만 bcrypt 검증 (불필요한 해시 연산 방지).
    serial 이 없으면 기존처럼 활성 단말기 전체를 순회한다.
    """
    if serial:
        t = db.query(TerminalDevice).filter(
            TerminalDevice.terminal_serial == serial,
            TerminalDevice.is_active == True,
        ).first()
        if t:
            try:
                if t.api_key_hash and pwd_context.verify(api_key, t.api_key_hash):
                    return t
            except ValueError:
                pass
        raise HTTPException(status_code=401, detail="Invalid terminal API key")

    # serial 미제공: 전체 활성 단말기를 순회 (하위 호환)
    terminals = db.query(TerminalDevice).filter(TerminalDevice.is_active == True).all()
    for t in terminals:
        # 해시 형식이 깨진 행이 하나라도 있으면 verify 가 예외를 던져 전체 인증이 500 이 된다.
        # 그런 행은 건너뛰고 나머지 단말기로 계속 대조한다.
        try:
            if t.api_key_hash and pwd_context.verify(api_key, t.api_key_hash):
                return t
        except ValueError:
            continue
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
    terminal = _auth_terminal(x_terminal_key, db, serial=req.terminal_id)

    # Validate merchant
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=400, detail="Merchant not found")
    # M-6: 비활성 가맹점 차단
    if not merchant.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 가맹점입니다")

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
        approved_at=req.approved_at or datetime.now(timezone.utc).replace(tzinfo=None),
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
