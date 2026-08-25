"""Owner advertising routes: place/competitor analysis, ad orders, executions.

Split out of the original app/api/owner_routes.py.
"""
import json
import logging
from datetime import datetime, timedelta, timezone, date as date_type
from urllib.parse import urlsplit, urlunsplit
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.merchant import Merchant
from app.models.ad import (
    AdOrder, AdOrderType, AdOrderStatus,
    AdOrderBlogDetail,
    AdOrderPlaceTrafficDetail, AdOrderShortsDetail,
    AdPlaceProfile, AdCompetitor, AdMetric, PlaceMetricSnapshot,
    SHORTS_CAMPAIGN_TYPES, SHORTS_CAMPAIGN_TYPE_CODES, SHORTS_CAMPAIGN_TYPE_LABELS,
    SHORTS_CAMPAIGN_TYPE_USES, SHORTS_DURATION_TIERS, SHORTS_DURATION_TIER_CODES,
    SHORTS_PLATFORMS, SHORTS_PLATFORM_CODES,
    SHORTS_MAX_COUNT,
)
from app.models.plan import AD_EXECUTION_TYPES
from app.models.system_config import (
    SystemConfig,
    AD_ORDER_MGMT_ENABLED,
    AD_BLOG_ENABLED,
    AD_PLACE_TRAFFIC_ENABLED,
    AD_SHORTS_ENABLED,
)
from app.utils.kst import today_kst, kst_day_start_utc
from app.services import naver_place
from app.services import ad_pricing, ai_service
from app.services import plan_service
from app.schemas.schemas import (
    AdBlogOrderCreate, AdPlaceTrafficOrderCreate, AdShortsOrderCreate,
    AdPlaceProfileCreate, AdCompetitorCreate,
)

from app.api.owner._helpers import require_owner, _get_owner_merchant, _date_range

router = APIRouter()

# 광고 분석에서 비교할 수 있는 경쟁업체 최대 개수
MAX_COMPETITORS = 5


def _normalize_place_url(value: str) -> str:
    """Normalize a public place URL while preserving its identifying query."""
    raw = (value or "").strip()
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="올바른 플레이스 URL을 입력해주세요") from exc
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(status_code=400, detail="http 또는 https로 시작하는 플레이스 URL을 입력해주세요")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def _ad_feature_enabled(db: Session, key: str) -> bool:
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    return bool(cfg and cfg.is_enabled)


def _require_ad_order_feature(db: Session, type_key: str) -> None:
    if not _ad_feature_enabled(db, AD_ORDER_MGMT_ENABLED):
        raise HTTPException(status_code=403, detail="광고 주문 기능이 현재 비활성화되어 있습니다")
    if not _ad_feature_enabled(db, type_key):
        raise HTTPException(status_code=403, detail="선택한 광고 상품이 현재 비활성화되어 있습니다")


def _require_plan_ad_quota(
    db: Session,
    merchant_id: int,
    order_type: AdOrderType,
    ad_type: str,
    requested_count: int = 1,
) -> None:
    """이번 달 광고 주문 건수가 배정 플랜의 월 한도를 넘지 않는지 검증한다.

    플랜이 배정되지 않았거나 해당 광고의 월 목표가 0이면 무제한으로 본다.
    """
    plan = plan_service.get_current_plan(db, merchant_id)
    if not plan:
        return
    limit = plan.target(ad_type, "monthly")
    if limit <= 0:
        return

    # KST 기준 이번 달 경계를 UTC naive datetime 으로 변환하여 DB 필터에 사용
    month_start, month_end = plan_service.month_bounds(today_kst())
    base_filters = (
        AdOrder.merchant_id == merchant_id,
        AdOrder.type == order_type,
        AdOrder.status != AdOrderStatus.REJECTED,  # 반려된 주문은 한도에서 제외
        AdOrder.created_at >= kst_day_start_utc(month_start),
        AdOrder.created_at < kst_day_start_utc(month_end + timedelta(days=1)),
    )
    if order_type == AdOrderType.BLOG:
        used = db.query(
            func.coalesce(func.sum(AdOrderBlogDetail.order_count), 0)
        ).join(AdOrder, AdOrder.id == AdOrderBlogDetail.order_id).filter(
            *base_filters
        ).scalar() or 0
    elif order_type == AdOrderType.PLACE_TRAFFIC:
        used = db.query(
            func.coalesce(func.sum(AdOrderPlaceTrafficDetail.order_count), 0)
        ).join(AdOrder, AdOrder.id == AdOrderPlaceTrafficDetail.order_id).filter(
            *base_filters
        ).scalar() or 0
    elif order_type == AdOrderType.SHORTS:
        used = db.query(
            func.coalesce(func.sum(AdOrderShortsDetail.distribution_count), 0)
        ).join(AdOrder, AdOrder.id == AdOrderShortsDetail.order_id).filter(
            *base_filters
        ).scalar() or 0
    else:
        used = db.query(func.count(AdOrder.id)).filter(*base_filters).scalar() or 0
    if int(used) + int(requested_count) > limit:
        raise HTTPException(status_code=403, detail="플랜 한도를 초과했습니다")


# ─── Ad Analysis ────────────────────────────────────────────

def _delta(today_value, yesterday_value):
    """어제 대비 증감. 한쪽이라도 값이 없으면 None."""
    if today_value is None or yesterday_value is None:
        return None
    return today_value - yesterday_value


def _daily_change(db: Session, merchant_id: int, place_url: str) -> dict:
    """오늘/어제 지표와 증감을 계산한다 (순위는 값이 작아질수록 상승)."""
    today = today_kst()
    yesterday = today - timedelta(days=1)
    rows = {
        m.date: m for m in db.query(AdMetric).filter(
            AdMetric.merchant_id == merchant_id,
            AdMetric.place_url == place_url,
            AdMetric.date.in_([today, yesterday]),
        ).all()
    }
    cur, prev = rows.get(today), rows.get(yesterday)
    return {
        "has_today": cur is not None,
        "today": {
            "date": str(today),
            "blog_review_count": cur.blog_review_count if cur else None,
            "visitor_review_count": cur.visitor_review_count if cur else None,
            "place_rank": cur.place_rank if cur else None,
        },
        "yesterday": {
            "date": str(yesterday),
            "blog_review_count": prev.blog_review_count if prev else None,
            "visitor_review_count": prev.visitor_review_count if prev else None,
            "place_rank": prev.place_rank if prev else None,
        },
        "blog_delta": _delta(
            cur.blog_review_count if cur else None,
            prev.blog_review_count if prev else None,
        ),
        "visitor_delta": _delta(
            cur.visitor_review_count if cur else None,
            prev.visitor_review_count if prev else None,
        ),
        # 순위는 숫자가 줄어야 상승이므로 (어제 - 오늘) 로 계산해 양수를 '상승'으로 맞춘다.
        "rank_delta": _delta(
            prev.place_rank if prev else None,
            cur.place_rank if cur else None,
        ),
    }


KST = timezone(timedelta(hours=9))


def _to_kst_str(dt: datetime) -> str:
    """naive UTC datetime 을 KST 문자열로 변환한다.

    DB에는 naive UTC(datetime.utcnow)로 저장되므로 그대로 내려주면
    화면에 9시간 이전 시각이 표시된다.
    """
    return dt.replace(tzinfo=timezone.utc).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def _collection_status(db: Session, merchant_id: int) -> dict:
    """마지막 자동 수집 시각과 오늘 수집 여부. 수집 시각은 KST로 반환."""
    today = today_kst()
    last = db.query(PlaceMetricSnapshot).filter(
        PlaceMetricSnapshot.merchant_id == merchant_id,
    ).order_by(PlaceMetricSnapshot.collected_at.desc()).first()
    today_count = db.query(func.count(AdMetric.id)).filter(
        AdMetric.merchant_id == merchant_id,
        AdMetric.date == today,
        AdMetric.source == "api",
    ).scalar() or 0
    return {
        "last_collected_at": _to_kst_str(last.collected_at) if last and last.collected_at else None,
        "last_keyword": last.keyword if last else None,
        "has_today_data": today_count > 0,
        "today_count": int(today_count),
    }


def _actual_place_name(db: Session, merchant_id: int, place_url: str, fallback: str | None = None) -> str:
    """플레이스 수집 결과에서 확인된 실제 매장명을 반환한다."""
    snapshot = db.query(PlaceMetricSnapshot).filter(
        PlaceMetricSnapshot.merchant_id == merchant_id,
        PlaceMetricSnapshot.place_url == place_url,
        PlaceMetricSnapshot.place_name.isnot(None),
    ).order_by(PlaceMetricSnapshot.collected_at.desc()).first()
    return (snapshot.place_name if snapshot and snapshot.place_name else None) or fallback or place_url


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
                (AdMetric.date >= start_date.date() if hasattr(start_date, 'date') else AdMetric.date >= start_date),
            ).order_by(AdMetric.date.desc()).all()
            my_metrics.append({
                "place_url": p.place_url, "nickname": p.nickname,
                "actual_name": _actual_place_name(db, merchant.id, p.place_url, p.nickname),
                "analysis_keyword": p.analysis_keyword,
                "daily_change": _daily_change(db, merchant.id, p.place_url),
                "data": [{
                    "date": str(m.date), "blog_review_count": m.blog_review_count,
                    "visitor_review_count": m.visitor_review_count,
                    "place_rank": m.place_rank, "search_keyword": m.search_keyword,
                } for m in metrics],
            })

    # Get metrics for competitors
    comp_metrics = []
    for c in competitors:
        metrics = db.query(AdMetric).filter(
            AdMetric.merchant_id == merchant.id,
            AdMetric.place_url == c.competitor_place_url,
            (AdMetric.date >= start_date.date() if hasattr(start_date, 'date') else AdMetric.date >= start_date),
        ).order_by(AdMetric.date.desc()).all()
        comp_metrics.append({
            "place_url": c.competitor_place_url, "memo": c.memo,
            "actual_name": _actual_place_name(db, merchant.id, c.competitor_place_url, c.memo),
            "daily_change": _daily_change(db, merchant.id, c.competitor_place_url),
            "data": [{
                "date": str(m.date), "blog_review_count": m.blog_review_count,
                "visitor_review_count": m.visitor_review_count,
                "place_rank": m.place_rank, "search_keyword": m.search_keyword,
            } for m in metrics],
        })

    return {
        "my_places": my_metrics,
        "competitors": comp_metrics,
        "profiles": [{
            "id": p.id, "place_url": p.place_url, "nickname": p.nickname,
            "actual_name": _actual_place_name(db, merchant.id, p.place_url, p.nickname) if p.place_url else p.nickname,
            "analysis_keyword": p.analysis_keyword,
        } for p in profiles],
        "competitor_list": [{
            "id": c.id, "place_url": c.competitor_place_url, "memo": c.memo,
            "actual_name": _actual_place_name(db, merchant.id, c.competitor_place_url, c.memo),
        } for c in competitors],
        "collection_status": _collection_status(db, merchant.id),
    }


# ─── Naver Place 자동 수집 ───────────────────────────────────

@router.post("/ad/fetch-now")
async def ad_fetch_now(
    force: bool = Query(False, description="오늘 수집분이 있어도 강제로 다시 조회"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """네이버 플레이스 리뷰 수 / 검색 순위를 즉시 수집한다 (병렬 조회)."""
    merchant = _get_owner_merchant(user, db)

    # 강제 재수집 연타는 네이버 요청 한도를 소진시키므로 쿨다운을 둔다.
    if force:
        last = db.query(PlaceMetricSnapshot).filter(
            PlaceMetricSnapshot.merchant_id == merchant.id,
        ).order_by(PlaceMetricSnapshot.collected_at.desc()).first()
        if last and last.collected_at:
            waited = (datetime.utcnow() - last.collected_at).total_seconds()
            cooldown = naver_place.FORCE_REFRESH_COOLDOWN_SECONDS
            if waited < cooldown:
                raise HTTPException(
                    status_code=429,
                    detail=f"방금 수집했습니다. {int(cooldown - waited)}초 후에 다시 시도해주세요.",
                )

    try:
        result = await naver_place.fetch_all_for_merchant(merchant.id, db=db, force=force)
    except Exception as exc:  # noqa: BLE001 — 수집 실패가 500 으로 전파되지 않게 한다
        raise HTTPException(status_code=502, detail=f"네이버 수집에 실패했습니다: {exc}") from exc

    result["collection_status"] = _collection_status(db, merchant.id)
    return result


@router.get("/ad/analysis/history")
def ad_analysis_history(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """일별 히스토리(블로그/방문자 리뷰 수, 순위)를 대상별로 반환한다."""
    merchant = _get_owner_merchant(user, db)
    today = today_kst()
    start = today - timedelta(days=days - 1)

    profiles = db.query(AdPlaceProfile).filter(AdPlaceProfile.merchant_id == merchant.id).all()
    competitors = db.query(AdCompetitor).filter(AdCompetitor.merchant_id == merchant.id).all()

    targets = [
        {"kind": "my", "label": _actual_place_name(db, merchant.id, p.place_url, p.nickname), "place_url": p.place_url}
        for p in profiles if p.place_url
    ] + [
        {"kind": "competitor", "label": _actual_place_name(db, merchant.id, c.competitor_place_url, c.memo),
         "place_url": c.competitor_place_url}
        for c in competitors
    ]

    dates = [str(start + timedelta(days=i)) for i in range((today - start).days + 1)]
    series = []
    for target in targets:
        rows = db.query(AdMetric).filter(
            AdMetric.merchant_id == merchant.id,
            AdMetric.place_url == target["place_url"],
            AdMetric.date >= start,
            AdMetric.date <= today,
        ).order_by(AdMetric.date.asc()).all()
        by_date = {str(r.date): r for r in rows}
        series.append({
            **target,
            "blog": [by_date[d].blog_review_count if d in by_date else None for d in dates],
            "visitor": [by_date[d].visitor_review_count if d in by_date else None for d in dates],
            "rank": [by_date[d].place_rank if d in by_date else None for d in dates],
            "daily_change": _daily_change(db, merchant.id, target["place_url"]),
        })

    return {
        "days": days,
        "dates": dates,
        "series": series,
        "collection_status": _collection_status(db, merchant.id),
    }


# ─── 한눈에 보기 (일별/주별 요약) ─────────────────────────────

RANK_OUT_OF_RANGE = naver_place.RANK_OUT_OF_RANGE


def _rank_text(rank) -> str:
    """순위 표기. 200위 밖 센티넬(201)은 문구로 바꾼다."""
    if rank is None:
        return "미확인"
    return "200위 밖" if rank >= RANK_OUT_OF_RANGE else f"{rank}위"


def _has_final_consonant(word: str) -> bool:
    """한글 마지막 글자에 받침이 있는지 확인한다 (조사 선택용)."""
    if not word:
        return False
    last = word.strip()[-1]
    if not ("가" <= last <= "힣"):
        # 숫자로 끝나면 읽는 소리 기준으로 판단 (0,1,3,6,7,8 은 받침 있음)
        return last in "0136780"
    return (ord(last) - 0xAC00) % 28 != 0


def _with_particle(word: str, consonant_form: str, vowel_form: str) -> str:
    """받침 유무에 따라 조사를 붙인다. 예: 와/과, 로/으로."""
    return word + (consonant_form if _has_final_consonant(word) else vowel_form)


def _latest_metric(db: Session, merchant_id: int, place_url: str, on_or_before=None):
    """지정일 이전(포함) 중 가장 최근 지표 1건을 가져온다. 데이터가 듬성해도 동작한다."""
    q = db.query(AdMetric).filter(
        AdMetric.merchant_id == merchant_id,
        AdMetric.place_url == place_url,
    )
    if on_or_before is not None:
        q = q.filter(AdMetric.date <= on_or_before)
    return q.order_by(AdMetric.date.desc()).first()


def _metric_snapshot(db: Session, merchant_id: int, place_url: str, period: str) -> dict:
    """현재 지표와 비교 기준(어제 / 지난주) 지표를 함께 계산한다."""
    current = _latest_metric(db, merchant_id, place_url)
    if current is None:
        return {"has_data": False}

    if period == "week":
        baseline = _latest_metric(db, merchant_id, place_url, current.date - timedelta(days=7))
    else:
        baseline = _latest_metric(db, merchant_id, place_url, current.date - timedelta(days=1))

    def _diff(now_value, before_value, reverse=False):
        if now_value is None or before_value is None:
            return None
        # 순위는 숫자가 작아질수록 상승이므로 부호를 뒤집어 양수를 '상승'으로 맞춘다.
        return (before_value - now_value) if reverse else (now_value - before_value)

    return {
        "has_data": True,
        "date": str(current.date),
        "blog": current.blog_review_count,
        "visitor": current.visitor_review_count,
        "rank": current.place_rank,
        "baseline_date": str(baseline.date) if baseline else None,
        "baseline_blog": baseline.blog_review_count if baseline else None,
        "baseline_visitor": baseline.visitor_review_count if baseline else None,
        "baseline_rank": baseline.place_rank if baseline else None,
        "blog_change": _diff(current.blog_review_count, baseline.blog_review_count if baseline else None),
        "visitor_change": _diff(current.visitor_review_count, baseline.visitor_review_count if baseline else None),
        "rank_change": _diff(current.place_rank, baseline.place_rank if baseline else None, reverse=True),
    }


def _competitor_insight(name: str, blog_gap, visitor_gap, mine: dict, period_label: str) -> str:
    """요청 예시와 같은 형태의 안내 문구를 만든다.

    두 지표의 우열 방향이 다르면 '~도' 가 아니라 '~지만 / ~는' 으로 이어 붙인다.
    """
    def _amount(gap):
        return f"{abs(gap)}건 " + ("많" if gap > 0 else "적")

    if blog_gap == 0 and visitor_gap == 0:
        sentence = f"블로그·방문자 리뷰 모두 {_with_particle(name, '과', '와')} 같습니다."
    elif blog_gap == 0:
        sentence = (f"블로그 리뷰는 {_with_particle(name, '과', '와')} 같고, "
                    f"방문자 리뷰는 {_amount(visitor_gap)}습니다.")
    elif visitor_gap == 0:
        sentence = (f"블로그 리뷰가 {name}보다 {_amount(blog_gap)}고, "
                    f"방문자 리뷰는 같습니다.")
    elif (blog_gap > 0) == (visitor_gap > 0):
        # 두 지표가 같은 방향 → '도' 로 연결
        sentence = (f"블로그 리뷰가 {name}보다 {_amount(blog_gap)}고, "
                    f"방문자 리뷰도 {_amount(visitor_gap)}습니다.")
    else:
        # 방향이 엇갈림 → '지만 / 는' 으로 연결
        sentence = (f"블로그 리뷰는 {name}보다 {_amount(blog_gap)}지만, "
                    f"방문자 리뷰는 {_amount(visitor_gap)}습니다.")

    # 순위 변화 문장
    rank_now, rank_before = mine.get("rank"), mine.get("baseline_rank")
    if rank_now is None:
        rank_sentence = ""
    elif rank_before is None:
        rank_sentence = f" 플레이스 순위는 {_rank_text(rank_now)}이며, {period_label} 데이터가 없어 변화는 비교할 수 없습니다."
    elif rank_before == rank_now:
        rank_sentence = f" 플레이스 순위는 {_with_particle(period_label, '과', '와')} 동일한 {_rank_text(rank_now)}입니다."
    else:
        moved = "상승" if rank_now < rank_before else "하락"
        rank_sentence = (
            f" 플레이스 순위는 {period_label} {_rank_text(rank_before)}에서 "
            f"오늘 {_with_particle(_rank_text(rank_now), '으로', '로')} {moved}했습니다."
        )
    return (sentence + rank_sentence).strip()


@router.get("/ad/analysis/overview")
def ad_analysis_overview(
    period: str = Query("day", pattern="^(day|week)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """한눈에 보기 — 우리 매장과 각 경쟁업체의 일별/주별 비교 요약."""
    merchant = _get_owner_merchant(user, db)
    period_label = "지난주" if period == "week" else "어제"

    profiles = db.query(AdPlaceProfile).filter(
        AdPlaceProfile.merchant_id == merchant.id,
    ).all()
    competitors = db.query(AdCompetitor).filter(
        AdCompetitor.merchant_id == merchant.id,
    ).all()

    # 우리 매장이 여러 곳이면 순위가 가장 높은 곳을 대표로 삼는다.
    my_candidates = []
    for profile in profiles:
        if not profile.place_url:
            continue
        snapshot = _metric_snapshot(db, merchant.id, profile.place_url, period)
        if snapshot["has_data"]:
            my_candidates.append({
                "name": _actual_place_name(db, merchant.id, profile.place_url, profile.nickname),
                "place_url": profile.place_url,
                **snapshot,
            })

    mine = min(
        my_candidates,
        key=lambda c: c["rank"] if c["rank"] is not None else 10 ** 6,
    ) if my_candidates else None

    comp_items = []
    for competitor in competitors:
        snapshot = _metric_snapshot(db, merchant.id, competitor.competitor_place_url, period)
        name = _actual_place_name(db, merchant.id, competitor.competitor_place_url, competitor.memo)
        if not snapshot["has_data"] or mine is None:
            comp_items.append({
                "id": competitor.id, "name": name,
                "place_url": competitor.competitor_place_url,
                "has_data": False,
                "insight": "아직 수집된 데이터가 없습니다. 상단 ‘지금 수집’을 눌러주세요.",
            })
            continue

        blog_gap = (mine["blog"] or 0) - (snapshot["blog"] or 0)
        visitor_gap = (mine["visitor"] or 0) - (snapshot["visitor"] or 0)
        rank_gap = (
            snapshot["rank"] - mine["rank"]
            if (mine["rank"] is not None and snapshot["rank"] is not None) else None
        )
        wins = sum([blog_gap > 0, visitor_gap > 0, bool(rank_gap and rank_gap > 0)])
        losses = sum([blog_gap < 0, visitor_gap < 0, bool(rank_gap and rank_gap < 0)])

        comp_items.append({
            "id": competitor.id, "name": name,
            "place_url": competitor.competitor_place_url,
            "has_data": True,
            "blog": snapshot["blog"], "visitor": snapshot["visitor"], "rank": snapshot["rank"],
            "blog_gap": blog_gap, "visitor_gap": visitor_gap, "rank_gap": rank_gap,
            "comp_blog_change": snapshot["blog_change"],
            "comp_visitor_change": snapshot["visitor_change"],
            "comp_rank_change": snapshot["rank_change"],
            "verdict": "ahead" if wins > losses else ("behind" if losses > wins else "even"),
            "wins": wins, "losses": losses,
            "insight": _competitor_insight(name, blog_gap, visitor_gap, mine, period_label),
        })

    # 종합 한 줄 요약
    ready = [c for c in comp_items if c["has_data"]]
    if mine is None:
        headline = "우리 매장 플레이스를 등록하고 지표를 수집하면 비교 요약을 제공합니다."
    elif not ready:
        headline = "경쟁업체를 등록하고 ‘지금 수집’을 실행하면 비교 요약을 제공합니다."
    else:
        ahead = sum(1 for c in ready if c["verdict"] == "ahead")
        behind = sum(1 for c in ready if c["verdict"] == "behind")
        rank_move = mine.get("rank_change")
        if mine.get("baseline_date") is None:
            move_text = f"플레이스 순위는 {_rank_text(mine.get('rank'))}이며 {period_label} 비교 데이터가 아직 없습니다"
        elif rank_move is None or rank_move == 0:
            move_text = f"플레이스 순위는 {_with_particle(_rank_text(mine.get('rank')), '으로', '로')} 큰 변동이 없습니다"
        else:
            move_text = (
                f"플레이스 순위는 {period_label} 대비 {abs(rank_move)}단계 "
                f"{'상승해 ' if rank_move > 0 else '하락해 '}{_rank_text(mine.get('rank'))}입니다"
            )
        headline = f"경쟁업체 {len(ready)}곳 중 {ahead}곳에 앞서고 {behind}곳에 뒤집니다. {move_text}."

    return {
        "period": period,
        "period_label": period_label,
        "my_place": mine,
        "competitors": comp_items,
        "headline": headline,
        "has_data": bool(mine and ready),
        "collection_status": _collection_status(db, merchant.id),
    }


@router.get("/ad/recommendation")
async def ad_recommendation(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """마케팅 추천 문구.

    최고관리자가 OpenAI API 키를 등록해 두면 AI 추천을 사용하고,
    없으면 화면의 기존 규칙 기반 문구를 그대로 쓰도록 mode 를 내려준다.
    """
    merchant = _get_owner_merchant(user, db)
    overview = ad_analysis_overview(period="day", db=db, user=user)

    if not ai_service.is_configured(db):
        return {"ai_enabled": False, "mode": "rule", "text": None}

    context = {
        "merchant_name": merchant.name,
        "my_place": overview.get("my_place"),
        "competitors": [c for c in overview.get("competitors", []) if c.get("has_data")],
    }
    try:
        text = await ai_service.generate_ad_recommendation(db, context)
    except Exception as exc:  # noqa: BLE001 — AI 실패 시 규칙 기반으로 되돌린다
        logging.getLogger(__name__).warning("AI 추천 생성 실패: %s", exc)
        text = None

    if not text:
        return {"ai_enabled": True, "mode": "rule", "text": None}
    return {"ai_enabled": True, "mode": "ai", "text": text}


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
            AdMetric.merchant_id == merchant.id,
            AdMetric.place_url == place_url,
            (AdMetric.date >= start_date.date() if hasattr(start_date, 'date') else AdMetric.date >= start_date),
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
            "analysis_keyword": p.analysis_keyword,
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

    all_targets = my_summaries + comp_summaries
    missing_targets = [
        {
            "type": "my" if target in my_summaries else "competitor",
            "name": target.get("nickname") or target.get("name") or target["place_url"],
            "place_url": target["place_url"],
        }
        for target in all_targets if not target["metrics"]
    ]
    stale_cutoff = (today_kst() - timedelta(days=14))
    stale_targets = [
        {
            "type": "my" if target in my_summaries else "competitor",
            "name": target.get("nickname") or target.get("name") or target["place_url"],
            "place_url": target["place_url"],
            "latest_date": target["metrics"]["latest_date"],
        }
        for target in all_targets
        if target["metrics"] and datetime.strptime(target["metrics"]["latest_date"], "%Y-%m-%d").date() < stale_cutoff
    ]
    primary_keyword = next((p.analysis_keyword for p in profiles if p.analysis_keyword), None)

    return {
        "my_places": my_summaries,
        "competitors": comp_summaries,
        "comparison": comparison,
        "head_to_head": _head_to_head(my_valid, comp_summaries),
        "max_competitors": MAX_COMPETITORS,
        "range": range,
        "analysis_keyword": primary_keyword,
        "data_status": {
            "target_count": len(all_targets),
            "ready_count": len(all_targets) - len(missing_targets),
            "missing_targets": missing_targets,
            "stale_targets": stale_targets,
            "needs_admin_action": bool(missing_targets or stale_targets),
        },
    }


def _head_to_head(my_valid: list, comp_summaries: list) -> list:
    """우리 매장 대표값과 각 경쟁업체를 1:1 로 비교한 결과를 만든다.

    종합(평균) 비교와 별개로, 경쟁업체별 우열을 개별 확인하기 위한 데이터.
    """
    if not my_valid:
        return []

    # 우리 매장이 여러 곳이면 가장 상위 순위인 곳을 대표로 삼는다.
    def _rank_key(summary):
        rank = summary["metrics"]["latest_rank"]
        return rank if rank is not None else 10 ** 6

    mine = min(my_valid, key=_rank_key)
    my_metrics = mine["metrics"]

    results = []
    for comp in comp_summaries:
        metrics = comp["metrics"]
        if not metrics:
            results.append({
                "competitor_id": comp["id"],
                "name": comp["name"],
                "place_url": comp["place_url"],
                "has_data": False,
            })
            continue

        blog_gap = (my_metrics["latest_blog_reviews"] or 0) - (metrics["latest_blog_reviews"] or 0)
        visitor_gap = (my_metrics["latest_visitor_reviews"] or 0) - (metrics["latest_visitor_reviews"] or 0)
        # 순위는 숫자가 작을수록 상위이므로 (상대 - 우리) 가 양수면 우리가 앞선다.
        my_rank, comp_rank = my_metrics["latest_rank"], metrics["latest_rank"]
        rank_gap = (comp_rank - my_rank) if (my_rank and comp_rank) else None

        wins = sum([blog_gap > 0, visitor_gap > 0, bool(rank_gap and rank_gap > 0)])
        losses = sum([blog_gap < 0, visitor_gap < 0, bool(rank_gap and rank_gap < 0)])

        results.append({
            "competitor_id": comp["id"],
            "name": comp["name"],
            "place_url": comp["place_url"],
            "has_data": True,
            "my_blog": my_metrics["latest_blog_reviews"],
            "comp_blog": metrics["latest_blog_reviews"],
            "blog_gap": blog_gap,
            "my_visitor": my_metrics["latest_visitor_reviews"],
            "comp_visitor": metrics["latest_visitor_reviews"],
            "visitor_gap": visitor_gap,
            "my_rank": my_rank,
            "comp_rank": comp_rank,
            "rank_gap": rank_gap,
            "wins": wins,
            "losses": losses,
            "verdict": "ahead" if wins > losses else ("behind" if losses > wins else "even"),
        })
    return results


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
    url = _normalize_place_url(req.place_url) if req.place_url else None
    if not url:
        raise HTTPException(status_code=400, detail="플레이스 URL은 필수입니다")
    duplicate = db.query(AdPlaceProfile).filter(
        AdPlaceProfile.merchant_id == merchant.id,
        AdPlaceProfile.place_url == url,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="이미 등록된 우리 매장 플레이스입니다")
    p = AdPlaceProfile(
        merchant_id=merchant.id,
        place_url=url,
        place_id=req.place_id,
        nickname=(req.nickname or "").strip() or None,
        analysis_keyword=(req.analysis_keyword or "").strip() or None,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


@router.post("/ad/competitors")
def create_competitor(req: AdCompetitorCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    url = _normalize_place_url(req.competitor_place_url)
    registered = db.query(func.count(AdCompetitor.id)).filter(
        AdCompetitor.merchant_id == merchant.id,
    ).scalar() or 0
    if registered >= MAX_COMPETITORS:
        raise HTTPException(
            status_code=400,
            detail=f"경쟁업체는 최대 {MAX_COMPETITORS}개까지 등록할 수 있습니다. "
                   f"기존 항목을 삭제한 뒤 추가해주세요.",
        )
    duplicate = db.query(AdCompetitor).filter(
        AdCompetitor.merchant_id == merchant.id,
        AdCompetitor.competitor_place_url == url,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="이미 등록된 경쟁업체입니다")
    if db.query(AdPlaceProfile).filter(
        AdPlaceProfile.merchant_id == merchant.id,
        AdPlaceProfile.place_url == url,
    ).first():
        raise HTTPException(status_code=400, detail="우리 매장 URL은 경쟁업체로 등록할 수 없습니다")
    c = AdCompetitor(
        merchant_id=merchant.id,
        competitor_place_url=url,
        memo=(req.memo or "").strip() or None,
    )
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
                    "order_count": detail.order_count,
                    "unit_price": str(detail.unit_price or 0),
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        elif o.type == AdOrderType.PLACE_TRAFFIC:
            detail = db.query(AdOrderPlaceTrafficDetail).filter(AdOrderPlaceTrafficDetail.order_id == o.id).first()
            if detail:
                item["place_traffic_detail"] = {
                    "place_name_or_id": detail.place_name_or_id,
                    "order_count": detail.order_count,
                    "unit_price": str(detail.unit_price or 0),
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        elif o.type == AdOrderType.SHORTS:
            detail = db.query(AdOrderShortsDetail).filter(AdOrderShortsDetail.order_id == o.id).first()
            if detail:
                item["shorts_detail"] = {
                    "campaign_name": detail.campaign_name,
                    "campaign_type": detail.campaign_type,
                    "campaign_type_label": SHORTS_CAMPAIGN_TYPE_LABELS.get(detail.campaign_type, detail.campaign_type),
                    "distribution_count": detail.distribution_count,
                    "video_production_count": detail.video_production_count,
                    "platforms": json.loads(detail.platforms_json) if detail.platforms_json else [],
                    "est_total_cost": str(detail.est_total_cost or 0),
                }
        results.append(item)
    return results


@router.get("/ad/pricing")
def get_owner_ad_pricing(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """원장 주문 화면에서 사용하는 현재 광고 단가."""
    _get_owner_merchant(user, db)
    return ad_pricing.get_ad_pricing(db)


@router.post("/ad/blog-orders")
def create_blog_order(req: AdBlogOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    _require_ad_order_feature(db, AD_BLOG_ENABLED)
    if req.order_count < 10:
        raise HTTPException(status_code=400, detail="블로그 배포 최소 주문 수량은 10건입니다")
    _require_plan_ad_quota(
        db, merchant.id, AdOrderType.BLOG, "blog_review", req.order_count
    )
    pricing = ad_pricing.get_ad_pricing(db)
    unit_price = pricing["blog_unit_price"]
    if unit_price == 0:
        raise HTTPException(status_code=400, detail="광고 단가가 0원으로 설정되어 있어 주문할 수 없습니다. 관리자에게 문의하세요")
    total_cost = unit_price * req.order_count
    keywords = [item.strip() for item in req.main_keywords if item.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="메인 키워드를 1개 이상 입력해주세요")
    links = [_normalize_place_url(item) for item in req.links]
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
        links_json=json.dumps(links),
        main_keywords_json=json.dumps(keywords),
        hashtags_json=json.dumps([item.strip().lstrip("#") for item in req.hashtags if item.strip()]),
        description=req.description,
        extra_image_link=req.extra_image_link,
        order_count=req.order_count,
        unit_price=unit_price,
        est_total_cost=total_cost,
    )
    db.add(detail)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "status": order.status.value,
        "estimate": {
            "order_count": req.order_count,
            "unit_price": unit_price,
            "total_cost": total_cost,
        },
    }


@router.post("/ad/place-traffic-orders")
def create_place_traffic_order(req: AdPlaceTrafficOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    _require_ad_order_feature(db, AD_PLACE_TRAFFIC_ENABLED)
    if req.order_count < 100:
        raise HTTPException(status_code=400, detail="플레이스 방문 최소 주문 수량은 100건입니다")
    _require_plan_ad_quota(
        db, merchant.id, AdOrderType.PLACE_TRAFFIC, "place_traffic", req.order_count
    )
    pricing = ad_pricing.get_ad_pricing(db)
    unit_price = pricing["place_traffic_unit_price"]
    if unit_price == 0:
        raise HTTPException(status_code=400, detail="광고 단가가 0원으로 설정되어 있어 주문할 수 없습니다. 관리자에게 문의하세요")
    total_cost = unit_price * req.order_count
    keywords = [item.strip() for item in req.search_keywords if item.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="검색 키워드를 1개 이상 입력해주세요")
    order = AdOrder(
        merchant_id=merchant.id, type=AdOrderType.PLACE_TRAFFIC,
        status=AdOrderStatus.REQUESTED, created_by=user.id,
    )
    db.add(order)
    db.flush()

    detail = AdOrderPlaceTrafficDetail(
        order_id=order.id,
        place_name_or_id=req.place_name_or_id,
        search_keywords_json=json.dumps(keywords),
        order_count=req.order_count,
        unit_price=unit_price,
        est_total_cost=total_cost,
    )
    db.add(detail)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "status": order.status.value,
        "estimate": {
            "order_count": req.order_count,
            "unit_price": unit_price,
            "total_cost": total_cost,
        },
    }


# ─── 쇼츠(숏폼) 배포 주문 ─────────────────────────────────────

@router.get("/ad/shorts-options")
def get_shorts_order_options(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """쇼츠 주문 폼이 사용하는 옵션 카탈로그와 단가를 반환한다.

    단가/옵션은 서버가 유일한 출처이므로 화면은 이 응답만 보고 폼을 그린다.
    """
    pricing = ad_pricing.get_ad_pricing(db)
    return {
        "campaign_types": [
            {"code": code, "label": label, "description": desc,
             "uses_distribution": uses_dist, "uses_production": uses_prod}
            for code, label, desc, uses_dist, uses_prod in SHORTS_CAMPAIGN_TYPES
        ],
        "duration_tiers": [
            {
                "code": code,
                "label": label,
                "unit_price": pricing["shorts_duration_prices"].get(code, price),
            }
            for code, label, price in SHORTS_DURATION_TIERS
        ],
        "platforms": [{"code": code, "label": label} for code, label in SHORTS_PLATFORMS],
        "distribution_unit_price": pricing["shorts_distribution_unit_price"],
        "max_count": SHORTS_MAX_COUNT,
    }


@router.post("/ad/shorts-orders")
def create_shorts_order(req: AdShortsOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """쇼츠 제작·배포 주문 접수. 예상 비용은 서버 단가로 재계산해 저장한다."""
    merchant = _get_owner_merchant(user, db)
    _require_ad_order_feature(db, AD_SHORTS_ENABLED)

    if req.campaign_type not in SHORTS_CAMPAIGN_TYPE_CODES:
        raise HTTPException(status_code=400, detail="캠페인 유형을 선택해주세요")
    uses = SHORTS_CAMPAIGN_TYPE_USES[req.campaign_type]

    # 배포 건수 · 플랫폼별 배분 검증
    platform_counts: dict = {}
    if uses["distribution"]:
        if req.distribution_count < 1:
            raise HTTPException(status_code=400, detail="배포 건수를 1건 이상 입력해주세요")
        for code, count in (req.platform_counts or {}).items():
            if code not in SHORTS_PLATFORM_CODES:
                raise HTTPException(status_code=400, detail="지원하지 않는 배포 플랫폼입니다")
            count = int(count or 0)
            if count < 0:
                raise HTTPException(status_code=400, detail="플랫폼별 배포 건수는 0건 이상이어야 합니다")
            if count > 0:
                platform_counts[code] = count
        if not platform_counts:
            raise HTTPException(status_code=400, detail="배포 플랫폼을 1개 이상 선택해주세요")
        if sum(platform_counts.values()) != req.distribution_count:
            raise HTTPException(status_code=400, detail="플랫폼별 배포 건수의 합이 전체 배포 건수와 일치해야 합니다")

    # 플랜 한도 검증: 쇼츠 사용량은 sum(distribution_count) 로 집계되므로,
    # 주문 건수(1)가 아니라 이번 주문의 총 배포 건수를 요청량으로 넘긴다.
    _require_plan_ad_quota(
        db, merchant.id, AdOrderType.SHORTS, "shorts",
        requested_count=int(req.distribution_count or 0) if uses["distribution"] else 0,
    )

    # 제작 건수 · 영상 길이 등급 검증
    duration_tier = req.video_duration_tier or None
    if uses["production"]:
        if req.video_production_count < 1:
            raise HTTPException(status_code=400, detail="영상제작 건수를 1건 이상 입력해주세요")
        if duration_tier not in SHORTS_DURATION_TIER_CODES:
            raise HTTPException(status_code=400, detail="영상 길이를 선택해주세요")
    else:
        duration_tier = None

    if req.campaign_type == "existing_video_distribution" and not (req.uploaded_video_url or "").strip():
        raise HTTPException(status_code=400, detail="기존 영상 기반 배포는 영상 URL이 필요합니다")

    if req.start_date and req.end_date and req.end_date < req.start_date:
        raise HTTPException(status_code=400, detail="종료 희망일은 시작 희망일 이후여야 합니다")

    est = ad_pricing.shorts_estimate(
        ad_pricing.get_ad_pricing(db),
        req.campaign_type,
        req.distribution_count,
        req.video_production_count,
        duration_tier,
    )
    if est["total_cost"] == 0 and (uses["distribution"] or uses["production"]):
        raise HTTPException(status_code=400, detail="광고 단가가 0원으로 설정되어 있어 주문할 수 없습니다. 관리자에게 문의하세요")

    categories = {
        code: (req.brief_categories or {}).get(code, "").strip()
        for code in SHORTS_PLATFORM_CODES
        if (req.brief_categories or {}).get(code, "").strip()
    }

    order = AdOrder(
        merchant_id=merchant.id, type=AdOrderType.SHORTS,
        status=AdOrderStatus.REQUESTED, created_by=user.id,
    )
    db.add(order)
    db.flush()

    detail = AdOrderShortsDetail(
        order_id=order.id,
        campaign_name=req.campaign_name.strip(),
        brand_name=(req.brand_name or "").strip() or merchant.name,
        industry=(req.industry or "").strip() or None,
        website_url=(req.website_url or "").strip() or None,
        description=req.description,
        campaign_type=req.campaign_type,
        distribution_count=est["distribution_count"],
        video_production_count=est["production_count"],
        video_duration_tier=duration_tier,
        platforms_json=json.dumps(list(platform_counts.keys())),
        platform_counts_json=json.dumps(platform_counts),
        start_date=req.start_date,
        end_date=req.end_date,
        target_keywords_json=json.dumps([item.strip() for item in req.target_keywords if item.strip()]),
        reference_links_json=json.dumps([item.strip() for item in req.reference_links if item.strip()]),
        uploaded_video_url=(req.uploaded_video_url or "").strip() or None,
        brief_product_name=(req.brief_product_name or "").strip() or None,
        brief_product_detail=req.brief_product_detail,
        brief_categories_json=json.dumps(categories),
        brief_tone=(req.brief_tone or "").strip() or None,
        brief_style=(req.brief_style or "").strip() or None,
        brief_target_audience=req.brief_target_audience,
        brief_key_messages=req.brief_key_messages,
        brief_avoid=req.brief_avoid,
        brief_hashtags_json=json.dumps([item.strip().lstrip("#") for item in req.brief_hashtags if item.strip()]),
        creator_min_followers=(req.creator_min_followers or "").strip() or None,
        creator_gender=(req.creator_gender or "").strip() or None,
        creator_age_group=(req.creator_age_group or "").strip() or None,
        creator_requirements=req.creator_requirements,
        brand_forbidden_words=req.brand_forbidden_words,
        brand_no_competitor=req.brand_no_competitor,
        brand_no_adult=req.brand_no_adult,
        brand_no_violence=req.brand_no_violence,
        brand_no_political=req.brand_no_political,
        track_utm=req.track_utm,
        track_promo_code=req.track_promo_code,
        kpi_goals_json=json.dumps([item.strip() for item in req.kpi_goals if item.strip()]),
        est_distribution_cost=est["distribution_cost"],
        est_production_cost=est["production_cost"],
        est_total_cost=est["total_cost"],
    )
    db.add(detail)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "status": order.status.value,
        "campaign_type_label": SHORTS_CAMPAIGN_TYPE_LABELS[req.campaign_type],
        "estimate": est,
    }


# ─── Ad Executions (원장 조회 전용) ──────────────────────────

@router.get("/ad/executions/summary")
def owner_ad_execution_summary(
    date: Optional[str] = Query(default=None, description="기준일 (YYYY-MM-DD, 기본 오늘)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """내 가맹점의 현재 플랜 + 광고 집행 현황 (어드민 집계를 본인 가맹점으로 제한).

    가맹점이 없는 계정에서도 404 대신 빈 응답을 반환한다.
    """
    merchant = db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()

    if date:
        try:
            target = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    else:
        target = today_kst()

    month_start, month_end = plan_service.month_bounds(target)

    if not merchant:
        return {
            "date": str(target),
            "month_start": str(month_start),
            "month_end": str(month_end),
            "ad_types": [],
            "merchant": None,
        }

    summary = plan_service.build_summary(db, target, [merchant])
    return {
        "date": str(target),
        "month_start": str(month_start),
        "month_end": str(month_end),
        "ad_types": [{"code": code, "label": label} for code, label in AD_EXECUTION_TYPES],
        "merchant": summary[0] if summary else None,
    }
