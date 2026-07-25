"""
Owner (원장님) API routes.
Covers: transactions, staff management, staff sales, ad analysis, ad orders,
        receipt review management, merchant info update.
"""
import json
import uuid
import base64
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant, STAFF_MANAGED_CATEGORIES
from app.models.staff import Staff
from app.models.transaction import Transaction
from app.models.settlement import Settlement
from app.models.ad import (
    AdOrder, AdOrderType, AdOrderStatus,
    AdOrderBlogDetail, AdOrderBlogImage,
    AdOrderPlaceTrafficDetail,
    AdPlaceProfile, AdCompetitor, AdMetric,
)
from app.models.receipt_review import ReceiptReviewConfig, ReceiptReview
from app.models.luxury_product import (
    LuxuryProduct, LuxuryProductOrder, LuxuryCategoryEnum,
    LUXURY_CATEGORY_LABELS, LuxuryProductStatus,
)
from app.models.affiliate_mall import AffiliateMall
from app.auth.dependencies import get_current_user, require_roles
from app.services.settlement_service import compute_distribution
from app.services.visibility import commission_visible_for
from app.schemas.schemas import (
    StaffCreate, StaffUpdate, DesignerCreate, DesignerUpdate,
    AdBlogOrderCreate, AdPlaceTrafficOrderCreate,
    AdPlaceProfileCreate, AdCompetitorCreate,
)
from app.auth.jwt_handler import hash_password

router = APIRouter(prefix="/api/owner", tags=["owner"])

require_owner = require_roles([UserRole.ADMIN, UserRole.OWNER])


def _get_owner_merchant(user: User, db: Session) -> Merchant:
    """Get the merchant owned by this user."""
    m = db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="No merchant found for this owner")
    return m


def _date_range(range_str: str):
    now = datetime.utcnow()
    if range_str == "day":
        return now - timedelta(days=1), now
    elif range_str == "week":
        return now - timedelta(weeks=1), now
    elif range_str == "month":
        return now - timedelta(days=30), now
    else:  # all
        return datetime(2000, 1, 1), now


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


# ─── Staff Management ───────────────────────────────────────

@router.get("/staff")
def list_staff(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    staff_list = db.query(Staff).filter(Staff.merchant_id == merchant.id).all()
    return [{
        "id": s.id, "name": s.name, "staff_code": s.staff_code,
        "user_id": s.user_id, "is_active": s.is_active,
        "share_rate": float(s.share_rate) if s.share_rate is not None else 0.5,
        "created_at": str(s.created_at),
    } for s in staff_list]


def _clamp_share_rate(value: float) -> float:
    """분배율을 0~1 범위로 제한."""
    return max(0.0, min(1.0, float(value)))


@router.post("/staff")
def create_staff(req: StaffCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    # Check unique staff_code within merchant
    existing = db.query(Staff).filter(
        Staff.merchant_id == merchant.id, Staff.staff_code == req.staff_code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Staff code already exists in this merchant")
    s = Staff(
        merchant_id=merchant.id, name=req.name,
        staff_code=req.staff_code, user_id=req.user_id,
        share_rate=_clamp_share_rate(req.share_rate) if req.share_rate is not None else 0.5,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "name": s.name, "staff_code": s.staff_code, "share_rate": float(s.share_rate)}


@router.put("/staff/{sid}")
def update_staff(sid: int, req: StaffUpdate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    s = db.query(Staff).filter(Staff.id == sid, Staff.merchant_id == merchant.id).first()
    if not s:
        raise HTTPException(status_code=404)
    for k, v in req.model_dump(exclude_unset=True).items():
        if k == "share_rate" and v is not None:
            v = _clamp_share_rate(v)
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


# ─── Designer Account Management (원장이 디자이너 계정 등록) ───
# 디자이너는 직접 회원가입할 수 없고, 원장이 계정을 만들어 미용실에 귀속시킨다.

@router.get("/designers")
def list_designers(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """이 미용실에 귀속된 디자이너(로그인 계정 보유 Staff) 목록."""
    merchant = _get_owner_merchant(user, db)
    rows = db.query(Staff).filter(
        Staff.merchant_id == merchant.id, Staff.user_id.isnot(None)
    ).order_by(Staff.created_at.desc()).all()
    result = []
    for s in rows:
        u = db.query(User).filter(User.id == s.user_id).first()
        result.append({
            "staff_id": s.id,
            "user_id": s.user_id,
            "name": s.name,
            "staff_code": s.staff_code,
            "email": u.email if u else None,
            "phone": u.phone if u else None,
            "share_rate": float(s.share_rate) if s.share_rate is not None else 0.5,
            "is_active": s.is_active and (u.is_active if u else True),
            "created_at": str(s.created_at),
        })
    return result


@router.post("/designers")
def create_designer(req: DesignerCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """원장이 디자이너 계정을 직접 생성하고 본인 미용실에 귀속시킨다."""
    merchant = _get_owner_merchant(user, db)

    # 이메일 중복 체크
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")
    # 직원코드 중복 체크 (미용실 내)
    if db.query(Staff).filter(Staff.merchant_id == merchant.id, Staff.staff_code == req.staff_code).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 직원 코드입니다")

    # 1) 디자이너 로그인 계정 생성
    designer_user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        role=UserRole.DESIGNER,
        phone=req.phone,
    )
    db.add(designer_user)
    db.flush()

    # 2) Staff 로 미용실에 귀속
    staff = Staff(
        merchant_id=merchant.id,
        user_id=designer_user.id,
        name=req.name,
        staff_code=req.staff_code,
        share_rate=_clamp_share_rate(req.share_rate) if req.share_rate is not None else 0.5,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return {
        "staff_id": staff.id,
        "user_id": designer_user.id,
        "name": staff.name,
        "email": designer_user.email,
        "staff_code": staff.staff_code,
        "message": f"디자이너 '{req.name}' 계정이 등록되었습니다. ({merchant.name} 소속)",
    }


@router.put("/designers/{staff_id}")
def update_designer(staff_id: int, req: DesignerUpdate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """디자이너 정보 수정 (이름/연락처/분배율/활성/비밀번호 재설정)."""
    merchant = _get_owner_merchant(user, db)
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.merchant_id == merchant.id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="디자이너를 찾을 수 없습니다")
    u = db.query(User).filter(User.id == staff.user_id).first()

    payload = req.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        staff.name = payload["name"]
        if u:
            u.name = payload["name"]
    if "phone" in payload and u:
        u.phone = payload["phone"]
    if "share_rate" in payload and payload["share_rate"] is not None:
        staff.share_rate = _clamp_share_rate(payload["share_rate"])
    if "is_active" in payload and payload["is_active"] is not None:
        staff.is_active = payload["is_active"]
        if u:
            u.is_active = payload["is_active"]
    if payload.get("password"):
        if u:
            u.password_hash = hash_password(payload["password"])
    db.commit()
    return {"ok": True}


# ─── Staff Sales ─────────────────────────────────────────────

@router.get("/staff/{sid}/sales")
def staff_sales(
    sid: int,
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    merchant = _get_owner_merchant(user, db)
    staff = db.query(Staff).filter(Staff.id == sid, Staff.merchant_id == merchant.id).first()
    if not staff:
        raise HTTPException(status_code=404)
    start, end = _date_range(range)
    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.staff_id == sid,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()
    total = sum(float(t.amount) for t in txns)
    return {
        "staff_id": sid, "staff_name": staff.name,
        "range": range, "count": len(txns), "total_amount": total,
        "transactions": [{
            "id": t.id, "amount": float(t.amount),
            "approved_at": str(t.approved_at) if t.approved_at else None,
            "created_at": str(t.created_at),
        } for t in txns],
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


# ─── Ad Analysis ────────────────────────────────────────────

@router.get("/ad/analysis")
def ad_analysis(
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    merchant = _get_owner_merchant(user, db)
    start_date, end_date = _date_range(range)

    # Get my place profiles
    profiles = db.query(AdPlaceProfile).filter(AdPlaceProfile.merchant_id == merchant.id).all()
    # Get competitor profiles
    competitors = db.query(AdCompetitor).filter(AdCompetitor.merchant_id == merchant.id).all()

    # Get metrics for my places
    my_metrics = []
    for p in profiles:
        if p.place_url:
            metrics = db.query(AdMetric).filter(
                AdMetric.merchant_id == merchant.id,
                AdMetric.place_url == p.place_url,
                AdMetric.date >= start_date.date() if hasattr(start_date, 'date') else start_date,
            ).order_by(AdMetric.date.desc()).all()
            my_metrics.append({
                "place_url": p.place_url, "nickname": p.nickname,
                "data": [{
                    "date": str(m.date), "blog_review_count": m.blog_review_count,
                    "visitor_review_count": m.visitor_review_count,
                    "place_rank": m.place_rank,
                } for m in metrics],
            })

    # Get metrics for competitors
    comp_metrics = []
    for c in competitors:
        metrics = db.query(AdMetric).filter(
            AdMetric.place_url == c.competitor_place_url,
            AdMetric.date >= start_date.date() if hasattr(start_date, 'date') else start_date,
        ).order_by(AdMetric.date.desc()).all()
        comp_metrics.append({
            "place_url": c.competitor_place_url, "memo": c.memo,
            "data": [{
                "date": str(m.date), "blog_review_count": m.blog_review_count,
                "visitor_review_count": m.visitor_review_count,
                "place_rank": m.place_rank,
            } for m in metrics],
        })

    return {
        "my_places": my_metrics,
        "competitors": comp_metrics,
        "profiles": [{"id": p.id, "place_url": p.place_url, "nickname": p.nickname} for p in profiles],
        "competitor_list": [{"id": c.id, "place_url": c.competitor_place_url, "memo": c.memo} for c in competitors],
    }


# ─── Ad Analysis Comparison Summary ──────────────────────────

@router.get("/ad/analysis/summary")
def ad_analysis_summary(
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """우리 매장 vs 경쟁업체 비교 요약 데이터를 반환"""
    merchant = _get_owner_merchant(user, db)
    start_date, end_date = _date_range(range)

    profiles = db.query(AdPlaceProfile).filter(AdPlaceProfile.merchant_id == merchant.id).all()
    competitors = db.query(AdCompetitor).filter(AdCompetitor.merchant_id == merchant.id).all()

    def _aggregate_metrics(place_url, merchant_id_filter=None):
        """특정 place_url의 집계 지표를 계산"""
        q = db.query(AdMetric).filter(
            AdMetric.place_url == place_url,
            AdMetric.date >= start_date.date() if hasattr(start_date, 'date') else start_date,
        )
        if merchant_id_filter is not None:
            q = q.filter(AdMetric.merchant_id == merchant_id_filter)
        metrics = q.order_by(AdMetric.date.desc()).all()
        if not metrics:
            return None

        total_blog = sum(m.blog_review_count or 0 for m in metrics)
        total_visitor = sum(m.visitor_review_count or 0 for m in metrics)
        ranks = [m.place_rank for m in metrics if m.place_rank is not None]
        avg_rank = round(sum(ranks) / len(ranks), 1) if ranks else None
        best_rank = min(ranks) if ranks else None
        latest_rank = ranks[0] if ranks else None
        latest_blog = metrics[0].blog_review_count if metrics else 0
        latest_visitor = metrics[0].visitor_review_count if metrics else 0
        
        # 트렌드 계산 (최근 2개 데이터 비교)
        blog_trend = 0
        visitor_trend = 0
        rank_trend = 0
        if len(metrics) >= 2:
            blog_trend = (metrics[0].blog_review_count or 0) - (metrics[1].blog_review_count or 0)
            visitor_trend = (metrics[0].visitor_review_count or 0) - (metrics[1].visitor_review_count or 0)
            if metrics[0].place_rank and metrics[1].place_rank:
                rank_trend = metrics[1].place_rank - metrics[0].place_rank  # 양수면 순위 상승

        return {
            "data_count": len(metrics),
            "total_blog_reviews": total_blog,
            "total_visitor_reviews": total_visitor,
            "latest_blog_reviews": latest_blog,
            "latest_visitor_reviews": latest_visitor,
            "avg_rank": avg_rank,
            "best_rank": best_rank,
            "latest_rank": latest_rank,
            "blog_trend": blog_trend,
            "visitor_trend": visitor_trend,
            "rank_trend": rank_trend,
            "latest_date": str(metrics[0].date) if metrics else None,
        }

    # 우리 매장 집계
    my_summaries = []
    for p in profiles:
        if p.place_url:
            agg = _aggregate_metrics(p.place_url, merchant.id)
            my_summaries.append({
                "id": p.id,
                "nickname": p.nickname or p.place_url,
                "place_url": p.place_url,
                "metrics": agg,
            })

    # 경쟁업체 집계
    comp_summaries = []
    for c in competitors:
        agg = _aggregate_metrics(c.competitor_place_url)
        comp_summaries.append({
            "id": c.id,
            "name": c.memo or c.competitor_place_url,
            "place_url": c.competitor_place_url,
            "metrics": agg,
        })

    # 종합 비교 요약 생성
    comparison = {
        "my_avg_blog": 0, "comp_avg_blog": 0,
        "my_avg_visitor": 0, "comp_avg_visitor": 0,
        "my_best_rank": None, "comp_best_rank": None,
        "my_latest_rank": None, "comp_latest_rank": None,
        "insights": [],
    }

    # 우리 매장 평균
    my_valid = [s for s in my_summaries if s["metrics"]]
    comp_valid = [s for s in comp_summaries if s["metrics"]]

    if my_valid:
        comparison["my_avg_blog"] = round(sum(s["metrics"]["latest_blog_reviews"] for s in my_valid) / len(my_valid), 1)
        comparison["my_avg_visitor"] = round(sum(s["metrics"]["latest_visitor_reviews"] for s in my_valid) / len(my_valid), 1)
        ranks = [s["metrics"]["latest_rank"] for s in my_valid if s["metrics"]["latest_rank"]]
        comparison["my_latest_rank"] = min(ranks) if ranks else None
        best = [s["metrics"]["best_rank"] for s in my_valid if s["metrics"]["best_rank"]]
        comparison["my_best_rank"] = min(best) if best else None

    if comp_valid:
        comparison["comp_avg_blog"] = round(sum(s["metrics"]["latest_blog_reviews"] for s in comp_valid) / len(comp_valid), 1)
        comparison["comp_avg_visitor"] = round(sum(s["metrics"]["latest_visitor_reviews"] for s in comp_valid) / len(comp_valid), 1)
        ranks = [s["metrics"]["latest_rank"] for s in comp_valid if s["metrics"]["latest_rank"]]
        comparison["comp_latest_rank"] = min(ranks) if ranks else None
        best = [s["metrics"]["best_rank"] for s in comp_valid if s["metrics"]["best_rank"]]
        comparison["comp_best_rank"] = min(best) if best else None

    # 인사이트 생성
    if my_valid and comp_valid:
        if comparison["my_avg_blog"] > comparison["comp_avg_blog"]:
            comparison["insights"].append({"type": "positive", "text": f"블로그 리뷰가 경쟁업체 대비 {comparison['my_avg_blog'] - comparison['comp_avg_blog']:.0f}개 더 많습니다."})
        elif comparison["my_avg_blog"] < comparison["comp_avg_blog"]:
            comparison["insights"].append({"type": "warning", "text": f"블로그 리뷰가 경쟁업체 대비 {comparison['comp_avg_blog'] - comparison['my_avg_blog']:.0f}개 부족합니다. 블로그 마케팅을 강화하세요."})

        if comparison["my_avg_visitor"] > comparison["comp_avg_visitor"]:
            comparison["insights"].append({"type": "positive", "text": f"방문자 리뷰가 경쟁업체 대비 {comparison['my_avg_visitor'] - comparison['comp_avg_visitor']:.0f}개 더 많습니다."})
        elif comparison["my_avg_visitor"] < comparison["comp_avg_visitor"]:
            comparison["insights"].append({"type": "warning", "text": f"방문자 리뷰가 경쟁업체 대비 {comparison['comp_avg_visitor'] - comparison['my_avg_visitor']:.0f}개 부족합니다."})

        if comparison["my_latest_rank"] and comparison["comp_latest_rank"]:
            if comparison["my_latest_rank"] < comparison["comp_latest_rank"]:
                comparison["insights"].append({"type": "positive", "text": f"플레이스 순위가 경쟁업체({comparison['comp_latest_rank']}위)보다 높습니다({comparison['my_latest_rank']}위)."})
            elif comparison["my_latest_rank"] > comparison["comp_latest_rank"]:
                comparison["insights"].append({"type": "warning", "text": f"플레이스 순위가 경쟁업체({comparison['comp_latest_rank']}위)보다 낮습니다({comparison['my_latest_rank']}위). 순위 개선이 필요합니다."})
    elif not my_valid and not comp_valid:
        comparison["insights"].append({"type": "info", "text": "아직 등록된 분석 데이터가 없습니다. 플레이스 프로필과 경쟁업체를 등록하고 지표를 입력해주세요."})
    elif not comp_valid:
        comparison["insights"].append({"type": "info", "text": "경쟁업체가 등록되지 않았습니다. 경쟁업체를 추가하면 비교 분석을 제공합니다."})

    return {
        "my_places": my_summaries,
        "competitors": comp_summaries,
        "comparison": comparison,
        "range": range,
    }


# ─── Delete Place Profile & Competitor ────────────────────────

@router.delete("/ad/place-profiles/{pid}")
def delete_place_profile(pid: int, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    p = db.query(AdPlaceProfile).filter(AdPlaceProfile.id == pid, AdPlaceProfile.merchant_id == merchant.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.delete("/ad/competitors/{cid}")
def delete_competitor(cid: int, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    c = db.query(AdCompetitor).filter(AdCompetitor.id == cid, AdCompetitor.merchant_id == merchant.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="경쟁업체를 찾을 수 없습니다")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ─── Ad Place Profiles & Competitors ────────────────────────

@router.post("/ad/place-profiles")
def create_place_profile(req: AdPlaceProfileCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    p = AdPlaceProfile(merchant_id=merchant.id, place_url=req.place_url, place_id=req.place_id, nickname=req.nickname)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


@router.post("/ad/competitors")
def create_competitor(req: AdCompetitorCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    c = AdCompetitor(merchant_id=merchant.id, competitor_place_url=req.competitor_place_url, memo=req.memo)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id}


# ─── Ad Orders ──────────────────────────────────────────────

@router.get("/ad/orders")
def list_owner_ad_orders(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    orders = db.query(AdOrder).filter(AdOrder.merchant_id == merchant.id).order_by(AdOrder.created_at.desc()).all()
    results = []
    for o in orders:
        item = {
            "id": o.id, "type": o.type.value, "status": o.status.value,
            "admin_memo": o.admin_memo, "created_at": str(o.created_at),
        }
        if o.type == AdOrderType.BLOG:
            detail = db.query(AdOrderBlogDetail).filter(AdOrderBlogDetail.order_id == o.id).first()
            if detail:
                item["blog_detail"] = {
                    "campaign_name": detail.campaign_name,
                    "address": detail.address, "contact": detail.contact,
                }
        elif o.type == AdOrderType.PLACE_TRAFFIC:
            detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == o.id).first()
            if detail:
                item["place_traffic_detail"] = {
                    "place_name_or_id": detail.place_name_or_id,
                }
        results.append(item)
    return results


@router.post("/ad/blog-orders")
def create_blog_order(req: AdBlogOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    order = AdOrder(
        merchant_id=merchant.id, type=AdOrderType.BLOG,
        status=AdOrderStatus.REQUESTED, created_by=user.id,
    )
    db.add(order)
    db.flush()

    detail = AdOrderBlogDetail(
        order_id=order.id,
        campaign_name=req.campaign_name,
        address=req.address, contact=req.contact,
        links_json=json.dumps(req.links),
        main_keywords_json=json.dumps(req.main_keywords),
        hashtags_json=json.dumps(req.hashtags),
        description=req.description,
        extra_image_link=req.extra_image_link,
    )
    db.add(detail)
    db.commit()
    db.refresh(order)
    return {"id": order.id, "status": order.status.value}


@router.post("/ad/place-traffic-orders")
def create_place_traffic_order(req: AdPlaceTrafficOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    order = AdOrder(
        merchant_id=merchant.id, type=AdOrderType.PLACE_TRAFFIC,
        status=AdOrderStatus.REQUESTED, created_by=user.id,
    )
    db.add(order)
    db.flush()

    detail = AdOrderPlaceTrafficDetail(
        order_id=order.id,
        place_name_or_id=req.place_name_or_id,
        search_keywords_json=json.dumps(req.search_keywords),
    )
    db.add(detail)
    db.commit()
    db.refresh(order)
    return {"id": order.id, "status": order.status.value}


# ─── Dashboard Stats ────────────────────────────────────────

@router.get("/dashboard-stats")
def owner_dashboard_stats(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    today_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= today_start,
    ).scalar()

    month_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= month_start,
    ).scalar()

    # 이번 주 (월요일 0시 ~ 현재)
    week_start = today_start - timedelta(days=today_start.weekday())
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


# ─── Merchant Info Update ──────────────────────────────────

@router.get("/merchant-info")
def get_merchant_info(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """매장 상세 정보 조회"""
    merchant = _get_owner_merchant(user, db)
    return {
        "id": merchant.id,
        "name": merchant.name,
        "business_no": merchant.business_no,
        "address": merchant.address,
        "phone": merchant.phone,
        "category": merchant.category,
        "category_custom": merchant.category_custom,
        "place_url": merchant.place_url,
        "is_active": merchant.is_active,
        "display_category": merchant.display_category,
        "needs_staff_management": merchant.needs_staff_management,
        "created_at": str(merchant.created_at),
    }


@router.put("/merchant-info")
def update_merchant_info(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
    name: Optional[str] = None,
    business_no: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    category: Optional[str] = None,
    category_custom: Optional[str] = None,
    place_url: Optional[str] = None,
):
    """매장 정보 업데이트 (분야, 플레이스 URL 등)"""
    merchant = _get_owner_merchant(user, db)
    if name is not None:
        merchant.name = name
    if business_no is not None:
        merchant.business_no = business_no
    if address is not None:
        merchant.address = address
    if phone is not None:
        merchant.phone = phone
    if category is not None:
        merchant.category = category
    if category_custom is not None:
        merchant.category_custom = category_custom
    if place_url is not None:
        merchant.place_url = place_url
    db.commit()
    db.refresh(merchant)
    return {
        "ok": True,
        "category": merchant.category,
        "display_category": merchant.display_category,
        "needs_staff_management": merchant.needs_staff_management,
    }


# ─── Receipt Review Management ────────────────────────────

@router.get("/receipt-review/config")
def get_receipt_review_config(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """매장의 영수증 리뷰 설정 조회"""
    merchant = _get_owner_merchant(user, db)
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.merchant_id == merchant.id
    ).first()
    if not config:
        return {"exists": False}
    return {
        "exists": True,
        "id": config.id,
        "token": config.token,
        "place_url": config.place_url,
        "welcome_message": config.welcome_message,
        "is_active": config.is_active,
        "created_at": str(config.created_at),
        "review_url": f"/static/review.html?t={config.token}",
    }


@router.post("/receipt-review/config")
def create_or_update_receipt_review_config(
    place_url: Optional[str] = None,
    welcome_message: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """영수증 리뷰 설정 생성 또는 업데이트 (QR/NFC 토큰 발급)"""
    merchant = _get_owner_merchant(user, db)
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.merchant_id == merchant.id
    ).first()

    if not config:
        config = ReceiptReviewConfig(
            merchant_id=merchant.id,
            token=ReceiptReviewConfig.generate_token(),
            place_url=place_url or merchant.place_url,
            welcome_message=welcome_message or "방문해주셔서 감사합니다! 영수증 리뷰를 남겨주세요.",
        )
        db.add(config)
    else:
        if place_url is not None:
            config.place_url = place_url
        if welcome_message is not None:
            config.welcome_message = welcome_message
        config.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(config)
    return {
        "id": config.id,
        "token": config.token,
        "place_url": config.place_url,
        "welcome_message": config.welcome_message,
        "review_url": f"/static/review.html?t={config.token}",
    }


@router.post("/receipt-review/config/regenerate-token")
def regenerate_review_token(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """QR/NFC 토큰 재발급"""
    merchant = _get_owner_merchant(user, db)
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.merchant_id == merchant.id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="리뷰 설정이 없습니다. 먼저 설정을 생성하세요.")
    config.token = ReceiptReviewConfig.generate_token()
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return {"token": config.token, "review_url": f"/static/review.html?t={config.token}"}


@router.get("/receipt-review/list")
def list_receipt_reviews(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """영수증 리뷰 목록 조회"""
    merchant = _get_owner_merchant(user, db)
    q = db.query(ReceiptReview).filter(ReceiptReview.merchant_id == merchant.id)
    if status:
        q = q.filter(ReceiptReview.status == status)
    reviews = q.order_by(ReceiptReview.created_at.desc()).limit(limit).all()
    return [{
        "id": r.id,
        "customer_name": r.customer_name,
        "customer_phone": r.customer_phone,
        "receipt_image_url": r.receipt_image_url,
        "status": r.status,
        "review_completed": r.review_completed,
        "memo": r.memo,
        "created_at": str(r.created_at),
    } for r in reviews]


@router.put("/receipt-review/{review_id}/status")
def update_review_status(
    review_id: int,
    status: str = Query(..., pattern="^(pending|approved|rejected)$"),
    memo: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """영수증 리뷰 상태 변경 (승인/반려)"""
    merchant = _get_owner_merchant(user, db)
    review = db.query(ReceiptReview).filter(
        ReceiptReview.id == review_id,
        ReceiptReview.merchant_id == merchant.id,
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")
    review.status = status
    if memo is not None:
        review.memo = memo
    review.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": review.status}


# ═══════════════════════════════════════════════════════════
# LUXURY STORE (명품스토어) — 골드회원(원장) 상품 조회/주문
# ═══════════════════════════════════════════════════════════

@router.get("/luxury/categories")
def get_owner_luxury_categories(user: User = Depends(require_owner)):
    """명품 카테고리 목록 (원장용)"""
    return [{"value": k, "label": v} for k, v in LUXURY_CATEGORY_LABELS.items()]


@router.get("/luxury/products")
def list_owner_luxury_products(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """활성 명품 상품 목록 (골드회원용 — active 상품만)"""
    q = db.query(LuxuryProduct).filter(
        LuxuryProduct.status == LuxuryProductStatus.ACTIVE
    ).order_by(LuxuryProduct.is_featured.desc(), LuxuryProduct.created_at.desc())
    if category:
        q = q.filter(LuxuryProduct.category == category)
    products = q.all()
    return [{
        "id": p.id, "name": p.name, "brand": p.brand,
        "category": p.category.value if p.category else "other",
        "category_label": p.category_label,
        "description": p.description, "price": p.price,
        "discount_price": p.discount_price, "display_price": p.display_price,
        "image_url": p.image_url, "stock": p.stock, "is_featured": p.is_featured,
        "created_at": str(p.created_at),
    } for p in products]


@router.post("/luxury/orders")
def create_luxury_order(
    product_id: int = Query(...),
    quantity: int = Query(1),
    memo: Optional[str] = Query(None),
    shipping_address: Optional[str] = Query(None),
    shipping_phone: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """명품 상품 주문"""
    product = db.query(LuxuryProduct).filter(
        LuxuryProduct.id == product_id,
        LuxuryProduct.status == LuxuryProductStatus.ACTIVE,
    ).first()
    if not product:
        raise HTTPException(404, "상품을 찾을 수 없습니다.")
    if product.stock < quantity:
        raise HTTPException(400, "재고가 부족합니다.")

    merchant = _get_owner_merchant(user, db)
    total_price = product.display_price * quantity

    order = LuxuryProductOrder(
        product_id=product_id, user_id=user.id,
        merchant_id=merchant.id if merchant else None,
        quantity=quantity, total_price=total_price,
        memo=memo, shipping_address=shipping_address,
        shipping_phone=shipping_phone,
    )
    db.add(order)
    # 재고 차감
    product.stock -= quantity
    db.commit()
    db.refresh(order)
    return {"id": order.id, "total_price": total_price, "message": "주문이 접수되었습니다."}


@router.get("/luxury/orders")
def list_owner_luxury_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """내 명품 주문 내역"""
    orders = db.query(LuxuryProductOrder).filter(
        LuxuryProductOrder.user_id == user.id
    ).order_by(LuxuryProductOrder.created_at.desc()).all()
    return [{
        "id": o.id, "product_id": o.product_id,
        "product_name": o.product.name if o.product else "-",
        "product_brand": o.product.brand if o.product else "-",
        "product_image": o.product.image_url if o.product else None,
        "quantity": o.quantity, "total_price": o.total_price,
        "status": o.status.value if o.status else "pending",
        "memo": o.memo, "admin_memo": o.admin_memo,
        "created_at": str(o.created_at),
    } for o in orders]


# ═══════════════════════════════════════════════════════════
# AFFILIATE MALLS (제휴중개몰) — 골드회원 조회
# ═══════════════════════════════════════════════════════════

@router.get("/affiliate-malls")
def list_owner_affiliate_malls(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """활성 제휴중개몰 목록 (원장용)"""
    malls = db.query(AffiliateMall).filter(
        AffiliateMall.is_active == True
    ).order_by(AffiliateMall.sort_order, AffiliateMall.id).all()
    return [{
        "id": m.id, "name": m.name, "logo_url": m.logo_url,
        "website_url": m.website_url, "description": m.description,
        "category": m.category, "commission_rate": m.commission_rate,
    } for m in malls]
