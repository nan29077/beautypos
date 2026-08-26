"""Admin routes — ad orders, ad metrics, analysis-targets, ad-feature-flags,
ad pricing, plans / merchant plan 배정, ad-executions 등 광고 관련 전부."""
import json
from datetime import datetime, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.utils.kst import today_kst, now_kst

from app.database import get_db
from app.models.user import User
from app.models.merchant import Merchant
from app.models.ad import (
    AdOrder, AdOrderStatus, AdMetric, AdOrderBlogDetail, AdOrderBlogImage,
    AdOrderPlaceTrafficDetail, AdOrderShortsDetail, AdPlaceProfile, AdCompetitor,
    SHORTS_DURATION_TIERS,
)
from app.auth.dependencies import require_admin
from app.models.system_config import (
    SystemConfig, AD_ORDER_MGMT_ENABLED, AD_BLOG_ENABLED, AD_PLACE_TRAFFIC_ENABLED,
    AD_SHORTS_ENABLED,
)
from app.services import ad_pricing
from app.services.settlement_service import get_effective_fee_rates
from app.schemas.schemas import (
    AdMetricCreate, AdOrderStatusUpdate, AdPricingUpdate,
    PlanUpdate, MerchantPlanAssign, AdExecutionCreate,
)
from app.models.plan import (
    Plan, MerchantPlan, AdExecution,
    AD_EXECUTION_TYPES, AD_EXECUTION_TYPE_CODES, AD_EXECUTION_TYPE_LABELS,
)
from app.services import plan_service
from app.api.admin._helpers import (
    _allowed_ad_order_statuses, _validate_ad_order_transition, _shorts_detail_payload,
    _validate_merchant_commission_fit, _sync_order_credit,
)
from app.services import ad_credit

# admin_memo 를 이어붙일 때 쓰는 줄바꿈
NEWLINE = chr(10)

router = APIRouter()


# ─── Ad Orders Management ───────────────────────────────────

@router.get("/ad/orders")
def list_ad_orders(db: Session = Depends(get_db), _=Depends(require_admin)):
    orders = db.query(AdOrder).order_by(AdOrder.created_at.desc()).all()

    # 주문마다 가맹점·작성자·상세를 따로 조회하면 주문 수만큼 쿼리가 늘어난다.
    # 필요한 것들을 종류별로 한 번씩만 읽어 사전으로 들고 간다.
    order_ids = [o.id for o in orders]
    merchant_names = dict(
        db.query(Merchant.id, Merchant.name)
        .filter(Merchant.id.in_({o.merchant_id for o in orders})).all()
    ) if orders else {}
    creator_names = dict(
        db.query(User.id, User.name)
        .filter(User.id.in_({o.created_by for o in orders if o.created_by})).all()
    ) if orders else {}
    blog_details = {
        d.order_id: d for d in db.query(AdOrderBlogDetail)
        .filter(AdOrderBlogDetail.order_id.in_(order_ids)).all()
    } if order_ids else {}
    place_details = {
        d.order_id: d for d in db.query(AdOrderPlaceTrafficDetail)
        .filter(AdOrderPlaceTrafficDetail.order_id.in_(order_ids)).all()
    } if order_ids else {}
    shorts_details = {
        d.order_id: d for d in db.query(AdOrderShortsDetail)
        .filter(AdOrderShortsDetail.order_id.in_(order_ids)).all()
    } if order_ids else {}

    results = []
    for o in orders:
        item = {
            "id": o.id, "merchant_id": o.merchant_id,
            "merchant_name": merchant_names.get(o.merchant_id),
            "type": o.type.value, "status": o.status.value,
            "created_by": o.created_by,
            "creator_name": creator_names.get(o.created_by),
            "admin_memo": o.admin_memo,
            "created_at": str(o.created_at),
            "allowed_statuses": _allowed_ad_order_statuses(o.status.value),
        }
        # attach details
        if o.type.value == "blog":
            detail = blog_details.get(o.id)
            if detail:
                try:
                    links_val = json.loads(detail.links_json) if detail.links_json else []
                    kw_val = json.loads(detail.main_keywords_json) if detail.main_keywords_json else []
                    tags_val = json.loads(detail.hashtags_json) if detail.hashtags_json else []
                except (json.JSONDecodeError, TypeError):
                    links_val, kw_val, tags_val = [], [], []
                item["blog_detail"] = {
                    "campaign_name": detail.campaign_name,
                    "address": detail.address,
                    "contact": detail.contact,
                    "links": links_val,
                    "main_keywords": kw_val,
                    "hashtags": tags_val,
                    "description": detail.description,
                    "order_count": detail.order_count,
                    "unit_price": str(detail.unit_price or 0),
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        elif o.type.value == "place_traffic":
            detail = place_details.get(o.id)
            if detail:
                try:
                    sk_val = json.loads(detail.search_keywords_json) if detail.search_keywords_json else []
                except (json.JSONDecodeError, TypeError):
                    sk_val = []
                item["place_traffic_detail"] = {
                    "place_name_or_id": detail.place_name_or_id,
                    "search_keywords": sk_val,
                    "order_count": detail.order_count,
                    "unit_price": str(detail.unit_price or 0),
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        elif o.type.value == "shorts":
            detail = shorts_details.get(o.id)
            if detail:
                item["shorts_detail"] = _shorts_detail_payload(detail)
        results.append(item)
    return results


def _change_ad_order_status(
    db: Session, oid: int, status: str, admin: User,
    admin_memo: Optional[str] = None, append_memo: bool = False,
) -> dict:
    """광고 주문 상태를 바꾼다. 상태 변경 엔드포인트가 공통으로 쓰는 한 곳이다.

    반려하면 차감했던 광고비 크레딧을 되돌리고, 반려를 풀면 다시 차감한다.
    크레딧 처리는 자체 커밋이므로, 뒤이은 상태 커밋이 실패하면 보상 함수로
    되돌려 잔액과 주문 상태가 어긋나지 않게 한다.
    """
    order = db.query(AdOrder).filter(AdOrder.id == oid).first()
    if not order:
        raise HTTPException(status_code=404, detail="광고주문을 찾을 수 없습니다")

    valid = [s.value for s in AdOrderStatus]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {valid}")
    _validate_ad_order_transition(order.status.value, status)

    old_status = order.status.value
    undo_credit = _sync_order_credit(db, order, status, admin.id)

    order.status = AdOrderStatus(status)
    order.assigned_admin_id = admin.id
    if admin_memo:
        if append_memo:
            stamp = now_kst().strftime("%Y-%m-%d %H:%M")
            order.admin_memo = (order.admin_memo or "") + NEWLINE + f"[{stamp} KST] {admin_memo}"
        else:
            order.admin_memo = admin_memo
    order.updated_at = datetime.utcnow()

    try:
        db.commit()
    except Exception:
        db.rollback()
        if undo_credit:
            undo_credit()
        raise

    return {
        "ok": True,
        "order_id": order.id,
        "old_status": old_status,
        "new_status": order.status.value,
        "status": order.status.value,
        "credit_refunded": bool(undo_credit) and status == "rejected",
        "credit_balance": ad_credit.balance_of(db, order.merchant_id),
    }


@router.post("/ad/orders/{oid}/status")
def update_ad_order_status(oid: int, req: AdOrderStatusUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """상태 변경 (구 엔드포인트). /ad/orders/{oid}/execute 와 같은 처리를 한다."""
    return _change_ad_order_status(db, oid, req.status, admin, req.admin_memo)


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
            try:
                links_val = json.loads(detail.links_json) if detail.links_json else []
                kw_val = json.loads(detail.main_keywords_json) if detail.main_keywords_json else []
                tags_val = json.loads(detail.hashtags_json) if detail.hashtags_json else []
            except (json.JSONDecodeError, TypeError):
                links_val, kw_val, tags_val = [], [], []
            item["blog_detail"] = {
                "campaign_name": detail.campaign_name,
                "address": detail.address,
                "contact": detail.contact,
                "links": links_val,
                "main_keywords": kw_val,
                "hashtags": tags_val,
                "description": detail.description,
                "images": [{"id": img.id, "file_path": img.file_path} for img in images],
                "order_count": detail.order_count,
                "unit_price": str(detail.unit_price or 0),
                "est_total_cost": str(detail.est_total_cost or 0),
            }
    elif order.type.value == "place_traffic":
        detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == order.id).first()
        if detail:
            try:
                sk_val = json.loads(detail.search_keywords_json) if detail.search_keywords_json else []
            except (json.JSONDecodeError, TypeError):
                sk_val = []
            item["place_traffic_detail"] = {
                "place_name_or_id": detail.place_name_or_id,
                "search_keywords": sk_val,
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
    """Execute/update an ad order with full status tracking.

    반려 시 크레딧 환급을 포함한 상태 변경 처리는 _change_ad_order_status() 한 곳에 있다.
    """
    result = _change_ad_order_status(db, oid, status, admin, admin_memo, append_memo=True)
    return {**result, "assigned_admin": admin.name}


# ═══════════════════════════════════════════════════════════
# 광고 기능 스위치 (블로그 배포 / 플레이스 방문 ON/OFF)
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
# 가맹점별 광고 수량 오버라이드
# ═══════════════════════════════════════════════════════════

from app.models.plan import MerchantAdOverride  # noqa: E402 (plan 임포트 보완)
from pydantic import BaseModel as _BaseModel


class _AdOverrideItem(_BaseModel):
    ad_type: str
    monthly_override: Optional[int] = None  # None = 오버라이드 제거 (플랜 기본값 복원)


class _AdOverrideRequest(_BaseModel):
    overrides: list[_AdOverrideItem]


@router.get("/merchants/{merchant_id}/ad-override")
def get_merchant_ad_override(merchant_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """가맹점의 플랜 기본값 + 개별 오버라이드 설정 조회."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    plan = plan_service.get_current_plan(db, merchant_id)
    override_rows = (
        db.query(MerchantAdOverride)
        .filter(MerchantAdOverride.merchant_id == merchant_id)
        .all()
    )
    override_by_type = {r.ad_type: r.monthly_override for r in override_rows}

    from app.models.plan import AD_EXECUTION_TYPES
    items = []
    for ad_type, label in AD_EXECUTION_TYPES:
        plan_monthly = plan.target(ad_type, "monthly") if plan else 0
        ov = override_by_type.get(ad_type)
        items.append({
            "ad_type": ad_type,
            "ad_type_label": label,
            "plan_monthly": plan_monthly,
            "monthly_override": ov,
            "effective_monthly": ov if ov is not None else plan_monthly,
        })

    return {
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "plan_name": plan.name if plan else "미배정",
        "plan_code": plan.code if plan else None,
        "items": items,
    }


@router.put("/merchants/{merchant_id}/ad-override")
def set_merchant_ad_override(
    merchant_id: int,
    req: _AdOverrideRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """가맹점별 광고 수량 오버라이드 저장.

    monthly_override=null 이면 해당 광고 타입 오버라이드를 제거하고 플랜 기본값을 사용한다.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    from app.models.plan import AD_EXECUTION_TYPE_CODES
    for item in req.overrides:
        if item.ad_type not in AD_EXECUTION_TYPE_CODES:
            raise HTTPException(status_code=400, detail=f"알 수 없는 광고 타입: {item.ad_type}")
        if item.monthly_override is not None and item.monthly_override < 0:
            raise HTTPException(status_code=400, detail="월 목표 건수는 0 이상이어야 합니다")
        plan_service.set_override(db, merchant_id, item.ad_type, item.monthly_override)

    db.commit()
    return {"ok": True, "merchant_id": merchant.id, "merchant_name": merchant.name}


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
        # 숨김 처리된 광고 종류는 목록에서 제외한다 (레이블 조회는 전체 목록을 쓴다)
        "ad_types": [{"code": c, "label": l} for c, l in AD_EXECUTION_TYPES],
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
