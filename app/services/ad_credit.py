"""매장 광고비 크레딧 — 충전 · 차감 · 환불.

잔액을 바꾸는 모든 경로가 _apply() 한 곳을 지나간다.
원장을 남기지 않고 잔액만 바뀌는 길을 만들지 않기 위한 것이다.
"""
import logging
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ad_credit import (
    AdCreditLedger,
    AdCreditRefund,
    CREDIT_ENTRY_LABELS,
    ENTRY_ADJUST,
    ENTRY_CHARGE,
    ENTRY_REFUND,
    ENTRY_REVERSE,
    ENTRY_USE,
    MIN_REFUND_AMOUNT,
    MerchantAdCredit,
    REFUND_APPROVED,
    REFUND_PENDING,
    REFUND_REJECTED,
    REFUND_STATUS_LABELS,
)
from app.models.user import User
from app.utils.kst import fmt_kst

logger = logging.getLogger(__name__)

# 한 번에 충전할 수 있는 상한. 0 하나 더 붙는 오입력을 막는다.
MAX_CHARGE_AMOUNT = 100_000_000


# 행 잠금(SELECT ... FOR UPDATE)을 지원하는 백엔드.
# SQLite 는 문법 자체가 없어 그대로 걸면 OperationalError 가 난다.
_ROW_LOCK_DIALECTS = {"mysql", "mariadb", "postgresql"}


def _money(value) -> Decimal:
    return Decimal(str(value or 0))


def _supports_row_lock(db: Session) -> bool:
    bind = db.get_bind()
    return bool(bind is not None and bind.dialect.name in _ROW_LOCK_DIALECTS)


# ─── 잔액 ───────────────────────────────────────────────────

def get_or_create(db: Session, merchant_id: int) -> MerchantAdCredit:
    """잔액 행을 가져오고, 없으면 만든다.

    커밋하지 않고 flush 만 한다. 주문 행을 만들다가 차감하는 경로에서 여기가
    커밋해 버리면, 뒤이어 잔액 부족으로 실패해도 주문만 남는다.
    """
    credit = db.query(MerchantAdCredit).filter(
        MerchantAdCredit.merchant_id == merchant_id
    ).first()
    if credit is None:
        credit = MerchantAdCredit(merchant_id=merchant_id, balance=0)
        db.add(credit)
        db.flush()
    return credit


def lock_credit(db: Session, merchant_id: int) -> MerchantAdCredit:
    """잔액 행을 잠근 채로 읽는다.

    두 요청이 동시에 "잔액 확인 → 차감"을 하면 잔액보다 많이 나갈 수 있다.
    행을 먼저 잠가 뒤 요청이 앞 요청의 커밋을 기다리게 만든다.
    잠금은 이 트랜잭션이 커밋/롤백될 때 풀린다 (_apply() 끝의 commit).

    SQLite 에는 FOR UPDATE 가 없다. 로컬 개발용 단일 프로세스라 경합이 사실상
    없으므로 잠금 없이 같은 행을 돌려준다.
    """
    if _supports_row_lock(db):
        credit = db.query(MerchantAdCredit).filter(
            MerchantAdCredit.merchant_id == merchant_id
        ).with_for_update().first()
        if credit is not None:
            return credit
    return get_or_create(db, merchant_id)


def balance_of(db: Session, merchant_id: int) -> float:
    credit = db.query(MerchantAdCredit).filter(
        MerchantAdCredit.merchant_id == merchant_id
    ).first()
    return float(credit.balance) if credit else 0.0


def _apply(db: Session, merchant_id: int, entry_type: str, delta,
           memo: Optional[str], actor_id: Optional[int],
           order_id: Optional[int] = None,
           credit: Optional[MerchantAdCredit] = None) -> AdCreditLedger:
    """잔액을 움직이고 원장에 남긴다. 잔액 변경의 유일한 통로다.

    credit 을 넘기지 않으면 여기서 행을 잠그고 읽는다. 호출부가 이미 잠근 행을
    넘기면(use 처럼 잔액 검사를 먼저 해야 하는 경우) 그 행을 그대로 쓴다.
    """
    if credit is None:
        credit = lock_credit(db, merchant_id)
    new_balance = _money(credit.balance) + _money(delta)
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="잔액이 부족합니다")

    credit.balance = new_balance
    entry = AdCreditLedger(
        merchant_id=merchant_id,
        entry_type=entry_type,
        amount=_money(delta),
        balance_after=new_balance,
        ad_order_id=order_id,
        memo=memo,
        created_by=actor_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def charge(db: Session, merchant_id: int, amount, memo: Optional[str],
           actor_id: Optional[int]) -> AdCreditLedger:
    """관리자가 입금을 확인하고 크레딧을 올린다."""
    value = _money(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="충전 금액은 0보다 커야 합니다")
    if value > MAX_CHARGE_AMOUNT:
        raise HTTPException(
            status_code=400,
            detail=f"한 번에 충전할 수 있는 금액은 {MAX_CHARGE_AMOUNT:,}원까지입니다",
        )
    return _apply(db, merchant_id, ENTRY_CHARGE, value, memo, actor_id)


def use(db: Session, merchant_id: int, amount, order_id: Optional[int],
        memo: Optional[str], actor_id: Optional[int]) -> AdCreditLedger:
    """주문 시 차감한다. 잔액이 모자라면 주문 자체를 막는다.

    잔액 확인과 차감이 같은 잠금 안에서 일어나야 동시 주문 두 건이 같은 잔액을
    보고 둘 다 통과하는 사고가 나지 않는다.
    """
    value = _money(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="차감 금액이 올바르지 않습니다")
    credit = lock_credit(db, merchant_id)
    current = _money(credit.balance)
    if current < value:
        shortfall = value - current
        raise HTTPException(
            status_code=400,
            detail=f"광고비 잔액이 부족합니다. {int(shortfall):,}원을 더 충전해주세요",
        )
    return _apply(db, merchant_id, ENTRY_USE, -value, memo, actor_id, order_id, credit=credit)


def reverse(db: Session, merchant_id: int, amount, order_id: Optional[int],
            memo: Optional[str], actor_id: Optional[int]) -> AdCreditLedger:
    """주문 취소나 집행 실패로 차감을 되돌린다."""
    value = _money(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="반환 금액이 올바르지 않습니다")
    return _apply(db, merchant_id, ENTRY_REVERSE, value, memo, actor_id, order_id)


def adjust(db: Session, merchant_id: int, delta, memo: str,
           actor_id: Optional[int]) -> AdCreditLedger:
    """관리자 수동 조정. 사유 없이는 조정할 수 없다."""
    if not (memo or "").strip():
        raise HTTPException(status_code=400, detail="수동 조정은 사유를 반드시 입력해야 합니다")
    if _money(delta) == 0:
        raise HTTPException(status_code=400, detail="조정 금액이 0원입니다")
    return _apply(db, merchant_id, ENTRY_ADJUST, _money(delta), memo.strip(), actor_id)


# ─── 환불 ───────────────────────────────────────────────────

def request_refund(db: Session, merchant_id: int, reason: Optional[str],
                   user: User) -> AdCreditRefund:
    """남은 잔액 전액을 환불 신청한다.

    부분 환불을 받지 않는 이유: '환불 후 잔액 9,000원' 같은 상태가 생기면
    최소 금액 규칙이 무의미해지고 정산도 복잡해진다.
    """
    pending = db.query(AdCreditRefund).filter(
        AdCreditRefund.merchant_id == merchant_id,
        AdCreditRefund.status == REFUND_PENDING,
    ).first()
    if pending:
        raise HTTPException(status_code=400, detail="이미 처리 대기 중인 환불 신청이 있습니다")

    balance = _money(balance_of(db, merchant_id))
    if balance < MIN_REFUND_AMOUNT:
        raise HTTPException(
            status_code=400,
            detail=f"환불은 잔액이 {MIN_REFUND_AMOUNT:,}원 이상일 때 신청할 수 있습니다 "
                   f"(현재 {int(balance):,}원)",
        )

    refund = AdCreditRefund(
        merchant_id=merchant_id,
        amount=balance,
        status=REFUND_PENDING,
        reason=(reason or "").strip()[:255] or None,
        requested_by=user.id,
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return refund


def approve_refund(db: Session, refund: AdCreditRefund, admin: User,
                   memo: Optional[str]) -> AdCreditRefund:
    """송금을 마친 뒤 완료 처리한다. 이 시점에 잔액에서 차감한다."""
    from datetime import datetime

    if refund.status != REFUND_PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 환불 신청입니다")

    credit = lock_credit(db, refund.merchant_id)
    balance = _money(credit.balance)
    amount = _money(refund.amount)
    if balance < amount:
        # 신청 후 주문으로 잔액이 줄어든 경우 — 남은 만큼만 환불한다.
        amount = balance
        refund.amount = amount
    if amount <= 0:
        raise HTTPException(status_code=400, detail="환불할 잔액이 남아 있지 않습니다")

    _apply(db, refund.merchant_id, ENTRY_REFUND, -amount,
           f"환불 신청 #{refund.id} 처리", admin.id, credit=credit)
    refund.status = REFUND_APPROVED
    refund.processed_by = admin.id
    refund.processed_at = datetime.utcnow()
    refund.admin_memo = (memo or "").strip()[:255] or None
    db.commit()
    db.refresh(refund)
    return refund


def reject_refund(db: Session, refund: AdCreditRefund, admin: User,
                  memo: Optional[str]) -> AdCreditRefund:
    from datetime import datetime

    if refund.status != REFUND_PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 환불 신청입니다")
    refund.status = REFUND_REJECTED
    refund.processed_by = admin.id
    refund.processed_at = datetime.utcnow()
    refund.admin_memo = (memo or "").strip()[:255] or None
    db.commit()
    db.refresh(refund)
    return refund


# ─── 조회 · 검증 ────────────────────────────────────────────

def ledger_list(db: Session, merchant_id: int, limit: int = 100) -> list:
    return db.query(AdCreditLedger).filter(
        AdCreditLedger.merchant_id == merchant_id
    ).order_by(AdCreditLedger.id.desc()).limit(limit).all()


def verify(db: Session, merchant_id: int) -> dict:
    """원장 합계와 잔액이 맞는지 확인한다.

    잔액은 캐시일 뿐이므로 어긋날 수 있다. 관리자 화면에서 눈으로 볼 수 있게 한다.
    """
    total = db.query(func.coalesce(func.sum(AdCreditLedger.amount), 0)).filter(
        AdCreditLedger.merchant_id == merchant_id
    ).scalar() or 0
    balance = _money(balance_of(db, merchant_id))
    ledger_total = _money(total)
    return {
        "balance": float(balance),
        "ledger_total": float(ledger_total),
        "matches": balance == ledger_total,
        "difference": float(balance - ledger_total),
    }


def credit_dict(db: Session, merchant_id: int, merchant_name: Optional[str] = None) -> dict:
    check = verify(db, merchant_id)
    return {
        "merchant_id": merchant_id,
        "merchant_name": merchant_name,
        "balance": check["balance"],
        "ledger_total": check["ledger_total"],
        "balance_matches": check["matches"],
        "min_refund_amount": MIN_REFUND_AMOUNT,
        "refundable": check["balance"] >= MIN_REFUND_AMOUNT,
    }


def ledger_dict(row: AdCreditLedger) -> dict:
    return {
        "id": row.id,
        "entry_type": row.entry_type,
        "entry_label": CREDIT_ENTRY_LABELS.get(row.entry_type, row.entry_type),
        "amount": float(row.amount or 0),
        "balance_after": float(row.balance_after or 0),
        "ad_order_id": row.ad_order_id,
        "memo": row.memo,
        "created_at": fmt_kst(row.created_at),
    }


def refund_dict(row: AdCreditRefund, merchant_name: Optional[str] = None) -> dict:
    return {
        "id": row.id,
        "merchant_id": row.merchant_id,
        "merchant_name": merchant_name,
        "amount": float(row.amount or 0),
        "status": row.status,
        "status_label": REFUND_STATUS_LABELS.get(row.status, row.status),
        "reason": row.reason,
        "admin_memo": row.admin_memo,
        "created_at": fmt_kst(row.created_at),
        "processed_at": fmt_kst(row.processed_at),
    }
