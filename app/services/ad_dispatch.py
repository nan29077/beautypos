"""광고 자동 집행 엔진.

플랜에 정해둔 일별 목표만큼 리워드팝에 주문을 넣고 결과를 기록한다.
자동 집행(스케줄러·관리자 수동 실행)과 매장 추가 주문이 같은 경로를 쓴다.

설계상 지키는 것
    호출 전에 행을 먼저 남긴다 — 주문은 성공했는데 커밋이 실패하면 다음 날 또 나간다.
    멱등키로 중복을 막는다 — 몇 번을 실행해도 하루 한 번만 나간다.
    재시도할 값이 있는 오류만 재시도한다 — 무한 재시도는 포인트를 태운다.
    드라이런에서는 실제로 보내지 않고 요청 내용만 기록한다.
"""
import json
import logging
from datetime import date as date_cls, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ad_dispatch import (
    AdDispatch,
    EXECUTED_STATUSES,
    MAX_RETRY,
    RETRY_BACKOFF_MINUTES,
    SKIP_ALREADY_DONE,
    SKIP_INTEGRATION_OFF,
    SKIP_NO_KEYWORD,
    SKIP_NO_PLAN,
    SKIP_NO_PRICE,
    SKIP_REASON_LABELS,
    SKIP_ZERO_TARGET,
    SOURCE_AUTO,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_DONE,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SENT,
    STATUS_SKIPPED,
    build_idempotency_key,
)
from app.models.merchant import Merchant
from app.models.plan import AdExecution, AD_EXECUTION_TYPE_LABELS
from app.services import ad_keyword, ad_pricing, plan_service, rewardpop
from app.utils.kst import fmt_kst, today_kst

logger = logging.getLogger(__name__)

# 1차 자동 집행 대상. 영수증 리뷰는 ADPAY 자체 기능이라 외부 호출이 필요 없고,
# 쇼츠는 리워드팝 상품에 없다. 플레이스 저장은 플레이스 방문에 통합됐다.
DISPATCHABLE_AD_TYPES = ["blog_review", "place_traffic"]

# 광고 종류별 단가 키
UNIT_PRICE_KEYS = {
    "blog_review": "blog_unit_price",
    "place_traffic": "place_traffic_unit_price",
}

# 한 번에 쓰는 키워드 수
KEYWORDS_PER_DISPATCH = 2


# ─── 대상 산출 · 사전 점검 ──────────────────────────────────

def _unit_price(pricing: dict, ad_type: str) -> int:
    return int(pricing.get(UNIT_PRICE_KEYS.get(ad_type, ""), 0) or 0)


def _already_executed(db: Session, merchant_id: int, ad_type: str, day: date_cls) -> bool:
    """오늘 이 가맹점·광고가 이미 (실패가 아닌 상태로) 나갔는지."""
    return db.query(AdDispatch).filter(
        AdDispatch.merchant_id == merchant_id,
        AdDispatch.ad_type == ad_type,
        AdDispatch.execution_date == day,
        AdDispatch.source == SOURCE_AUTO,
        AdDispatch.status.in_(list(EXECUTED_STATUSES) + [STATUS_DRY_RUN]),
    ).first() is not None


def build_plan(db: Session, target_date: Optional[date_cls] = None,
               merchant_id: Optional[int] = None) -> dict:
    """오늘 무엇이 나갈지 계산한다. 아무것도 전송하지 않는다.

    관리자 화면의 '미리보기'와 실제 실행이 같은 계산을 쓰도록 한 곳에 모았다.
    """
    target_date = target_date or today_kst()
    pricing = ad_pricing.get_ad_pricing(db)
    integration_on = rewardpop.is_enabled(db)
    settings = rewardpop.get_settings(db)

    q = db.query(Merchant).filter(Merchant.is_active == True)  # noqa: E712
    if merchant_id:
        q = q.filter(Merchant.id == merchant_id)
    merchants = q.order_by(Merchant.name.asc()).all()

    items = []
    for merchant in merchants:
        plan = plan_service.get_current_plan(db, merchant.id)
        for ad_type in DISPATCHABLE_AD_TYPES:
            entry = {
                "merchant_id": merchant.id,
                "merchant_name": merchant.name,
                "ad_type": ad_type,
                "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(ad_type, ad_type),
                "target": 0,
                "keywords": [],
                "unit_price": _unit_price(pricing, ad_type),
                "est_cost": 0,
                "action": "skip",
                "skip_reason": None,
            }

            if not plan:
                entry["skip_reason"] = SKIP_NO_PLAN
                items.append(entry)
                continue

            target = plan_service.daily_target_for_date(
                plan.target(ad_type, "monthly"), target_date
            )
            entry["target"] = target
            if target <= 0:
                entry["skip_reason"] = SKIP_ZERO_TARGET
                items.append(entry)
                continue

            if _already_executed(db, merchant.id, ad_type, target_date):
                entry["skip_reason"] = SKIP_ALREADY_DONE
                items.append(entry)
                continue

            keywords = ad_keyword.pick_for_date(
                ad_keyword.usable_keywords(db, merchant.id, ad_type),
                target_date, KEYWORDS_PER_DISPATCH,
            )
            entry["keywords"] = [k.keyword for k in keywords]
            if not keywords:
                entry["skip_reason"] = SKIP_NO_KEYWORD
                items.append(entry)
                continue

            if entry["unit_price"] <= 0:
                entry["skip_reason"] = SKIP_NO_PRICE
                items.append(entry)
                continue

            if not integration_on:
                entry["skip_reason"] = SKIP_INTEGRATION_OFF
                items.append(entry)
                continue

            entry["est_cost"] = entry["unit_price"] * target
            entry["action"] = "dispatch"
            items.append(entry)

    to_dispatch = [i for i in items if i["action"] == "dispatch"]
    return {
        "date": str(target_date),
        "dry_run": bool(settings.get("dry_run", True)),
        "integration_enabled": integration_on,
        "items": items,
        "dispatch_count": len(to_dispatch),
        "total_count": sum(i["target"] for i in to_dispatch),
        "est_total_cost": sum(i["est_cost"] for i in to_dispatch),
        "skip_reason_labels": SKIP_REASON_LABELS,
    }


# ─── 집행 ───────────────────────────────────────────────────

def _record_skip(db: Session, item: dict, target_date: date_cls, actor_id: Optional[int]) -> Optional[AdDispatch]:
    """관리자가 봐야 하는 보류만 행으로 남긴다.

    '오늘 목표 없음'과 '이미 집행됨'은 정상 상황이라 매일 행을 쌓으면 노이즈가 된다.
    """
    if item["skip_reason"] in (SKIP_ZERO_TARGET, SKIP_ALREADY_DONE):
        return None
    key = build_idempotency_key(SOURCE_AUTO, item["merchant_id"], item["ad_type"], target_date)
    row = db.query(AdDispatch).filter(AdDispatch.idempotency_key == key).first()
    if row is None:
        row = AdDispatch(
            merchant_id=item["merchant_id"], ad_type=item["ad_type"],
            execution_date=target_date, source=SOURCE_AUTO,
            idempotency_key=key, created_by=actor_id,
        )
        db.add(row)
    row.requested_count = item["target"]
    row.keyword = ", ".join(item["keywords"]) or None
    row.status = STATUS_SKIPPED
    row.skip_reason = item["skip_reason"]
    row.error_message = None
    db.commit()
    return row


def _build_request(item: dict, target_date: date_cls) -> dict:
    """리워드팝에 보낼 요청 본문.

    [명세 미확정] 필드 이름은 리워드팝 문서를 받으면 맞춰야 한다.
    지금은 무엇을 보내려 하는지 관리자가 눈으로 확인할 수 있게 하는 것이 목적이다.
    """
    return {
        "ad_type": item["ad_type"],
        "merchant_id": item["merchant_id"],
        "merchant_name": item["merchant_name"],
        "keywords": item["keywords"],
        "count": item["target"],
        "date": str(target_date),
    }


async def _dispatch_one(db: Session, item: dict, target_date: date_cls,
                        dry_run: bool, actor_id: Optional[int]) -> AdDispatch:
    key = build_idempotency_key(SOURCE_AUTO, item["merchant_id"], item["ad_type"], target_date)
    payload = _build_request(item, target_date)

    # 호출 전에 흔적을 먼저 남긴다. 주문은 나갔는데 커밋이 실패하면
    # 다음 실행 때 같은 주문이 또 나가기 때문이다.
    row = db.query(AdDispatch).filter(AdDispatch.idempotency_key == key).first()
    if row is None:
        row = AdDispatch(
            merchant_id=item["merchant_id"], ad_type=item["ad_type"],
            execution_date=target_date, source=SOURCE_AUTO,
            idempotency_key=key, created_by=actor_id,
        )
        db.add(row)
    row.requested_count = item["target"]
    row.keyword = ", ".join(item["keywords"]) or None
    row.request_json = json.dumps(payload, ensure_ascii=False)
    row.cost_amount = item["est_cost"]
    row.dry_run = dry_run
    row.skip_reason = None
    row.error_message = None
    row.status = STATUS_DRY_RUN if dry_run else STATUS_PENDING
    db.commit()

    if dry_run:
        # 실제로 보내지 않는다. 집행 실적(AdExecution)에도 반영하지 않는다.
        return row

    try:
        result = await rewardpop.create_order(db, item["ad_type"], payload)
    except rewardpop.SpecMissing as exc:
        _mark_failed(db, row, exc.message, retryable=False)
        return row
    except rewardpop.RewardpopError as exc:
        _mark_failed(db, row, exc.message, retryable=exc.retryable)
        return row

    row.status = STATUS_SENT
    row.external_order_id = str(result.get("external_order_id") or "") or None
    row.response_json = json.dumps(result.get("raw"), ensure_ascii=False, default=str)
    db.commit()
    sync_execution(db, row.merchant_id, row.ad_type, row.execution_date)
    return row


def _mark_failed(db: Session, row: AdDispatch, message: str, retryable: bool) -> None:
    row.status = STATUS_FAILED
    row.error_message = (message or "")[:500]
    if retryable and row.retry_count < MAX_RETRY:
        minutes = RETRY_BACKOFF_MINUTES[min(row.retry_count, len(RETRY_BACKOFF_MINUTES) - 1)]
        row.next_retry_at = datetime.utcnow() + timedelta(minutes=minutes)
    else:
        # 재시도해도 소용없는 오류는 다시 시도하지 않는다.
        row.next_retry_at = None
        row.retry_count = MAX_RETRY
    db.commit()


def sync_execution(db: Session, merchant_id: int, ad_type: str, day: date_cls) -> int:
    """그날 성공한 집행 건수를 합산해 AdExecution 에 반영한다.

    증가시키지 않고 매번 다시 계산해 덮어쓴다. 몇 번을 불러도 결과가 같아
    중복 반영이나 누락이 생기지 않는다.
    """
    rows = db.query(AdDispatch).filter(
        AdDispatch.merchant_id == merchant_id,
        AdDispatch.ad_type == ad_type,
        AdDispatch.execution_date == day,
        AdDispatch.status.in_(list(EXECUTED_STATUSES)),
        AdDispatch.dry_run == False,  # noqa: E712
    ).all()
    total = sum(int(r.requested_count or 0) for r in rows)

    execution = db.query(AdExecution).filter(
        AdExecution.merchant_id == merchant_id,
        AdExecution.ad_type == ad_type,
        AdExecution.execution_date == day,
    ).first()
    if total <= 0:
        return 0
    if execution is None:
        execution = AdExecution(
            merchant_id=merchant_id, ad_type=ad_type, execution_date=day,
            executed_count=total, note="리워드팝 자동 집행",
        )
        db.add(execution)
    else:
        execution.executed_count = total
    db.commit()
    return total


async def run(db: Session, target_date: Optional[date_cls] = None,
              merchant_id: Optional[int] = None, dry_run: Optional[bool] = None,
              actor_id: Optional[int] = None) -> dict:
    """집행을 실행한다. 스케줄러와 관리자 수동 실행이 함께 쓴다."""
    target_date = target_date or today_kst()
    plan = build_plan(db, target_date, merchant_id)
    if dry_run is None:
        dry_run = plan["dry_run"]

    dispatched, skipped, failed = [], [], []
    for item in plan["items"]:
        if item["action"] == "skip":
            row = _record_skip(db, item, target_date, actor_id)
            skipped.append({**item, "dispatch_id": row.id if row else None})
            continue
        row = await _dispatch_one(db, item, target_date, dry_run, actor_id)
        entry = {**item, "dispatch_id": row.id, "status": row.status,
                 "error": row.error_message}
        (failed if row.status == STATUS_FAILED else dispatched).append(entry)

    logger.info(
        "광고 집행 %s — 전송 %d, 실패 %d, 보류 %d (드라이런=%s)",
        target_date, len(dispatched), len(failed), len(skipped), dry_run,
    )
    return {
        "date": str(target_date),
        "dry_run": dry_run,
        "dispatched": dispatched,
        "failed": failed,
        "skipped": skipped,
        "dispatched_count": len(dispatched),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
    }


async def retry(db: Session, row: AdDispatch, actor_id: Optional[int] = None) -> AdDispatch:
    """실패한 집행을 다시 시도한다."""
    if row.status != STATUS_FAILED:
        return row
    item = {
        "merchant_id": row.merchant_id,
        "merchant_name": row.merchant.name if row.merchant else "",
        "ad_type": row.ad_type,
        "target": int(row.requested_count or 0),
        "keywords": [k.strip() for k in (row.keyword or "").split(",") if k.strip()],
        "est_cost": float(row.cost_amount or 0),
    }
    row.retry_count = int(row.retry_count or 0) + 1
    db.commit()
    return await _dispatch_one(db, item, row.execution_date, False, actor_id)


# ─── 상태 추적 ──────────────────────────────────────────────

async def refresh_statuses(db: Session, target_date: Optional[date_cls] = None,
                           limit: int = 50) -> dict:
    """접수된 주문의 최종 상태를 리워드팝에서 받아 채운다.

    웹훅이 있으면 그쪽이 낫지만, 명세를 확인하기 전까지는 조회로 맞춘다.
    상태를 읽지 못한 건은 손대지 않는다 — 모르는 값을 완료로 바꾸면
    집행 실적이 부풀려진다.
    """
    q = db.query(AdDispatch).filter(
        AdDispatch.status.in_([STATUS_SENT, STATUS_RUNNING]),
        AdDispatch.dry_run == False,  # noqa: E712
        AdDispatch.external_order_id.isnot(None),
    )
    if target_date:
        q = q.filter(AdDispatch.execution_date == target_date)
    rows = q.order_by(AdDispatch.id.asc()).limit(limit).all()

    updated, unchanged, errors = 0, 0, []
    for row in rows:
        try:
            result = await rewardpop.get_order_status(db, row.external_order_id)
        except rewardpop.SpecMissing as exc:
            # 경로가 없으면 나머지도 마찬가지다. 한 번만 알리고 그만둔다.
            return {"checked": 0, "updated": 0, "unchanged": 0,
                    "spec_missing": True, "detail": exc.message}
        except rewardpop.RewardpopError as exc:
            errors.append({"dispatch_id": row.id, "detail": exc.message})
            continue

        new_status = result.get("status")
        if not new_status or new_status == row.status:
            unchanged += 1
            continue

        row.status = STATUS_DONE if new_status == "done" else (
            STATUS_FAILED if new_status == "failed" else STATUS_RUNNING
        )
        if new_status == "failed":
            row.error_message = f"리워드팝 상태: {result.get('raw_status')}"[:500]
            # 접수까지 됐다가 실패한 건은 자동 재시도 대상으로 두지 않는다.
            row.retry_count = MAX_RETRY
        row.response_json = json.dumps(result.get("raw"), ensure_ascii=False, default=str)
        db.commit()
        sync_execution(db, row.merchant_id, row.ad_type, row.execution_date)
        updated += 1

    return {
        "checked": len(rows), "updated": updated, "unchanged": unchanged,
        "errors": errors,
    }


# ─── 집행·비용 집계 ─────────────────────────────────────────

def report(db: Session, start: date_cls, end: date_cls) -> dict:
    """기간별 집행 건수와 비용. 드라이런과 보류·실패는 제외한다."""
    rows = db.query(AdDispatch).filter(
        AdDispatch.execution_date >= start,
        AdDispatch.execution_date <= end,
        AdDispatch.status.in_(list(EXECUTED_STATUSES)),
        AdDispatch.dry_run == False,  # noqa: E712
    ).all()

    names = dict(db.query(Merchant.id, Merchant.name).all())
    by_merchant, by_type = {}, {}
    for row in rows:
        count = int(row.requested_count or 0)
        cost = float(row.cost_amount or 0)

        m = by_merchant.setdefault(row.merchant_id, {
            "merchant_id": row.merchant_id,
            "merchant_name": names.get(row.merchant_id, "-"),
            "count": 0, "cost": 0.0, "dispatches": 0,
        })
        m["count"] += count
        m["cost"] += cost
        m["dispatches"] += 1

        t = by_type.setdefault(row.ad_type, {
            "ad_type": row.ad_type,
            "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(row.ad_type, row.ad_type),
            "count": 0, "cost": 0.0, "dispatches": 0,
        })
        t["count"] += count
        t["cost"] += cost
        t["dispatches"] += 1

    # 실패·보류는 따로 세어 얼마나 새고 있는지 보여준다.
    problem_rows = db.query(AdDispatch).filter(
        AdDispatch.execution_date >= start,
        AdDispatch.execution_date <= end,
        AdDispatch.status.in_([STATUS_FAILED, STATUS_SKIPPED]),
    ).all()
    problems = {}
    for row in problem_rows:
        key = row.skip_reason or ("failed" if row.status == STATUS_FAILED else "unknown")
        label = SKIP_REASON_LABELS.get(key, "집행 실패" if key == "failed" else key)
        entry = problems.setdefault(key, {"reason": key, "label": label, "count": 0})
        entry["count"] += 1

    return {
        "start": str(start),
        "end": str(end),
        "total_count": sum(m["count"] for m in by_merchant.values()),
        "total_cost": sum(m["cost"] for m in by_merchant.values()),
        "total_dispatches": len(rows),
        "by_merchant": sorted(by_merchant.values(), key=lambda x: x["cost"], reverse=True),
        "by_ad_type": sorted(by_type.values(), key=lambda x: x["cost"], reverse=True),
        "problems": sorted(problems.values(), key=lambda x: x["count"], reverse=True),
    }


# ─── 직렬화 ─────────────────────────────────────────────────

def to_dict(row: AdDispatch, merchant_name: Optional[str] = None) -> dict:
    return {
        "id": row.id,
        "merchant_id": row.merchant_id,
        "merchant_name": merchant_name,
        "ad_type": row.ad_type,
        "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(row.ad_type, row.ad_type),
        "execution_date": str(row.execution_date),
        "source": row.source,
        "requested_count": row.requested_count,
        "keyword": row.keyword,
        "status": row.status,
        "status_label": row.status_label,
        "skip_reason": row.skip_reason,
        "skip_reason_label": row.skip_reason_label,
        "external_order_id": row.external_order_id,
        "error_message": row.error_message,
        "retry_count": row.retry_count,
        "retryable": row.retryable,
        "cost_amount": float(row.cost_amount or 0),
        "dry_run": bool(row.dry_run),
        "created_at": fmt_kst(row.created_at),
        "request_json": row.request_json,
    }
