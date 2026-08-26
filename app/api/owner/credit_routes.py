"""Owner routes — 내 매장 광고비 크레딧.

플랜에 포함된 집행량을 넘겨 광고를 더 주문하려면 광고비를 충전해야 한다.
충전은 관리자가 입금을 확인하고 반영하므로 여기서는 조회와 환불 신청만 한다.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.owner._helpers import _get_owner_merchant, require_owner
from app.database import get_db
from app.models.ad_credit import AdCreditRefund, MIN_REFUND_AMOUNT, REFUND_PENDING
from app.models.user import User
from app.schemas.schemas import AdCreditRefundRequest
from app.services import ad_credit

router = APIRouter()


@router.get("/ad/credit")
def my_credit(db: Session = Depends(get_db), user: User = Depends(require_owner),
    merchant_id: Optional[int] = Query(None, description="최고관리자 전용: 대상 가맹점 ID"),
):
    """잔액과 사용 내역, 환불 신청 현황."""
    merchant = _get_owner_merchant(user, db, merchant_id)
    info = ad_credit.credit_dict(db, merchant.id, merchant.name)
    refunds = db.query(AdCreditRefund).filter(
        AdCreditRefund.merchant_id == merchant.id
    ).order_by(AdCreditRefund.id.desc()).limit(20).all()
    pending = next((r for r in refunds if r.status == REFUND_PENDING), None)
    return {
        **info,
        # 매장에는 원장 그대로가 아니라 읽기 쉬운 사용 내역만 보여준다.
        "ledger": [ad_credit.ledger_dict(row) for row in ad_credit.ledger_list(db, merchant.id, 50)],
        "refunds": [ad_credit.refund_dict(row) for row in refunds],
        "has_pending_refund": pending is not None,
        "min_refund_amount": MIN_REFUND_AMOUNT,
    }


@router.post("/ad/credit/refund")
def request_credit_refund(
    req: AdCreditRefundRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """남은 잔액 전액을 환불 신청한다 (잔액이 최소 금액 이상일 때)."""
    merchant = _get_owner_merchant(user, db)
    refund = ad_credit.request_refund(db, merchant.id, req.reason, user)
    return ad_credit.refund_dict(refund, merchant.name)
