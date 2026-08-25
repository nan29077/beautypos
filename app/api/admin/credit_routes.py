"""Admin routes — 매장 광고비 크레딧 관리.

매장이 입금하면 관리자가 여기서 크레딧을 반영하고, 환불 신청을 처리한다.
잔액을 바꾸는 모든 동작은 app.services.ad_credit 을 거쳐 원장에 남는다.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.ad_credit import (
    AdCreditRefund, MerchantAdCredit, MIN_REFUND_AMOUNT,
    REFUND_PENDING, REFUND_STATUSES,
)
from app.models.merchant import Merchant
from app.models.user import User
from app.schemas.schemas import AdCreditAdjust, AdCreditCharge, AdCreditRefundProcess
from app.services import ad_credit

router = APIRouter()


def _merchant_or_404(db: Session, merchant_id: int) -> Merchant:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    return merchant


@router.get("/ad-credits")
def list_ad_credits(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """가맹점별 잔액 목록. 잔액이 원장과 어긋난 곳도 함께 표시한다."""
    merchants = db.query(Merchant).filter(Merchant.is_active == True).order_by(  # noqa: E712
        Merchant.name.asc()
    ).all()
    balances = dict(
        db.query(MerchantAdCredit.merchant_id, MerchantAdCredit.balance).all()
    )
    rows = []
    for m in merchants:
        if m.id not in balances:
            # 아직 충전한 적 없는 매장은 잔액 0 으로 보여주되 행은 만들지 않는다.
            rows.append({"merchant_id": m.id, "merchant_name": m.name, "balance": 0.0,
                         "balance_matches": True, "refundable": False,
                         "min_refund_amount": MIN_REFUND_AMOUNT})
            continue
        rows.append(ad_credit.credit_dict(db, m.id, m.name))

    pending = db.query(AdCreditRefund).filter(
        AdCreditRefund.status == REFUND_PENDING
    ).count()
    return {
        "credits": rows,
        "total_balance": sum(r["balance"] for r in rows),
        "pending_refunds": pending,
        "min_refund_amount": MIN_REFUND_AMOUNT,
    }


@router.get("/merchants/{merchant_id}/ad-credit")
def get_merchant_credit(
    merchant_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """한 매장의 잔액과 원장."""
    merchant = _merchant_or_404(db, merchant_id)
    return {
        **ad_credit.credit_dict(db, merchant_id, merchant.name),
        "ledger": [ad_credit.ledger_dict(r) for r in ad_credit.ledger_list(db, merchant_id, limit)],
    }


@router.post("/merchants/{merchant_id}/ad-credit/charge")
def charge_merchant_credit(
    merchant_id: int,
    req: AdCreditCharge,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """입금을 확인하고 크레딧을 올린다."""
    merchant = _merchant_or_404(db, merchant_id)
    entry = ad_credit.charge(db, merchant_id, req.amount, req.memo, admin.id)
    return {
        "ok": True,
        "entry": ad_credit.ledger_dict(entry),
        **ad_credit.credit_dict(db, merchant_id, merchant.name),
    }


@router.post("/merchants/{merchant_id}/ad-credit/adjust")
def adjust_merchant_credit(
    merchant_id: int,
    req: AdCreditAdjust,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """수동 조정. 잘못 반영한 충전을 되돌리는 등 예외 처리용이며 사유가 필수다."""
    merchant = _merchant_or_404(db, merchant_id)
    entry = ad_credit.adjust(db, merchant_id, req.delta, req.memo, admin.id)
    return {
        "ok": True,
        "entry": ad_credit.ledger_dict(entry),
        **ad_credit.credit_dict(db, merchant_id, merchant.name),
    }


# ─── 환불 처리 ──────────────────────────────────────────────

@router.get("/ad-credit-refunds")
def list_refunds(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """환불 신청 목록. 처리 대기 건이 먼저 온다."""
    q = db.query(AdCreditRefund)
    if status:
        q = q.filter(AdCreditRefund.status == status)
    rows = q.order_by(AdCreditRefund.status.asc(), AdCreditRefund.id.desc()).all()
    names = dict(db.query(Merchant.id, Merchant.name).all())
    return {
        "refunds": [ad_credit.refund_dict(r, names.get(r.merchant_id, "-")) for r in rows],
        "statuses": [{"code": c, "label": l} for c, l in REFUND_STATUSES],
        "pending_count": sum(1 for r in rows if r.status == REFUND_PENDING),
    }


def _refund_or_404(db: Session, refund_id: int) -> AdCreditRefund:
    refund = db.query(AdCreditRefund).filter(AdCreditRefund.id == refund_id).first()
    if not refund:
        raise HTTPException(status_code=404, detail="환불 신청을 찾을 수 없습니다")
    return refund


@router.post("/ad-credit-refunds/{refund_id}/approve")
def approve_refund(
    refund_id: int,
    req: AdCreditRefundProcess,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """송금을 마친 뒤 완료 처리한다. 이 시점에 잔액에서 차감된다."""
    refund = ad_credit.approve_refund(db, _refund_or_404(db, refund_id), admin, req.memo)
    merchant = db.query(Merchant).filter(Merchant.id == refund.merchant_id).first()
    return ad_credit.refund_dict(refund, merchant.name if merchant else None)


@router.post("/ad-credit-refunds/{refund_id}/reject")
def reject_refund(
    refund_id: int,
    req: AdCreditRefundProcess,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    refund = ad_credit.reject_refund(db, _refund_or_404(db, refund_id), admin, req.memo)
    merchant = db.query(Merchant).filter(Merchant.id == refund.merchant_id).first()
    return ad_credit.refund_dict(refund, merchant.name if merchant else None)
