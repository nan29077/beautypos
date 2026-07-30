"""
Sales Manager (영업관리자) API routes.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.settlement import (
    MerchantSalesAssignment, FeePolicy, PayoutRequest, PayoutStatus,
)
from app.auth.dependencies import get_current_user, require_roles
from app.services.settlement_service import (
    compute_distribution, get_effective_fee_rates, apply_vat, VAT_RATE,
)
from app.services.visibility import commission_visible_for
from app.schemas.schemas import PayoutRequestCreate

router = APIRouter(prefix="/api/sales", tags=["sales"])

require_sales = require_roles([UserRole.ADMIN, UserRole.SALES])


def _date_range(range_str: str):
    now = datetime.utcnow()
    if range_str == "day":
        return now - timedelta(days=1), now
    elif range_str == "week":
        return now - timedelta(weeks=1), now
    elif range_str == "month":
        return now - timedelta(days=30), now
    else:
        return datetime(2000, 1, 1), now


@router.get("/merchants")
def list_my_merchants(db: Session = Depends(get_db), user: User = Depends(require_sales)):
    assigns = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.sales_manager_user_id == user.id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).all()
    results = []
    for a in assigns:
        m = db.query(Merchant).filter(Merchant.id == a.merchant_id).first()
        if m:
            results.append({
                "id": m.id, "name": m.name, "address": m.address,
                "phone": m.phone, "commission_rate": float(a.commission_rate),
            })
    return results


@router.get("/merchants/{mid}/stats")
def merchant_stats(
    mid: int,
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_sales),
):
    # Verify assignment
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == mid,
        MerchantSalesAssignment.sales_manager_user_id == user.id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    if not assign:
        raise HTTPException(status_code=403, detail="Not assigned to this merchant")

    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404)

    start, end = _date_range(range)
    txns = db.query(Transaction).filter(
        Transaction.merchant_id == mid,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()

    gross = sum(float(t.amount) for t in txns)

    # 기본 수수료율은 정산 로직(settlement_service)과 반드시 같아야 한다.
    # net_amount 는 net_payout = gross - merchant_fee 기준.
    # 저장된 수수료율은 부가세 별도이므로 금액 계산은 실제 적용율(× 1.1)로 한다.
    merchant_fee_rate, pg_fee_rate, commission_rate = get_effective_fee_rates(
        db, mid, assign.sales_manager_user_id
    )
    merchant_fee_rate_vat = apply_vat(merchant_fee_rate)
    pg_fee_rate_vat = apply_vat(pg_fee_rate)

    merchant_fee = round(gross * merchant_fee_rate_vat)
    pg_fee = round(gross * pg_fee_rate_vat, 2)
    commission = round(gross * commission_rate, 2)

    show_commission = commission_visible_for(db, user.role)
    return {
        "merchant_id": mid, "merchant_name": merchant.name,
        "range": range,
        "transaction_count": len(txns),
        "gross_amount": gross,
        # 수수료율 — merchant_fee_rate/pg_fee_rate 는 부가세 별도, *_with_vat 가 실제 적용율
        "merchant_fee_rate": merchant_fee_rate,
        "pg_fee_rate": pg_fee_rate,
        "merchant_fee_rate_with_vat": merchant_fee_rate_vat,
        "pg_fee_rate_with_vat": pg_fee_rate_vat,
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        # 금액은 부가세 포함 적용율 기준
        "merchant_fee": merchant_fee,
        "pg_fee": pg_fee,
        "show_commission": show_commission,
        "commission_rate": commission_rate if show_commission else None,
        "commission_amount": commission if show_commission else None,
        "net_amount": round(gross - merchant_fee, 2),
    }


@router.get("/merchants/{mid}/breakdown")
def merchant_breakdown(
    mid: int,
    range: str = Query("month", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_sales),
):
    """딜러가 담당 가맹점의 하위 단계(원장/디자이너) 분배 내역을 조회.

    영업수수료 표시 설정이 OFF 면 커미션 금액·비율을 마스킹한다.
    """
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == mid,
        MerchantSalesAssignment.sales_manager_user_id == user.id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    if not assign and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not assigned to this merchant")

    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404)

    start, end = _date_range(range)
    txns = db.query(Transaction).filter(
        Transaction.merchant_id == mid,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()

    result = compute_distribution(db, mid, txns)
    show_commission = commission_visible_for(db, user.role)
    result["show_sales_commission"] = show_commission
    if not show_commission:
        result["sales_commission"] = None
        result["sales_commission_rate"] = None
        for d in result["designers"]:
            d["sales_commission"] = None
    result["range"] = range
    result["merchant_name"] = merchant.name
    return result


# ─── Payout Requests ────────────────────────────────────────

@router.get("/payout-requests")
def list_my_payout_requests(db: Session = Depends(get_db), user: User = Depends(require_sales)):
    reqs = db.query(PayoutRequest).filter(
        PayoutRequest.requester_user_id == user.id
    ).order_by(PayoutRequest.created_at.desc()).all()
    return [{
        "id": r.id, "amount": float(r.amount),
        "bank_info": r.bank_info, "memo": r.memo,
        "status": r.status.value if r.status else None,
        "created_at": str(r.created_at),
        "reviewed_at": str(r.reviewed_at) if r.reviewed_at else None,
    } for r in reqs]


@router.post("/payout-requests")
def create_payout_request(req: PayoutRequestCreate, db: Session = Depends(get_db), user: User = Depends(require_sales)):
    pr = PayoutRequest(
        requester_user_id=user.id,
        role=user.role.value if isinstance(user.role, UserRole) else user.role,
        amount=req.amount,
        bank_info=req.bank_info,
        memo=req.memo,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return {"id": pr.id, "status": pr.status.value}


# ─── Dashboard Stats ────────────────────────────────────────

@router.get("/dashboard-stats")
def sales_dashboard_stats(db: Session = Depends(get_db), user: User = Depends(require_sales)):
    assigns = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.sales_manager_user_id == user.id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).all()
    merchant_ids = [a.merchant_id for a in assigns]

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    today_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id.in_(merchant_ids),
        Transaction.created_at >= today_start,
    ).scalar() if merchant_ids else 0

    month_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id.in_(merchant_ids),
        Transaction.created_at >= month_start,
    ).scalar() if merchant_ids else 0

    total_commission = 0
    for a in assigns:
        gross = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.merchant_id == a.merchant_id,
        ).scalar()
        total_commission += float(gross) * float(a.commission_rate)

    pending_payouts = db.query(func.count(PayoutRequest.id)).filter(
        PayoutRequest.requester_user_id == user.id,
        PayoutRequest.status == PayoutStatus.PENDING,
    ).scalar()

    show_commission = commission_visible_for(db, user.role)
    return {
        "merchant_count": len(merchant_ids),
        "today_sales": float(today_sales),
        "month_sales": float(month_sales),
        "show_commission": show_commission,
        "total_commission": round(total_commission, 2) if show_commission else None,
        "pending_payouts": pending_payouts,
    }
