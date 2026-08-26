"""외부 서비스 웹훅 수신 라우터.

온기(ONGI) 결제 노티 — 결제가 완료되면 온기 API 서버가 이 엔드포인트로
POST 한다. JWT 인증 대신 HMAC-SHA256 서명(X-Ongi-Signature)으로 검증한다.

응답 정책
    온기 쪽 타임아웃이 약 15초이고 재전송 큐가 없으므로, 서명 검증만 마치면
    바로 200 을 돌려주고 실제 반영(상세 조회 → upsert)은 백그라운드로 처리한다.
    반영에 실패해도 폴링 동기화(ongi_sync)의 lookback 이 다음 주기에 따라잡는다.
"""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.services import ongi, ongi_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

MAX_BODY_BYTES = 64 * 1024


def _verify_signature(timestamp, signature, raw_body: bytes) -> tuple:
    """(secret_configured, signature_ok) — 동기 DB 조회라 스레드풀에서 부른다."""
    db = SessionLocal()
    try:
        configured = ongi.get_notify_secret(db) is not None
        ok = configured and ongi.verify_notify_signature(
            db, timestamp=timestamp, signature=signature, raw_body=raw_body
        )
        return configured, ok
    finally:
        db.close()


@router.post("/ongi/payment")
async def ongi_payment_notify(request: Request, background_tasks: BackgroundTasks):
    """온기 결제 완료 노티 수신.

    시크릿이 등록된 경우 서명이 틀리면 401 로 거절한다. 시크릿이 없으면
    수신은 하되, 반영 단계(process_notify)에서 온기 상세 조회가 성공한
    건만 저장한다 — 서명 없는 본문을 그대로 믿지 않기 위해서다.
    """
    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="body too large")

    secret_configured, signature_ok = await run_in_threadpool(
        _verify_signature,
        request.headers.get("X-Ongi-Timestamp"),
        request.headers.get("X-Ongi-Signature"),
        raw_body,
    )
    if secret_configured and not signature_ok:
        logger.warning("온기 노티 서명 검증 실패 — 요청 거절")
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid json")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid json")

    # 현재 이벤트는 payment.completed 하나 — 모르는 이벤트는 조용히 무시한다
    # (온기가 이벤트를 추가해도 5xx 로 경고 로그를 만들지 않기 위해서다).
    event = payload.get("event")
    if event != "payment.completed":
        logger.info("온기 노티 무시 — 처리하지 않는 이벤트: %s", event)
        return {"ok": True, "ignored": True}

    if ongi_sync._to_int(payload.get("payment_pk")) is None:
        raise HTTPException(status_code=400, detail="missing payment_pk")

    # 온기 타임아웃(약 15초) 안에 응답하기 위해 반영은 백그라운드로 넘긴다.
    background_tasks.add_task(ongi_sync.process_notify, payload, signature_ok)
    return {"ok": True}
