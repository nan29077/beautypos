"""광고 자동 집행 스케줄러.

매일 관리자가 정한 시각(기본 14:00 KST)에 ad_dispatch.run() 을 호출한다.
순위 수집 스케줄러(rank_scheduler)와 같은 방식으로 asyncio 만 쓰며,
FastAPI lifespan 에 등록된다.

중복 집행을 막는 두 겹
    1) AdDispatch 의 멱등키 유니크 제약 — 같은 날 같은 가맹점·광고는 한 번만
    2) 여기의 일일 실행 잠금 — 서버 인스턴스를 늘려도 하루 한 프로세스만 집행

멱등키만으로도 이중 주문은 막히지만, 잠금이 없으면 여러 프로세스가 동시에
리워드팝을 호출하다 한쪽이 유니크 충돌로 죽는다. 호출 자체를 아끼는 편이 낫다.

블로그 월별 접수 스케줄러(_blog_scheduler_loop)는 플레이스 일별 집행 스케줄러
(_scheduler_loop)와 완전히 독립된 루프다. 매월 첫 평일에 한 번 실행된다.
"""
import asyncio
import logging
from datetime import date as date_cls, datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 잠금을 담아 두는 SystemConfig 키. 값은 "YYYY-MM-DD" 형태의 마지막 집행일이다.
DISPATCH_LOCK_KEY = "ad_dispatch_last_run"

# 블로그 월별 접수 잠금 키. 값은 "YYYY-MM" 형태의 마지막 접수 월이다.
BLOG_DISPATCH_LOCK_KEY = "blog_dispatch_last_month"

# 시각 설정을 다시 읽는 주기. 관리자가 화면에서 집행 시각을 바꿔도
# 서버 재시작 없이 다음 확인 때 반영된다.
CHECK_INTERVAL_SECONDS = 60


def next_run_at(now: datetime, hour: int, minute: int) -> datetime:
    """다음 실행 시각(KST). 이미 지났으면 다음 날로 넘긴다."""
    target = now.astimezone(KST).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now.astimezone(KST):
        target += timedelta(days=1)
    return target


def acquire_daily_lock(db, day) -> bool:
    """오늘 몫의 집행 권한을 딱 한 번만 내준다.

    조건부 UPDATE 한 방으로 처리한다. 두 프로세스가 동시에 들어와도
    실제로 값을 바꾼 쪽만 True 를 받는다.
    """
    from app.models.system_config import SystemConfig

    today = str(day)
    row = db.query(SystemConfig).filter(
        SystemConfig.config_key == DISPATCH_LOCK_KEY
    ).first()
    if row is None:
        row = SystemConfig(
            config_key=DISPATCH_LOCK_KEY,
            config_value="",
            description="광고 자동 집행 마지막 실행일 (하루 한 번만 돌게 하는 잠금)",
        )
        db.add(row)
        db.commit()

    result = db.execute(
        text(
            "UPDATE system_configs SET config_value = :today "
            "WHERE config_key = :key AND (config_value IS NULL OR config_value <> :today)"
        ),
        {"today": today, "key": DISPATCH_LOCK_KEY},
    )
    db.commit()
    return (result.rowcount or 0) > 0


async def run_once(force: bool = False) -> dict:
    """오늘 몫을 한 번 집행한다. 잠금을 이미 누가 가져갔으면 건너뛴다."""
    from app.database import SessionLocal
    from app.services import ad_dispatch, rewardpop
    from app.utils.kst import today_kst

    db = SessionLocal()
    try:
        today = today_kst()
        if not rewardpop.is_enabled(db):
            logger.info("광고 자동 집행 건너뜀 — 리워드팝 연동이 꺼져 있음")
            return {"skipped": True, "reason": "integration_off", "date": str(today)}
        if not force and not acquire_daily_lock(db, today):
            logger.info("광고 자동 집행 건너뜀 — 오늘(%s) 이미 실행됨", today)
            return {"skipped": True, "reason": "already_run_today", "date": str(today)}
        return await ad_dispatch.run(db, target_date=today)
    finally:
        db.close()


def acquire_blog_monthly_lock(db, year_month: str) -> bool:
    """이달 블로그 접수 권한을 딱 한 번만 내준다.

    조건부 UPDATE 한 방으로 처리한다. 두 프로세스가 동시에 들어와도
    실제로 값을 바꾼 쪽만 True 를 받는다.
    """
    from app.models.system_config import SystemConfig

    row = db.query(SystemConfig).filter(
        SystemConfig.config_key == BLOG_DISPATCH_LOCK_KEY
    ).first()
    if row is None:
        row = SystemConfig(
            config_key=BLOG_DISPATCH_LOCK_KEY,
            config_value="",
            description="블로그 월별 자동 접수 마지막 실행월 (월 한 번만 돌게 하는 잠금)",
        )
        db.add(row)
        db.commit()

    result = db.execute(
        text(
            "UPDATE system_configs SET config_value = :month "
            "WHERE config_key = :key AND (config_value IS NULL OR config_value <> :month)"
        ),
        {"month": year_month, "key": BLOG_DISPATCH_LOCK_KEY},
    )
    db.commit()
    return (result.rowcount or 0) > 0


def _is_first_weekday_of_month(day: date_cls) -> bool:
    """오늘이 이 달의 첫 번째 평일(월~금)인가."""
    first = date_cls(day.year, day.month, 1)
    while first.weekday() >= 5:  # 5=토, 6=일
        first += timedelta(days=1)
    return day == first


async def run_blog_once(force: bool = False) -> dict:
    """이달 블로그 접수를 한 번 집행한다. 잠금을 이미 누가 가져갔으면 건너뛴다."""
    from app.database import SessionLocal
    from app.services import ad_dispatch, rewardpop
    from app.utils.kst import today_kst

    db = SessionLocal()
    try:
        today = today_kst()
        year_month = f"{today.year}-{today.month:02d}"
        if not rewardpop.is_enabled(db):
            logger.info("블로그 월별 접수 건너뜀 — 리워드팝 연동이 꺼져 있음")
            return {"skipped": True, "reason": "integration_off", "month": year_month}
        if not force and not acquire_blog_monthly_lock(db, year_month):
            logger.info("블로그 월별 접수 건너뜀 — 이달(%s) 이미 실행됨", year_month)
            return {"skipped": True, "reason": "already_run_this_month", "month": year_month}
        now_kst_hour = datetime.now(KST).hour
        return await ad_dispatch.dispatch_blog_monthly(
            db, target_date=today, now_kst_hour=now_kst_hour,
        )
    finally:
        db.close()


async def _blog_scheduler_loop() -> None:
    """매월 첫 평일에 블로그 월별 접수를 실행한다.

    일별 플레이스 집행 스케줄러(_scheduler_loop)와 완전히 독립된 루프다.
    집행 시각은 플레이스 일별 집행과 같은 DB 설정(dispatch_hour/minute)을 읽어 쓴다.
    매 루프마다 첫 평일 여부를 확인하고, 맞으면 월 잠금을 획득해 접수한다.
    """
    from app.database import SessionLocal
    from app.services import rewardpop

    logger.info("블로그 월별 접수 스케줄러 시작")
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("블로그 월별 접수 스케줄러 종료")
            raise

        db = SessionLocal()
        try:
            settings = rewardpop.get_settings(db)
            hour = int(settings.get("dispatch_hour", 14))
            minute = int(settings.get("dispatch_minute", 0))
        except Exception as exc:  # noqa: BLE001
            logger.warning("블로그 접수 시각 설정을 읽지 못했습니다: %s", exc)
            hour, minute = 14, 0
        finally:
            db.close()

        now = datetime.now(KST)
        # 지정 시각을 막 지난 구간(+5분 이내)에 들어왔을 때만 시도한다.
        if now.hour == hour and minute <= now.minute < minute + 5:
            today = now.date()
            if _is_first_weekday_of_month(today):
                try:
                    result = await run_blog_once()
                    if not result.get("skipped"):
                        logger.info(
                            "블로그 월별 접수 완료 — 전송 %s, 실패 %s, 보류 %s",
                            result.get("dispatched_count"), result.get("failed_count"),
                            result.get("skipped_count"),
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning("블로그 월별 접수 중 오류: %s", exc)


async def _scheduler_loop() -> None:
    """설정된 시각이 되면 집행한다.

    집행 시각은 관리자 화면에서 바꿀 수 있으므로 매번 다시 읽는다.
    긴 sleep 대신 1분마다 확인하는 이유도 그것이다.
    """
    from app.database import SessionLocal
    from app.services import rewardpop

    logger.info("광고 자동 집행 스케줄러 시작")
    last_status_slot = None
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("광고 자동 집행 스케줄러 종료")
            raise

        db = SessionLocal()
        try:
            settings = rewardpop.get_settings(db)
            hour = int(settings.get("dispatch_hour", 14))
            minute = int(settings.get("dispatch_minute", 0))
            integration_enabled = rewardpop.is_enabled(db)
        except Exception as exc:  # noqa: BLE001 — 설정을 못 읽어도 루프는 살아 있어야 한다
            logger.warning("집행 시각 설정을 읽지 못했습니다: %s", exc)
            hour, minute, integration_enabled = 14, 0, False
        finally:
            db.close()

        now = datetime.now(KST)
        # 접수된 캠페인의 상태를 5분마다 동기화한다. GET 조회라 외부 주문을 만들지 않는다.
        status_slot = now.strftime("%Y-%m-%d %H:%M") if now.minute % 5 == 0 else None
        if integration_enabled and status_slot and status_slot != last_status_slot:
            last_status_slot = status_slot
            status_db = SessionLocal()
            try:
                from app.services import ad_dispatch
                await ad_dispatch.refresh_statuses(status_db, limit=200)
            except Exception as exc:  # noqa: BLE001 — 상태 조회 실패로 집행 루프를 죽이지 않는다
                logger.warning("리워드팝 광고 상태 자동 동기화 실패: %s", exc)
            finally:
                status_db.close()
        # 지정 시각을 막 지난 구간에 들어왔을 때만 집행한다.
        # 실제 중복 방지는 일일 잠금이 하므로 이 창은 넉넉해도 된다.
        if now.hour == hour and minute <= now.minute < minute + 5:
            try:
                result = await run_once()
                if not result.get("skipped"):
                    logger.info(
                        "광고 자동 집행 완료 — 전송 %s, 실패 %s, 보류 %s",
                        result.get("dispatched_count"), result.get("failed_count"),
                        result.get("skipped_count"),
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — 실패해도 다음 날 다시 시도한다
                logger.warning("광고 자동 집행 중 오류: %s", exc)


def start(app) -> None:
    """FastAPI lifespan 에서 호출 — 스케줄러 태스크를 등록한다."""
    from app.config import get_settings

    if not get_settings().AD_DISPATCH_SCHEDULER_ENABLED:
        logger.info("광고 자동 집행 스케줄러가 비활성화되어 있습니다")
        return
    app.state.ad_dispatch_task = asyncio.create_task(_scheduler_loop())
    app.state.blog_dispatch_task = asyncio.create_task(_blog_scheduler_loop())


async def stop(app) -> None:
    for attr in ("ad_dispatch_task", "blog_dispatch_task"):
        task = getattr(app.state, attr, None)
        if task is None:
            continue
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        setattr(app.state, attr, None)
