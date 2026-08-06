"""Admin routes — 대시보드 통계(stats/landing, stats/enhanced), AI 설정 등
다른 도메인 파일에 명확히 속하지 않는 나머지 엔드포인트."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.utils.kst import today_kst, kst_day_start_utc

from app.database import get_db
from app.models.user import User
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.ad import AdOrder, AdOrderStatus
from app.models.settlement import PayoutRequest, PayoutStatus
from app.auth.dependencies import require_admin
from app.services import ai_service
from app.schemas.schemas import AISettingsUpdate

router = APIRouter()


# ─── Landing Stats ──────────────────────────────────────────

@router.get("/stats/landing")
def landing_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Aggregated stats for the admin dashboard home.

    매출 총액과 최근 결제 내역이 포함되므로 최고관리자만 조회할 수 있다.
    """
    total_merchants = db.query(func.count(Merchant.id)).scalar() or 0
    total_transactions = db.query(func.count(Transaction.id)).scalar() or 0
    total_ad_orders = db.query(func.count(AdOrder.id)).scalar() or 0
    total_volume = db.query(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    total_users = db.query(func.count(User.id)).scalar() or 0

    # KST 기준 오늘/이번 달 경계 → naive UTC datetime 으로 변환하여 DB 필터에 사용
    _kst_today = today_kst()
    today_start = kst_day_start_utc(_kst_today)
    month_start = kst_day_start_utc(_kst_today.replace(day=1))
    yesterday_start = kst_day_start_utc(_kst_today - timedelta(days=1))

    today_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.created_at >= today_start).scalar()
    today_txn_count = db.query(func.count(Transaction.id)).filter(
        Transaction.created_at >= today_start).scalar()
    month_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.created_at >= month_start).scalar()
    yesterday_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.created_at >= yesterday_start, Transaction.created_at < today_start).scalar()

    # Pending payouts
    pending_payouts = db.query(func.count(PayoutRequest.id)).filter(
        PayoutRequest.status == PayoutStatus.PENDING).scalar() or 0
    # Pending ad orders
    pending_ad = db.query(func.count(AdOrder.id)).filter(
        AdOrder.status.in_([AdOrderStatus.REQUESTED, AdOrderStatus.REVIEWING])
    ).scalar() or 0

    # Weekly data (KST 날짜 기준으로 7일간)
    weekly_data = []
    for i in range(6, -1, -1):
        kst_day = _kst_today - timedelta(days=i)
        day_start = kst_day_start_utc(kst_day)
        day_end = kst_day_start_utc(kst_day + timedelta(days=1))
        day_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.created_at >= day_start, Transaction.created_at < day_end).scalar()
        day_count = db.query(func.count(Transaction.id)).filter(
            Transaction.created_at >= day_start, Transaction.created_at < day_end).scalar()
        weekly_data.append({
            "date": kst_day.strftime("%m/%d"),
            "day": ["월","화","수","목","금","토","일"][kst_day.weekday()],
            "sales": float(day_sales), "count": day_count,
        })

    # Recent transactions
    recent_txns = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(10).all()
    recent_list = []
    for tx in recent_txns:
        m = db.query(Merchant).filter(Merchant.id == tx.merchant_id).first()
        recent_list.append({
            "id": tx.id, "amount": float(tx.amount), "merchant_name": m.name if m else "-",
            "card_brand": tx.card_brand, "created_at": str(tx.created_at),
        })

    return {
        "total_merchants": total_merchants,
        "total_transactions": total_transactions,
        "total_ad_orders": total_ad_orders,
        "total_volume": float(total_volume),
        "total_users": total_users,
        "today_sales": float(today_sales),
        "today_txn_count": today_txn_count,
        "month_sales": float(month_sales),
        "yesterday_sales": float(yesterday_sales),
        "pending_payouts": pending_payouts,
        "pending_ad_orders": pending_ad,
        "weekly_data": weekly_data,
        "recent_transactions": recent_list,
    }


# ═══════════════════════════════════════════════════════════
# Enhanced Dashboard Stats (for richer admin dashboard)
# ═══════════════════════════════════════════════════════════

@router.get("/stats/enhanced")
def enhanced_admin_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Enhanced dashboard stats with more data for admin dashboard."""
    _kst_today2 = today_kst()
    today_start = kst_day_start_utc(_kst_today2)
    month_start = kst_day_start_utc(_kst_today2.replace(day=1))

    # Recent activities (last 20 actions)
    recent_activities = []

    # Recent ad orders
    recent_ads = db.query(AdOrder).order_by(AdOrder.created_at.desc()).limit(5).all()
    for o in recent_ads:
        m = db.query(Merchant).filter(Merchant.id == o.merchant_id).first()
        recent_activities.append({
            "type": "ad_order",
            "icon": "bullhorn",
            "color": "warning",
            "text": f"광고주문 #{o.id} ({m.name if m else '-'}) - {o.type.value}",
            "status": o.status.value,
            "created_at": str(o.created_at),
        })

    # Recent payouts
    recent_payouts = db.query(PayoutRequest).order_by(PayoutRequest.created_at.desc()).limit(5).all()
    for p in recent_payouts:
        u = db.query(User).filter(User.id == p.requester_user_id).first()
        recent_activities.append({
            "type": "payout",
            "icon": "money-bill-wave",
            "color": "danger",
            "text": f"출금요청 {u.name if u else '-'} - {float(p.amount):,.0f}원",
            "status": p.status.value if p.status else "pending",
            "created_at": str(p.created_at),
        })

    # Sort by date
    recent_activities.sort(key=lambda x: x["created_at"], reverse=True)

    # Monthly revenue trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        m_start = (month_start.replace(day=1) - timedelta(days=i*30)).replace(day=1)
        m_end = (m_start + timedelta(days=32)).replace(day=1)
        m_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.created_at >= m_start, Transaction.created_at < m_end
        ).scalar()
        m_count = db.query(func.count(Transaction.id)).filter(
            Transaction.created_at >= m_start, Transaction.created_at < m_end
        ).scalar()
        monthly_trend.append({
            "month": m_start.strftime("%Y-%m"),
            "label": m_start.strftime("%m월"),
            "sales": float(m_sales),
            "count": m_count,
        })

    # Top merchants by sales this month
    top_merchants = []
    merchants = db.query(Merchant).filter(Merchant.is_active == True).all()
    for m in merchants:
        m_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.merchant_id == m.id,
            Transaction.created_at >= month_start,
        ).scalar()
        m_count = db.query(func.count(Transaction.id)).filter(
            Transaction.merchant_id == m.id,
            Transaction.created_at >= month_start,
        ).scalar()
        if float(m_sales) > 0:
            top_merchants.append({
                "id": m.id, "name": m.name,
                "sales": float(m_sales), "count": m_count,
            })
    top_merchants.sort(key=lambda x: x["sales"], reverse=True)

    # Alerts/Notifications
    pending_payout_count = db.query(func.count(PayoutRequest.id)).filter(
        PayoutRequest.status == PayoutStatus.PENDING).scalar() or 0
    pending_ad_count = db.query(func.count(AdOrder.id)).filter(
        AdOrder.status.in_([AdOrderStatus.REQUESTED, AdOrderStatus.REVIEWING])
    ).scalar() or 0

    alerts = []
    if pending_payout_count > 0:
        alerts.append({"type": "warning", "icon": "money-bill-wave", "text": f"대기 중인 출금요청 {pending_payout_count}건이 있습니다.", "link": "admin-payouts"})
    if pending_ad_count > 0:
        alerts.append({"type": "info", "icon": "bullhorn", "text": f"검토 대기 중인 광고주문 {pending_ad_count}건이 있습니다.", "link": "admin-adorders"})

    # New users this month
    new_users_month = db.query(func.count(User.id)).filter(
        User.created_at >= month_start).scalar() or 0

    return {
        "recent_activities": recent_activities[:15],
        "monthly_trend": monthly_trend,
        "top_merchants": top_merchants[:10],
        "alerts": alerts,
        "new_users_month": new_users_month,
    }


# ═══════════════════════════════════════════════════════════
# AI 설정 (OpenAI API 키 관리)
# ═══════════════════════════════════════════════════════════

@router.get("/settings/ai")
def get_ai_settings(db: Session = Depends(get_db), _=Depends(require_admin)):
    """OpenAI API 키 등록 여부와 마스킹된 값을 반환한다 (평문은 노출하지 않는다)."""
    key = ai_service.get_api_key(db)
    return {
        "configured": key is not None,
        "masked_key": ai_service.mask_api_key(key) if key else None,
    }


@router.post("/settings/ai")
def save_ai_settings(
    req: AISettingsUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """OpenAI API 키를 암호화해 저장/갱신한다."""
    key = (req.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API 키를 입력해주세요")
    if not key.startswith("sk-") or len(key) < 20:
        raise HTTPException(status_code=400, detail="올바른 OpenAI API 키 형식이 아닙니다 (sk- 로 시작)")
    ai_service.save_api_key(db, key)
    return {"ok": True, "configured": True, "masked_key": ai_service.mask_api_key(key)}


@router.delete("/settings/ai")
def delete_ai_settings(db: Session = Depends(get_db), _=Depends(require_admin)):
    """저장된 OpenAI API 키를 삭제한다."""
    removed = ai_service.delete_api_key(db)
    if not removed:
        raise HTTPException(status_code=404, detail="등록된 API 키가 없습니다")
    return {"ok": True, "configured": False}


@router.get("/settings/ai/status")
async def test_ai_connection(db: Session = Depends(get_db), _=Depends(require_admin)):
    """저장된 키로 OpenAI 에 실제 요청을 보내 연결 상태를 확인한다."""
    key = ai_service.get_api_key(db)
    if not key:
        return {"configured": False, "ok": False, "detail": "등록된 API 키가 없습니다."}
    result = await ai_service.test_connection(key)
    return {"configured": True, **result}
