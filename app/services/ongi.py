"""온기(ONGI) QR 결제 연동 어댑터.

외부 결제 서버(api.ongi.site)를 아는 유일한 파일이다. 다른 모듈은 이 파일의
함수만 호출하며, 온기의 URL·인증 헤더·응답 봉투 형태를 직접 알지 못한다.
명세가 바뀌어도 수정 범위가 여기서 멈추도록 하기 위한 것이다.
(리워드팝 어댑터 app/services/rewardpop.py 와 같은 구조를 따른다.)

온기 API 요약 (문서: https://www.ongi.site/api/)
    Base URL: https://api.ongi.site/api/external/integration/merchant/v1/organization
    인증: X-API-Key 헤더 (필수) + X-API-MID 헤더 (선택, 조직 MID와 일치해야 함)
    응답 봉투: {success, status_code, error_code, message, data, [pagination], timestamp}
    결제 내역: GET /payment-transactions/list · GET /payment-transactions/{id}/detail
    결제 노티: 온기 → 우리 서버 POST, HMAC-SHA256 (sha256=hex) 서명 검증

API 키·노티 시크릿은 Fernet 으로 암호화해 SystemConfig 에 저장한다. 나머지
설정(기준 URL, API MID, 동기화 주기)은 JSON 한 건으로 같은 테이블에 둔다.
관리자가 화면에서 바로 바꿀 수 있어야 키 재발급에 서버 재시작이 필요 없다.
"""
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.system_config import (
    SystemConfig,
    ONGI_API_KEY,
    ONGI_SETTINGS,
    ONGI_NOTIFY_SECRET,
)
from app.services.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0

DEFAULT_BASE_URL = "https://api.ongi.site/api/external/integration/merchant/v1/organization"

DEFAULT_SETTINGS = {
    "base_url": DEFAULT_BASE_URL,
    "api_mid": "",                # 선택 — 전달 시 X-API-MID 헤더로 나가며 조직 MID와 일치해야 한다
    "sync_interval_minutes": 10,  # 결제 내역 폴링 주기 (동기화 잡에서 사용)
    "sync_lookback_days": 3,      # 폴링 시 되짚어볼 기간 — 노티 유실·사후 취소를 흡수한다
}

# 온기 결제 상태 문자열 (list API의 state 파라미터 / 응답 status 필드)
PAYMENT_STATE_COMPLETED = "완료"
PAYMENT_STATE_CANCELLED = "취소"


class OngiError(Exception):
    """온기 호출 실패. retryable 이 참이면 잠시 후 재시도할 가치가 있다."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status = status
        self.error_code = error_code


# ─── 설정 저장·조회 ─────────────────────────────────────────

def _get_config(db: Session, key: str) -> Optional[SystemConfig]:
    return db.query(SystemConfig).filter(SystemConfig.config_key == key).first()


def mask_api_key(plain: str) -> str:
    """API 키를 'z31j...••••••••ift8' 형태로 마스킹한다."""
    if not plain:
        return ""
    if len(plain) <= 8:
        return "•" * len(plain)
    return f"{plain[:4]}...{'•' * 8}{plain[-4:]}"


def _get_secret(db: Session, config_key: str) -> Optional[str]:
    cfg = _get_config(db, config_key)
    if not cfg or not cfg.config_value:
        return None
    try:
        return decrypt_value(cfg.config_value)
    except Exception as exc:  # noqa: BLE001 — 키 손상 / ENCRYPTION_KEY 변경 시
        logger.warning("온기 비밀값(%s) 복호화 실패: %s", config_key, exc)
        return None


def _save_secret(db: Session, config_key: str, plain: str, description: str) -> None:
    cfg = _get_config(db, config_key)
    if not cfg:
        cfg = SystemConfig(config_key=config_key, description=description)
        db.add(cfg)
    cfg.config_value = encrypt_value(plain)
    cfg.is_enabled = True
    db.commit()


def _delete_secret(db: Session, config_key: str) -> bool:
    cfg = _get_config(db, config_key)
    if not cfg or not cfg.config_value:
        return False
    cfg.config_value = None
    cfg.is_enabled = False
    db.commit()
    return True


def get_api_key(db: Session) -> Optional[str]:
    """저장된 온기 API 키를 복호화해 반환한다. 없으면 None."""
    return _get_secret(db, ONGI_API_KEY)


def save_api_key(db: Session, plain: str) -> None:
    """API 키를 암호화해 저장한다. 저장과 동시에 연동을 사용 상태로 둔다."""
    _save_secret(db, ONGI_API_KEY, plain, "온기 가맹점 API 키 (결제 내역 연동용, Fernet 암호화 저장)")


def delete_api_key(db: Session) -> bool:
    """저장된 API 키를 제거한다. 삭제된 경우 True."""
    return _delete_secret(db, ONGI_API_KEY)


def is_enabled(db: Session) -> bool:
    """연동 사용 스위치. 키가 없으면 항상 거짓."""
    cfg = _get_config(db, ONGI_API_KEY)
    return bool(cfg and cfg.config_value and cfg.is_enabled)


def set_enabled(db: Session, enabled: bool) -> None:
    cfg = _get_config(db, ONGI_API_KEY)
    if not cfg:
        return
    cfg.is_enabled = bool(enabled)
    db.commit()


def get_notify_secret(db: Session) -> Optional[str]:
    """결제 노티 HMAC 시크릿 (ongi_nt_ 접두사). 없으면 None."""
    return _get_secret(db, ONGI_NOTIFY_SECRET)


def save_notify_secret(db: Session, plain: str) -> None:
    _save_secret(db, ONGI_NOTIFY_SECRET, plain, "온기 결제 노티 HMAC 시크릿 (Fernet 암호화 저장)")


def delete_notify_secret(db: Session) -> bool:
    return _delete_secret(db, ONGI_NOTIFY_SECRET)


def _clean_int(value: Any, fallback: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, parsed))


def normalize_settings(raw: Optional[dict]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    base = str(raw.get("base_url") or DEFAULT_SETTINGS["base_url"]).strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = DEFAULT_SETTINGS["base_url"]
    return {
        "base_url": base,
        "api_mid": str(raw.get("api_mid") or "").strip(),
        "sync_interval_minutes": _clean_int(
            raw.get("sync_interval_minutes"), DEFAULT_SETTINGS["sync_interval_minutes"], 1, 1440
        ),
        "sync_lookback_days": _clean_int(
            raw.get("sync_lookback_days"), DEFAULT_SETTINGS["sync_lookback_days"], 1, 90
        ),
    }


def get_settings(db: Session) -> dict:
    cfg = _get_config(db, ONGI_SETTINGS)
    if not cfg or not cfg.config_value:
        return dict(DEFAULT_SETTINGS)
    try:
        return normalize_settings(json.loads(cfg.config_value))
    except (ValueError, TypeError):
        logger.warning("온기 설정 JSON 파싱 실패 — 기본값을 사용한다")
        return dict(DEFAULT_SETTINGS)


def save_settings(db: Session, raw: dict) -> dict:
    """설정을 정규화해 저장하고 저장된 값을 돌려준다."""
    clean = normalize_settings(raw)
    cfg = _get_config(db, ONGI_SETTINGS)
    if not cfg:
        cfg = SystemConfig(
            config_key=ONGI_SETTINGS,
            description="온기 연동 설정 (기준 URL, API MID, 동기화 주기)",
        )
        db.add(cfg)
    cfg.config_value = json.dumps(clean, ensure_ascii=False)
    cfg.is_enabled = True
    db.commit()
    return clean


# ─── HTTP 호출 ──────────────────────────────────────────────

def _request_context(db: Session) -> tuple:
    """요청 한 건에 필요한 (API 키, 설정) 을 한 번에 읽는다."""
    return get_api_key(db), get_settings(db)


async def _request(
    db: Session,
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """온기에 요청을 보내고 응답 봉투 전체(dict)를 돌려준다.

    실패는 전부 OngiError 로 통일하며, 재시도해도 소용없는 오류(4xx)와
    잠시 후 다시 시도할 값이 있는 오류(타임아웃, 5xx, 429)를 구분한다.
    HTTP 는 성공이어도 봉투의 success 가 거짓이면 오류로 취급한다.
    """
    # 키·설정 조회는 동기 DB 호출이라 스레드풀에서 처리한다.
    api_key, settings = await run_in_threadpool(_request_context, db)
    if not api_key:
        raise OngiError("온기 API 키가 등록되지 않았습니다.")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-API-Key": api_key,
        "X-Timestamp": str(int(time.time())),
    }
    if settings["api_mid"]:
        headers["X-API-MID"] = settings["api_mid"]
    url = settings["base_url"] + path

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.request(
                method.upper(), url,
                headers=headers,
                params=params or None,
                json=json_body,
            )
    except httpx.TimeoutException:
        raise OngiError("온기 응답이 지연되었습니다.", retryable=True)
    except Exception as exc:  # noqa: BLE001 — 네트워크 계열은 모두 재시도 대상
        logger.warning("온기 연결 실패 (%s %s): %s", method, url, exc)
        raise OngiError("온기 서버에 연결하지 못했습니다.", retryable=True)

    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = None

    if status in (401, 403):
        raise OngiError(
            "API 키가 올바르지 않거나 권한이 없습니다. (API MID 설정도 확인해주세요)",
            status=status, error_code=_body_error_code(body),
        )
    if status == 429:
        raise OngiError("요청 한도를 초과했습니다.", retryable=True, status=status)
    if status >= 500:
        raise OngiError(f"온기 서버 오류입니다. (HTTP {status})", retryable=True, status=status)
    if status >= 400 or not isinstance(body, dict):
        raise OngiError(_error_detail(body, status), status=status, error_code=_body_error_code(body))
    if not body.get("success"):
        raise OngiError(_error_detail(body, status), status=status, error_code=_body_error_code(body))
    return body


def _body_error_code(body: Any) -> Optional[str]:
    if isinstance(body, dict) and isinstance(body.get("error_code"), str):
        return body["error_code"]
    return None


def _error_detail(body: Any, status: int) -> str:
    """오류 응답에서 사람이 읽을 메시지를 최대한 뽑아낸다."""
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            code = _body_error_code(body)
            return f"{message.strip()} ({code or f'HTTP {status}'})"
    return f"요청이 거절되었습니다. (HTTP {status})"


# ─── 공개 동작 ──────────────────────────────────────────────

async def test_connection(db: Session) -> dict:
    """저장된 키로 결제 내역 1건을 조회해 연동 상태를 확인한다."""
    if not await run_in_threadpool(get_api_key, db):
        return {"ok": False, "detail": "등록된 API 키가 없습니다."}
    try:
        body = await _request(
            db, "GET", "/payment-transactions/list", params={"page": 1, "limit": 1}
        )
    except OngiError as exc:
        return {"ok": False, "detail": exc.message, "retryable": exc.retryable}
    total = (body.get("pagination") or {}).get("total")
    return {"ok": True, "detail": "온기 연결에 성공했습니다.", "total_payments": total}


async def list_payments(
    db: Session,
    *,
    page: int = 1,
    limit: int = 100,
    start_date: Optional[str] = None,   # YYYY-MM-DD
    end_date: Optional[str] = None,     # YYYY-MM-DD
    qr_id: Optional[int] = None,
    state: Optional[str] = None,        # 완료 | 취소
) -> dict:
    """결제 내역 한 페이지를 조회한다.

    돌려주는 형태: {"items": [dict, ...], "pagination": dict}
    항목 필드는 온기 응답 그대로다 (id, paidAt, amount, payPrice, status,
    paymentType, memberName, orderCode, paymentCode, qrId, transactionNo …).
    """
    params: dict = {"page": max(1, page), "limit": max(1, min(100, limit))}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if qr_id is not None:
        params["qr_id"] = qr_id
    if state:
        params["state"] = state
    body = await _request(db, "GET", "/payment-transactions/list", params=params)
    data = body.get("data")
    return {
        "items": data if isinstance(data, list) else [],
        "pagination": body.get("pagination") or {},
    }


async def iter_payments(
    db: Session,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    qr_id: Optional[int] = None,
    state: Optional[str] = None,
    max_pages: int = 50,
):
    """결제 내역을 페이지 넘기며 전부 순회하는 async generator.

    동기화 잡이 기간 내 전체 건을 훑을 때 사용한다. max_pages 는 폭주 방지용
    상한이며, 상한에 걸리면 경고만 남기고 멈춘다 (다음 주기에 이어서 받는다).
    """
    page = 1
    while True:
        result = await list_payments(
            db, page=page, limit=100,
            start_date=start_date, end_date=end_date, qr_id=qr_id, state=state,
        )
        for item in result["items"]:
            yield item
        pagination = result["pagination"]
        last_page = pagination.get("last_page") or page
        if page >= last_page or not result["items"]:
            return
        page += 1
        if page > max_pages:
            logger.warning(
                "온기 결제 내역 페이지 상한(%d)에 도달 — 남은 페이지는 다음 동기화에서 처리",
                max_pages,
            )
            return


async def get_payment(db: Session, payment_id: int) -> dict:
    """결제 내역 단건을 조회한다. 온기 응답의 data(dict)를 그대로 돌려준다."""
    body = await _request(db, "GET", f"/payment-transactions/{int(payment_id)}/detail")
    data = body.get("data")
    if not isinstance(data, dict):
        raise OngiError("결제 내역 응답 형태가 예상과 다릅니다.")
    return data


async def list_qrs(
    db: Session,
    *,
    page: int = 1,
    limit: int = 100,
    status: Optional[str] = None,   # 활성 | 비활성
    search: Optional[str] = None,
) -> dict:
    """QR 코드 목록을 조회한다. 대시보드에서 qrId → 이름 매핑에 사용한다."""
    params: dict = {"page": max(1, page), "limit": max(1, min(100, limit))}
    if status:
        params["status"] = status
    if search:
        params["search"] = search
    body = await _request(db, "GET", "/qr-management/list", params=params)
    data = body.get("data")
    return {
        "items": data if isinstance(data, list) else [],
        "pagination": body.get("pagination") or {},
    }


# ─── 결제 노티(웹훅) 서명 검증 ──────────────────────────────

def verify_notify_signature(
    db: Session,
    *,
    timestamp: Optional[str],
    signature: Optional[str],
    raw_body: bytes,
) -> bool:
    """온기 결제 노티의 HMAC-SHA256 서명을 검증한다.

    메시지는 "{X-Ongi-Timestamp}.{raw_body}" 이고, 헤더 값은 "sha256=" + hex 다.
    반드시 JSON 파싱 전의 raw body 를 그대로 넣어야 한다.
    시크릿이 등록되지 않은 경우 검증 불가이므로 False 를 돌려준다 —
    시크릿 없이 노티를 받을지는 호출부(웹훅 라우트)가 정책으로 정한다.
    """
    secret = get_notify_secret(db)
    if not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        f"{timestamp or ''}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def status_summary(db: Session) -> dict:
    """화면에 뿌릴 연동 상태 요약. API 키 평문은 절대 내보내지 않는다."""
    key = get_api_key(db)
    settings = get_settings(db)
    # 마지막 동기화 시각(KST ISO) — ongi_sync 가 잠금 값으로 기록한다.
    last_sync = _get_config(db, "ongi_sync_last_run")
    return {
        "configured": key is not None,
        "enabled": is_enabled(db),
        "masked_key": mask_api_key(key) if key else None,
        "notify_secret_configured": get_notify_secret(db) is not None,
        "last_synced_at": (last_sync.config_value or None) if last_sync else None,
        "settings": settings,
    }
