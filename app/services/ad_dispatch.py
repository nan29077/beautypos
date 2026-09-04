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
import random
from datetime import date as date_cls, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.ad_dispatch import (
    AdDispatch,
    EXECUTED_STATUSES,
    MAX_RETRY,
    RETRY_BACKOFF_MINUTES,
    SKIP_ALREADY_DONE,
    SKIP_INTEGRATION_OFF,
    SKIP_INVALID_CONFIG,
    SKIP_LOW_BALANCE,
    SKIP_NO_CONFIG,
    SKIP_NO_KEYWORD,
    SKIP_NO_EXTERNAL_API,
    SKIP_NO_PLACE_CODE,
    SKIP_NO_PLAN,
    SKIP_NO_PRICE,
    SKIP_REASON_LABELS,
    SKIP_ZERO_TARGET,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    SOURCE_ORDER,
    STATUS_DRY_RUN,
    STATUS_MANUAL_DONE,
    STATUS_MANUAL_QUEUED,
    STATUS_FAILED,
    STATUS_DONE,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SENT,
    STATUS_SKIPPED,
    STATUS_STOPPED,
    build_idempotency_key,
)
from app.models.merchant import Merchant
from app.models.merchant_ad_config import (
    AUTO_COUNT_OPTIONS,
    KEYWORD_MODE_CODES,
    MISSION_ACTIONS,
    MerchantAdConfig,
)
from app.models.plan import AdExecution, AD_EXECUTION_TYPE_LABELS
from app.services import ad_keyword, ad_pricing, plan_service, rewardpop
from app.utils.kst import fmt_kst, today_kst

logger = logging.getLogger(__name__)

# 1차 자동 집행 대상. 영수증 리뷰는 ADPAY 자체 기능이라 외부 호출이 필요 없고,
# 쇼츠는 리워드팝 상품에 없다. 플레이스 저장은 플레이스 방문에 통합됐다.
# RewardPop 공식 /ads API는 플레이스 미션 전용이다. 블로그 배포는 호환되는
# 신규 접수 API가 없고, 클로 플러스도 2026-09-01부터 접수가 중단됐다.
DISPATCHABLE_AD_TYPES = ["place_traffic"]

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
        AdDispatch.status.in_(list(EXECUTED_STATUSES)),
        AdDispatch.dry_run == False,  # noqa: E712
    ).first() is not None


def _get_ad_config(db: Session, merchant_id: int, ad_type: str) -> Optional[MerchantAdConfig]:
    """매장별 광고 집행 설정 조회. 없으면 None."""
    return db.query(MerchantAdConfig).filter(
        MerchantAdConfig.merchant_id == merchant_id,
        MerchantAdConfig.ad_type == ad_type,
    ).first()


def _config_error(config: MerchantAdConfig) -> Optional[str]:
    """공식 CreateAdDto 규격에 맞지 않는 설정이면 사람이 읽을 사유를 반환한다."""
    category = config.mission_category
    action = config.mission_action
    allowed_actions = {code for code, _ in MISSION_ACTIONS.get(category or "", [])}
    if not category or not action or action not in allowed_actions:
        return "missionCategory와 missionAction 조합이 올바르지 않습니다"
    if config.keyword_mode not in KEYWORD_MODE_CODES:
        return "keywordMode가 올바르지 않습니다"
    if config.keyword_mode == "AUTO" and config.auto_count not in AUTO_COUNT_OPTIONS:
        return f"AUTO 모드는 autoCount가 {AUTO_COUNT_OPTIONS} 중 하나여야 합니다"
    return None


def _point_cost(item: dict, by_mission: Optional[dict]) -> Optional[float]:
    """이 건이 리워드팝 포인트를 얼마나 먹는지. 공급 단가를 모르면 None."""
    if not by_mission:
        return None
    cfg = item.get("ad_config") or {}
    key = f"{cfg.get('mission_category')}:{cfg.get('mission_action')}"
    price = by_mission.get(key)
    if price is None:
        return None
    return float(price) * int(item["target"])


def _apply_balance_gate(items: list, budget: Optional[dict]) -> dict:
    """포인트가 모자라면 오늘 집행을 통째로 보류시킨다.

    부분 집행을 하지 않는 이유
        리워드팝에는 취소 API 가 없다. 한 번 나간 주문은 되돌릴 수 없으므로,
        "어디까지 나갔는지" 가 애매한 상태를 만들지 않는다. 관리자가 충전한 뒤
        다시 실행하면 멱등키 덕분에 같은 건이 두 번 나가지 않는다.
        어느 매장을 자르고 어느 매장을 살릴지 임의로 정하지 않는 뜻도 있다.

    비교 기준
        1순위 리워드팝 공급 단가(GET /accounts/prices) × 수량 — 실제 차감액
        2순위 ADPAY 판매 단가 × 수량 — 단가를 못 읽었을 때의 보수적 대용
             (판매가 >= 원가라 필요액을 과대평가한다. 덜 나가는 쪽이 안전하다.)
    """
    result = {
        "balance_checked": False,
        "balance": None,
        "required_points": None,
        "balance_basis": None,
        "balance_error": None,
        "low_balance": False,
    }
    if not budget:
        return result
    # 드라이런은 포인트를 쓰지 않는다. 숫자는 보여주되 집행을 막지는 않는다.
    enforce = budget.get("enforce", True)
    result["balance_error"] = budget.get("error")
    balance = budget.get("balance")
    result["balance"] = balance
    if balance is None:
        # 잔액을 못 읽었다고 집행을 막지는 않는다. 잔액 API 장애로 하루를
        # 통째로 날리는 편이 더 큰 손해다. 화면에 경고만 띄운다.
        return result

    targets = [i for i in items if i["action"] == "dispatch"]
    if not targets:
        result["balance_checked"] = True
        return result

    by_mission = budget.get("by_mission")
    costs = [_point_cost(i, by_mission) for i in targets]
    if all(c is not None for c in costs):
        required = sum(costs)
        basis = "supply_price"
    else:
        required = sum(float(i["est_cost"]) for i in targets)
        basis = "sale_price"

    result.update({
        "balance_checked": True,
        "required_points": required,
        "balance_basis": basis,
    })
    if required > float(balance):
        result["low_balance"] = True
        if not enforce:
            return result
        for item in targets:
            item["action"] = "skip"
            item["skip_reason"] = SKIP_LOW_BALANCE
            item["validation_error"] = (
                f"리워드팝 포인트 부족 — 필요 {int(required):,} / 잔액 {int(balance):,}"
            )
    return result


def build_plan(db: Session, target_date: Optional[date_cls] = None,
               merchant_id: Optional[int] = None,
               budget: Optional[dict] = None) -> dict:
    """오늘 무엇이 나갈지 계산한다. 아무것도 전송하지 않는다.

    관리자 화면의 '미리보기'와 실제 실행이 같은 계산을 쓰도록 한 곳에 모았다.
    budget 을 넘기면 리워드팝 포인트 잔액까지 반영해 보류 여부를 정한다
    (외부 호출이 필요해 여기서 직접 조회하지 않는다 — fetch_budget 참고).
    """
    target_date = target_date or today_kst()
    pricing = ad_pricing.get_ad_pricing(db)
    integration_on = rewardpop.is_enabled(db)
    # 화면 설정 + 환경변수(REWARDPOP_DRY_RUN) 를 합친 실효값
    dry_run_on = rewardpop.dry_run_enabled(db)

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
                "place_code": merchant.place_code,
                "ad_type": ad_type,
                "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(ad_type, ad_type),
                "target": 0,
                "keywords": [],
                "ad_config": None,
                "unit_price": _unit_price(pricing, ad_type),
                "est_cost": 0,
                "action": "skip",
                "skip_reason": None,
                "validation_error": None,
            }

            if not plan:
                entry["skip_reason"] = SKIP_NO_PLAN
                items.append(entry)
                continue

            effective_monthly = plan_service.effective_monthly_target(
                db, merchant.id, ad_type, plan
            )
            target = plan_service.daily_target_for_date(effective_monthly, target_date)
            entry["target"] = target
            if target <= 0:
                entry["skip_reason"] = SKIP_ZERO_TARGET
                items.append(entry)
                continue

            if _already_executed(db, merchant.id, ad_type, target_date):
                entry["skip_reason"] = SKIP_ALREADY_DONE
                items.append(entry)
                continue

            # 리워드팝 집행 설정 확인 (placeCode, missionCategory 등)
            ad_config = _get_ad_config(db, merchant.id, ad_type)
            if ad_config is None:
                entry["skip_reason"] = SKIP_NO_CONFIG
                items.append(entry)
                continue
            entry["ad_config"] = {
                "mission_category": ad_config.mission_category,
                "mission_action": ad_config.mission_action,
                "keyword_mode": ad_config.keyword_mode,
                "auto_count": ad_config.auto_count,
            }
            config_error = _config_error(ad_config)
            if config_error:
                entry["skip_reason"] = SKIP_INVALID_CONFIG
                entry["validation_error"] = config_error
                items.append(entry)
                continue

            # placeCode 확인
            if not merchant.place_code or not str(merchant.place_code).isdigit():
                entry["skip_reason"] = SKIP_NO_PLACE_CODE
                entry["validation_error"] = "placeCode는 숫자여야 합니다"
                items.append(entry)
                continue

            # MANUAL 모드일 때만 키워드 체크
            if ad_config.keyword_mode == "MANUAL":
                keywords = ad_keyword.pick_for_date(
                    ad_keyword.usable_keywords(db, merchant.id, ad_type),
                    target_date, KEYWORDS_PER_DISPATCH,
                )
                entry["keywords"] = [k.keyword for k in keywords]
                if not keywords:
                    entry["skip_reason"] = SKIP_NO_KEYWORD
                    items.append(entry)
                    continue
            # AUTO 모드는 리워드팝이 키워드를 자동 추출하므로 키워드 체크 불필요

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

            # VISIT 카테고리는 8가지 액션으로 균등 분배하여 각각 별도 주문으로 접수한다.
            # 날짜를 시드로 셔플해 매일 다른 순서로 집행된다.
            # SAVE 계열(PLACE_SAVE)과 그 외 카테고리는 기존 단일 주문 흐름을 유지한다.
            if ad_config.mission_category == "VISIT":
                _all_visit_actions = [
                    "WRITE_REVIEW", "FIND_PATH", "SPOT_CHECK",
                    "RANDOM_MISSION", "BUSINESS_HOURS", "INTRODUCTION",
                    "WALK_COUNT", "BUS_STATION",
                ]
                _rng = random.Random(str(target_date))
                _visit_actions = _all_visit_actions[:]
                _rng.shuffle(_visit_actions)
                _base, _remainder = divmod(target, len(_visit_actions))
                for _i, _action in enumerate(_visit_actions):
                    _action_target = _base + (_remainder if _i == 0 else 0)
                    if _action_target <= 0:
                        continue
                    _action_entry = {
                        **entry,
                        "target": _action_target,
                        "est_cost": entry["unit_price"] * _action_target,
                        "mission_action_override": _action,
                        # ad_config을 복사해 mission_action도 해당 액션으로 맞춘다.
                        # _point_cost()가 category:action 키로 단가를 조회하기 때문이다.
                        "ad_config": {**entry["ad_config"], "mission_action": _action},
                    }
                    items.append(_action_entry)
            else:
                items.append(entry)

    balance_info = _apply_balance_gate(items, budget)

    to_dispatch = [i for i in items if i["action"] == "dispatch"]
    return {
        "date": str(target_date),
        "dry_run": dry_run_on,
        "integration_enabled": integration_on,
        "items": items,
        "dispatch_count": len(to_dispatch),
        "total_count": sum(i["target"] for i in to_dispatch),
        "est_total_cost": sum(i["est_cost"] for i in to_dispatch),
        "skip_reason_labels": SKIP_REASON_LABELS,
        **balance_info,
    }


async def fetch_budget(db: Session) -> dict:
    """집행 전에 리워드팝 포인트 잔액과 공급 단가를 한 번씩 읽는다.

    실패해도 예외를 올리지 않는다. 잔액을 못 읽으면 게이트를 걸지 않고
    경고만 남긴다 (조회 장애로 하루 집행을 통째로 막지 않기 위해서다).
    """
    budget = {"balance": None, "by_mission": None, "error": None}
    if not await run_in_threadpool(rewardpop.is_enabled, db):
        return budget
    try:
        result = await rewardpop.get_balance(db)
        budget["balance"] = result.get("balance")
        if budget["balance"] is None:
            budget["error"] = "잔액 응답에서 포인트 값을 찾지 못했습니다."
    except rewardpop.RewardpopError as exc:
        budget["error"] = exc.message
        logger.warning("리워드팝 잔액 조회 실패 — 잔액 점검 없이 진행한다: %s", exc.message)
        return budget
    try:
        prices = await rewardpop.get_prices(db)
        budget["by_mission"] = prices.get("by_mission") or None
    except rewardpop.RewardpopError as exc:
        # 공급 단가를 못 읽으면 판매 단가로 대신 본다. 집행을 막지는 않는다.
        logger.info("리워드팝 공급 단가 조회 실패 — 판매 단가로 대신 본다: %s", exc.message)
    return budget


async def preview(db: Session, target_date: Optional[date_cls] = None,
                  merchant_id: Optional[int] = None) -> dict:
    """관리자 미리보기 — 잔액까지 반영한 집행 계획."""
    budget = await fetch_budget(db)
    budget["enforce"] = not await run_in_threadpool(rewardpop.dry_run_enabled, db)
    return await run_in_threadpool(build_plan, db, target_date, merchant_id, budget)


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
    row.error_message = item.get("validation_error")
    db.commit()
    return row


def _build_request(item: dict, target_date: date_cls) -> dict:
    """리워드팝 POST /ads 에 보낼 요청 본문.

    리워드팝 명세 필드:
        placeCode       - 네이버 플레이스 숫자 코드
        missionCategory - VISIT | SAVE
        missionAction   - WRITE_REVIEW | FIND_PATH | SPOT_CHECK 등 (VISIT 계열)
                          PLACE_SAVE (SAVE 계열)
        startDate       - 집행 시작일 (YYYY-MM-DD)
        workDays        - 집행 일수 (1일 집행이므로 항상 1)
        dailyQuantity   - 하루 집행 수량
        keywordMode     - MANUAL | AUTO
        keywords        - 파이프(|) 구분 문자열 (MANUAL 모드일 때만)
        autoCount       - AUTO 모드 키워드 수 (10 | 30 | 50)

    필드 이름은 이 함수 안에서만 바꾸면 된다.
    집행 행(request_json)에 그대로 남기므로 관리자가 무엇을 보냈는지 확인할 수 있다.
    """
    cfg = item.get("ad_config") or {}
    keyword_mode = cfg.get("keyword_mode", "MANUAL")
    # VISIT 분배 시 mission_action_override가 있으면 해당 액션으로 전송한다.
    # SAVE 계열 등 분배 없는 건은 ad_config의 mission_action을 그대로 쓴다.
    mission_action = item.get("mission_action_override") or cfg.get("mission_action")

    payload = {
        "placeCode": int(item["place_code"]),
        "missionCategory": cfg.get("mission_category"),
        "missionAction": mission_action,
        "startDate": str(target_date),
        "workDays": 1,
        "dailyQuantity": item["target"],
        "keywordMode": keyword_mode,
    }

    if keyword_mode == "MANUAL":
        # 파이프(|) 구분 문자열로 전달
        payload["keywords"] = "|".join(item.get("keywords", []))
    else:
        # AUTO 모드: 리워드팝이 자동 추출할 키워드 수
        auto_count = cfg.get("auto_count")
        if auto_count:
            payload["autoCount"] = auto_count

    return payload


def _prepare_row(db: Session, item: dict, target_date: date_cls,
                 dry_run: bool, actor_id: Optional[int], payload: dict) -> AdDispatch:
    """전송 전에 집행 행을 남긴다 (동기 DB 작업).

    호출 전에 흔적을 먼저 남긴다. 주문은 나갔는데 커밋이 실패하면
    다음 실행 때 같은 주문이 또 나가기 때문이다.
    """
    source = item.get("source", SOURCE_AUTO)
    order_id = item.get("ad_order_id")
    key = build_idempotency_key(
        source, item["merchant_id"], item["ad_type"], target_date, order_id=order_id,
    )
    # VISIT 분배 시 액션별로 다른 멱등키를 부여한다.
    # 형태: auto:{merchant_id}:{ad_type}:{date}:{action}
    action_override = item.get("mission_action_override")
    if action_override:
        key = f"{key}:{action_override}"
    row = db.query(AdDispatch).filter(AdDispatch.idempotency_key == key).first()
    if row is None:
        row = AdDispatch(
            merchant_id=item["merchant_id"], ad_type=item["ad_type"],
            execution_date=target_date, source=source, ad_order_id=order_id,
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
    row.next_retry_at = None
    row.status = STATUS_DRY_RUN if dry_run else STATUS_PENDING
    db.commit()
    return row


def _apply_counts(row: AdDispatch, counts: Optional[dict]) -> None:
    """리워드팝이 알려준 실제 수치를 행에 옮긴다. 없는 값은 건드리지 않는다.

    응답에 없던 항목을 0 으로 덮어쓰면 이미 채워둔 실적이 사라진다.
    """
    if not counts:
        return
    for key, attr in (("delivered_count", "delivered_count"),
                      ("reward_count", "reward_count"),
                      ("keyword_count", "keyword_count")):
        if key in counts:
            setattr(row, attr, int(counts[key]))


def _apply_counts_only(db: Session, row: AdDispatch, result: dict) -> None:
    """상태 문자열은 못 읽었지만 수량은 바뀐 경우 (동기 DB 작업)."""
    _apply_counts(row, result.get("counts"))
    db.commit()


def _mark_sent(db: Session, row: AdDispatch, result: dict) -> None:
    """전송 성공을 기록하고 집행 실적에 반영한다 (동기 DB 작업)."""
    result_status = result.get("status")
    if result_status == "done":
        row.status = STATUS_DONE
    elif result_status == "stopped":
        row.status = STATUS_STOPPED
    elif result_status == "failed":
        row.status = STATUS_FAILED
        row.retry_count = MAX_RETRY
        row.error_message = "리워드팝이 광고 등록을 오류 상태로 응답했습니다"
    elif result_status == "running":
        row.status = STATUS_RUNNING
    else:
        row.status = STATUS_SENT
    row.external_order_id = str(result.get("external_order_id") or "") or None
    row.external_status = (result.get("raw_status") or None)
    _apply_counts(row, result.get("counts"))
    row.response_json = json.dumps(result.get("raw"), ensure_ascii=False, default=str)
    row.next_retry_at = None
    db.commit()
    sync_execution(db, row.merchant_id, row.ad_type, row.execution_date)


def _store_keywords(db: Session, row: AdDispatch, found: dict) -> None:
    """AUTO 모드에서 회수한 키워드를 행에 남긴다 (동기 DB 작업)."""
    words = [w for w in (found.get("keywords") or []) if w]
    if not words:
        return
    row.keywords_json = json.dumps(words, ensure_ascii=False)
    row.keyword_count = int(found.get("keyword_count") or len(words))
    # keyword 컬럼은 200자라 요약만 담는다. 원본은 keywords_json 에 있다.
    row.keyword = ", ".join(words)[:200]
    db.commit()


async def _collect_auto_keywords(db: Session, row: AdDispatch, item: dict) -> None:
    """AUTO 모드로 나간 건의 실제 키워드를 리워드팝에서 받아 적는다.

    실패해도 집행 자체는 성공이다. 예외를 올리지 않고 로그만 남긴다.
    """
    cfg = item.get("ad_config") or {}
    if cfg.get("keyword_mode") != "AUTO" or not row.external_order_id:
        return
    try:
        found = await rewardpop.get_ad_keywords(db, row.external_order_id)
    except rewardpop.RewardpopError as exc:
        logger.info("AUTO 키워드 회수 실패 (dispatch=%s): %s", row.id, exc.message)
        return
    await run_in_threadpool(_store_keywords, db, row, found)


async def _dispatch_one(db: Session, item: dict, target_date: date_cls,
                        dry_run: bool, actor_id: Optional[int]) -> AdDispatch:
    payload = _build_request(item, target_date)

    # 동기 DB 작업은 스레드풀에 넘겨 이벤트 루프를 막지 않는다.
    row = await run_in_threadpool(
        _prepare_row, db, item, target_date, dry_run, actor_id, payload
    )

    if dry_run:
        # 실제로 보내지 않는다. 집행 실적(AdExecution)에도 반영하지 않는다.
        return row

    try:
        result = await rewardpop.create_order(db, item["ad_type"], payload)
    except rewardpop.SpecMissing as exc:
        await run_in_threadpool(_mark_failed, db, row, exc.message, False)
        return row
    except rewardpop.RewardpopError as exc:
        await run_in_threadpool(_mark_failed, db, row, exc.message, exc.retryable)
        return row

    await run_in_threadpool(_mark_sent, db, row, result)
    await _collect_auto_keywords(db, row, item)
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
        if execution is not None:
            execution.executed_count = 0
            db.commit()
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
    # 실제로 보낼 때만 포인트 잔액으로 막는다. 드라이런은 숫자만 보여준다.
    effective_dry_run = (
        dry_run if dry_run is not None
        else await run_in_threadpool(rewardpop.dry_run_enabled, db)
    )
    budget = await fetch_budget(db)
    budget["enforce"] = not effective_dry_run
    plan = await run_in_threadpool(build_plan, db, target_date, merchant_id, budget)
    if dry_run is None:
        dry_run = plan["dry_run"]

    dispatched, skipped, failed = [], [], []
    for item in plan["items"]:
        if item["action"] == "skip":
            row = await run_in_threadpool(_record_skip, db, item, target_date, actor_id)
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
        "balance": plan.get("balance"),
        "required_points": plan.get("required_points"),
        "balance_basis": plan.get("balance_basis"),
        "balance_error": plan.get("balance_error"),
        "low_balance": plan.get("low_balance", False),
    }


def _additional_order_item(db: Session, order) -> dict:
    """가맹점의 추가 플레이스 주문을 공식 CreateAdDto 입력으로 변환한다."""
    from app.models.ad import AdOrderPlaceTrafficDetail, AdOrderType

    order_type = order.type.value if hasattr(order.type, "value") else str(order.type)
    if order_type != AdOrderType.PLACE_TRAFFIC.value:
        raise rewardpop.RewardpopError(
            "리워드팝 공식 API가 지원하는 추가 주문은 플레이스 방문 광고입니다. "
            "블로그·쇼츠 주문은 리워드팝으로 전송하지 않습니다."
        )

    merchant = order.merchant or db.query(Merchant).filter(Merchant.id == order.merchant_id).first()
    if not merchant or not merchant.place_code or not str(merchant.place_code).isdigit():
        raise rewardpop.RewardpopError("가맹점의 숫자형 네이버 placeCode를 먼저 등록해주세요.")

    config = _get_ad_config(db, order.merchant_id, "place_traffic")
    if config is None:
        raise rewardpop.RewardpopError("가맹점의 리워드팝 플레이스 집행 설정을 먼저 등록해주세요.")
    category = config.mission_category
    action = config.mission_action
    allowed_actions = {code for code, _ in MISSION_ACTIONS.get(category or "", [])}
    if not category or not action or action not in allowed_actions:
        raise rewardpop.RewardpopError("missionCategory와 missionAction 조합을 확인해주세요.")

    detail = db.query(AdOrderPlaceTrafficDetail).filter(
        AdOrderPlaceTrafficDetail.order_id == order.id
    ).first()
    if detail is None:
        raise rewardpop.RewardpopError("플레이스 추가 주문 상세정보를 찾을 수 없습니다.")
    order_count = int(detail.order_count or 0)
    if order_count < 1:
        raise rewardpop.RewardpopError("추가 주문 수량은 1건 이상이어야 합니다.")
    try:
        keywords = [str(k).strip() for k in json.loads(detail.search_keywords_json or "[]") if str(k).strip()]
    except (TypeError, ValueError):
        keywords = []
    if not keywords:
        raise rewardpop.RewardpopError("추가 주문에 전송할 검색 키워드가 없습니다.")

    return {
        "merchant_id": order.merchant_id,
        "merchant_name": merchant.name,
        "place_code": merchant.place_code,
        "ad_type": "place_traffic",
        "source": SOURCE_ORDER,
        "ad_order_id": order.id,
        "target": order_count,
        "keywords": keywords[:200],
        "est_cost": float(detail.est_total_cost or 0),
        # 추가 주문 화면에서 키워드를 명시했으므로 MANUAL 규격으로 보낸다.
        "ad_config": {
            "mission_category": category,
            "mission_action": action,
            "keyword_mode": "MANUAL",
            "auto_count": None,
        },
    }


async def dispatch_ad_order(db: Session, order, actor_id: Optional[int] = None) -> AdDispatch:
    """관리자 승인된 추가 플레이스 주문을 리워드팝에 정확히 한 번 전송한다."""
    if not rewardpop.is_enabled(db):
        raise rewardpop.RewardpopError("리워드팝 API 키를 등록하고 연동을 활성화해주세요.")
    if rewardpop.dry_run_enabled(db):
        raise rewardpop.RewardpopError("추가 주문을 실제 집행하려면 드라이런을 해제해주세요.")

    existing = db.query(AdDispatch).filter(AdDispatch.ad_order_id == order.id).first()
    if existing is not None:
        if existing.status in EXECUTED_STATUSES or existing.status == STATUS_DONE:
            return existing
        raise rewardpop.RewardpopError(
            existing.error_message or "이 추가 주문에는 확인이 필요한 기존 전송 기록이 있습니다."
        )

    item = _additional_order_item(db, order)
    return await _dispatch_one(db, item, today_kst(), False, actor_id)


async def retry(db: Session, row: AdDispatch, actor_id: Optional[int] = None) -> AdDispatch:
    """실패한 집행을 다시 시도한다."""
    if row.status != STATUS_FAILED:
        return row
    merchant = row.merchant
    ad_config = _get_ad_config(db, row.merchant_id, row.ad_type)
    item = {
        "merchant_id": row.merchant_id,
        "merchant_name": merchant.name if merchant else "",
        "place_code": merchant.place_code if merchant else None,
        "ad_type": row.ad_type,
        "source": row.source,
        "ad_order_id": row.ad_order_id,
        "target": int(row.requested_count or 0),
        "keywords": [k.strip() for k in (row.keyword or "").split(",") if k.strip()],
        "est_cost": float(row.cost_amount or 0),
        "ad_config": {
            "mission_category": ad_config.mission_category if ad_config else None,
            "mission_action": ad_config.mission_action if ad_config else None,
            "keyword_mode": ad_config.keyword_mode if ad_config else "MANUAL",
            "auto_count": ad_config.auto_count if ad_config else None,
        },
    }
    await run_in_threadpool(_bump_retry, db, row)
    return await _dispatch_one(db, item, row.execution_date, False, actor_id)


def _bump_retry(db: Session, row: AdDispatch) -> None:
    row.retry_count = int(row.retry_count or 0) + 1
    db.commit()


# ─── 상태 추적 ──────────────────────────────────────────────

def _pending_status_rows(db: Session, target_date: Optional[date_cls], limit: int) -> list:
    """상태를 확인해야 하는 집행 행들 (동기 DB 조회)."""
    q = db.query(AdDispatch).filter(
        AdDispatch.status.in_([STATUS_SENT, STATUS_RUNNING]),
        AdDispatch.dry_run == False,  # noqa: E712
        AdDispatch.external_order_id.isnot(None),
    )
    if target_date:
        q = q.filter(AdDispatch.execution_date == target_date)
    return q.order_by(AdDispatch.id.asc()).limit(limit).all()


def _apply_external_status(db: Session, row: AdDispatch, new_status: str, result: dict) -> None:
    """리워드팝에서 읽어온 상태를 반영한다 (동기 DB 작업)."""
    row.status = (
        STATUS_DONE if new_status == "done" else
        STATUS_STOPPED if new_status == "stopped" else
        STATUS_FAILED if new_status == "failed" else
        STATUS_SENT if new_status == "sent" else
        STATUS_RUNNING
    )
    if new_status == "failed":
        row.error_message = f"리워드팝 상태: {result.get('raw_status')}"[:500]
        # 접수까지 됐다가 실패한 건은 자동 재시도 대상으로 두지 않는다.
        row.retry_count = MAX_RETRY
    if new_status == "stopped":
        # 실패가 아니다 — 이미 나간 만큼은 실적이다. 사유만 남긴다.
        row.error_message = f"리워드팝에서 중지됨 (상태: {result.get('raw_status')})"[:500]
    row.external_status = (result.get("raw_status") or row.external_status)
    _apply_counts(row, result.get("counts"))
    row.response_json = json.dumps(result.get("raw"), ensure_ascii=False, default=str)
    if row.ad_order_id and new_status == "done":
        from app.models.ad import AdOrder, AdOrderStatus
        order = db.query(AdOrder).filter(AdOrder.id == row.ad_order_id).first()
        if order is not None and order.status == AdOrderStatus.RUNNING:
            order.status = AdOrderStatus.DONE
            order.updated_at = datetime.utcnow()
    db.commit()
    sync_execution(db, row.merchant_id, row.ad_type, row.execution_date)


async def refresh_statuses(db: Session, target_date: Optional[date_cls] = None,
                           limit: int = 50) -> dict:
    """접수된 주문의 최종 상태를 리워드팝에서 받아 채운다.

    웹훅이 있으면 그쪽이 낫지만, 명세를 확인하기 전까지는 조회로 맞춘다.
    상태를 읽지 못한 건은 손대지 않는다 — 모르는 값을 완료로 바꾸면
    집행 실적이 부풀려진다.
    """
    rows = await run_in_threadpool(_pending_status_rows, db, target_date, limit)

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
        counts = result.get("counts") or {}
        # 상태가 그대로여도 실제 적립 수는 계속 늘어난다. 수량만 바뀌어도 기록한다.
        counts_changed = any(
            key in counts and int(counts[key]) != getattr(row, key)
            for key in ("delivered_count", "reward_count", "keyword_count")
        )
        if (not new_status or new_status == row.status) and not counts_changed:
            unchanged += 1
            continue
        if not new_status:
            await run_in_threadpool(_apply_counts_only, db, row, result)
            updated += 1
            continue

        await run_in_threadpool(_apply_external_status, db, row, new_status, result)
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
    stopped_count = 0
    for row in rows:
        count = int(row.requested_count or 0)
        # 리워드팝이 알려준 실측. 아직 안 받아온 건은 None 이라 요청 수와 구분된다.
        delivered = int(row.delivered_count) if row.delivered_count is not None else None
        rewarded = int(row.reward_count) if row.reward_count is not None else None
        cost = float(row.cost_amount or 0)
        if row.status == STATUS_STOPPED:
            stopped_count += 1

        m = by_merchant.setdefault(row.merchant_id, {
            "merchant_id": row.merchant_id,
            "merchant_name": names.get(row.merchant_id, "-"),
            "count": 0, "delivered": 0, "rewarded": 0, "measured": 0,
            "cost": 0.0, "dispatches": 0,
        })
        m["count"] += count
        m["cost"] += cost
        m["dispatches"] += 1

        t = by_type.setdefault(row.ad_type, {
            "ad_type": row.ad_type,
            "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(row.ad_type, row.ad_type),
            "count": 0, "delivered": 0, "rewarded": 0, "measured": 0,
            "cost": 0.0, "dispatches": 0,
        })
        t["count"] += count
        t["cost"] += cost
        t["dispatches"] += 1

        if delivered is not None or rewarded is not None:
            for bucket in (m, t):
                bucket["delivered"] += delivered or 0
                bucket["rewarded"] += rewarded or 0
                bucket["measured"] += 1

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
        # 실측 — 리워드팝에서 상태를 받아온 건만 합산된다.
        "total_delivered": sum(m["delivered"] for m in by_merchant.values()),
        "total_rewarded": sum(m["rewarded"] for m in by_merchant.values()),
        "measured_dispatches": sum(m["measured"] for m in by_merchant.values()),
        "stopped_dispatches": stopped_count,
        "total_cost": sum(m["cost"] for m in by_merchant.values()),
        "total_dispatches": len(rows),
        "by_merchant": sorted(by_merchant.values(), key=lambda x: x["cost"], reverse=True),
        "by_ad_type": sorted(by_type.values(), key=lambda x: x["cost"], reverse=True),
        "problems": sorted(problems.values(), key=lambda x: x["count"], reverse=True),
    }


# ─── 수동 접수 큐 (블로그 배포) ─────────────────────────────
#
# 리워드팝에는 클로 블로그 상품이 있고 GET /accounts/prices 로 단가도 조회되지만,
# 그걸 접수하는 엔드포인트가 공개 API 에 없다 (/ads/cloblog 는 404).
# 그래서 블로그는 "자동 전송"이 아니라 "자동 배분 + 사람이 접수"로 돌린다.
#
#   시스템이 하는 일 — 최고관리자가 넣은 월 목표를 일 단위로 쪼개 오늘 접수할 목록을 만든다.
#   사람이 하는 일   — 리워드팝 어드민에서 그만큼 접수하고 완료 버튼을 누른다.
#   그 다음은 자동   — 진도표(AdExecution)와 기간 집계에 플레이스와 똑같이 반영된다.
#
# 일/월 분배 계산은 plan_service 의 것을 그대로 쓴다. 플레이스 방문과 같은 함수라
# 나중에 리워드팝이 블로그 접수 API 를 열어주면 MANUAL_AD_TYPES 에서 빼고
# DISPATCHABLE_AD_TYPES 로 옮기기만 하면 된다 — 분배·집계 로직은 손댈 것이 없다.

MANUAL_AD_TYPES = ["blog_review"]

# 블로그 자동 월별 접수 대상. 매월 첫 평일에 한 번 접수하며, 일별 자동 집행(DISPATCHABLE)
# 경로와는 완전히 분리된 별도 스케줄러/함수를 쓴다.
# 플레이스 방문(place_traffic)과 달리 블로그는 월 단위 캠페인이라 daily_dispatch에
# 넣지 않는다. 리워드팝 POST /ads/cloblog 가 열린 시점에 추가했다.
BLOG_MONTHLY_AD_TYPES = ["blog_review"]

# ADPAY 광고 종류 → 리워드팝 매체 코드(GET /accounts/prices 의 mediaType).
# 플레이스가 아닌 매체는 missionCategory/missionAction 이 null 이라 이 코드로만 단가를 찾는다.
MEDIA_TYPE_BY_AD_TYPE = {
    "blog_review": "cloblog",
}


def supply_unit_price(by_media: Optional[dict], ad_type: str) -> Optional[dict]:
    """리워드팝 공급 단가(원가) 1건. 못 찾으면 None.

    한 매체에 단가가 여러 개 오면 **가장 낮은 값을 쓰지 않고 가장 높은 값**을 쓴다.
    필요 포인트를 적게 잡았다가 접수 도중 잔액이 모자라는 쪽이,
    넉넉히 잡아뒀다가 남는 쪽보다 훨씬 나쁘다.
    """
    media = MEDIA_TYPE_BY_AD_TYPE.get(ad_type)
    if not media or not by_media:
        return None
    values = by_media.get(media)
    if not values:
        return None
    return {"media_type": media, "price": float(max(values)), "ambiguous": len(values) > 1}

MANUAL_STATE_TODO = "todo"      # 오늘 접수해야 함
MANUAL_STATE_DONE = "done"      # 접수 완료 처리됨
MANUAL_STATE_SKIP = "skip"      # 오늘 할 일 없음 (목표 0 · 플랜 없음 · 단가 미설정)


def _manual_row(db: Session, merchant_id: int, ad_type: str, day: date_cls) -> Optional[AdDispatch]:
    key = build_idempotency_key(SOURCE_MANUAL, merchant_id, ad_type, day)
    return db.query(AdDispatch).filter(AdDispatch.idempotency_key == key).first()


def _manual_month_done(db: Session, merchant_id: int, ad_type: str, day: date_cls) -> int:
    """이번 달 들어 실제로 접수 완료된 누적 건수."""
    first, last = plan_service.month_bounds(day)
    rows = db.query(AdDispatch).filter(
        AdDispatch.merchant_id == merchant_id,
        AdDispatch.ad_type == ad_type,
        AdDispatch.execution_date >= first,
        AdDispatch.execution_date <= last,
        AdDispatch.status == STATUS_MANUAL_DONE,
        AdDispatch.dry_run == False,  # noqa: E712
    ).all()
    return sum(int(r.requested_count or 0) for r in rows)


def _manual_meta(row: Optional[AdDispatch]) -> dict:
    """완료 처리할 때 남긴 메모·처리자 정보. 스키마를 늘리지 않으려고 response_json 에 담는다."""
    if row is None or not row.response_json:
        return {}
    try:
        data = json.loads(row.response_json)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def build_manual_queue(db: Session, target_date: Optional[date_cls] = None,
                       merchant_id: Optional[int] = None,
                       by_media: Optional[dict] = None) -> dict:
    """오늘 사람이 접수해야 할 목록. 아무것도 전송하지 않고 행도 만들지 않는다.

    행을 미리 만들지 않는 이유 — 화면을 열어봤다는 이유만으로 원장에 행이 쌓이면
    "무엇이 실제로 처리됐는지"가 흐려진다. 행은 완료 처리할 때 처음 생긴다.

    by_media 를 넘기면 리워드팝 공급 단가(원가)와 필요 포인트까지 함께 계산한다.
    외부 호출이 필요해 여기서 직접 조회하지 않는다 — manual_queue 참고.
    """
    target_date = target_date or today_kst()
    pricing = ad_pricing.get_ad_pricing(db)

    q = db.query(Merchant).filter(Merchant.is_active == True)  # noqa: E712
    if merchant_id:
        q = q.filter(Merchant.id == merchant_id)
    merchants = q.order_by(Merchant.name.asc()).all()

    items = []
    for merchant in merchants:
        plan = plan_service.get_current_plan(db, merchant.id)
        for ad_type in MANUAL_AD_TYPES:
            unit_price = _unit_price(pricing, ad_type)
            supply = supply_unit_price(by_media, ad_type)
            monthly = plan_service.effective_monthly_target(db, merchant.id, ad_type, plan) if plan else 0
            target = plan_service.daily_target_for_date(monthly, target_date)
            row = _manual_row(db, merchant.id, ad_type, target_date)
            meta = _manual_meta(row)
            done = row is not None and row.status == STATUS_MANUAL_DONE

            entry = {
                "merchant_id": merchant.id,
                "merchant_name": merchant.name,
                "place_code": merchant.place_code,
                "ad_type": ad_type,
                "ad_type_label": AD_EXECUTION_TYPE_LABELS.get(ad_type, ad_type),
                "monthly_target": monthly,
                # 이 달 며칠까지 왔으면 몇 건이 쌓여 있어야 하는지 — 밀린 정도를 본다
                "month_expected": plan_service.expected_target_through_date(monthly, target_date),
                "month_done": _manual_month_done(db, merchant.id, ad_type, target_date),
                "daily_description": plan_service.daily_target_description(monthly, target_date),
                "target": target,
                "unit_price": unit_price,
                "est_cost": unit_price * target,
                # 리워드팝에서 실제로 빠지는 원가. 단가를 못 읽었으면 None
                "supply_unit_price": supply["price"] if supply else None,
                "supply_ambiguous": bool(supply and supply["ambiguous"]),
                "required_points": supply["price"] * target if supply else None,
                "margin": (unit_price - supply["price"]) * target if supply else None,
                "keywords": [],
                "state": MANUAL_STATE_TODO,
                "skip_reason": None,
                "dispatch_id": row.id if row else None,
                "done_count": int(row.requested_count or 0) if done else 0,
                "external_order_id": row.external_order_id if row else None,
                "note": meta.get("note"),
                "completed_at": meta.get("completed_at"),
            }

            if not plan:
                entry["state"] = MANUAL_STATE_SKIP
                entry["skip_reason"] = SKIP_NO_PLAN
            elif target <= 0:
                entry["state"] = MANUAL_STATE_SKIP
                entry["skip_reason"] = SKIP_ZERO_TARGET
            elif unit_price <= 0:
                entry["state"] = MANUAL_STATE_SKIP
                entry["skip_reason"] = SKIP_NO_PRICE
            elif done:
                entry["state"] = MANUAL_STATE_DONE
            else:
                # 승인된 키워드가 있으면 접수할 때 쓰라고 보여준다. 없어도 막지 않는다
                # — 자동 전송이 아니라 사람이 접수하는 것이라 판단은 관리자가 한다.
                picked = ad_keyword.pick_for_date(
                    ad_keyword.usable_keywords(db, merchant.id, ad_type),
                    target_date, KEYWORDS_PER_DISPATCH,
                )
                entry["keywords"] = [k.keyword for k in picked]

            items.append(entry)

    todo = [i for i in items if i["state"] == MANUAL_STATE_TODO]
    done_items = [i for i in items if i["state"] == MANUAL_STATE_DONE]
    priced = [i for i in todo if i["required_points"] is not None]
    return {
        "date": str(target_date),
        "ad_types": [
            {"code": c, "label": AD_EXECUTION_TYPE_LABELS.get(c, c)} for c in MANUAL_AD_TYPES
        ],
        "items": items,
        "todo_count": len(todo),
        "todo_total": sum(i["target"] for i in todo),
        "todo_cost": sum(i["est_cost"] for i in todo),
        "done_count": len(done_items),
        "done_total": sum(i["done_count"] for i in done_items),
        # 오늘 접수분이 리워드팝 포인트를 얼마나 먹는지. 단가를 못 읽은 건은 빠져 있다
        "required_points": sum(i["required_points"] for i in priced) if priced else None,
        "unpriced_count": len(todo) - len(priced),
        "supply_price_error": None,
        "skip_reason_labels": SKIP_REASON_LABELS,
        # 이 광고가 왜 자동이 아니라 수동인지 — 화면 안내 문구가 이 라벨을 쓴다
        "manual_reason": SKIP_NO_EXTERNAL_API,
        "manual_reason_label": SKIP_REASON_LABELS[SKIP_NO_EXTERNAL_API],
    }


async def manual_queue(db: Session, target_date: Optional[date_cls] = None,
                       merchant_id: Optional[int] = None) -> dict:
    """수동 접수 큐 + 리워드팝 공급 단가(원가).

    단가 조회가 실패해도 큐 자체는 그대로 보여준다 — 조회 장애로 그날 접수를
    통째로 막지 않는다. 대신 왜 원가가 비었는지 화면에 사유를 남긴다.
    """
    by_media, error = None, None
    if await run_in_threadpool(rewardpop.is_enabled, db):
        try:
            prices = await rewardpop.get_prices(db)
            by_media = prices.get("by_media") or None
        except rewardpop.RewardpopError as exc:
            error = exc.message
            logger.info("수동 접수 큐 — 공급 단가 조회 실패: %s", exc.message)
    else:
        error = "리워드팝 연동이 꺼져 있어 공급 단가를 읽지 못했습니다."

    queue = await run_in_threadpool(build_manual_queue, db, target_date, merchant_id, by_media)
    queue["supply_price_error"] = error
    return queue


def complete_manual(db: Session, merchant_id: int, ad_type: str, day: date_cls,
                    count: Optional[int] = None, external_order_id: Optional[str] = None,
                    note: Optional[str] = None, actor_id: Optional[int] = None) -> AdDispatch:
    """관리자가 외부에서 접수를 마쳤다고 표시한다.

    같은 가맹점·광고·날짜에 행이 하나뿐이므로(멱등키) 여러 번 눌러도
    실적이 중복으로 쌓이지 않는다. 수량을 고쳐 다시 누르면 그 값으로 덮어쓴다.
    """
    if ad_type not in MANUAL_AD_TYPES:
        raise ValueError(
            f"'{ad_type}' 은 수동 접수 대상이 아닙니다 (대상: {', '.join(MANUAL_AD_TYPES)})"
        )
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise ValueError("가맹점을 찾을 수 없습니다")

    plan = plan_service.get_current_plan(db, merchant_id)
    monthly = plan_service.effective_monthly_target(db, merchant_id, ad_type, plan) if plan else 0
    target = plan_service.daily_target_for_date(monthly, day)
    # 수량을 안 넘기면 그날 목표만큼 접수한 것으로 본다.
    final_count = int(count if count is not None else target)
    if final_count < 1:
        raise ValueError("접수 수량은 1건 이상이어야 합니다")

    unit_price = _unit_price(ad_pricing.get_ad_pricing(db), ad_type)

    key = build_idempotency_key(SOURCE_MANUAL, merchant_id, ad_type, day)
    row = db.query(AdDispatch).filter(AdDispatch.idempotency_key == key).first()
    if row is None:
        row = AdDispatch(
            merchant_id=merchant_id, ad_type=ad_type, execution_date=day,
            source=SOURCE_MANUAL, idempotency_key=key, created_by=actor_id,
        )
        db.add(row)

    row.requested_count = final_count
    # 사람이 직접 확인한 수라 요청 수 = 실제 나간 수로 본다.
    row.delivered_count = final_count
    row.status = STATUS_MANUAL_DONE
    row.skip_reason = None
    row.error_message = None
    row.next_retry_at = None
    row.dry_run = False
    row.external_order_id = (external_order_id or "").strip() or None
    row.cost_amount = unit_price * final_count
    row.response_json = json.dumps({
        "manual": True,
        "note": (note or "").strip() or None,
        "completed_by": actor_id,
        "completed_at": datetime.utcnow().isoformat(timespec="seconds"),
        "daily_target": target,
    }, ensure_ascii=False)
    db.commit()

    sync_execution(db, merchant_id, ad_type, day)
    logger.info("수동 접수 완료 — 가맹점 %s / %s / %s / %d건",
                merchant_id, ad_type, day, final_count)
    return row


def revert_manual(db: Session, row: AdDispatch, actor_id: Optional[int] = None) -> AdDispatch:
    """완료 처리를 되돌린다. 행은 남기고 실적에서만 뺀다.

    행을 지우지 않는 이유 — 누가 언제 잘못 눌렀는지가 원장에서 사라지면
    나중에 매장과 건수를 두고 다툴 때 확인할 방법이 없다.
    """
    if row.source != SOURCE_MANUAL:
        raise ValueError("수동 접수 건이 아닙니다")
    meta = _manual_meta(row)
    meta.update({
        "reverted": True,
        "reverted_by": actor_id,
        "reverted_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    row.status = STATUS_MANUAL_QUEUED
    row.delivered_count = None
    row.cost_amount = 0
    row.response_json = json.dumps(meta, ensure_ascii=False)
    db.commit()
    # 실적에서 빠지도록 다시 계산한다 (0 건이면 AdExecution 도 0 이 된다).
    sync_execution(db, row.merchant_id, row.ad_type, row.execution_date)
    return row


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
        "delivered_count": row.delivered_count,
        "reward_count": row.reward_count,
        "keyword_count": row.keyword_count,
        "external_status": row.external_status,
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
        "is_manual": bool(row.is_manual),
        "created_at": fmt_kst(row.created_at),
        "request_json": row.request_json,
    }


# ─── 블로그 월별 자동 접수 ────────────────────────────────────
#
# 리워드팝 POST /ads/cloblog 를 통해 매월 첫 평일에 한 번 접수한다.
# 일별 자동 집행(DISPATCHABLE_AD_TYPES / build_plan / run)과는 완전히 독립된 경로다.
# 블로그는 월 단위 캠페인이라 workDays 가 월말까지이고, dailyWorkload 는
# MerchantAdConfig.auto_count 에 저장한 값을 그대로 사용한다.
#
# startDate 결정 규칙 (리워드팝 제약):
#   - 주말(토·일) 접수 불가
#   - 16:00(KST) 이후 당일 시작 불가 → 다음 평일
#   - 금요일 16:00 이후 주말 시작일 지정 불가 → 월요일 이후

BLOG_POST_TYPES = ["INFO", "REVIEW", "FREE"]
BLOG_MIN_DAILY_WORKLOAD = 3


def _next_blog_weekday(ref_date: date_cls, now_kst_hour: int) -> date_cls:
    """리워드팝 제약에 따른 다음 유효한 블로그 시작일.

    ref_date: KST 기준 오늘(또는 임의 기준일)
    now_kst_hour: 현재 KST 시각(0~23). 16 이상이면 당일 불가.

    규칙:
      1. 주말이면 다음 월요일.
      2. 평일 16시 이상이면 다음 평일.
         (금요일 16시 이상 → 월요일)
      3. 평일 16시 미만이면 오늘.
    """
    d = ref_date
    # 주말이면 월요일로
    if d.weekday() >= 5:  # 5=토, 6=일
        days_ahead = 7 - d.weekday()
        d = d + timedelta(days=days_ahead)
        return d
    # 평일인데 16시 이상이면 다음 평일
    if now_kst_hour >= 16:
        d = d + timedelta(days=1)
        # 넘어간 날이 주말이면 월요일까지
        while d.weekday() >= 5:
            d = d + timedelta(days=1)
    return d


def _blog_work_days(start_date: date_cls) -> int:
    """start_date 부터 해당 월 말일까지의 달력 일수 (start_date 포함)."""
    from calendar import monthrange
    _, last_day = monthrange(start_date.year, start_date.month)
    month_end = date_cls(start_date.year, start_date.month, last_day)
    return max(1, (month_end - start_date).days + 1)


def _blog_config_error(config: "MerchantAdConfig") -> Optional[str]:
    """블로그 접수에 필요한 필드가 채워져 있는지 확인한다."""
    if not config.blog_place_url:
        return "blog_place_url(네이버 모바일 플레이스 URL)이 등록되지 않았습니다"
    if "m.place.naver.com" not in (config.blog_place_url or ""):
        return "blog_place_url은 m.place.naver.com으로 시작하는 모바일 URL이어야 합니다"
    if not config.blog_place_name:
        return "blog_place_name(업체명)이 등록되지 않았습니다"
    if not config.blog_main_keyword:
        return "blog_main_keyword(필수 키워드)가 등록되지 않았습니다"
    try:
        work_kw = json.loads(config.blog_work_keywords or "[]")
        if not isinstance(work_kw, list) or not work_kw:
            raise ValueError
    except (TypeError, ValueError):
        return "blog_work_keywords(작업 키워드)가 올바른 JSON 배열이 아닙니다"
    try:
        tags = json.loads(config.blog_tags or "[]")
        if not isinstance(tags, list) or len(tags) < 5:
            return "blog_tags(해시태그)는 5개 이상이어야 합니다"
    except (TypeError, ValueError):
        return "blog_tags(해시태그)가 올바른 JSON 배열이 아닙니다"
    if config.blog_post_type not in BLOG_POST_TYPES:
        return f"blog_post_type은 {BLOG_POST_TYPES} 중 하나여야 합니다"
    daily = int(config.auto_count or 0)
    if daily < BLOG_MIN_DAILY_WORKLOAD:
        return f"일 배포 건수(auto_count)는 최소 {BLOG_MIN_DAILY_WORKLOAD}건 이상이어야 합니다"
    return None


def _build_blog_request(config: "MerchantAdConfig", start_date: date_cls, work_days: int) -> dict:
    """리워드팝 POST /ads/cloblog 에 보낼 요청 본문을 조립한다."""
    work_kw = json.loads(config.blog_work_keywords or "[]")
    tags = json.loads(config.blog_tags or "[]")
    payload: dict = {
        "placeUrl": config.blog_place_url,
        "placeName": config.blog_place_name,
        "mainKeyword": config.blog_main_keyword,
        "workKeywords": [str(k).strip() for k in work_kw if str(k).strip()],
        "tags": [str(t).strip() for t in tags if str(t).strip()],
        "postType": config.blog_post_type,
        "startDate": str(start_date),
        "dailyWorkload": int(config.auto_count),
        "workDays": work_days,
    }
    if config.blog_store_address:
        payload["storeAddress"] = config.blog_store_address
    if config.blog_store_phone:
        payload["storePhone"] = config.blog_store_phone
    if config.blog_extra_link:
        payload["extraLink"] = config.blog_extra_link
    return payload


def _already_blog_dispatched_this_month(db: Session, merchant_id: int, month_start: date_cls) -> bool:
    """이번 달 블로그 자동 접수가 이미 성공(sent/running/done)으로 나갔는지."""
    from calendar import monthrange
    _, last_day = monthrange(month_start.year, month_start.month)
    month_end = date_cls(month_start.year, month_start.month, last_day)
    return db.query(AdDispatch).filter(
        AdDispatch.merchant_id == merchant_id,
        AdDispatch.ad_type == "blog_review",
        AdDispatch.execution_date >= month_start,
        AdDispatch.execution_date <= month_end,
        AdDispatch.source == SOURCE_AUTO,
        AdDispatch.status.in_(list(EXECUTED_STATUSES) + [STATUS_SENT, STATUS_RUNNING]),
        AdDispatch.dry_run == False,  # noqa: E712
    ).first() is not None


def build_blog_monthly_plan(
    db: Session,
    target_date: Optional[date_cls] = None,
    merchant_id: Optional[int] = None,
    now_kst_hour: int = 0,
) -> dict:
    """이번 달 블로그 자동 접수 계획을 계산한다. 아무것도 전송하지 않는다.

    target_date: 접수 기준일 (기본: 오늘 KST). 첫 평일 여부 확인에도 쓴다.
    now_kst_hour: 현재 KST 시각(0~23). startDate 계산에 반영된다.
    """
    target_date = target_date or today_kst()
    integration_on = rewardpop.is_enabled(db)
    dry_run_on = rewardpop.dry_run_enabled(db)

    from calendar import monthrange
    _, last_day = monthrange(target_date.year, target_date.month)
    month_start = date_cls(target_date.year, target_date.month, 1)
    # 이 달의 첫 평일 계산
    first_weekday = month_start
    while first_weekday.weekday() >= 5:
        first_weekday = first_weekday + timedelta(days=1)

    q = db.query(Merchant).filter(Merchant.is_active == True)  # noqa: E712
    if merchant_id:
        q = q.filter(Merchant.id == merchant_id)
    merchants = q.order_by(Merchant.name.asc()).all()

    items = []
    for merchant in merchants:
        entry = {
            "merchant_id": merchant.id,
            "merchant_name": merchant.name,
            "ad_type": "blog_review",
            "ad_type_label": AD_EXECUTION_TYPE_LABELS.get("blog_review", "블로그 리뷰"),
            "target_month": f"{target_date.year}-{target_date.month:02d}",
            "action": "skip",
            "skip_reason": None,
            "validation_error": None,
            "start_date": None,
            "work_days": None,
            "daily_workload": None,
            "request_payload": None,
        }

        config = _get_ad_config(db, merchant.id, "blog_review")
        if config is None:
            entry["skip_reason"] = SKIP_NO_CONFIG
            items.append(entry)
            continue

        config_error = _blog_config_error(config)
        if config_error:
            entry["skip_reason"] = SKIP_INVALID_CONFIG
            entry["validation_error"] = config_error
            items.append(entry)
            continue

        if _already_blog_dispatched_this_month(db, merchant.id, month_start):
            entry["skip_reason"] = SKIP_ALREADY_DONE
            items.append(entry)
            continue

        if not integration_on:
            entry["skip_reason"] = SKIP_INTEGRATION_OFF
            items.append(entry)
            continue

        start_date = _next_blog_weekday(target_date, now_kst_hour)
        work_days = _blog_work_days(start_date)
        payload = _build_blog_request(config, start_date, work_days)

        entry["action"] = "dispatch"
        entry["start_date"] = str(start_date)
        entry["work_days"] = work_days
        entry["daily_workload"] = int(config.auto_count)
        entry["request_payload"] = payload
        items.append(entry)

    to_dispatch = [i for i in items if i["action"] == "dispatch"]
    return {
        "target_month": f"{target_date.year}-{target_date.month:02d}",
        "first_weekday_of_month": str(first_weekday),
        "dry_run": dry_run_on,
        "integration_enabled": integration_on,
        "items": items,
        "dispatch_count": len(to_dispatch),
        "skip_reason_labels": SKIP_REASON_LABELS,
    }


async def dispatch_blog_monthly(
    db: Session,
    target_date: Optional[date_cls] = None,
    merchant_id: Optional[int] = None,
    dry_run: Optional[bool] = None,
    actor_id: Optional[int] = None,
    now_kst_hour: int = 0,
) -> dict:
    """블로그 광고를 이번 달 단위로 리워드팝에 접수한다.

    스케줄러가 매월 첫 평일에 호출하며, 관리자 수동 실행도 같은 경로를 쓴다.
    멱등키로 중복 접수를 막는다 — 이미 이번 달 접수가 나간 가맹점은 건너뛴다.
    """
    target_date = target_date or today_kst()
    effective_dry_run = (
        dry_run if dry_run is not None
        else await run_in_threadpool(rewardpop.dry_run_enabled, db)
    )

    plan = await run_in_threadpool(
        build_blog_monthly_plan, db, target_date, merchant_id, now_kst_hour,
    )

    dispatched, skipped, failed = [], [], []
    for item in plan["items"]:
        if item["action"] == "skip":
            skipped.append(item)
            continue

        payload = item["request_payload"]
        # 집행 전 행 기록 (SOURCE_AUTO + ad_type + 해당 월 1일을 execution_date로 사용)
        from calendar import monthrange
        month_start = date_cls(target_date.year, target_date.month, 1)
        key = build_idempotency_key(SOURCE_AUTO, item["merchant_id"], "blog_review", month_start)

        def _upsert_blog_row(db=db, item=item, payload=payload,
                             effective_dry_run=effective_dry_run, actor_id=actor_id,
                             month_start=month_start, key=key):
            row = db.query(AdDispatch).filter(AdDispatch.idempotency_key == key).first()
            if row is None:
                row = AdDispatch(
                    merchant_id=item["merchant_id"], ad_type="blog_review",
                    execution_date=month_start, source=SOURCE_AUTO,
                    idempotency_key=key, created_by=actor_id,
                )
                db.add(row)
            row.requested_count = item["daily_workload"]
            row.request_json = json.dumps(payload, ensure_ascii=False)
            row.dry_run = effective_dry_run
            row.skip_reason = None
            row.error_message = None
            row.status = STATUS_DRY_RUN if effective_dry_run else STATUS_PENDING
            db.commit()
            return row

        row = await run_in_threadpool(_upsert_blog_row)

        if effective_dry_run:
            dispatched.append({**item, "dispatch_id": row.id, "status": row.status, "error": None})
            continue

        try:
            result = await rewardpop.create_blog_order(db, payload)
        except rewardpop.SpecMissing as exc:
            await run_in_threadpool(_mark_failed, db, row, exc.message, False)
            failed.append({**item, "dispatch_id": row.id, "status": STATUS_FAILED, "error": exc.message})
            continue
        except rewardpop.RewardpopError as exc:
            await run_in_threadpool(_mark_failed, db, row, exc.message, exc.retryable)
            failed.append({**item, "dispatch_id": row.id, "status": STATUS_FAILED, "error": exc.message})
            continue

        await run_in_threadpool(_mark_sent, db, row, result)
        dispatched.append({
            **item,
            "dispatch_id": row.id,
            "status": row.status,
            "external_order_id": result.get("external_order_id"),
            "error": None,
        })

    logger.info(
        "블로그 월별 접수 %s — 전송 %d, 실패 %d, 보류 %d (드라이런=%s)",
        f"{target_date.year}-{target_date.month:02d}",
        len(dispatched), len(failed), len(skipped), effective_dry_run,
    )
    return {
        "target_month": plan["target_month"],
        "dry_run": effective_dry_run,
        "dispatched": dispatched,
        "failed": failed,
        "skipped": skipped,
        "dispatched_count": len(dispatched),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
    }
