"""광고 주문 단가 설정과 서버 기준 예산 계산."""
import json

from sqlalchemy.orm import Session

from app.models.ad import (
    SHORTS_CAMPAIGN_TYPE_USES,
    SHORTS_DISTRIBUTION_UNIT_PRICE,
    SHORTS_DURATION_TIER_PRICES,
)
from app.models.system_config import AD_PRICING_CONFIG, SystemConfig


DEFAULT_AD_PRICING = {
    "blog_unit_price": 0,
    "place_traffic_unit_price": 0,
    "shorts_distribution_unit_price": SHORTS_DISTRIBUTION_UNIT_PRICE,
    "shorts_duration_prices": dict(SHORTS_DURATION_TIER_PRICES),
}


def _non_negative_int(value, fallback: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def normalize_ad_pricing(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    duration_raw = raw.get("shorts_duration_prices")
    duration_raw = duration_raw if isinstance(duration_raw, dict) else {}
    return {
        "blog_unit_price": _non_negative_int(
            raw.get("blog_unit_price"), DEFAULT_AD_PRICING["blog_unit_price"]
        ),
        "place_traffic_unit_price": _non_negative_int(
            raw.get("place_traffic_unit_price"),
            DEFAULT_AD_PRICING["place_traffic_unit_price"],
        ),
        "shorts_distribution_unit_price": _non_negative_int(
            raw.get("shorts_distribution_unit_price"),
            DEFAULT_AD_PRICING["shorts_distribution_unit_price"],
        ),
        "shorts_duration_prices": {
            code: _non_negative_int(
                duration_raw.get(code), DEFAULT_AD_PRICING["shorts_duration_prices"][code]
            )
            for code in DEFAULT_AD_PRICING["shorts_duration_prices"]
        },
    }


def get_ad_pricing(db: Session) -> dict:
    cfg = db.query(SystemConfig).filter(
        SystemConfig.config_key == AD_PRICING_CONFIG
    ).first()
    if not cfg or not cfg.config_value:
        return normalize_ad_pricing(None)
    try:
        return normalize_ad_pricing(json.loads(cfg.config_value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return normalize_ad_pricing(None)


def save_ad_pricing(db: Session, pricing: dict) -> dict:
    normalized = normalize_ad_pricing(pricing)
    cfg = db.query(SystemConfig).filter(
        SystemConfig.config_key == AD_PRICING_CONFIG
    ).first()
    if not cfg:
        cfg = SystemConfig(
            config_key=AD_PRICING_CONFIG,
            description="광고 유형별 단가 설정",
            is_enabled=True,
        )
        db.add(cfg)
    cfg.config_value = json.dumps(normalized, ensure_ascii=False)
    cfg.is_enabled = True
    db.commit()
    return normalized


def shorts_estimate(
    pricing: dict,
    campaign_type: str,
    distribution_count: int,
    video_production_count: int,
    video_duration_tier: str | None,
) -> dict:
    uses = SHORTS_CAMPAIGN_TYPE_USES.get(
        campaign_type, {"distribution": True, "production": True}
    )
    dist_count = int(distribution_count or 0) if uses["distribution"] else 0
    prod_count = int(video_production_count or 0) if uses["production"] else 0
    dist_unit = pricing["shorts_distribution_unit_price"]
    prod_unit = pricing["shorts_duration_prices"].get(video_duration_tier or "", 0)
    distribution_cost = dist_count * dist_unit
    production_cost = prod_count * prod_unit
    return {
        "distribution_count": dist_count,
        "production_count": prod_count,
        "distribution_unit_price": dist_unit,
        "production_unit_price": prod_unit,
        "distribution_cost": distribution_cost,
        "production_cost": production_cost,
        "total_cost": distribution_cost + production_cost,
    }
