"""
Terminal transaction ingest API.
Authenticates via terminal API key in X-Terminal-Key header.
"""
import json
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.database import get_db
from app.models.terminal import TerminalDevice
from app.models.transaction import Transaction, TransactionStatus
from app.models.settlement import Settlement
from app.models.staff import Staff
from app.models.merchant import Merchant
from app.models.user import User, UserRole
from app.auth.jwt_handler import decode_token
from app.schemas.schemas import TerminalTransactionCreate, TransactionCancelRequest

router = APIRouter(prefix="/api/terminal", tags=["terminal"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


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


def _duplicate_response(txn: Transaction) -> dict:
    """Idempotent payload for an already-ingested transaction."""
    return {
        "id": txn.id,
        "merchant_id": txn.merchant_id,
        "staff_id": txn.staff_id,
        "amount": float(txn.amount),
        "assigned_to": "staff" if txn.staff_id else "owner",
        "duplicate": True,
        "note": "이미 접수된 승인번호입니다 (중복 결제 방지)",
    }


@router.post("/transactions")
def ingest_transaction(
    req: TerminalTransactionCreate,
    response: Response,
    x_terminal_key: str = Header(..., alias="X-Terminal-Key"),
    db: Session = Depends(get_db),
):
    """
    Receive a payment from a terminal device.
    - Authenticates via X-Terminal-Key header.
    - If staff_code is valid for the merchant, assigns to that staff.
    - Otherwise assigns to the merchant owner.
    - (terminal_id, approval_code) 가 중복이면 기존 거래를 200 으로 그대로 돌려준다.
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

    # 동일 단말기 + 동일 승인번호는 재전송으로 보고 멱등 응답한다.
    if req.approval_code:
        existing = db.query(Transaction).filter(
            Transaction.terminal_id == terminal.id,
            Transaction.approval_code == req.approval_code,
        ).first()
        if existing:
            response.status_code = 200
            return _duplicate_response(existing)

    # Staff code resolution
    staff_id = None
    owner_user_id = merchant.owner_user_id
    log_note = None

    # DB 는 naive UTC 로 저장한다 (app/utils/kst.py 규약). 단말기가 tz-aware 값을
    # 보내면(예: KST +09:00) 그대로 저장하면 표시 시각이 어긋나므로 UTC 로 정규화한다.
    approved_at_value = req.approved_at
    if approved_at_value is not None and approved_at_value.tzinfo is not None:
        approved_at_value = approved_at_value.astimezone(timezone.utc).replace(tzinfo=None)

    # approval_code 가 없는 거래는 unique 제약으로 걸러지지 않으므로,
    # (terminal_id + amount + approved_at) 조합으로 재전송(중복)을 막는다.
    # approved_at 미제공 시에는 수신 시각이 매번 달라 조합 비교가 불가능하므로 건너뛴다.
    if not req.approval_code and approved_at_value is not None:
        existing = db.query(Transaction).filter(
            Transaction.terminal_id == terminal.id,
            Transaction.approval_code.is_(None),
            Transaction.amount == req.amount,
            Transaction.approved_at == approved_at_value,
            Transaction.status == TransactionStatus.APPROVED,
        ).first()
        if existing:
            response.status_code = 200
            return _duplicate_response(existing)

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
        approved_at=approved_at_value or datetime.now(timezone.utc).replace(tzinfo=None),
        raw_payload_json=json.dumps(req.model_dump(), default=str),
    )
    db.add(txn)
    try:
        db.commit()
    except IntegrityError:
        # 동시 요청으로 unique 제약에 걸린 경우에도 같은 멱등 응답을 준다.
        db.rollback()
        existing = db.query(Transaction).filter(
            Transaction.terminal_id == terminal.id,
            Transaction.approval_code == req.approval_code,
        ).first()
        if existing:
            response.status_code = 200
            return _duplicate_response(existing)
        raise HTTPException(status_code=409, detail="거래를 저장하지 못했습니다 (중복 승인번호)")
    db.refresh(txn)

    return {
        "id": txn.id,
        "merchant_id": txn.merchant_id,
        "staff_id": txn.staff_id,
        "amount": float(txn.amount),
        "assigned_to": "staff" if staff_id else "owner",
        "note": log_note,
    }


def _auth_cancel_actor(
    txn: Transaction,
    db: Session,
    x_terminal_key: Optional[str],
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    """취소 요청자를 검증한다. 단말기 키 또는 ADMIN/OWNER 토큰만 허용."""
    if x_terminal_key:
        terminal = _auth_terminal(x_terminal_key, db)
        if txn.terminal_id != terminal.id:
            raise HTTPException(status_code=403, detail="해당 단말기의 거래가 아닙니다")
        return "terminal"

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if user.role == UserRole.ADMIN:
        return "admin"
    if user.role == UserRole.OWNER:
        merchant = db.query(Merchant).filter(
            Merchant.id == txn.merchant_id,
            Merchant.owner_user_id == user.id,
        ).first()
        if not merchant:
            raise HTTPException(status_code=403, detail="본인 가맹점의 거래만 취소할 수 있습니다")
        return "owner"
    raise HTTPException(status_code=403, detail="결제 취소 권한이 없습니다")


@router.post("/transactions/{transaction_id}/cancel")
def cancel_transaction(
    transaction_id: int,
    req: Optional[TransactionCancelRequest] = None,
    x_terminal_key: Optional[str] = Header(None, alias="X-Terminal-Key"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """결제 취소. 단말기(X-Terminal-Key) 또는 ADMIN/OWNER 토큰으로 호출한다."""
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="거래를 찾을 수 없습니다")

    cancelled_by = _auth_cancel_actor(txn, db, x_terminal_key, credentials)

    if txn.status == TransactionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="이미 취소된 거래입니다")

    # 이미 정산(Settlement)에 포함된 거래는 취소를 막는다.
    # 정산 계산(settlements/calculate)은 merchant_id + created_at 이
    # period_start~period_end 안에 드는 APPROVED 거래를 합산하므로,
    # 같은 조건으로 정산 존재 여부를 확인한다 (취소 시 정산 금액 과대 계상 방지).
    if txn.created_at is not None:
        settled = db.query(Settlement).filter(
            Settlement.merchant_id == txn.merchant_id,
            Settlement.period_start <= txn.created_at,
            Settlement.period_end >= txn.created_at,
        ).first()
        if settled:
            raise HTTPException(
                status_code=409,
                detail="정산에 포함된 거래는 취소할 수 없습니다. 관리자에게 문의하세요.",
            )

    txn.status = TransactionStatus.CANCELLED
    txn.cancelled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    txn.cancel_reason = ((req.cancel_reason if req else None) or "").strip() or None
    db.commit()
    db.refresh(txn)

    return {
        "id": txn.id,
        "status": txn.status.value,
        "cancelled_at": txn.cancelled_at.isoformat(),
        "cancel_reason": txn.cancel_reason,
        "cancelled_by": cancelled_by,
    }
