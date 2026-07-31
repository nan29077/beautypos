"""
Admin API routes — accessible only by ADMIN role.
Covers: merchants CRUD, PG config, transactions, payout requests,
        ad orders management, metrics, fee policies, sales assignments, landing stats.
"""
import json
import secrets
from datetime import datetime, timedelta, date as date_type
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.utils.kst import today_kst, kst_day_start_utc, fmt_kst, now_kst

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.pg import PGProvider, MerchantPGConfig, PGConfigStatus
from app.models.terminal import TerminalDevice
from app.models.transaction import Transaction
from app.models.settlement import (
    FeePolicy, SalesCommissionPolicy, MerchantSalesAssignment, Settlement, PayoutRequest, PayoutStatus,
)
from app.models.ad import (
    AdOrder, AdOrderStatus, AdMetric, AdOrderBlogDetail, AdOrderBlogImage,
    AdOrderPlaceTrafficDetail, AdOrderShortsDetail, AdPlaceProfile, AdCompetitor,
    SHORTS_CAMPAIGN_TYPE_LABELS, SHORTS_DURATION_TIERS,
)
from app.models.staff import Staff
from app.models.affiliate_mall import AffiliateMall
from app.auth.dependencies import require_admin
from app.auth.jwt_handler import hash_password
from app.models.system_config import (
    SystemConfig, AD_ORDER_MGMT_ENABLED, AD_BLOG_ENABLED, AD_PLACE_TRAFFIC_ENABLED,
    AD_SHORTS_ENABLED,
    COMMISSION_VISIBLE_TO_SALES, COMMISSION_VISIBLE_TO_OWNER, COMMISSION_VISIBLE_TO_DESIGNER,
)
from app.services import ad_pricing, ai_service
from app.services.encryption import encrypt_value, decrypt_value, mask_value
from app.services.pg_service import get_pg_provider
from app.services.settlement_service import (
    compute_distribution, get_effective_fee_rates, compute_fee_distribution,
    DEFAULT_MERCHANT_FEE_RATE, DEFAULT_PG_FEE_RATE, DEFAULT_SALES_COMMISSION_RATE,
    apply_vat, format_rate_excl_vat, format_rate_with_vat,
    VAT_RATE, VAT_NOTICE, get_available_payout,
)
from app.schemas.schemas import (
    MerchantCreate, MerchantUpdate, PGConfigCreate,
    AdMetricCreate, AdOrderStatusUpdate, AdPricingUpdate,
    FeePolicyUpdate, GlobalFeeSettingsUpdate, MerchantFeeOverrideUpdate, SalesCommissionOverrideUpdate,
    SalesAssignmentCreate, SalesAssignmentUpdate,
    CommissionVisibilityUpdate, StaffShareRateUpdate, AISettingsUpdate,
    PlanUpdate, MerchantPlanAssign, AdExecutionCreate,
)
from app.models.plan import (
    Plan, MerchantPlan, AdExecution,
    AD_EXECUTION_TYPE_CODES, AD_EXECUTION_TYPE_LABELS,
)
from app.services import plan_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

AD_ORDER_TRANSITIONS = {
    "requested": ["reviewing", "rejected"],
    "reviewing": ["running", "rejected"],
    "running": ["done", "rejected"],
    "done": [],
    "rejected": ["reviewing"],
}


def _allowed_ad_order_statuses(status: str) -> list[str]:
    return AD_ORDER_TRANSITIONS.get(status, [])


def _validate_ad_order_transition(current: str, requested: str) -> None:
    if requested not in _allowed_ad_order_statuses(current):
        raise HTTPException(
            status_code=409,
            detail=f"'{current}' 상태에서 '{requested}' 상태로 변경할 수 없습니다",
        )


# ─── Merchants ───────────────────────────────────────────────

@router.get("/merchants")
def list_merchants(db: Session = Depends(get_db), _=Depends(require_admin)):
    merchants = db.query(Merchant).all()
    results = []
    for m in merchants:
        results.append({
            "id": m.id, "name": m.name, "owner_user_id": m.owner_user_id,
            "business_no": m.business_no, "address": m.address,
            "phone": m.phone, "is_active": m.is_active,
            "created_at": str(m.created_at),
        })
    return results


@router.post("/merchants")
def create_merchant(req: MerchantCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    owner = db.query(User).filter(User.id == req.owner_user_id).first()
    if not owner:
        raise HTTPException(status_code=400, detail="소유자 계정을 찾을 수 없습니다")
    # 원장 화면은 owner_user_id 로 가맹점을 1개만 찾으므로, 잘못된 역할·중복 소유를 등록 시점에 막는다.
    if owner.role != UserRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail=f"사장님(원장) 역할의 계정만 가맹점 소유자가 될 수 있습니다. (현재: {owner.role.value})",
        )
    existing = db.query(Merchant).filter(Merchant.owner_user_id == req.owner_user_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"이 계정은 이미 '{existing.name}' 가맹점을 소유하고 있습니다",
        )
    m = Merchant(
        name=req.name, owner_user_id=req.owner_user_id,
        business_no=req.business_no, address=req.address, phone=req.phone,
    )
    db.add(m)
    db.flush()
    plan_service.ensure_default_plan(db, m.id)  # 신규 가맹점은 베이직 플랜으로 시작
    db.commit()
    db.refresh(m)
    return {"id": m.id, "name": m.name}


@router.put("/merchants/{mid}")
def update_merchant(mid: int, req: MerchantUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    m = db.query(Merchant).filter(Merchant.id == mid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Merchant not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return {"ok": True}


@router.get("/merchants/{mid}")
def get_merchant(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    m = db.query(Merchant).filter(Merchant.id == mid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return {
        "id": m.id, "name": m.name, "owner_user_id": m.owner_user_id,
        "business_no": m.business_no, "address": m.address,
        "phone": m.phone, "is_active": m.is_active,
    }


# ─── PG Config ───────────────────────────────────────────────

@router.get("/merchants/{mid}/pg-configs")
def list_pg_configs(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    configs = db.query(MerchantPGConfig).filter(MerchantPGConfig.merchant_id == mid).all()
    results = []
    for c in configs:
        provider = db.query(PGProvider).filter(PGProvider.id == c.provider_id).first()
        results.append({
            "id": c.id,
            "provider_id": c.provider_id,
            "provider_code": provider.code if provider else None,
            "provider_name": provider.name if provider else None,
            "mid": c.mid,
            "secret_masked": mask_value(decrypt_value(c.secret_encrypted)),
            "status": c.status.value if c.status else None,
            "last_tested_at": str(c.last_tested_at) if c.last_tested_at else None,
        })
    return results


@router.post("/merchants/{mid}/pg-config")
def create_pg_config(mid: int, req: PGConfigCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    provider = db.query(PGProvider).filter(PGProvider.id == req.provider_id).first()
    if not provider:
        raise HTTPException(status_code=400, detail="PG Provider not found")

    config = MerchantPGConfig(
        merchant_id=mid,
        provider_id=req.provider_id,
        mid=req.mid,
        secret_encrypted=encrypt_value(req.secret),
        status=PGConfigStatus.CONNECTED,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"id": config.id, "status": config.status.value}


@router.post("/merchants/{mid}/pg-test")
def test_pg_config(mid: int, config_id: int = Query(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    config = db.query(MerchantPGConfig).filter(
        MerchantPGConfig.id == config_id, MerchantPGConfig.merchant_id == mid
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="PG config not found")

    provider_row = db.query(PGProvider).filter(PGProvider.id == config.provider_id).first()
    if not provider_row:
        raise HTTPException(status_code=400, detail="Provider not found")

    pg = get_pg_provider(provider_row.code)
    secret = decrypt_value(config.secret_encrypted)
    result = pg.test_connection(config.mid, secret)

    config.last_tested_at = datetime.utcnow()
    if result["success"]:
        config.status = PGConfigStatus.TESTED
    db.commit()

    return result


# ─── PG Providers list ───────────────────────────────────────

@router.get("/pg-providers")
def list_pg_providers(db: Session = Depends(get_db), _=Depends(require_admin)):
    providers = db.query(PGProvider).all()
    return [{"id": p.id, "code": p.code, "name": p.name} for p in providers]


# ─── Terminals ───────────────────────────────────────────────

@router.get("/terminals")
def list_terminals(
    merchant_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """단말기 목록. API 키는 해시로만 보관되므로 절대 반환하지 않는다."""
    q = db.query(TerminalDevice)
    if merchant_id:
        q = q.filter(TerminalDevice.merchant_id == merchant_id)
    terminals = q.order_by(TerminalDevice.id).all()
    merchant_names = {m.id: m.name for m in db.query(Merchant).all()}

    results = []
    for t in terminals:
        txn_count = db.query(func.count(Transaction.id)).filter(
            Transaction.terminal_id == t.id,
        ).scalar() or 0
        last_txn = db.query(Transaction).filter(
            Transaction.terminal_id == t.id,
        ).order_by(Transaction.created_at.desc()).first()
        results.append({
            "id": t.id,
            "merchant_id": t.merchant_id,
            "merchant_name": merchant_names.get(t.merchant_id, f"가맹점#{t.merchant_id}"),
            "terminal_serial": t.terminal_serial,
            "memo": t.memo,
            "is_active": t.is_active,
            "transaction_count": int(txn_count),
            "last_transaction_at": str(last_txn.created_at) if last_txn else None,
            "created_at": str(t.created_at),
        })
    return results


# ─── Transactions ────────────────────────────────────────────

@router.get("/transactions")
def list_all_transactions(
    merchant_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200, offset: int = 0,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    q = db.query(Transaction)
    if merchant_id:
        q = q.filter(Transaction.merchant_id == merchant_id)
    if date_from:
        q = q.filter(Transaction.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        q = q.filter(Transaction.created_at <= datetime.fromisoformat(date_to) + timedelta(days=1))
    total_count = q.count()
    total_amount = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        *[c for c in q.whereclause.clauses] if hasattr(q, 'whereclause') and q.whereclause is not None else []
    ).scalar() if False else 0
    # Calculate total from filtered query
    amount_q = db.query(func.coalesce(func.sum(Transaction.amount), 0))
    if merchant_id:
        amount_q = amount_q.filter(Transaction.merchant_id == merchant_id)
    if date_from:
        amount_q = amount_q.filter(Transaction.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        amount_q = amount_q.filter(Transaction.created_at <= datetime.fromisoformat(date_to) + timedelta(days=1))
    total_amount = float(amount_q.scalar())

    txns = q.order_by(Transaction.created_at.desc()).offset(offset).limit(limit).all()
    results = []
    for t in txns:
        staff_name = None
        if t.staff_id:
            staff = db.query(Staff).filter(Staff.id == t.staff_id).first()
            staff_name = staff.name if staff else None
        m = db.query(Merchant).filter(Merchant.id == t.merchant_id).first()
        results.append({
            "id": t.id, "merchant_id": t.merchant_id,
            "merchant_name": m.name if m else f"가맹점#{t.merchant_id}",
            "terminal_id": t.terminal_id,
            "staff_id": t.staff_id, "staff_name": staff_name,
            "amount": float(t.amount), "installment_months": t.installment_months,
            "card_brand": t.card_brand, "approval_code": t.approval_code,
            "staff_code_input": t.staff_code_input,
            "approved_at": str(t.approved_at) if t.approved_at else None,
            "created_at": str(t.created_at),
        })
    return {"transactions": results, "total_count": total_count, "total_amount": total_amount}


# ─── Payout Requests ────────────────────────────────────────

@router.get("/payout-requests")
def list_payout_requests(db: Session = Depends(get_db), _=Depends(require_admin)):
    reqs = db.query(PayoutRequest).order_by(PayoutRequest.created_at.desc()).all()
    results = []
    for r in reqs:
        user = db.query(User).filter(User.id == r.requester_user_id).first()
        # 이 요청 자체는 차감에서 빼서, amount 와 바로 비교할 수 있는 잔액을 보여준다.
        available = get_available_payout(db, r.requester_user_id, r.role, exclude_payout_id=r.id)
        results.append({
            "id": r.id, "requester_user_id": r.requester_user_id,
            "requester_name": user.name if user else None,
            "role": r.role, "amount": float(r.amount),
            "available_balance": float(available),
            "bank_info": r.bank_info, "memo": r.memo,
            "status": r.status.value if r.status else None,
            "created_at": str(r.created_at),
            "reviewed_at": str(r.reviewed_at) if r.reviewed_at else None,
        })
    return results


@router.post("/payout-requests/{pid}/approve")
def approve_payout(pid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pr = db.query(PayoutRequest).filter(PayoutRequest.id == pid).first()
    if not pr:
        raise HTTPException(status_code=404)
    if pr.status != PayoutStatus.PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 페이아웃 요청입니다.")
    pr.status = PayoutStatus.APPROVED
    pr.reviewed_at = datetime.utcnow()
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "approved"}


@router.post("/payout-requests/{pid}/reject")
def reject_payout(pid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pr = db.query(PayoutRequest).filter(PayoutRequest.id == pid).first()
    if not pr:
        raise HTTPException(status_code=404)
    if pr.status != PayoutStatus.PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 페이아웃 요청입니다.")
    pr.status = PayoutStatus.REJECTED
    pr.reviewed_at = datetime.utcnow()
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "rejected"}


# ─── Ad Orders Management ───────────────────────────────────

_SHORTS_TIER_LABELS = {code: label for code, label, _ in SHORTS_DURATION_TIERS}


def _shorts_detail_payload(detail: AdOrderShortsDetail) -> dict:
    """쇼츠 주문 상세를 API 응답 형태로 직렬화한다."""
    def _load(raw, fallback):
        return json.loads(raw) if raw else fallback

    return {
        "campaign_name": detail.campaign_name,
        "brand_name": detail.brand_name,
        "industry": detail.industry,
        "website_url": detail.website_url,
        "description": detail.description,
        "campaign_type": detail.campaign_type,
        "campaign_type_label": SHORTS_CAMPAIGN_TYPE_LABELS.get(detail.campaign_type, detail.campaign_type),
        "distribution_count": detail.distribution_count,
        "video_production_count": detail.video_production_count,
        "video_duration_tier": detail.video_duration_tier,
        "video_duration_label": _SHORTS_TIER_LABELS.get(detail.video_duration_tier or "", "-"),
        "platforms": _load(detail.platforms_json, []),
        "platform_counts": _load(detail.platform_counts_json, {}),
        "start_date": str(detail.start_date) if detail.start_date else None,
        "end_date": str(detail.end_date) if detail.end_date else None,
        "target_keywords": _load(detail.target_keywords_json, []),
        "reference_links": _load(detail.reference_links_json, []),
        "uploaded_video_url": detail.uploaded_video_url,
        "brief_product_name": detail.brief_product_name,
        "brief_product_detail": detail.brief_product_detail,
        "brief_categories": _load(detail.brief_categories_json, {}),
        "brief_tone": detail.brief_tone,
        "brief_style": detail.brief_style,
        "brief_target_audience": detail.brief_target_audience,
        "brief_key_messages": detail.brief_key_messages,
        "brief_avoid": detail.brief_avoid,
        "brief_hashtags": _load(detail.brief_hashtags_json, []),
        "creator_min_followers": detail.creator_min_followers,
        "creator_gender": detail.creator_gender,
        "creator_age_group": detail.creator_age_group,
        "creator_requirements": detail.creator_requirements,
        "brand_forbidden_words": detail.brand_forbidden_words,
        "brand_no_competitor": detail.brand_no_competitor,
        "brand_no_adult": detail.brand_no_adult,
        "brand_no_violence": detail.brand_no_violence,
        "brand_no_political": detail.brand_no_political,
        "track_utm": detail.track_utm,
        "track_promo_code": detail.track_promo_code,
        "kpi_goals": _load(detail.kpi_goals_json, []),
        "est_distribution_cost": str(detail.est_distribution_cost or 0),
        "est_production_cost": str(detail.est_production_cost or 0),
        "est_total_cost": str(detail.est_total_cost or 0),
    }


@router.get("/ad/orders")
def list_ad_orders(db: Session = Depends(get_db), _=Depends(require_admin)):
    orders = db.query(AdOrder).order_by(AdOrder.created_at.desc()).all()
    results = []
    for o in orders:
        merchant = db.query(Merchant).filter(Merchant.id == o.merchant_id).first()
        creator = db.query(User).filter(User.id == o.created_by).first()
        item = {
            "id": o.id, "merchant_id": o.merchant_id,
            "merchant_name": merchant.name if merchant else None,
            "type": o.type.value, "status": o.status.value,
            "created_by": o.created_by,
            "creator_name": creator.name if creator else None,
            "admin_memo": o.admin_memo,
            "created_at": str(o.created_at),
            "allowed_statuses": _allowed_ad_order_statuses(o.status.value),
        }
        # attach details
        if o.type.value == "blog":
            detail = db.query(AdOrderBlogDetail).filter(AdOrderBlogDetail.order_id == o.id).first()
            if detail:
                item["blog_detail"] = {
                    "campaign_name": detail.campaign_name,
                    "address": detail.address,
                    "contact": detail.contact,
                    "links": json.loads(detail.links_json) if detail.links_json else [],
                    "main_keywords": json.loads(detail.main_keywords_json) if detail.main_keywords_json else [],
                    "hashtags": json.loads(detail.hashtags_json) if detail.hashtags_json else [],
                    "description": detail.description,
                    "order_count": detail.order_count,
                    "unit_price": str(detail.unit_price or 0),
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        elif o.type.value == "place_traffic":
            detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == o.id).first()
            if detail:
                item["place_traffic_detail"] = {
                    "place_name_or_id": detail.place_name_or_id,
                    "search_keywords": json.loads(detail.search_keywords_json) if detail.search_keywords_json else [],
                    "order_count": detail.order_count,
                    "unit_price": str(detail.unit_price or 0),
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        elif o.type.value == "shorts":
            detail = db.query(AdOrderShortsDetail).filter(AdOrderShortsDetail.order_id == o.id).first()
            if detail:
                item["shorts_detail"] = _shorts_detail_payload(detail)
        results.append(item)
    return results


@router.post("/ad/orders/{oid}/status")
def update_ad_order_status(oid: int, req: AdOrderStatusUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    order = db.query(AdOrder).filter(AdOrder.id == oid).first()
    if not order:
        raise HTTPException(status_code=404)
    valid = [s.value for s in AdOrderStatus]
    if req.status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {valid}")
    _validate_ad_order_transition(order.status.value, req.status)
    order.status = AdOrderStatus(req.status)
    order.assigned_admin_id = admin.id
    if req.admin_memo:
        order.admin_memo = req.admin_memo
    db.commit()
    return {"ok": True, "status": order.status.value}


# ─── Ad Metrics ──────────────────────────────────────────────

@router.post("/ad/metrics")
def create_ad_metric(req: AdMetricCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    target_urls = {
        row.place_url for row in db.query(AdPlaceProfile).filter(
            AdPlaceProfile.merchant_id == req.merchant_id,
            AdPlaceProfile.place_url.isnot(None),
        ).all()
    }
    target_urls.update(
        row.competitor_place_url for row in db.query(AdCompetitor).filter(
            AdCompetitor.merchant_id == req.merchant_id,
        ).all()
    )
    if req.place_url not in target_urls:
        raise HTTPException(status_code=400, detail="해당 매장의 분석 대상에 등록되지 않은 플레이스입니다")

    metric = db.query(AdMetric).filter(
        AdMetric.merchant_id == req.merchant_id,
        AdMetric.place_url == req.place_url,
        AdMetric.date == req.date,
    ).first()
    updated = metric is not None
    if not metric:
        metric = AdMetric(
            merchant_id=req.merchant_id,
            place_url=req.place_url,
            date=req.date,
        )
        db.add(metric)
    metric.blog_review_count = max(0, req.blog_review_count)
    metric.visitor_review_count = max(0, req.visitor_review_count)
    metric.place_rank = max(1, req.place_rank) if req.place_rank is not None else None
    metric.search_keyword = (req.search_keyword or "").strip() or None
    metric.source = req.source
    metric.created_by = admin.id
    db.commit()
    db.refresh(metric)
    return {"id": metric.id, "updated": updated}


@router.get("/ad/analysis-targets")
def list_ad_analysis_targets(
    merchant_id: int = Query(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    profiles = db.query(AdPlaceProfile).filter(AdPlaceProfile.merchant_id == merchant_id).all()
    competitors = db.query(AdCompetitor).filter(AdCompetitor.merchant_id == merchant_id).all()
    primary_keyword = next((p.analysis_keyword for p in profiles if p.analysis_keyword), None)

    targets = []
    for row in profiles:
        if row.place_url:
            targets.append({
                "type": "my",
                "name": row.nickname or merchant.name,
                "place_url": row.place_url,
                "search_keyword": row.analysis_keyword or primary_keyword,
            })
    for row in competitors:
        targets.append({
            "type": "competitor",
            "name": row.memo or row.competitor_place_url,
            "place_url": row.competitor_place_url,
            "search_keyword": primary_keyword,
        })

    for target in targets:
        latest = db.query(AdMetric).filter(
            AdMetric.merchant_id == merchant_id,
            AdMetric.place_url == target["place_url"],
        ).order_by(AdMetric.date.desc()).first()
        target["latest_metric"] = {
            "date": str(latest.date),
            "blog_review_count": latest.blog_review_count,
            "visitor_review_count": latest.visitor_review_count,
            "place_rank": latest.place_rank,
            "search_keyword": latest.search_keyword,
        } if latest else None

    return {
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "analysis_keyword": primary_keyword,
        "targets": targets,
        "ready_count": sum(1 for target in targets if target["latest_metric"]),
    }


@router.get("/ad/metrics")
def list_ad_metrics(
    merchant_id: int = Query(...),
    place_url: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    q = db.query(AdMetric).filter(AdMetric.merchant_id == merchant_id)
    if place_url:
        q = q.filter(AdMetric.place_url == place_url)
    rows = q.order_by(AdMetric.date.desc()).limit(limit).all()
    return [{
        "id": row.id,
        "place_url": row.place_url,
        "date": str(row.date),
        "blog_review_count": row.blog_review_count,
        "visitor_review_count": row.visitor_review_count,
        "place_rank": row.place_rank,
        "search_keyword": row.search_keyword,
        "source": row.source,
    } for row in rows]


# ─── Fee Policies ────────────────────────────────────────────

@router.get("/merchants/{mid}/fee-policy")
def get_fee_policy(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == mid,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None
    mfr, pgr, comm_rate = get_effective_fee_rates(db, mid, sales_manager_user_id)

    sales_info = None
    if assign:
        sales_user = db.query(User).filter(User.id == assign.sales_manager_user_id).first()
        sales_info = {
            "assignment_id": assign.id,
            "sales_manager_id": assign.sales_manager_user_id,
            "sales_manager_name": sales_user.name if sales_user else None,
            "commission_rate": comm_rate,
            "commission_rate_pct": round(comm_rate * 100, 2),
            "memo": assign.memo,
        }

    # 실제 적용율 (부가세 포함) — 금액은 이 값으로 계산된다.
    mfr_vat = apply_vat(mfr)
    pgr_vat = apply_vat(pgr)

    sample = 10000
    sim_merchant_fee = round(sample * mfr_vat)
    sim_pg_cost = round(sample * pgr_vat)
    sim_platform = sim_merchant_fee - sim_pg_cost
    sim_commission = round(sample * comm_rate)
    sim_company = sim_platform - sim_commission
    sim_net = sample - sim_merchant_fee

    return {
        "merchant_id": mid,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": mfr,
        "pg_fee_rate": pgr,
        "has_fee_policy": fp is not None,
        "has_sales_manager": assign is not None,
        "sales_info": sales_info,
        # 실제 적용율 (부가세 포함)
        "merchant_fee_rate_with_vat": mfr_vat,
        "pg_fee_rate_with_vat": pgr_vat,
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_label": format_rate_with_vat(mfr),
        "pg_fee_rate_label": format_rate_with_vat(pgr),
        # 하위 호환 필드
        "vat_inclusive_rate": pgr_vat,
        "pg_fee_rate_excl_vat": pgr,
        "description": (
            f"미용실수수료 {format_rate_excl_vat(mfr)} / PG비용 {format_rate_excl_vat(pgr)}"
            f" / 영업커미션 {comm_rate*100:.2f}%"
            f" — 실제 적용: 미용실 {mfr_vat*100:.2f}% / PG {pgr_vat*100:.2f}%"
        ),
        "simulation": {
            "sample_amount": sample,
            "merchant_fee_amount": sim_merchant_fee,
            "pg_cost": sim_pg_cost,
            "platform_income": sim_platform,
            "commission_amount": sim_commission,
            "company_profit": sim_company,
            "net_amount": int(sim_net),
            # 하위 호환
            "pg_fee_amount": sim_pg_cost,
            "vat_included": True,
            "breakdown": (
                f"결제 {sample:,}원 → 미용실수수료 {sim_merchant_fee:,}원"
                f" (PG {sim_pg_cost:,}원 + 플랫폼 {sim_platform:,}원"
                + (f" = 영업 {sim_commission:,}원 + 회사 {sim_company:,}원" if assign else "")
                + f") → 미용실수령액 {int(sim_net):,}원"
                + " (수수료 금액은 부가세 포함)"
            ),
        },
    }


@router.post("/merchants/{mid}/fee-policy")
def set_fee_policy(mid: int, req: FeePolicyUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """하위 호환 엔드포인트 — pg_fee_rate 만 저장. 신규는 PUT /merchants/{mid}/fee-override 사용 권장.

    req.pg_fee_rate 는 **부가세 별도** 기준으로 그대로 저장하고, 정산 계산 시 × 1.1 이 적용된다.
    """
    pgr = float(req.pg_fee_rate)
    pgr_vat = apply_vat(pgr)
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    mfr_global, _, _ = get_effective_fee_rates(db, None)

    # 저장 전 교차 검증 — 변경 후 플랫폼 수익률이 기존 커미션율을 감당하는지 확인한다.
    new_mfr = float(fp.merchant_fee_rate) if fp and fp.merchant_fee_rate is not None else mfr_global
    _validate_merchant_commission_fit(db, mid, new_mfr, pgr)

    # pg_fee_rate 는 부가세 별도 저장값, vat_inclusive_rate 는 실제 적용율(× 1.1)
    if fp:
        fp.pg_fee_rate = pgr
        fp.vat_inclusive_rate = round(pgr_vat, 4)
    else:
        fp = FeePolicy(merchant_id=mid, pg_fee_rate=pgr, merchant_fee_rate=mfr_global,
                       vat_inclusive_rate=round(pgr_vat, 4))
        db.add(fp)
    db.commit()
    return {
        "ok": True,
        "pg_fee_rate": pgr,
        "pg_fee_rate_with_vat": pgr_vat,
        "vat_inclusive_rate": pgr_vat,
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "pg_fee_rate_label": format_rate_with_vat(pgr),
        "example": (
            f"10,000원 결제 시 PG수수료 {int(10000 * pgr_vat):,}원"
            f" (입력 {pgr*100:.2f}% 부가세 별도 → 실제 적용 {pgr_vat*100:.2f}%)"
            f" / 미용실수령액 {int(10000 * (1 - pgr_vat)):,}원"
        ),
    }


# ─── 통합 수수료 현황 (모든 가맹점 + 영업관리자 배정 한번에) ──

@router.get("/fee-policy-overview")
def fee_policy_overview(db: Session = Depends(get_db), _=Depends(require_admin)):
    """모든 가맹점의 수수료정책 + 영업관리자 배정 현황을 일괄 조회"""
    merchants = db.query(Merchant).filter(Merchant.is_active == True).all()
    results = []
    for m in merchants:
        fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == m.id).first()
        assign = db.query(MerchantSalesAssignment).filter(
            MerchantSalesAssignment.merchant_id == m.id,
            MerchantSalesAssignment.is_active == True,  # noqa: E712
        ).first()
        sales_manager_user_id = assign.sales_manager_user_id if assign else None

        mfr, pgr, comm_rate = get_effective_fee_rates(db, m.id, sales_manager_user_id)
        platform_rate = mfr - pgr
        company_rate = platform_rate - comm_rate

        # 실제 적용율 (부가세 포함) — 금액은 이 값으로 계산된다.
        mfr_vat = apply_vat(mfr)
        pgr_vat = apply_vat(pgr)

        sales_name = None
        if assign:
            su = db.query(User).filter(User.id == assign.sales_manager_user_id).first()
            sales_name = su.name if su else None

        sample = 10000
        sim_merchant_fee = round(sample * mfr_vat)
        sim_pg_cost = round(sample * pgr_vat)
        sim_platform = sim_merchant_fee - sim_pg_cost
        sim_commission = round(sample * comm_rate)
        sim_company = sim_platform - sim_commission
        sim_net = sample - sim_merchant_fee

        results.append({
            "merchant_id": m.id,
            "merchant_name": m.name,
            "category": m.display_category if hasattr(m, 'display_category') else None,
            "has_fee_policy": fp is not None,
            "has_sales_manager": assign is not None,
            "sales_manager_name": sales_name,
            "merchant_fee_rate": mfr,
            "merchant_fee_rate_pct": round(mfr * 100, 2),
            "pg_fee_rate": pgr,
            "pg_fee_rate_pct": round(pgr * 100, 2),
            "platform_rate": round(platform_rate, 4),
            "commission_rate": comm_rate,
            "commission_rate_pct": round(comm_rate * 100, 2),
            "company_profit_rate": round(company_rate, 4),
            "assignment_id": assign.id if assign else None,
            # 실제 적용율 (부가세 포함) — 위 rate 필드는 부가세 별도 저장값
            "merchant_fee_rate_with_vat": mfr_vat,
            "merchant_fee_rate_with_vat_pct": round(mfr_vat * 100, 2),
            "pg_fee_rate_with_vat": pgr_vat,
            "pg_fee_rate_with_vat_pct": round(pgr_vat * 100, 2),
            "vat_rate": VAT_RATE,
            "fee_rate_vat_exclusive": True,
            # 하위 호환 필드
            "pg_fee_rate_excl_vat": pgr,
            "pg_fee_rate_excl_vat_pct": round(pgr * 100, 2),
            "vat_inclusive_rate": pgr_vat,
            "vat_inclusive_rate_pct": round(pgr_vat * 100, 2),
            # 시뮬레이션 (10,000원 기준)
            "sim_merchant_fee": sim_merchant_fee,
            "sim_pg_fee": sim_pg_cost,
            "sim_platform": sim_platform,
            "sim_commission": sim_commission,
            "sim_company": sim_company,
            "sim_net": int(sim_net),
        })
    return results


# ─── Sales Assignments (영업관리자 연결) ─────────────────────

@router.get("/sales-assignments")
def list_sales_assignments(db: Session = Depends(get_db), _=Depends(require_admin)):
    assigns = db.query(MerchantSalesAssignment).all()
    results = []
    for a in assigns:
        user = db.query(User).filter(User.id == a.sales_manager_user_id).first()
        merchant = db.query(Merchant).filter(Merchant.id == a.merchant_id).first()
        results.append({
            "id": a.id, "merchant_id": a.merchant_id,
            "merchant_name": merchant.name if merchant else None,
            "sales_manager_user_id": a.sales_manager_user_id,
            "sales_manager_name": user.name if user else None,
            "commission_rate": float(a.commission_rate),
            "memo": a.memo if hasattr(a, 'memo') else None,
            "is_active": a.is_active if hasattr(a, 'is_active') else True,
        })
    return results


@router.post("/sales-assignments")
def create_sales_assignment(req: SalesAssignmentCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    # 영업관리자 역할 확인
    sales_user = db.query(User).filter(User.id == req.sales_manager_user_id).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=400, detail="영업관리자 역할의 사용자만 배정할 수 있습니다.")
    # 가맹점 확인
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다.")
    # 한 가맹점에 활성 배정 1개만 허용
    active_existing = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == req.merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    if active_existing:
        raise HTTPException(
            status_code=400,
            detail="이미 해당 가맹점에 활성 영업관리자 배정이 존재합니다. 기존 배정을 해제 후 시도해주세요.",
        )
    # 커미션율 검증 (유효 수수료율 기준)
    mfr, pgr, _ = get_effective_fee_rates(db, req.merchant_id)
    platform_rate = mfr - pgr
    if req.commission_rate < 0 or req.commission_rate > platform_rate + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=f"영업 커미션율은 0% ~ 플랫폼 수익률({platform_rate*100:.2f}%) 이하여야 합니다. 입력값: {req.commission_rate*100:.2f}%",
        )
    a = MerchantSalesAssignment(
        merchant_id=req.merchant_id,
        sales_manager_user_id=req.sales_manager_user_id,
        commission_rate=req.commission_rate,
        memo=req.memo,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "commission_rate": float(a.commission_rate)}


@router.put("/sales-assignments/{aid}")
def update_sales_assignment(aid: int, req: SalesAssignmentUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    a = db.query(MerchantSalesAssignment).filter(MerchantSalesAssignment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="영업배정을 찾을 수 없습니다.")
    if req.commission_rate is not None:
        # 커미션율 검증 (생성 시와 동일하게 유효 수수료율 기준)
        mfr, pgr, _ = get_effective_fee_rates(db, a.merchant_id)
        _validate_commission_rate(req.commission_rate, mfr, pgr)
        a.commission_rate = req.commission_rate
    if req.memo is not None:
        a.memo = req.memo
    if req.is_active is not None:
        a.is_active = req.is_active
    db.commit()
    return {"ok": True}


@router.delete("/sales-assignments/{aid}")
def delete_sales_assignment(aid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    a = db.query(MerchantSalesAssignment).filter(MerchantSalesAssignment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="영업배정을 찾을 수 없습니다.")
    db.delete(a)
    db.commit()
    return {"ok": True}


# 영업관리자 목록 조회 (dropdown용)
@router.get("/sales-managers")
def list_sales_managers(db: Session = Depends(get_db), _=Depends(require_admin)):
    users = db.query(User).filter(User.role == UserRole.SALES, User.is_active == True).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "referral_code": u.referral_code} for u in users]


# ─── Users Management ───────────────────────────────────────

@router.get("/users")
def list_all_users(
    role: Optional[str] = None,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """전체 사용자 목록 (역할별 필터 가능)"""
    q = db.query(User)
    if role:
        q = q.filter(User.role == UserRole(role))
    users = q.order_by(User.created_at.desc()).all()

    results = []
    for u in users:
        # 소유 가맹점 이름 조회
        merchant = db.query(Merchant).filter(Merchant.owner_user_id == u.id).first()
        # 영업관리자인 경우 담당 가맹점 수
        assigned_count = 0
        if u.role == UserRole.SALES:
            assigned_count = db.query(MerchantSalesAssignment).filter(
                MerchantSalesAssignment.sales_manager_user_id == u.id,
                MerchantSalesAssignment.is_active == True,
            ).count()
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role.value,
            "phone": u.phone,
            "is_active": u.is_active,
            "created_at": str(u.created_at),
            "merchant_name": merchant.name if merchant else None,
            "assigned_merchant_count": assigned_count,
            "referral_code": u.referral_code if u.role == UserRole.SALES else None,
        })
    return results


@router.post("/users/create-sales")
def create_sales_user(
    name: str = Query(..., description="영업관리자 이름"),
    email: str = Query(..., description="이메일"),
    password: str = Query(..., description="초기 비밀번호"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """최고관리자가 영업관리자 계정을 직접 생성한다. 고유 추천 코드가 자동 발급된다."""
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    referral_code = f"SALES-{secrets.token_hex(4).upper()}"
    while db.query(User).filter(User.referral_code == referral_code).first():
        referral_code = f"SALES-{secrets.token_hex(4).upper()}"

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=UserRole.SALES,
        referral_code=referral_code,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": "sales",
        "referral_code": user.referral_code,
    }


@router.put("/users/{uid}/role")
def update_user_role(uid: int, role: str = Query(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    """사용자 역할 변경"""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    valid_roles = [r.value for r in UserRole]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 역할입니다. 사용 가능: {valid_roles}")
    user.role = UserRole(role)
    db.commit()
    return {"ok": True, "role": role}


@router.put("/users/{uid}/toggle-active")
def toggle_user_active(uid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """사용자 활성/비활성 토글"""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user.is_active = not user.is_active
    db.commit()
    return {"ok": True, "is_active": user.is_active}


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


# ─── Settlements ─────────────────────────────────────────────

@router.get("/settlements")
def list_settlements(
    merchant_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    q = db.query(Settlement)
    if merchant_id:
        q = q.filter(Settlement.merchant_id == merchant_id)
    settlements = q.order_by(Settlement.created_at.desc()).all()
    merchant_names = {m.id: m.name for m in db.query(Merchant).all()}
    return [{
        "id": s.id, "merchant_id": s.merchant_id,
        "merchant_name": merchant_names.get(s.merchant_id, f"가맹점#{s.merchant_id}"),
        "period_start": str(s.period_start), "period_end": str(s.period_end),
        "gross_amount": float(s.gross_amount), "pg_fee_amount": float(s.pg_fee_amount),
        "net_amount": float(s.net_amount), "commission_amount": float(s.commission_amount),
        "created_at": str(s.created_at),
    } for s in settlements]


@router.post("/settlements/calculate")
def calculate_settlement(
    merchant_id: int = Query(...),
    period_start: str = Query(...),
    period_end: str = Query(...),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """가맹점 정산 계산 및 Settlement 생성.

    수수료 체계 (새 구조):
    - 미용실 수수료(merchant_fee) = 결제액 × merchant_fee_rate (미용실이 내는 총 수수료)
    - PG 실비용(pg_cost) = 결제액 × pg_fee_rate (PG사에 지불)
    - 플랫폼 수익 = merchant_fee - pg_cost
    - 영업 커미션 = 결제액 × sales_commission_rate
    - 회사 순수익 = 플랫폼 수익 - 영업 커미션
    - 미용실 실수령액(net) = 결제액 - merchant_fee
    """
    from datetime import datetime as dt
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    start = dt.fromisoformat(period_start)
    end = dt.fromisoformat(period_end)
    if end.hour == 0 and end.minute == 0 and end.second == 0:
        end = end + timedelta(days=1) - timedelta(microseconds=1)

    # 같은 기간으로 재호출 시 Settlement 중복 생성 방지 (기간 겹침 검사)
    existing = db.query(Settlement).filter(
        Settlement.merchant_id == merchant_id,
        Settlement.period_start <= end,
        Settlement.period_end >= start,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 해당 기간에 정산이 존재합니다.")

    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant_id,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()

    gross = sum(float(t.amount) for t in txns)

    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None

    merchant_fee_rate, pg_fee_rate, commission_rate = get_effective_fee_rates(
        db, merchant_id, sales_manager_user_id
    )

    dist = compute_fee_distribution(gross, merchant_fee_rate, pg_fee_rate, commission_rate)

    settlement = Settlement(
        merchant_id=merchant_id,
        sales_manager_user_id=sales_manager_user_id,
        period_start=start,
        period_end=end,
        gross_amount=round(gross, 2),
        merchant_fee_amount=dist["merchant_fee"],
        pg_fee_amount=dist["pg_cost"],
        net_amount=dist["net_payout"],
        commission_amount=dist["sales_commission"],
        company_profit_amount=dist["company_profit"],
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)
    return {
        "id": settlement.id,
        "merchant_name": merchant.name,
        "gross_amount": gross,
        "merchant_fee_amount": dist["merchant_fee"],
        "pg_fee_amount": dist["pg_cost"],
        "platform_income": dist["platform_income"],
        "commission_amount": dist["sales_commission"],
        "company_profit_amount": dist["company_profit"],
        "net_amount": dist["net_payout"],
        "transactions_count": len(txns),
        # 저장값 (부가세 별도)
        "merchant_fee_rate": merchant_fee_rate,
        "pg_fee_rate": pg_fee_rate,
        "sales_commission_rate": commission_rate,
        # 실제 적용율 (부가세 포함) — 위 금액은 이 값으로 계산됨
        "merchant_fee_rate_with_vat": dist["merchant_fee_rate_with_vat"],
        "pg_fee_rate_with_vat": dist["pg_fee_rate_with_vat"],
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
    }


# ═══════════════════════════════════════════════════════════
# AFFILIATE MALLS (제휴중개몰)
# ═══════════════════════════════════════════════════════════

@router.get("/affiliate-malls")
def list_affiliate_malls(db: Session = Depends(get_db), _=Depends(require_admin)):
    """제휴중개몰 목록"""
    malls = db.query(AffiliateMall).order_by(AffiliateMall.sort_order, AffiliateMall.id).all()
    return [{
        "id": m.id, "name": m.name, "logo_url": m.logo_url,
        "website_url": m.website_url, "description": m.description,
        "category": m.category, "commission_rate": m.commission_rate,
        "is_active": m.is_active, "sort_order": m.sort_order,
        "created_at": str(m.created_at),
    } for m in malls]


@router.post("/affiliate-malls")
def create_affiliate_mall(
    name: str = Query(...),
    logo_url: Optional[str] = Query(None),
    website_url: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    commission_rate: Optional[str] = Query(None),
    sort_order: int = Query(0),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """제휴중개몰 등록"""
    mall = AffiliateMall(
        name=name, logo_url=logo_url, website_url=website_url,
        description=description, category=category,
        commission_rate=commission_rate, sort_order=sort_order,
    )
    db.add(mall)
    db.commit()
    db.refresh(mall)
    return {"id": mall.id, "name": mall.name, "message": "제휴중개몰이 등록되었습니다."}


@router.put("/affiliate-malls/{mall_id}")
def update_affiliate_mall(
    mall_id: int,
    name: Optional[str] = Query(None),
    logo_url: Optional[str] = Query(None),
    website_url: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    commission_rate: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    sort_order: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """제휴중개몰 수정"""
    mall = db.query(AffiliateMall).filter(AffiliateMall.id == mall_id).first()
    if not mall:
        raise HTTPException(404, "중개몰을 찾을 수 없습니다.")
    if name is not None: mall.name = name
    if logo_url is not None: mall.logo_url = logo_url
    if website_url is not None: mall.website_url = website_url
    if description is not None: mall.description = description
    if category is not None: mall.category = category
    if commission_rate is not None: mall.commission_rate = commission_rate
    if is_active is not None: mall.is_active = is_active
    if sort_order is not None: mall.sort_order = sort_order
    db.commit()
    return {"id": mall.id, "message": "제휴중개몰이 수정되었습니다."}


@router.delete("/affiliate-malls/{mall_id}")
def delete_affiliate_mall(
    mall_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """제휴중개몰 삭제"""
    mall = db.query(AffiliateMall).filter(AffiliateMall.id == mall_id).first()
    if not mall:
        raise HTTPException(404, "중개몰을 찾을 수 없습니다.")
    db.delete(mall)
    db.commit()
    return {"message": "제휴중개몰이 삭제되었습니다."}


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
# Ad Order Execution - Full Implementation (Task 6)
# ═══════════════════════════════════════════════════════════

@router.get("/ad/orders/{oid}")
def get_ad_order_detail(oid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Get detailed ad order info for admin review/execution."""
    order = db.query(AdOrder).filter(AdOrder.id == oid).first()
    if not order:
        raise HTTPException(status_code=404, detail="광고주문을 찾을 수 없습니다")

    merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()
    creator = db.query(User).filter(User.id == order.created_by).first()
    assigned = db.query(User).filter(User.id == order.assigned_admin_id).first() if order.assigned_admin_id else None

    item = {
        "id": order.id,
        "merchant_id": order.merchant_id,
        "merchant_name": merchant.name if merchant else None,
        "type": order.type.value,
        "status": order.status.value,
        "created_by": order.created_by,
        "creator_name": creator.name if creator else None,
        "assigned_admin_id": order.assigned_admin_id,
        "assigned_admin_name": assigned.name if assigned else None,
        "admin_memo": order.admin_memo,
        "created_at": str(order.created_at),
        "updated_at": str(order.updated_at),
        "allowed_statuses": _allowed_ad_order_statuses(order.status.value),
    }

    if order.type.value == "blog":
        detail = db.query(AdOrderBlogDetail).filter(AdOrderBlogDetail.order_id == order.id).first()
        if detail:
            images = db.query(AdOrderBlogImage).filter(AdOrderBlogImage.order_id == order.id).all()
            item["blog_detail"] = {
                "campaign_name": detail.campaign_name,
                "address": detail.address,
                "contact": detail.contact,
                "links": json.loads(detail.links_json) if detail.links_json else [],
                "main_keywords": json.loads(detail.main_keywords_json) if detail.main_keywords_json else [],
                "hashtags": json.loads(detail.hashtags_json) if detail.hashtags_json else [],
                "description": detail.description,
                "images": [{"id": img.id, "file_path": img.file_path} for img in images],
                "order_count": detail.order_count,
                "unit_price": str(detail.unit_price or 0),
                "est_total_cost": str(detail.est_total_cost or 0),
            }
    elif order.type.value == "place_traffic":
        detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == order.id).first()
        if detail:
            item["place_traffic_detail"] = {
                "place_name_or_id": detail.place_name_or_id,
                "search_keywords": json.loads(detail.search_keywords_json) if detail.search_keywords_json else [],
                "order_count": detail.order_count,
                "unit_price": str(detail.unit_price or 0),
                "est_total_cost": str(detail.est_total_cost or 0),
            }
    elif order.type.value == "shorts":
        detail = db.query(AdOrderShortsDetail).filter(AdOrderShortsDetail.order_id == order.id).first()
        if detail:
            item["shorts_detail"] = _shorts_detail_payload(detail)

    return item


@router.put("/ad/orders/{oid}/execute")
def execute_ad_order(
    oid: int,
    status: str = Query(...),
    admin_memo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Execute/update an ad order with full status tracking."""
    order = db.query(AdOrder).filter(AdOrder.id == oid).first()
    if not order:
        raise HTTPException(status_code=404)

    valid = [s.value for s in AdOrderStatus]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {valid}")
    _validate_ad_order_transition(order.status.value, status)

    old_status = order.status.value
    order.status = AdOrderStatus(status)
    order.assigned_admin_id = admin.id
    if admin_memo:
        order.admin_memo = (order.admin_memo or "") + f"\n[{now_kst().strftime('%Y-%m-%d %H:%M')} KST] {admin_memo}"
    order.updated_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "order_id": order.id,
        "old_status": old_status,
        "new_status": status,
        "assigned_admin": admin.name,
    }


# ═══════════════════════════════════════════════════════════
# 광고 기능 스위치 (블로그 배포 / 플레이스 유입 ON/OFF)
# ═══════════════════════════════════════════════════════════

def _get_config(db: Session, key: str) -> SystemConfig:
    """설정값 가져오기 (없으면 생성)"""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if not cfg:
        cfg = SystemConfig(config_key=key, is_enabled=False)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/ad-feature-flags")
def get_ad_feature_flags(db: Session = Depends(get_db), _=Depends(require_admin)):
    """광고 기능 스위치 상태 조회"""
    master = _get_config(db, AD_ORDER_MGMT_ENABLED)
    blog = _get_config(db, AD_BLOG_ENABLED)
    place = _get_config(db, AD_PLACE_TRAFFIC_ENABLED)
    shorts = _get_config(db, AD_SHORTS_ENABLED)
    return {
        "ad_order_mgmt_enabled": master.is_enabled,
        "ad_blog_enabled": blog.is_enabled,
        "ad_place_traffic_enabled": place.is_enabled,
        "ad_shorts_enabled": shorts.is_enabled,
    }


@router.put("/ad-feature-flags")
def update_ad_feature_flags(
    ad_order_mgmt_enabled: Optional[bool] = Query(None),
    ad_blog_enabled: Optional[bool] = Query(None),
    ad_place_traffic_enabled: Optional[bool] = Query(None),
    ad_shorts_enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """광고 기능 스위치 ON/OFF 변경"""
    result = {}
    if ad_order_mgmt_enabled is not None:
        cfg = _get_config(db, AD_ORDER_MGMT_ENABLED)
        cfg.is_enabled = ad_order_mgmt_enabled
        result["ad_order_mgmt_enabled"] = ad_order_mgmt_enabled
    if ad_blog_enabled is not None:
        cfg = _get_config(db, AD_BLOG_ENABLED)
        cfg.is_enabled = ad_blog_enabled
        result["ad_blog_enabled"] = ad_blog_enabled
    if ad_place_traffic_enabled is not None:
        cfg = _get_config(db, AD_PLACE_TRAFFIC_ENABLED)
        cfg.is_enabled = ad_place_traffic_enabled
        result["ad_place_traffic_enabled"] = ad_place_traffic_enabled
    if ad_shorts_enabled is not None:
        cfg = _get_config(db, AD_SHORTS_ENABLED)
        cfg.is_enabled = ad_shorts_enabled
        result["ad_shorts_enabled"] = ad_shorts_enabled
    db.commit()
    return {"ok": True, **result}


@router.get("/ad-pricing")
def get_ad_pricing(db: Session = Depends(get_db), _=Depends(require_admin)):
    """최고관리자 광고 단가 설정 조회."""
    return ad_pricing.get_ad_pricing(db)


@router.put("/ad-pricing")
def update_ad_pricing(
    req: AdPricingUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """최고관리자 광고 단가 설정 저장."""
    valid_tiers = {code for code, _, _ in SHORTS_DURATION_TIERS}
    unknown_tiers = set(req.shorts_duration_prices) - valid_tiers
    if unknown_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 쇼츠 영상 길이입니다: {', '.join(sorted(unknown_tiers))}",
        )
    return {
        "ok": True,
        **ad_pricing.save_ad_pricing(db, req.model_dump()),
    }


# ═══════════════════════════════════════════════════════════
# 전역/가맹점별/영업관리자별 수수료 설정
# ═══════════════════════════════════════════════════════════

def _validate_commission_rate(commission_rate: float, merchant_fee_rate: float, pg_fee_rate: float):
    """영업 커미션율 검증: (merchant_fee_rate - pg_fee_rate) 초과 시 400."""
    platform_rate = merchant_fee_rate - pg_fee_rate
    if commission_rate < 0 or commission_rate > platform_rate + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=(
                f"영업 커미션율({commission_rate*100:.2f}%)이 플랫폼 수익률"
                f"({platform_rate*100:.2f}%)을 초과합니다 "
                f"(미용실 수수료 {merchant_fee_rate*100:.2f}% − PG 비용 {pg_fee_rate*100:.2f}%)"
            ),
        )


def _validate_merchant_commission_fit(
    db: Session, merchant_id: int, merchant_fee_rate: float, pg_fee_rate: float
):
    """수수료율 변경 전 교차 검증.

    해당 가맹점의 기존 유효 영업 커미션율이 새 플랫폼 수익률
    (merchant_fee_rate - pg_fee_rate)을 초과하면 400.
    검증 없이 저장하면 이후 정산 계산에서 ValueError → 500 이 된다.

    배정 여부와 무관하게 get_effective_fee_rates() 로 유효 커미션율을 구해 검증한다.
    영업담당자 미배정 가맹점은 커미션 0% 이므로 플랫폼 수익률이 음수
    (merchant_fee_rate < pg_fee_rate)인 경우만 걸러진다.
    """
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None
    _, _, commission_rate = get_effective_fee_rates(
        db, merchant_id, sales_manager_user_id
    )
    _validate_commission_rate(commission_rate, merchant_fee_rate, pg_fee_rate)


@router.get("/fee-settings")
def get_fee_settings(db: Session = Depends(get_db), _=Depends(require_admin)):
    """전역 기본 수수료 설정 조회 (merchant_id=NULL 레코드).

    merchant_fee_rate / pg_fee_rate 는 부가세 별도 기준 저장값이며,
    *_with_vat 필드가 실제 적용율(× 1.1)이다.
    """
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id.is_(None)).first()
    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id.is_(None)
    ).first()

    mfr = float(fp.merchant_fee_rate) if fp else DEFAULT_MERCHANT_FEE_RATE
    pgr = float(fp.pg_fee_rate) if fp else DEFAULT_PG_FEE_RATE
    scr = float(scp.commission_rate) if scp else DEFAULT_SALES_COMMISSION_RATE
    platform_rate = mfr - pgr
    company_rate = platform_rate - scr

    # 실제 적용율 (부가세 포함) — 금액은 이 값으로 계산된다.
    mfr_vat = apply_vat(mfr)
    pgr_vat = apply_vat(pgr)

    # 시뮬레이션 — compute_fee_distribution() 과 동일한 계산 순서 (부가세 포함 적용율 기준).
    # 조회 엔드포인트이므로 커미션율 검증(ValueError)을 타지 않도록 직접 계산한다.
    sample = 10000
    sim_merchant_fee = round(sample * mfr_vat)
    sim_pg_cost = round(sample * pgr_vat)
    sim_platform = sim_merchant_fee - sim_pg_cost
    sim_commission = round(sample * scr)
    sim_company = sim_platform - sim_commission
    sim_net = sample - sim_merchant_fee
    return {
        # 저장값 (부가세 별도)
        "merchant_fee_rate": mfr,
        "pg_fee_rate": pgr,
        "sales_commission_rate": scr,
        "platform_rate": round(platform_rate, 4),
        "company_profit_rate": round(company_rate, 4),
        "has_global_fee_policy": fp is not None,
        "has_global_commission_policy": scp is not None,
        # 부가세 (VAT 10% 별도)
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_with_vat": mfr_vat,
        "pg_fee_rate_with_vat": pgr_vat,
        "merchant_fee_rate_label": format_rate_with_vat(mfr),
        "pg_fee_rate_label": format_rate_with_vat(pgr),
        "sales_commission_rate_label": f"{scr * 100:.2f}% (부가세 미적용)",
        "simulation": {
            "sample_amount": sample,
            "merchant_fee": sim_merchant_fee,
            "pg_cost": sim_pg_cost,
            "platform_income": sim_platform,
            "sales_commission": sim_commission,
            "company_profit": sim_company,
            "net_payout": int(sim_net),
            "vat_included": True,
            "note": "금액은 부가세 포함 실제 적용율 기준입니다.",
        },
    }


@router.put("/fee-settings")
def update_fee_settings(req: GlobalFeeSettingsUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """전역 기본 수수료 설정 저장/갱신.

    입력값(merchant_fee_rate / pg_fee_rate)은 **부가세 별도** 기준으로 그대로 저장하고,
    실제 정산 계산 시 × 1.1 이 적용된다. 검증은 부가세 별도 기준으로 수행한다.
    """
    _validate_commission_rate(req.sales_commission_rate, req.merchant_fee_rate, req.pg_fee_rate)

    # FeePolicy 전역 레코드 (merchant_id=NULL)
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id.is_(None)).first()
    if fp:
        fp.merchant_fee_rate = req.merchant_fee_rate
        fp.pg_fee_rate = req.pg_fee_rate
    else:
        fp = FeePolicy(
            merchant_id=None,
            merchant_fee_rate=req.merchant_fee_rate,
            pg_fee_rate=req.pg_fee_rate,
        )
        db.add(fp)

    # SalesCommissionPolicy 전역 레코드 (sales_manager_user_id=NULL)
    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id.is_(None)
    ).first()
    if scp:
        scp.commission_rate = req.sales_commission_rate
    else:
        scp = SalesCommissionPolicy(
            sales_manager_user_id=None,
            commission_rate=req.sales_commission_rate,
        )
        db.add(scp)

    db.commit()
    return {
        "ok": True,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": req.merchant_fee_rate,
        "pg_fee_rate": req.pg_fee_rate,
        "sales_commission_rate": req.sales_commission_rate,
        # 실제 적용율 (부가세 포함)
        "merchant_fee_rate_with_vat": apply_vat(req.merchant_fee_rate),
        "pg_fee_rate_with_vat": apply_vat(req.pg_fee_rate),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_label": format_rate_with_vat(req.merchant_fee_rate),
        "pg_fee_rate_label": format_rate_with_vat(req.pg_fee_rate),
    }


@router.get("/merchants/{mid}/fee-override")
def get_merchant_fee_override(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """가맹점 개별 수수료 오버라이드 조회 (수수료율은 모두 부가세 별도 기준)."""
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    mfr, pgr, _ = get_effective_fee_rates(db, mid)
    return {
        "merchant_id": mid,
        "merchant_name": merchant.name,
        "has_override": fp is not None,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": float(fp.merchant_fee_rate) if fp else None,
        "pg_fee_rate": float(fp.pg_fee_rate) if fp else None,
        "effective_merchant_fee_rate": mfr,
        "effective_pg_fee_rate": pgr,
        # 실제 적용율 (부가세 포함)
        "effective_merchant_fee_rate_with_vat": apply_vat(mfr),
        "effective_pg_fee_rate_with_vat": apply_vat(pgr),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "effective_merchant_fee_rate_label": format_rate_with_vat(mfr),
        "effective_pg_fee_rate_label": format_rate_with_vat(pgr),
    }


@router.put("/merchants/{mid}/fee-override")
def update_merchant_fee_override(
    mid: int, req: MerchantFeeOverrideUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """가맹점 개별 수수료 오버라이드 설정 (None 값이면 해당 필드 전역값 사용).

    입력값은 **부가세 별도** 기준으로 그대로 저장하고, 정산 계산 시 × 1.1 이 적용된다.
    """
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    mfr_default, pgr_default, _ = get_effective_fee_rates(db, None)

    # 오버라이드 값이 없으면 기존 레코드 삭제 (전역값 사용)
    if req.merchant_fee_rate is None and req.pg_fee_rate is None:
        if fp:
            # 전역값으로 되돌려도 기존 커미션율이 수용 가능해야 한다.
            _validate_merchant_commission_fit(db, mid, mfr_default, pgr_default)
            db.delete(fp)
            db.commit()
        return {"ok": True, "action": "reset_to_global", "vat_notice": VAT_NOTICE}

    # 저장 전 교차 검증 — 변경 후 유효 수수료율로 기존 커미션율을 확인한다.
    new_mfr = float(req.merchant_fee_rate) if req.merchant_fee_rate is not None else (
        float(fp.merchant_fee_rate) if fp and fp.merchant_fee_rate is not None else mfr_default
    )
    new_pgr = float(req.pg_fee_rate) if req.pg_fee_rate is not None else (
        float(fp.pg_fee_rate) if fp and fp.pg_fee_rate is not None else pgr_default
    )
    _validate_merchant_commission_fit(db, mid, new_mfr, new_pgr)

    if fp:
        if req.merchant_fee_rate is not None:
            fp.merchant_fee_rate = req.merchant_fee_rate
        if req.pg_fee_rate is not None:
            fp.pg_fee_rate = req.pg_fee_rate
    else:
        # 새 레코드 생성 (미지정 필드는 전역값에서 채움)
        fp = FeePolicy(
            merchant_id=mid,
            merchant_fee_rate=req.merchant_fee_rate if req.merchant_fee_rate is not None else mfr_default,
            pg_fee_rate=req.pg_fee_rate if req.pg_fee_rate is not None else pgr_default,
        )
        db.add(fp)

    db.commit()
    saved_mfr = float(fp.merchant_fee_rate)
    saved_pgr = float(fp.pg_fee_rate)
    return {
        "ok": True,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": saved_mfr,
        "pg_fee_rate": saved_pgr,
        # 실제 적용율 (부가세 포함)
        "merchant_fee_rate_with_vat": apply_vat(saved_mfr),
        "pg_fee_rate_with_vat": apply_vat(saved_pgr),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_label": format_rate_with_vat(saved_mfr),
        "pg_fee_rate_label": format_rate_with_vat(saved_pgr),
    }


@router.get("/sales/{uid}/commission-override")
def get_sales_commission_override(uid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """영업관리자 개별 커미션율 조회."""
    sales_user = db.query(User).filter(User.id == uid).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=404, detail="영업관리자를 찾을 수 없습니다")
    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id == uid
    ).first()
    global_scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id.is_(None)
    ).first()
    return {
        "sales_manager_user_id": uid,
        "sales_manager_name": sales_user.name,
        "has_override": scp is not None,
        "commission_rate": float(scp.commission_rate) if scp else None,
        "effective_commission_rate": (
            float(scp.commission_rate) if scp
            else (float(global_scp.commission_rate) if global_scp else DEFAULT_SALES_COMMISSION_RATE)
        ),
    }


@router.put("/sales/{uid}/commission-override")
def update_sales_commission_override(
    uid: int, req: SalesCommissionOverrideUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """영업관리자 개별 커미션율 설정 (commission_rate=None이면 전역값 사용으로 초기화)."""
    sales_user = db.query(User).filter(User.id == uid).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=404, detail="영업관리자를 찾을 수 없습니다")

    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id == uid
    ).first()

    if req.commission_rate is None:
        if scp:
            db.delete(scp)
            db.commit()
        return {"ok": True, "action": "reset_to_global"}

    # 전역 수수료 설정으로 플랫폼 수익률 계산해서 검증
    mfr, pgr, _ = get_effective_fee_rates(db, None)
    _validate_commission_rate(req.commission_rate, mfr, pgr)

    if scp:
        scp.commission_rate = req.commission_rate
    else:
        scp = SalesCommissionPolicy(
            sales_manager_user_id=uid,
            commission_rate=req.commission_rate,
        )
        db.add(scp)

    db.commit()
    return {"ok": True, "commission_rate": float(scp.commission_rate)}


# ═══════════════════════════════════════════════════════════
# 영업수수료 표시 설정 (역할별 ON/OFF)
# ═══════════════════════════════════════════════════════════

def _get_config_default(db: Session, key: str, default: bool = True) -> SystemConfig:
    """설정값 가져오기 (없으면 default 로 생성)."""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if not cfg:
        cfg = SystemConfig(config_key=key, is_enabled=default)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/commission-visibility")
def get_commission_visibility(db: Session = Depends(get_db), _=Depends(require_admin)):
    """역할별 영업수수료 표시 여부 조회 (기본값 표시=True)."""
    return {
        "admin": True,  # 최고관리자는 항상 표시
        "sales": _get_config_default(db, COMMISSION_VISIBLE_TO_SALES).is_enabled,
        "owner": _get_config_default(db, COMMISSION_VISIBLE_TO_OWNER).is_enabled,
        "designer": _get_config_default(db, COMMISSION_VISIBLE_TO_DESIGNER).is_enabled,
    }


@router.put("/commission-visibility")
def update_commission_visibility(
    req: CommissionVisibilityUpdate, db: Session = Depends(get_db), _=Depends(require_admin),
):
    """역할별 영업수수료 표시 여부 변경."""
    mapping = {
        "sales": COMMISSION_VISIBLE_TO_SALES,
        "owner": COMMISSION_VISIBLE_TO_OWNER,
        "designer": COMMISSION_VISIBLE_TO_DESIGNER,
    }
    for field, key in mapping.items():
        value = getattr(req, field)
        if value is not None:
            cfg = _get_config_default(db, key)
            cfg.is_enabled = value
    db.commit()
    return {
        "ok": True,
        "admin": True,
        "sales": _get_config_default(db, COMMISSION_VISIBLE_TO_SALES).is_enabled,
        "owner": _get_config_default(db, COMMISSION_VISIBLE_TO_OWNER).is_enabled,
        "designer": _get_config_default(db, COMMISSION_VISIBLE_TO_DESIGNER).is_enabled,
    }


# ═══════════════════════════════════════════════════════════
# 디자이너 분배율 관리 (관리자도 설정 가능)
# ═══════════════════════════════════════════════════════════

@router.get("/merchants/{mid}/staff")
def admin_list_merchant_staff(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """가맹점 직원(디자이너) 목록 + 분배율."""
    staff_list = db.query(Staff).filter(Staff.merchant_id == mid).all()
    return [{
        "id": s.id, "name": s.name, "staff_code": s.staff_code,
        "user_id": s.user_id, "is_active": s.is_active,
        "share_rate": float(s.share_rate) if s.share_rate is not None else 0.5,
    } for s in staff_list]


@router.put("/staff/{sid}/share-rate")
def admin_update_staff_share_rate(
    sid: int, req: StaffShareRateUpdate, db: Session = Depends(get_db), _=Depends(require_admin),
):
    """디자이너 분배율 설정 (0~1)."""
    s = db.query(Staff).filter(Staff.id == sid).first()
    if not s:
        raise HTTPException(status_code=404, detail="Staff not found")
    s.share_rate = max(0.0, min(1.0, req.share_rate))
    db.commit()
    return {"id": s.id, "name": s.name, "share_rate": float(s.share_rate)}


@router.get("/merchants/{mid}/settlement-breakdown")
def admin_settlement_breakdown(
    mid: int,
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """관리자용 디자이너/원장 분배 내역 (전체 항목 노출)."""
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404)
    q = db.query(Transaction).filter(Transaction.merchant_id == mid)
    if period_start:
        q = q.filter(Transaction.created_at >= datetime.fromisoformat(period_start))
    if period_end:
        q = q.filter(Transaction.created_at <= datetime.fromisoformat(period_end))
    txns = q.all()
    result = compute_distribution(db, mid, txns)
    result["merchant_name"] = merchant.name
    result["show_sales_commission"] = True
    return result


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


# ═══════════════════════════════════════════════════════════
# 플랜 관리 (베이직 / 스탠다드 / 프리미엄)
# ═══════════════════════════════════════════════════════════

_PLAN_ORDER = {"basic": 0, "standard": 1, "premium": 2}


@router.get("/plans")
def list_plans(db: Session = Depends(get_db), _=Depends(require_admin)):
    """전체 플랜 목록 (베이직 → 스탠다드 → 프리미엄 순)."""
    plans = db.query(Plan).all()
    plans.sort(key=lambda p: _PLAN_ORDER.get(p.code, 99))
    return [plan_service.plan_payload(p) for p in plans]


@router.put("/plans/{plan_id}")
def update_plan(
    plan_id: int,
    req: PlanUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """플랜 수수료율 / 월 광고 목표 건수 수정.

    수수료율은 부가세 별도 공급가로 저장한다. 일별 광고 목표는 월 목표를 실제
    달력 일수에 맞춰 자동 분배하므로 직접 입력받지 않는다.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="플랜을 찾을 수 없습니다")

    changes = req.model_dump(exclude_unset=True, exclude_none=True)
    # 이전 클라이언트가 일별 값을 보내더라도 월 목표 자동 배분 원칙을 우선한다.
    changes = {field: value for field, value in changes.items() if not field.endswith("_daily")}
    if not changes:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다")
    for field, value in changes.items():
        setattr(plan, field, value)
        if field.endswith("_monthly"):
            # DB의 기존 일별 컬럼은 호환용 평균값으로만 유지한다.
            setattr(plan, field.removesuffix("_monthly") + "_daily", int(value) // 30)

    if "merchant_fee_rate" in changes:
        db.flush()
        assigned_merchant_ids = {
            row[0] for row in db.query(MerchantPlan.merchant_id).distinct().all()
            if (current := plan_service.current_assignment(db, row[0])) and current.plan_id == plan.id
        }
        for merchant_id in assigned_merchant_ids:
            effective_mfr, effective_pgr, _ = get_effective_fee_rates(db, merchant_id)
            _validate_merchant_commission_fit(db, merchant_id, effective_mfr, effective_pgr)

    db.commit()
    db.refresh(plan)
    return plan_service.plan_payload(plan)


@router.get("/merchants/{merchant_id}/plan")
def get_merchant_plan(merchant_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """가맹점의 현재 플랜과 배정 정보."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    assignment = plan_service.current_assignment(db, merchant_id)
    if not assignment:
        return {
            "merchant_id": merchant.id, "merchant_name": merchant.name,
            "plan": None, "assigned_at": None, "assigned_by": None, "assigned_by_name": None,
        }
    return {
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "plan": plan_service.plan_payload(assignment.plan),
        "assigned_at": str(assignment.assigned_at),
        "assigned_by": assignment.assigned_by,
        "assigned_by_name": assignment.assigner.name if assignment.assigner else None,
    }


@router.put("/merchants/{merchant_id}/plan")
def change_merchant_plan(
    merchant_id: int,
    req: MerchantPlanAssign,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """가맹점 플랜 변경 (배정 이력이 한 건 추가된다)."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    plan = db.query(Plan).filter(Plan.id == req.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="플랜을 찾을 수 없습니다")

    plan_service.assign_plan(db, merchant_id, plan.id, assigned_by=admin.id)
    # 새 플랜 수수료가 현재 PG 비용·영업 커미션을 감당할 수 있는지 커밋 전에 검증한다.
    effective_mfr, effective_pgr, _ = get_effective_fee_rates(db, merchant_id)
    _validate_merchant_commission_fit(db, merchant_id, effective_mfr, effective_pgr)
    db.commit()
    return {
        "ok": True, "merchant_id": merchant.id, "merchant_name": merchant.name,
        "plan": plan_service.plan_payload(plan),
    }


# ═══════════════════════════════════════════════════════════
# 광고 집행 기록
# ═══════════════════════════════════════════════════════════

def _parse_date(value: Optional[str], field: str = "date") -> date_type:
    if not value:
        return today_kst()
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} 형식이 올바르지 않습니다 (YYYY-MM-DD)")


@router.post("/ad-executions")
def create_ad_execution(
    req: AdExecutionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """집행 건수 입력. 같은 가맹점·광고종류·날짜가 이미 있으면 값을 덮어쓴다."""
    if req.ad_type not in AD_EXECUTION_TYPE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"광고 종류가 올바르지 않습니다 ({', '.join(AD_EXECUTION_TYPE_CODES)})",
        )
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    exec_date = req.execution_date or today_kst()
    row = (
        db.query(AdExecution)
        .filter(
            AdExecution.merchant_id == req.merchant_id,
            AdExecution.ad_type == req.ad_type,
            AdExecution.execution_date == exec_date,
        )
        .first()
    )
    if row:
        row.executed_count = req.executed_count
        if req.note is not None:
            row.note = req.note
        row.created_by = admin.id
    else:
        row = AdExecution(
            merchant_id=req.merchant_id,
            ad_type=req.ad_type,
            executed_count=req.executed_count,
            execution_date=exec_date,
            note=req.note,
            created_by=admin.id,
        )
        db.add(row)
    db.commit()
    db.refresh(row)

    summary = plan_service.build_summary(db, exec_date, [merchant])
    return {
        "ok": True,
        "id": row.id,
        "merchant_id": row.merchant_id,
        "ad_type": row.ad_type,
        "executed_count": row.executed_count,
        "execution_date": str(row.execution_date),
        "summary": summary[0] if summary else None,
    }


@router.get("/ad-executions/summary")
def ad_execution_summary(
    date: Optional[str] = Query(default=None, description="기준일 (YYYY-MM-DD, 기본 오늘)"),
    merchant_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """가맹점별 × 광고종류별 오늘집행 / 월누적 / 일목표 / 월목표 / 잔여건수."""
    target = _parse_date(date)
    q = db.query(Merchant).filter(Merchant.is_active == True)  # noqa: E712
    if merchant_id:
        q = q.filter(Merchant.id == merchant_id)
    merchants = q.order_by(Merchant.name.asc()).all()

    month_start, month_end = plan_service.month_bounds(target)
    return {
        "date": str(target),
        "month_start": str(month_start),
        "month_end": str(month_end),
        "ad_types": [{"code": c, "label": l} for c, l in AD_EXECUTION_TYPE_LABELS.items()],
        "merchants": plan_service.build_summary(db, target, merchants),
    }


@router.get("/ad-executions")
def list_ad_executions(
    date: Optional[str] = Query(default=None, description="특정 일자 (YYYY-MM-DD)"),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    merchant_id: Optional[int] = Query(default=None),
    ad_type: Optional[str] = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """집행 기록 목록 (날짜별 필터)."""
    q = db.query(AdExecution)
    if date:
        q = q.filter(AdExecution.execution_date == _parse_date(date))
    else:
        if date_from:
            q = q.filter(AdExecution.execution_date >= _parse_date(date_from, "date_from"))
        if date_to:
            q = q.filter(AdExecution.execution_date <= _parse_date(date_to, "date_to"))
    if merchant_id:
        q = q.filter(AdExecution.merchant_id == merchant_id)
    if ad_type:
        q = q.filter(AdExecution.ad_type == ad_type)

    rows = q.order_by(AdExecution.execution_date.desc(), AdExecution.id.desc()).limit(limit).all()
    merchant_names = {m.id: m.name for m in db.query(Merchant).all()}
    return [
        {
            "id": r.id,
            "merchant_id": r.merchant_id,
            "merchant_name": merchant_names.get(r.merchant_id, "-"),
            "ad_type": r.ad_type,
            "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(r.ad_type, r.ad_type),
            "executed_count": r.executed_count,
            "execution_date": str(r.execution_date),
            "note": r.note,
            "created_by": r.created_by,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]
