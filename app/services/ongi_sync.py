"""온기(ONGI) 결제 내역 동기화 잡.

관리자가 정한 주기(기본 10분)마다 온기 결제 서버를 폴링해 최근
lookback 기간(기본 3일)의 결제를 ongi_transactions 에 upsert 한다.

되짚어 받는(lookback) 이유
    온기 결제 노티는 재전송 큐가 없어 유실될 수 있고, 취소는 노티가 아예
    오지 않는다. 최근 며칠을 매번 다시 훑으면 유실 건과 사후 취소가
    자연히 따라잡힌다. 온기 결제 id 유니크 제약 덕에 중복은 생기지 않는다.

중복 실행을 막는 두 겹 (ad_dispatch_scheduler 와 같은 방식)
    1) ongi_payment_id 유니크 제약 — 어떤 경우에도 같은 결제가 두 행이 되지 않는다
    2) SystemConfig 조건부 UPDATE 잠금 — 서버 인스턴스를 늘려도 주기당 한 프로세스만 폴링
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.ongi_transaction import OngiTransaction
from app.utils.kst import KST, today_kst

logger = logging.getLogger(__name__)

# 잠금을 담아 두는 SystemConfig 키. 값은 ISO 형식의 마지막 동기화 시각(KST)이다.
SYNC_LOCK_KEY = "ongi_sync_last_run"
LOCK_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# 주기 설정을 다시 읽는 간격. 관리자가 화면에서 주기를 바꿔도
# 서버 재시작 없이 다음 확인 때 반영된다.
CHECK_INTERVAL_SECONDS = 60


def acquire_sync_lock(db: Session, interval_minutes: int) -> bool:
    """이번 주기 몫의 폴링 권한을 딱 한 프로세스에만 내준다.

    조건부 UPDATE 한 방으로 처리한다. 마지막 실행이 (주기 - 45초) 이전일 때만
    값을 바꿀 수 있고, 실제로 바꾼 쪽만 True 를 받는다. 45초 여유는 확인 루프가
    1분 간격이라 실행 시각이 매번 조금씩 뒤로 밀리는 것을 막기 위한 것이다.
    ISO 문자열은 사전순 비교가 시간순 비교와 같다.
    """
    from app.models.system_config import SystemConfig

    now = datetime.now(KST)
    now_s = now.strftime(LOCK_TIME_FORMAT)
    cutoff_s = (now - timedelta(minutes=interval_minutes) + timedelta(seconds=45)).strftime(LOCK_TIME_FORMAT)

    row = db.query(SystemConfig).filter(SystemConfig.config_key == SYNC_LOCK_KEY).first()
    if row is None:
        row = SystemConfig(
            config_key=SYNC_LOCK_KEY,
            config_value="",
            description="온기 결제 동기화 마지막 실행 시각 (주기당 한 번만 돌게 하는 잠금)",
        )
        db.add(row)
        db.commit()

    result = db.execute(
        text(
            "UPDATE system_configs SET config_value = :now "
            "WHERE config_key = :key AND (config_value IS NULL OR config_value = '' "
            "OR config_value < :cutoff)"
        ),
        {"now": now_s, "key": SYNC_LOCK_KEY, "cutoff": cutoff_s},
    )
    db.commit()
    return (result.rowcount or 0) > 0


def _parse_dt(value) -> Optional[datetime]:
    """온기의 'YYYY-MM-DD HH:MM:SS' (또는 ISO) 문자열을 naive datetime 으로."""
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def _to_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_item(row: OngiTransaction, item: dict, qr_names: dict) -> None:
    """온기 응답 한 건을 로컬 행에 옮겨 적는다."""
    row.payment_code = item.get("paymentCode")
    row.order_code = item.get("orderCode")
    row.organization_id = _to_int(item.get("organizationId"))
    row.api_mid = item.get("apiMid")
    row.status = str(item.get("status") or "")
    row.amount = _to_int(item.get("amount"))
    row.pay_price = _to_int(item.get("payPrice"))
    row.discount_price = _to_int(item.get("discountPrice"))
    row.payment_type = item.get("paymentType")
    row.division = item.get("division")
    row.payment_words = item.get("paymentWords")
    row.member_name = item.get("memberName")
    row.ongi_member_id = _to_int(item.get("memberId"))
    row.qr_id = _to_int(item.get("qrId"))
    if row.qr_id is not None and qr_names.get(row.qr_id):
        row.qr_name = qr_names[row.qr_id]
    row.auth_no = item.get("authNo")
    row.transaction_no = item.get("transactionNo")
    row.pg_merchant_id = item.get("merchantId")
    row.result_code = item.get("resultCode")
    row.result_message = item.get("resultMessage")
    row.paid_at = _parse_dt(item.get("paidAt"))
    row.ongi_updated_at = (item.get("updatedAt") or "")[:30] or None
    row.synced_at = datetime.utcnow()
    row.raw_json = json.dumps(item, ensure_ascii=False)


async def _fetch_qr_names(db: Session) -> dict:
    """qrId → QR 이름 매핑. 실패해도 동기화는 계속한다 (이름만 비게 된다)."""
    from app.services import ongi

    names: dict = {}
    try:
        page = 1
        while page <= 10:
            result = await ongi.list_qrs(db, page=page, limit=100)
            for qr in result["items"]:
                qr_id = _to_int(qr.get("id"))
                if qr_id is not None:
                    names[qr_id] = qr.get("name")
            last_page = result["pagination"].get("last_page") or page
            if page >= last_page or not result["items"]:
                break
            page += 1
    except ongi.OngiError as exc:
        logger.warning("온기 QR 목록 조회 실패 (이름 매핑 생략): %s", exc.message)
    return names


async def sync_window(db: Session, start_date: str, end_date: str) -> dict:
    """지정 기간의 온기 결제를 전부 받아 upsert 한다.

    돌려주는 형태: {"fetched": n, "created": n, "updated": n, "start_date", "end_date"}
    """
    from app.services import ongi

    qr_names = await _fetch_qr_names(db)

    fetched = created = updated = 0
    async for item in ongi.iter_payments(db, start_date=start_date, end_date=end_date):
        ongi_id = _to_int(item.get("id"))
        if ongi_id is None:
            logger.warning("온기 결제 응답에 id 가 없어 건너뜀: %s", item)
            continue
        fetched += 1

        row = db.query(OngiTransaction).filter(
            OngiTransaction.ongi_payment_id == ongi_id
        ).first()
        if row is None:
            row = OngiTransaction(ongi_payment_id=ongi_id)
            _apply_item(row, item, qr_names)
            db.add(row)
            created += 1
        else:
            # 온기 updatedAt·상태가 그대로면 쓰기를 아낀다 (매 주기 전체 행 갱신 방지)
            same_stamp = row.ongi_updated_at == ((item.get("updatedAt") or "")[:30] or None)
            same_status = row.status == str(item.get("status") or "")
            if same_stamp and same_status:
                continue
            _apply_item(row, item, qr_names)
            updated += 1

        if (created + updated) % 100 == 0:
            db.commit()

    db.commit()
    logger.info(
        "온기 결제 동기화 완료 — 조회 %d, 신규 %d, 갱신 %d (%s ~ %s)",
        fetched, created, updated, start_date, end_date,
    )
    return {
        "fetched": fetched, "created": created, "updated": updated,
        "start_date": start_date, "end_date": end_date,
    }


# ─── 결제 노티(웹훅) 처리 ───────────────────────────────────

def _parse_notify_paid_at(payload: dict) -> Optional[datetime]:
    """tr_day(YYYYMMDD) + tr_time(HHmmss) 를 결제 시각으로 조립한다."""
    day = payload.get("tr_day")
    if not day or not isinstance(day, str):
        return None
    time_part = payload.get("tr_time") if isinstance(payload.get("tr_time"), str) else "000000"
    try:
        return datetime.strptime(f"{day} {time_part or '000000'}", "%Y%m%d %H%M%S")
    except ValueError:
        return None


def _apply_notify_payload(row, payload: dict) -> None:
    """노티 JSON(snake_case)을 로컬 행에 옮겨 적는다.

    조회 API(camelCase)와 필드 이름·의미가 조금 달라 별도로 매핑한다:
    노티의 payment_method(카드결제 등)가 조회 API의 paymentType 에,
    노티의 payment_type(일반송금·일시기부 등)이 조회 API의 division 에 해당한다.
    이 매핑이 어긋나더라도 다음 폴링 주기의 상세 조회가 정본으로 덮어쓴다.
    """
    row.payment_code = payload.get("payment_code")
    row.order_code = payload.get("order_code")
    row.organization_id = _to_int(payload.get("organization_pk"))
    row.status = str(payload.get("state") or "완료")
    row.amount = _to_int(payload.get("payment_amt"))
    row.pay_price = _to_int(payload.get("pay_price")) or _to_int(payload.get("payment_amt"))
    row.discount_price = _to_int(payload.get("discnt_price"))
    row.payment_type = payload.get("payment_method")
    row.division = payload.get("payment_type")
    row.member_name = payload.get("member_name")
    row.auth_no = payload.get("auth_no")
    row.transaction_no = payload.get("tr_no")
    row.result_code = payload.get("result_cd")
    row.result_message = payload.get("result_msg")
    row.paid_at = _parse_notify_paid_at(payload) or datetime.now(KST).replace(tzinfo=None)
    row.synced_at = datetime.utcnow()
    row.raw_json = json.dumps(payload, ensure_ascii=False)


async def process_notify(payload: dict, signature_ok: bool) -> dict:
    """결제 노티 한 건을 로컬 사본에 반영한다 (웹훅 라우트의 백그라운드 작업).

    payment_pk 로 온기 상세 조회 API 를 다시 불러 그 응답(정본)으로 upsert 한다.
    노티 본문을 그대로 믿지 않는 이유: 서명이 없는 가맹점 설정에서도 위조 데이터가
    저장되는 것을 막기 위해서다. 상세 조회가 실패하면 — 서명이 검증된 경우에만 —
    노티 본문으로 대신 채우고, 다음 폴링 주기가 정본으로 덮어쓰게 둔다.
    """
    from app.database import SessionLocal
    from app.services import ongi

    payment_pk = _to_int(payload.get("payment_pk"))
    if payment_pk is None:
        return {"ok": False, "reason": "missing_payment_pk"}

    db = SessionLocal()
    try:
        detail: Optional[dict] = None
        try:
            detail = await ongi.get_payment(db, payment_pk)
        except ongi.OngiError as exc:
            if not signature_ok:
                logger.warning(
                    "온기 노티 무시 — 상세 조회 실패(%s)이고 서명도 없어 본문을 믿을 수 없음 (payment_pk=%s)",
                    exc.message, payment_pk,
                )
                return {"ok": False, "reason": "detail_fetch_failed_unsigned"}
            logger.warning(
                "온기 노티 상세 조회 실패 — 서명 검증된 본문으로 대신 반영 (payment_pk=%s): %s",
                payment_pk, exc.message,
            )

        row = db.query(OngiTransaction).filter(
            OngiTransaction.ongi_payment_id == payment_pk
        ).first()
        created = row is None
        if created:
            row = OngiTransaction(ongi_payment_id=payment_pk)
            db.add(row)
        if detail is not None:
            qr_names: dict = {}
            _apply_item(row, detail, qr_names)
        else:
            _apply_notify_payload(row, payload)

        try:
            db.commit()
        except Exception:  # noqa: BLE001 — 폴링과의 경합으로 유니크 충돌 시 재시도
            db.rollback()
            existing = db.query(OngiTransaction).filter(
                OngiTransaction.ongi_payment_id == payment_pk
            ).first()
            if existing is None:
                raise
            if detail is not None:
                _apply_item(existing, detail, {})
            else:
                _apply_notify_payload(existing, payload)
            db.commit()
            created = False

        logger.info(
            "온기 노티 반영 — payment_pk=%s %s (정본: %s)",
            payment_pk, "신규" if created else "갱신", "상세 조회" if detail else "노티 본문",
        )
        return {"ok": True, "created": created, "source": "detail" if detail else "notify"}
    finally:
        db.close()


async def run_once(force: bool = False) -> dict:
    """이번 주기 몫을 한 번 동기화한다.

    force 가 참이면(관리자 수동 실행) 잠금·주기를 무시하고 바로 돈다.
    """
    from app.database import SessionLocal
    from app.services import ongi

    db = SessionLocal()
    try:
        if not ongi.is_enabled(db):
            return {"skipped": True, "reason": "integration_off"}
        settings = ongi.get_settings(db)
        if not force and not acquire_sync_lock(db, settings["sync_interval_minutes"]):
            return {"skipped": True, "reason": "recently_synced"}

        today = today_kst()
        start_date = str(today - timedelta(days=settings["sync_lookback_days"]))
        end_date = str(today)
        try:
            return await sync_window(db, start_date, end_date)
        except ongi.OngiError as exc:
            # 실패해도 다음 주기에 lookback 이 다시 훑으므로 기록만 남긴다
            logger.warning("온기 결제 동기화 실패: %s", exc.message)
            return {"skipped": True, "reason": "ongi_error", "detail": exc.message,
                    "retryable": exc.retryable}
    finally:
        db.close()


async def _scheduler_loop() -> None:
    """주기가 찼는지 1분마다 확인하고 동기화한다.

    실제 주기 판정과 다중 프로세스 조율은 acquire_sync_lock 이 하므로
    이 루프는 확인 간격만 짧게 유지하면 된다. 주기 설정을 매번 다시 읽어
    관리자 변경이 재시작 없이 반영된다.
    """
    logger.info("온기 결제 동기화 스케줄러 시작")
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("온기 결제 동기화 스케줄러 종료")
            raise

        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 실패해도 다음 주기에 다시 시도한다
            logger.warning("온기 결제 동기화 중 오류: %s", exc)


def start(app) -> None:
    """FastAPI lifespan 에서 호출 — 스케줄러 태스크를 등록한다."""
    from app.config import get_settings

    if not get_settings().ONGI_SYNC_ENABLED:
        logger.info("온기 결제 동기화 스케줄러가 비활성화되어 있습니다")
        return
    app.state.ongi_sync_task = asyncio.create_task(_scheduler_loop())


async def stop(app) -> None:
    task = getattr(app.state, "ongi_sync_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
    app.state.ongi_sync_task = None
