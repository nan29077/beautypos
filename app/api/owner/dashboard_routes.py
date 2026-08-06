"""Owner dashboard / sales / transactions / settlement routes.

Split out of the original app/api/owner_routes.py.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.models.staff import Staff
from app.models.transaction import Transaction, TransactionStatus
from app.models.settlement import Settlement
from app.utils.kst import today_kst, kst_day_start_utc
from app.services.settlement_service import compute_distribution
from app.services.visibility import commission_visible_for

from app.api.owner._helpers import require_owner, _get_owner_merchant, _date_range

router = APIRouter()


# ─── Transactions ────────────────────────────────────────────

@router.get("/transactions")
def list_owner_transactions(
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    staff_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    merchant = _get_owner_merchant(user, db)
    start, end = _date_range(range)
    q = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    )
    if staff_id:
        q = q.filter(Transaction.staff_id == staff_id)
    txns = q.order_by(Transaction.created_at.desc()).all()

    results = []
    for t in txns:
        staff_name = None
        if t.staff_id:
            staff = db.query(Staff).filter(Staff.id == t.staff_id).first()
            staff_name = staff.name if staff else None
        results.append({
            "id": t.id, "amount": float(t.amount),
            "installment_months": t.installment_months,
            "card_brand": t.card_brand,
            "staff_id": t.staff_id, "staff_name": staff_name,
            "staff_code_input": t.staff_code_input,
            "approval_code": t.approval_code,
            "approved_at": str(t.approved_at) if t.approved_at else None,
            "created_at": str(t.created_at),
        })
    return results


# ─── Calendar Monthly Data ──────────────────────────────────

@router.get("/calendar-monthly")
def calendar_monthly_data(
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """Get daily aggregated sales for a given month (calendar view)."""
    merchant = _get_owner_merchant(user, db)
    from calendar import monthrange
    from datetime import datetime
    _, last_day = monthrange(year, month)
    month_start = datetime(year, month, 1)
    month_end = datetime(year, month, last_day, 23, 59, 59)

    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= month_start,
        Transaction.created_at <= month_end,
    ).all()

    # Aggregate by day
    daily_map = {}
    for t in txns:
        day_key = t.created_at.strftime("%Y-%m-%d")
        if day_key not in daily_map:
            daily_map[day_key] = {"date": day_key, "total": 0, "count": 0}
        daily_map[day_key]["total"] += float(t.amount)
        daily_map[day_key]["count"] += 1

    return {
        "year": year,
        "month": month,
        "days": list(daily_map.values()),
    }


@router.get("/calendar-daily")
def calendar_daily_data(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """Get detailed transactions for a specific date."""
    merchant = _get_owner_merchant(user, db)
    from datetime import datetime
    day_start = datetime.strptime(date, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)

    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= day_start,
        Transaction.created_at < day_end,
    ).order_by(Transaction.created_at.desc()).all()

    results = []
    for t in txns:
        staff_name = None
        if t.staff_id:
            staff = db.query(Staff).filter(Staff.id == t.staff_id).first()
            staff_name = staff.name if staff else None
        results.append({
            "id": t.id, "amount": float(t.amount),
            "installment_months": t.installment_months,
            "card_brand": t.card_brand,
            "staff_name": staff_name,
            "approval_code": t.approval_code,
            "created_at": str(t.created_at),
        })
    return {
        "date": date,
        "transactions": results,
        "total": sum(r["amount"] for r in results),
        "count": len(results),
    }


# ─── Settlement Breakdown (디자이너 분배 정산) ────────────────

@router.get("/settlement-breakdown")
def owner_settlement_breakdown(
    range: str = Query("month", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """기간별 디자이너/원장 분배 내역.

    결제액 → PG수수료 → 영업수수료 → 분배가능액 → 디자이너 몫 / 원장 몫.
    영업수수료(딜러 커미션) 항목은 표시 설정이 OFF 면 마스킹한다.
    """
    merchant = _get_owner_merchant(user, db)
    start, end = _date_range(range)
    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
        Transaction.status == TransactionStatus.APPROVED,
    ).all()

    result = compute_distribution(db, merchant.id, txns)
    show_commission = commission_visible_for(db, user.role)
    result["show_sales_commission"] = show_commission

    if not show_commission:
        # 영업수수료 금액·비율을 숨기고, 분배가능액에 합산해 노출 (디자이너/원장 몫은 불변)
        result["sales_commission"] = None
        result["sales_commission_rate"] = None
        for d in result["designers"]:
            d["sales_commission"] = None

    result["range"] = range
    result["merchant_name"] = merchant.name
    return result


# ─── Settlements (관리자가 확정한 정산 내역) ──────────────────

@router.get("/settlements")
def list_owner_settlements(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """최고관리자가 계산·확정한 우리 매장 정산 내역.

    금액은 결제액 → PG수수료 → 실지급액(net) 순으로 내려주고,
    영업수수료 항목은 표시 설정이 OFF 면 마스킹한다.
    """
    merchant = _get_owner_merchant(user, db)
    rows = db.query(Settlement).filter(
        Settlement.merchant_id == merchant.id,
    ).order_by(Settlement.period_start.desc(), Settlement.id.desc()).limit(limit).all()

    show_commission = commission_visible_for(db, user.role)
    return [{
        "id": s.id,
        "merchant_name": merchant.name,
        "period_start": str(s.period_start),
        "period_end": str(s.period_end),
        "gross_amount": float(s.gross_amount),
        "pg_fee_amount": float(s.pg_fee_amount),
        "net_amount": float(s.net_amount),
        "commission_amount": float(s.commission_amount) if show_commission else None,
        "show_sales_commission": show_commission,
        "created_at": str(s.created_at),
    } for s in rows]


# ─── Dashboard Stats ────────────────────────────────────────

@router.get("/dashboard-stats")
def owner_dashboard_stats(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    _kst_today = today_kst()
    today_start = kst_day_start_utc(_kst_today)
    month_start = kst_day_start_utc(_kst_today.replace(day=1))

    today_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= today_start,
    ).scalar()

    month_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= month_start,
    ).scalar()

    # 이번 주 (KST 기준 이번 주 월요일 0시)
    week_start = kst_day_start_utc(_kst_today - timedelta(days=_kst_today.weekday()))
    week_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= week_start,
    ).scalar()

    # 전체 누적 매출
    total_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
    ).scalar()

    # 정산 예정: 가장 최근 정산의 period_end 이후 거래액 합계
    last_settlement = db.query(Settlement).filter(
        Settlement.merchant_id == merchant.id,
    ).order_by(Settlement.period_end.desc()).first()
    pending_q = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
    )
    if last_settlement:
        pending_q = pending_q.filter(Transaction.created_at > last_settlement.period_end)
    pending_settlement = pending_q.scalar()

    total_txns = db.query(func.count(Transaction.id)).filter(
        Transaction.merchant_id == merchant.id,
    ).scalar()

    staff_count = db.query(func.count(Staff.id)).filter(
        Staff.merchant_id == merchant.id, Staff.is_active == True,
    ).scalar()

    # --- 추가 통계 ---
    yesterday_start = today_start - timedelta(days=1)
    yesterday_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= yesterday_start,
        Transaction.created_at < today_start,
    ).scalar()

    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= last_month_start,
        Transaction.created_at < month_start,
    ).scalar()

    today_txn_count = db.query(func.count(Transaction.id)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= today_start,
    ).scalar()

    # 최근 7일 일별 매출
    weekly_data = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= day_start,
            Transaction.created_at < day_end,
        ).scalar()
        weekly_data.append({
            "date": day_start.strftime("%m/%d"),
            "day": ["월","화","수","목","금","토","일"][day_start.weekday()],
            "sales": float(day_sales),
        })

    # 최근 결제 5건
    recent_txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
    ).order_by(Transaction.created_at.desc()).limit(5).all()
    recent_list = []
    for tx in recent_txns:
        staff_name = None
        if tx.staff_id:
            s = db.query(Staff).filter(Staff.id == tx.staff_id).first()
            if s: staff_name = s.name
        recent_list.append({
            "id": tx.id,
            "amount": float(tx.amount),
            "staff_name": staff_name,
            "card_brand": tx.card_brand,
            "created_at": str(tx.created_at),
        })

    # 직원별 오늘 매출 TOP 5
    from sqlalchemy import desc as sa_desc
    staff_sales_today = []
    if staff_count > 0:
        staff_rows = db.query(
            Staff.name,
            func.coalesce(func.sum(Transaction.amount), 0).label('total')
        ).outerjoin(Transaction, (Transaction.staff_id == Staff.id) & (Transaction.created_at >= today_start)
        ).filter(Staff.merchant_id == merchant.id, Staff.is_active == True
        ).group_by(Staff.id).order_by(sa_desc('total')).limit(5).all()
        staff_sales_today = [{"name": r[0], "sales": float(r[1])} for r in staff_rows]

    return {
        "merchant_name": merchant.name,
        "merchant_id": merchant.id,
        "category": merchant.category,
        "category_custom": merchant.category_custom,
        "place_url": merchant.place_url,
        "business_no": merchant.business_no,
        "address": merchant.address,
        "phone": merchant.phone,
        "needs_staff_management": merchant.needs_staff_management,
        "today_sales": float(today_sales),
        "month_sales": float(month_sales),
        "week_sales": float(week_sales),
        "total_sales": float(total_sales),
        "pending_settlement": float(pending_settlement),
        "yesterday_sales": float(yesterday_sales),
        "last_month_sales": float(last_month_sales),
        "today_txn_count": today_txn_count,
        "total_transactions": total_txns,
        "active_staff": staff_count,
        "weekly_data": weekly_data,
        "recent_transactions": recent_list,
        "staff_sales_today": staff_sales_today,
    }
