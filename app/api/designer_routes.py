"""
Designer (디자이너) API routes.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.staff import Staff
from app.models.transaction import Transaction
from app.auth.dependencies import get_current_user, require_roles
from app.services.settlement_service import get_effective_fee_rates, get_sales_commission_rate
from app.services.visibility import commission_visible_for

router = APIRouter(prefix="/api/designer", tags=["designer"])

require_designer = require_roles([UserRole.ADMIN, UserRole.DESIGNER])


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


def _get_staff(user: User, db: Session) -> Staff:
    staff = db.query(Staff).filter(Staff.user_id == user.id, Staff.is_active == True).first()
    if not staff:
        raise HTTPException(status_code=404, detail="No staff record found for this designer")
    return staff


@router.get("/transactions")
def list_designer_transactions(
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_designer),
):
    staff = _get_staff(user, db)
    start, end = _date_range(range)

    txns = db.query(Transaction).filter(
        Transaction.staff_id == staff.id,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).order_by(Transaction.created_at.desc()).all()

    return [{
        "id": t.id, "amount": float(t.amount),
        "installment_months": t.installment_months,
        "card_brand": t.card_brand,
        "approval_code": t.approval_code,
        "approved_at": str(t.approved_at) if t.approved_at else None,
        "created_at": str(t.created_at),
    } for t in txns]


@router.get("/dashboard-stats")
def designer_dashboard_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_designer),
):
    staff = _get_staff(user, db)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    today_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.staff_id == staff.id,
        Transaction.created_at >= today_start,
    ).scalar()

    month_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.staff_id == staff.id,
        Transaction.created_at >= month_start,
    ).scalar()

    total_count = db.query(func.count(Transaction.id)).filter(
        Transaction.staff_id == staff.id,
    ).scalar()

    total_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.staff_id == staff.id,
    ).scalar()

    return {
        "staff_name": staff.name,
        "staff_code": staff.staff_code,
        "today_sales": float(today_sales),
        "month_sales": float(month_sales),
        "total_transactions": total_count,
        "total_sales": float(total_sales),
    }


@router.get("/settlement")
def designer_settlement(
    range: str = Query("month", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_designer),
):
    """디자이너 본인 분배 정산.

    본인 귀속 매출 → 미용실수수료 → 분배가능액(실수령액) → 디자이너 몫(본인 분배율).
    분배가능액은 정산 로직(settlement_service.compute_fee_distribution)의
    net_payout = gross - merchant_fee 와 동일 기준이어야 한다.
    영업수수료는 미용실수수료 내에서 차감되므로 분배가능액 산정에는 영향 없음.
    영업수수료 항목은 표시 설정이 OFF 면 마스킹.
    """
    staff = _get_staff(user, db)
    start, end = _date_range(range)
    txns = db.query(Transaction).filter(
        Transaction.staff_id == staff.id,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()

    gross = sum(float(t.amount) for t in txns)
    merchant_fee_rate, pg_fee_rate, _ = get_effective_fee_rates(db, staff.merchant_id)
    commission_rate = get_sales_commission_rate(db, staff.merchant_id)
    share_rate = float(staff.share_rate) if staff.share_rate is not None else 0.5

    merchant_fee = round(gross * merchant_fee_rate)
    pg_fee = round(gross * pg_fee_rate)
    sales_commission = round(gross * commission_rate)
    distributable = gross - merchant_fee
    designer_amount = round(distributable * share_rate)
    owner_amount = distributable - designer_amount

    show_commission = commission_visible_for(db, user.role)
    return {
        "range": range,
        "staff_name": staff.name,
        "count": len(txns),
        "gross": int(gross),
        "merchant_fee_rate": merchant_fee_rate,
        "merchant_fee": int(merchant_fee),
        "pg_fee": int(pg_fee),
        "sales_commission": int(sales_commission) if show_commission else None,
        "sales_commission_rate": commission_rate if show_commission else None,
        "show_sales_commission": show_commission,
        "distributable": int(distributable),
        "share_rate": share_rate,
        "designer_amount": int(designer_amount),
        "owner_amount": int(owner_amount),
    }
