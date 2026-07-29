"""
Admin API routes — accessible only by ADMIN role.
Covers: merchants CRUD, PG config, transactions, payout requests,
        ad orders management, metrics, fee policies, sales assignments, landing stats.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.pg import PGProvider, MerchantPGConfig, PGConfigStatus
from app.models.terminal import TerminalDevice
from app.models.transaction import Transaction
from app.models.settlement import (
    FeePolicy, MerchantSalesAssignment, Settlement, PayoutRequest, PayoutStatus,
)
from app.models.ad import (
    AdOrder, AdOrderStatus, AdMetric, AdOrderBlogDetail, AdOrderBlogImage,
    AdOrderPlaceTrafficDetail, AdPlaceProfile, AdCompetitor,
)
from app.models.staff import Staff
from app.models.affiliate_mall import AffiliateMall
from app.auth.dependencies import require_admin
from app.models.system_config import (
    SystemConfig, AD_ORDER_MGMT_ENABLED, AD_BLOG_ENABLED, AD_PLACE_TRAFFIC_ENABLED,
    COMMISSION_VISIBLE_TO_SALES, COMMISSION_VISIBLE_TO_OWNER, COMMISSION_VISIBLE_TO_DESIGNER,
)
from app.services import ai_service
from app.services.encryption import encrypt_value, decrypt_value, mask_value
from app.services.pg_service import get_pg_provider
from app.services.settlement_service import compute_distribution
from app.schemas.schemas import (
    MerchantCreate, MerchantUpdate, PGConfigCreate,
    AdMetricCreate, AdOrderStatusUpdate,
    FeePolicyUpdate, SalesAssignmentCreate, SalesAssignmentUpdate,
    CommissionVisibilityUpdate, StaffShareRateUpdate, AISettingsUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

AD_ORDER_TRANSITIONS = {
    "requested": ["reviewing", "rejected"],
    "reviewing": ["running", "rejected"],
    "running": ["done", "rejected"],
    "done": ["done"],
    "rejected": ["reviewing", "rejected"],
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
        raise HTTPException(status_code=400, detail="Owner user not found")
    m = Merchant(
        name=req.name, owner_user_id=req.owner_user_id,
        business_no=req.business_no, address=req.address, phone=req.phone,
    )
    db.add(m)
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
        results.append({
            "id": r.id, "requester_user_id": r.requester_user_id,
            "requester_name": user.name if user else None,
            "role": r.role, "amount": float(r.amount),
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
    pr.status = PayoutStatus.REJECTED
    pr.reviewed_at = datetime.utcnow()
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "rejected"}


# ─── Ad Orders Management ───────────────────────────────────

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
                    "links": detail.links_json,
                    "main_keywords": detail.main_keywords_json,
                    "hashtags": detail.hashtags_json,
                    "description": detail.description,
                }
        elif o.type.value == "place_traffic":
            detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == o.id).first()
            if detail:
                item["place_traffic_detail"] = {
                    "place_name_or_id": detail.place_name_or_id,
                    "search_keywords": detail.search_keywords_json,
                }
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
    pg_fee_rate = float(fp.pg_fee_rate) if fp else 0.035  # 적용율 = VAT 포함
    vat_inclusive_rate = pg_fee_rate                       # 호환 필드 (동일값)
    pg_fee_rate_excl_vat = round(pg_fee_rate / 1.1, 4)     # VAT 별도 환산 (표시용)

    # 영업관리자 배정 정보 조회
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == mid,
        MerchantSalesAssignment.is_active == True,
    ).first()
    sales_info = None
    if assign:
        sales_user = db.query(User).filter(User.id == assign.sales_manager_user_id).first()
        sales_info = {
            "assignment_id": assign.id,
            "sales_manager_id": assign.sales_manager_user_id,
            "sales_manager_name": sales_user.name if sales_user else None,
            "commission_rate": float(assign.commission_rate),
            "commission_rate_pct": round(float(assign.commission_rate) * 100, 2),
            "memo": assign.memo,
        }

    # 정산 시뮬레이션 (10,000원 기준)
    sample = 10000
    pg_fee_amount = round(sample * pg_fee_rate)
    commission_amount = round(sample * float(assign.commission_rate)) if assign else 0
    platform_amount = pg_fee_amount - commission_amount  # ADPAY 플랫폼 몫
    net_amount = sample - pg_fee_amount                  # 원장+디자이너 분배가능액

    return {
        "merchant_id": mid,
        "pg_fee_rate": pg_fee_rate,
        "pg_fee_rate_excl_vat": pg_fee_rate_excl_vat,
        "vat_inclusive_rate": vat_inclusive_rate,
        "has_fee_policy": fp is not None,
        "description": f"PG수수료 {pg_fee_rate*100:.2f}% (VAT 포함) · VAT 별도 {pg_fee_rate_excl_vat*100:.2f}%",
        "example": f"10,000원 결제 시 분배가능액 {int(net_amount)}원",
        # 영업관리자 연동 정보
        "has_sales_manager": assign is not None,
        "sales_info": sales_info,
        # 정산 시뮬레이션
        "simulation": {
            "sample_amount": sample,
            "pg_fee_amount": pg_fee_amount,
            "commission_amount": commission_amount,
            "platform_amount": platform_amount,
            "net_amount": int(net_amount),
            "owner_net": int(net_amount),
            "breakdown": f"결제 {sample:,}원 → PG수수료 {pg_fee_amount:,}원"
                        + (f" (영업 {commission_amount:,}원 + ADPAY {platform_amount:,}원)" if assign else f" (ADPAY {platform_amount:,}원, 영업 미배정)")
                        + f" → 분배가능액 {int(net_amount):,}원",
        },
    }


@router.post("/merchants/{mid}/fee-policy")
def set_fee_policy(mid: int, req: FeePolicyUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    # 입력값은 VAT 포함 PG 수수료율. pg_fee_rate 가 곧 적용율이며, vat_inclusive_rate 는 호환을 위해 동일 값으로 저장.
    rate = float(req.pg_fee_rate)
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    if fp:
        fp.pg_fee_rate = rate
        fp.vat_inclusive_rate = rate
    else:
        fp = FeePolicy(
            merchant_id=mid,
            pg_fee_rate=rate,
            vat_inclusive_rate=rate,
        )
        db.add(fp)
    db.commit()
    return {
        "ok": True,
        "pg_fee_rate": rate,
        "vat_inclusive_rate": rate,
        "example": f"10,000원 결제 시 PG수수료 {int(10000 * rate):,}원 / 분배가능액 {int(10000 * (1 - rate)):,}원"
    }


# ─── 통합 수수료 현황 (모든 가맹점 + 영업관리자 배정 한번에) ──

@router.get("/fee-policy-overview")
def fee_policy_overview(db: Session = Depends(get_db), _=Depends(require_admin)):
    """모든 가맹점의 수수료정책 + 영업관리자 배정 현황을 일괄 조회"""
    merchants = db.query(Merchant).filter(Merchant.is_active == True).all()
    results = []
    for m in merchants:
        fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == m.id).first()
        pg_fee_rate = float(fp.pg_fee_rate) if fp else 0.035  # 적용율 = VAT 포함
        vat_inclusive_rate = pg_fee_rate                       # 호환 필드
        pg_fee_rate_excl_vat = round(pg_fee_rate / 1.1, 4)     # VAT 별도 환산

        assign = db.query(MerchantSalesAssignment).filter(
            MerchantSalesAssignment.merchant_id == m.id,
            MerchantSalesAssignment.is_active == True,
        ).first()

        sales_name = None
        commission_rate = 0
        if assign:
            su = db.query(User).filter(User.id == assign.sales_manager_user_id).first()
            sales_name = su.name if su else None
            commission_rate = float(assign.commission_rate)

        sample = 10000
        pg_fee_amt = round(sample * pg_fee_rate)
        commission_amt = round(sample * commission_rate) if assign else 0
        platform_amt = pg_fee_amt - commission_amt
        net_amt = sample - pg_fee_amt

        results.append({
            "merchant_id": m.id,
            "merchant_name": m.name,
            "category": m.display_category if hasattr(m, 'display_category') else None,
            "pg_fee_rate": pg_fee_rate,
            "pg_fee_rate_pct": round(pg_fee_rate * 100, 2),
            "pg_fee_rate_excl_vat": pg_fee_rate_excl_vat,
            "pg_fee_rate_excl_vat_pct": round(pg_fee_rate_excl_vat * 100, 2),
            "vat_inclusive_rate": vat_inclusive_rate,
            "vat_inclusive_rate_pct": round(vat_inclusive_rate * 100, 2),
            "has_fee_policy": fp is not None,
            "has_sales_manager": assign is not None,
            "sales_manager_name": sales_name,
            "commission_rate": commission_rate,
            "commission_rate_pct": round(commission_rate * 100, 2),
            "assignment_id": assign.id if assign else None,
            # 시뮬레이션 (10,000원 기준)
            "sim_pg_fee": pg_fee_amt,
            "sim_commission": commission_amt,
            "sim_platform": platform_amt,
            "sim_net": int(net_amt),
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
    # 영업관리자 수익률 검증: 3.5% (VAT 별도) 이내여야 함
    if req.commission_rate < 0 or req.commission_rate > 0.035:
        raise HTTPException(
            status_code=400,
            detail=f"영업관리자 수익율은 0% ~ 3.5% (VAT 별도) 범위 내에서 설정해야 합니다. 입력값: {req.commission_rate*100:.2f}%"
        )
    # 영업관리자 역할 확인
    sales_user = db.query(User).filter(User.id == req.sales_manager_user_id).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=400, detail="영업관리자 역할의 사용자만 배정할 수 있습니다.")
    # 가맹점 확인
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다.")
    # 중복 확인
    existing = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == req.merchant_id,
        MerchantSalesAssignment.sales_manager_user_id == req.sales_manager_user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 해당 가맹점에 연결된 영업관리자입니다.")
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
        if req.commission_rate < 0 or req.commission_rate > 0.035:
            raise HTTPException(
                status_code=400,
                detail=f"영업관리자 수익율은 0% ~ 3.5% (VAT 별도) 범위 내에서 설정해야 합니다."
            )
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
    return [{"id": u.id, "name": u.name, "email": u.email} for u in users]


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
        })
    return results


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

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)
    yesterday_start = today_start - timedelta(days=1)

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

    # Weekly data
    weekly_data = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_sales = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.created_at >= day_start, Transaction.created_at < day_end).scalar()
        day_count = db.query(func.count(Transaction.id)).filter(
            Transaction.created_at >= day_start, Transaction.created_at < day_end).scalar()
        weekly_data.append({
            "date": day_start.strftime("%m/%d"),
            "day": ["월","화","수","목","금","토","일"][day_start.weekday()],
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
    """Calculate and create a settlement for a merchant and period.

    수수료 체계:
    - PG 수수료: 가맹점별 pg_fee_rate (기본 3.5%, 5% 등 가맹점별 설정 가능)
    - 영업 수수료: PG 수수료 내에서 배정된 비율 (예: 1%)
    - ADPAY 플랫폼 몫 = PG 수수료 - 영업 수수료
    - 분배가능액(net) = 결제액 - PG 수수료
    - 예시: 10,000원 결제, PG 5%, 영업 1%
        → PG수수료 500원 (영업 100원 + ADPAY 400원)
        → 분배가능액 9,500원 (원장 ↔ 디자이너 share_rate로 분배)
    """
    from datetime import datetime as dt
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    start = dt.fromisoformat(period_start)
    end = dt.fromisoformat(period_end)
    # 종료일을 날짜만 받으면 00:00 이 되어 마지막 하루가 통째로 빠진다. 그날 끝까지 포함시킨다.
    if end.hour == 0 and end.minute == 0 and end.second == 0:
        end = end + timedelta(days=1) - timedelta(microseconds=1)

    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant_id,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()

    gross = sum(float(t.amount) for t in txns)

    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == merchant_id).first()
    fee_rate = float(fp.pg_fee_rate) if fp else 0.035  # 기본 3.5%
    pg_fee = round(gross * fee_rate, 2)

    # 해제된 배정으로 커미션이 잡히지 않도록 활성 배정만 사용한다 (settlement_service 와 동일 기준).
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    commission = round(gross * float(assign.commission_rate), 2) if assign else 0
    platform_amount = round(pg_fee - commission, 2)  # ADPAY 플랫폼 몫

    net = round(gross - pg_fee, 2)

    settlement = Settlement(
        merchant_id=merchant_id,
        period_start=start, period_end=end,
        gross_amount=gross, pg_fee_amount=pg_fee,
        net_amount=net, commission_amount=commission,
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)
    return {
        "id": settlement.id, "gross_amount": gross,
        "merchant_name": merchant.name,
        "pg_fee_amount": pg_fee, "commission_amount": commission,
        "platform_amount": platform_amount,
        "net_amount": net, "transactions_count": len(txns),
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
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

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
                "links": detail.links_json,
                "main_keywords": detail.main_keywords_json,
                "hashtags": detail.hashtags_json,
                "description": detail.description,
                "images": [{"id": img.id, "file_path": img.file_path} for img in images],
            }
    elif order.type.value == "place_traffic":
        detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == order.id).first()
        if detail:
            item["place_traffic_detail"] = {
                "place_name_or_id": detail.place_name_or_id,
                "search_keywords": detail.search_keywords_json,
            }

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
        order.admin_memo = (order.admin_memo or "") + f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {admin_memo}"
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
    return {
        "ad_order_mgmt_enabled": master.is_enabled,
        "ad_blog_enabled": blog.is_enabled,
        "ad_place_traffic_enabled": place.is_enabled,
    }


@router.put("/ad-feature-flags")
def update_ad_feature_flags(
    ad_order_mgmt_enabled: Optional[bool] = Query(None),
    ad_blog_enabled: Optional[bool] = Query(None),
    ad_place_traffic_enabled: Optional[bool] = Query(None),
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
    db.commit()
    return {"ok": True, **result}


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
