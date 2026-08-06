"""Shared helpers for the admin API route modules.

Split out of the original monolithic app/api/admin_routes.py so that every
sub-router (merchant, pg, settlement, ad, payout, misc) can reuse the same
ad-order transition / commission-rate validation / shorts-detail serialization
helpers without duplicating code.
"""
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.settlement import MerchantSalesAssignment
from app.models.ad import AdOrderShortsDetail, SHORTS_CAMPAIGN_TYPE_LABELS, SHORTS_DURATION_TIERS
from app.services.settlement_service import get_effective_fee_rates

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


_SHORTS_TIER_LABELS = {code: label for code, label, _ in SHORTS_DURATION_TIERS}


def _shorts_detail_payload(detail: AdOrderShortsDetail) -> dict:
    """쇼츠 주문 상세를 API 응답 형태로 직렬화한다."""
    def _load(raw, fallback):
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return fallback

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
