"""
플레이스 순위/리뷰 자동 수집 스케줄러.

매일 한국시간 오후 2시에 모든 가맹점의 지표를 수집한다.
- 외부 스케줄러 라이브러리 없이 asyncio 만 사용한다 (FastAPI lifespan 에 등록).
- 당일 이미 수집된 대상은 건너뛴다 (fetch_all_for_merchant 의 캐시 로직 재사용).
- 화면의 '광고 분석하기' 수동 버튼과는 완전히 독립적으로 동작한다.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings

logger = logging.getLogger(__name__)

# 한국은 서머타임이 없으므로 고정 오프셋으로 충분하다 (tzdata 의존 없음).
KST = timezone(timedelta(hours=9))

# 가맹점 사이의 간격 — 네이버 요청이 한꺼번에 몰리지 않게 한다.
MERCHANT_INTERVAL_SECONDS = 5.0


def next_run_at(now: datetime, hour: int, minute: int) -> datetime:
    """다음 실행 시각(KST)을 계산한다. 이미 지났으면 다음 날로 넘긴다."""
    target = now.astimezone(KST).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now.astimezone(KST):
        target += timedelta(days=1)
    return target


def _merchant_ids_with_targets(db) -> list:
    """분석 대상(우리 매장 프로필 또는 경쟁업체)이 등록된 가맹점 id 목록."""
    from app.models.ad import AdPlaceProfile, AdCompetitor

    ids = {row[0] for row in db.query(AdPlaceProfile.merchant_id).distinct().all()}
    ids |= {row[0] for row in db.query(AdCompetitor.merchant_id).distinct().all()}
    return sorted(ids)


def _already_collected_today(db, merchant_id: int) -> bool:
    """오늘 자동 수집분이 이미 있으면 True.

    AdMetric 은 fetch_all_for_merchant 에서 UTC 날짜로 저장하므로
    같은 기준으로 조회해야 스킵 판정이 어긋나지 않는다.
    """
    from sqlalchemy import func
    from app.models.ad import AdMetric

    today = datetime.utcnow().date()
    count = db.query(func.count(AdMetric.id)).filter(
        AdMetric.merchant_id == merchant_id,
        AdMetric.date == today,
        AdMetric.source == "api",
    ).scalar() or 0
    return count > 0


async def collect_all_merchants() -> dict:
    """모든 가맹점의 지표를 순차 수집한다. 당일 수집분이 있으면 건너뛴다."""
    from app.database import SessionLocal
    from app.services import naver_place

    started = datetime.now(KST)
    db = SessionLocal()
    try:
        merchant_ids = _merchant_ids_with_targets(db)
    finally:
        db.close()

    collected = skipped = failed = 0
    for index, merchant_id in enumerate(merchant_ids):
        db = SessionLocal()
        try:
            if _already_collected_today(db, merchant_id):
                skipped += 1
                logger.info("자동 수집 건너뜀 (가맹점 %s): 오늘 데이터가 이미 있습니다", merchant_id)
                continue
            result = await naver_place.fetch_all_for_merchant(merchant_id, db=db, force=False)
            collected += result.get("collected", 0)
            failed += result.get("failed", 0)
            logger.info(
                "자동 수집 완료 (가맹점 %s): 저장 %s건, 실패 %s건, %.1f초",
                merchant_id, result.get("collected"), result.get("failed"),
                result.get("elapsed_seconds") or 0,
            )
        except Exception as exc:  # noqa: BLE001 — 한 곳이 실패해도 나머지는 계속 수집
            failed += 1
            logger.warning("자동 수집 실패 (가맹점 %s): %s", merchant_id, exc)
        finally:
            db.close()

        # 마지막 가맹점 뒤에는 쉬지 않는다.
        if index < len(merchant_ids) - 1:
            await asyncio.sleep(MERCHANT_INTERVAL_SECONDS)

    summary = {
        "merchants": len(merchant_ids),
        "collected": collected,
        "skipped": skipped,
        "failed": failed,
        "started_at": started.isoformat(),
        "elapsed_seconds": round((datetime.now(KST) - started).total_seconds(), 1),
    }
    logger.info("자동 수집 요약: %s", summary)
    return summary


async def _scheduler_loop(hour: int, minute: int) -> None:
    """매일 지정 시각까지 기다렸다가 수집을 실행한다."""
    logger.info("순위 자동 수집 스케줄러 시작 — 매일 %02d:%02d (KST)", hour, minute)
    while True:
        now = datetime.now(KST)
        target = next_run_at(now, hour, minute)
        wait_seconds = (target - now).total_seconds()
        logger.info("다음 자동 수집: %s (%.0f분 후)", target.isoformat(), wait_seconds / 60)
        try:
            await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            logger.info("순위 자동 수집 스케줄러 종료")
            raise
        try:
            await collect_all_merchants()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 실패해도 다음 날 다시 시도한다
            logger.warning("자동 수집 중 오류: %s", exc)
        # 같은 시각에 두 번 돌지 않도록 잠시 여유를 둔다.
        await asyncio.sleep(60)


def start(app) -> None:
    """FastAPI lifespan 에서 호출 — 스케줄러 태스크를 등록한다."""
    settings = get_settings()
    if not settings.RANK_SCHEDULER_ENABLED:
        logger.info("순위 자동 수집 스케줄러가 비활성화되어 있습니다")
        return
    task = asyncio.create_task(
        _scheduler_loop(settings.RANK_SCHEDULER_HOUR, settings.RANK_SCHEDULER_MINUTE)
    )
    app.state.rank_scheduler_task = task


async def stop(app) -> None:
    """FastAPI lifespan 종료 시 호출 — 태스크를 정리한다."""
    task = getattr(app.state, "rank_scheduler_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
    app.state.rank_scheduler_task = None
