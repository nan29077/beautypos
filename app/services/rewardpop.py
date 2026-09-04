"""
리워드팝(RewardPop) 연동 어댑터.

외부 광고 플랫폼을 아는 유일한 파일이다. 다른 모듈은 이 파일의 함수만 호출하며,
리워드팝의 URL·인증 방식·응답 형태를 직접 알지 못한다. 명세가 바뀌어도
수정 범위가 여기서 멈추도록 하기 위한 것이다.

키는 OpenAI 키와 동일하게 Fernet 으로 암호화해 SystemConfig 에 저장한다.
나머지 설정(기준 URL, 인증 방식, 경로, 집행 시각, 드라이런)은 JSON 한 건으로 묶어
같은 테이블에 둔다. 관리자가 화면에서 바로 바꿀 수 있어야 재발급·명세 변경에
서버 재시작이 필요 없다.

드라이런
    settings["dry_run"] 이 참이면 실제 호출 없이 요청 내용만 기록한다. 운영에서 실수로
    켜지는 것을 막기 위해 환경변수 REWARDPOP_DRY_RUN 으로 강제 덮어쓸 수 있다
    (true = 항상 드라이런, false = 항상 실제 전송, 미설정 = 화면 설정을 따름).
"""
import ipaddress
import json
import logging
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.system_config import (
    SystemConfig,
    REWARDPOP_API_KEY,
    REWARDPOP_SETTINGS,
)
from app.config import get_settings as get_app_settings
from app.services.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20.0
# AUTO 키워드 추출은 공식 문서상 최대 120초가 걸릴 수 있다.
ORDER_REQUEST_TIMEOUT = 130.0

# 비공식/테스트 호스트 호환용 인증 방식. 공식 호스트는 header로 고정한다.
AUTH_STYLES = [
    ("bearer", "Authorization: Bearer <키>"),
    ("header", "지정한 헤더에 키를 그대로"),
    ("query", "쿼리 파라미터로 키 전달"),
]
AUTH_STYLE_CODES = [code for code, _ in AUTH_STYLES]

DEFAULT_SETTINGS = {
    "base_url": "https://api.rewardpop.kr",
    "auth_style": "header",          # 공식 규격: x-api-key 헤더
    "auth_header": "x-api-key",      # auth_style == "header" 일 때 사용
    "auth_query": "api_key",         # auth_style == "query" 일 때 사용
    "ping_path": "/accounts/points", # 별도 ping이 없어 안전한 잔액 GET으로 인증 확인
    "balance_path": "/accounts/points",
    "order_path": "/ads",
    "blog_order_path": "/ads/cloblog",  # POST /ads/cloblog — 클로 블로그 월별 접수
    "status_path": "/ads",           # GET /ads?groupId=<외부 주문번호>
    # 등록된 전체 키워드 조회. AUTO 모드에서 리워드팝이 실제로 고른 키워드를 회수한다.
    "keywords_path": "/ads/{groupId}/keywords",
    # 미션별 공급 단가(원가). 집행 전 포인트 소요액을 계산하는 데 쓴다.
    "prices_path": "/accounts/prices",
    "dispatch_hour": 14,             # 자동 집행 시각 (KST)
    "dispatch_minute": 0,
    "dry_run": True,                 # 참이면 실제 호출 없이 요청 내용만 기록한다
}


class RewardpopError(Exception):
    """리워드팝 호출 실패. retryable 이 참이면 잠시 후 재시도할 가치가 있다."""

    def __init__(self, message: str, *, retryable: bool = False, status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status = status


class SpecMissing(RewardpopError):
    """API 명세가 아직 확정되지 않아 호출할 수 없는 경우."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


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


def get_api_key(db: Session) -> Optional[str]:
    """저장된 리워드팝 API 키를 복호화해 반환한다. 없으면 None."""
    cfg = _get_config(db, REWARDPOP_API_KEY)
    if not cfg or not cfg.config_value:
        return None
    try:
        return decrypt_value(cfg.config_value)
    except Exception as exc:  # noqa: BLE001 — 키 손상 / ENCRYPTION_KEY 변경 시
        logger.warning("리워드팝 API 키 복호화 실패: %s", exc)
        return None


def save_api_key(db: Session, plain: str) -> None:
    """API 키를 암호화해 저장한다. 저장과 동시에 연동을 사용 상태로 둔다."""
    cfg = _get_config(db, REWARDPOP_API_KEY)
    if not cfg:
        cfg = SystemConfig(
            config_key=REWARDPOP_API_KEY,
            description="리워드팝 API 키 (광고 자동 집행용, Fernet 암호화 저장)",
        )
        db.add(cfg)
    cfg.config_value = encrypt_value(plain)
    cfg.is_enabled = True
    db.commit()


def delete_api_key(db: Session) -> bool:
    """저장된 API 키를 제거한다. 삭제된 경우 True."""
    cfg = _get_config(db, REWARDPOP_API_KEY)
    if not cfg or not cfg.config_value:
        return False
    cfg.config_value = None
    cfg.is_enabled = False
    db.commit()
    return True


def is_enabled(db: Session) -> bool:
    """연동 사용 스위치. 키가 없으면 항상 거짓."""
    cfg = _get_config(db, REWARDPOP_API_KEY)
    return bool(cfg and cfg.config_value and cfg.is_enabled)


def set_enabled(db: Session, enabled: bool) -> None:
    cfg = _get_config(db, REWARDPOP_API_KEY)
    if not cfg:
        return
    cfg.is_enabled = bool(enabled)
    db.commit()


def _clean_int(value: Any, fallback: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, parsed))


def _clean_path(value: Any) -> str:
    """'/v1/orders' 형태로 정규화한다. 빈 값이면 빈 문자열."""
    text = (value or "").strip()
    if not text:
        return ""
    return text if text.startswith("/") else "/" + text


def _is_safe_url(url: str) -> bool:
    """RFC 1918·link-local·loopback 대역으로의 SSRF 요청을 차단한다."""
    try:
        host = urlparse(url).hostname or ""
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        return not (ip.is_private or ip.is_link_local or ip.is_loopback)
    except Exception:
        return False


def normalize_settings(raw: Optional[dict]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    style = str(raw.get("auth_style") or DEFAULT_SETTINGS["auth_style"]).strip()
    if style not in AUTH_STYLE_CODES:
        style = DEFAULT_SETTINGS["auth_style"]
    base = str(raw.get("base_url") or DEFAULT_SETTINGS["base_url"]).strip().rstrip("/")
    if not base.startswith(("http://", "https://")) or not _is_safe_url(base):
        base = DEFAULT_SETTINGS["base_url"]
    official = base.lower() == DEFAULT_SETTINGS["base_url"].lower()
    if official:
        style = "header"
    return {
        "base_url": base,
        "auth_style": style,
        "auth_header": (
            DEFAULT_SETTINGS["auth_header"] if official
            else str(raw.get("auth_header") or DEFAULT_SETTINGS["auth_header"]).strip()
        ),
        "auth_query": str(raw.get("auth_query") or DEFAULT_SETTINGS["auth_query"]).strip(),
        # 공식 API 경로는 고정값이다. 과거 빈 설정도 읽는 즉시 안전한 기본값으로 보정한다.
        "ping_path": _clean_path(DEFAULT_SETTINGS["ping_path"] if official else raw.get("ping_path")),
        "balance_path": _clean_path(DEFAULT_SETTINGS["balance_path"] if official else raw.get("balance_path")),
        "order_path": _clean_path(DEFAULT_SETTINGS["order_path"] if official else raw.get("order_path")),
        "blog_order_path": _clean_path(
            DEFAULT_SETTINGS["blog_order_path"] if official else raw.get("blog_order_path")
        ),
        "status_path": _clean_path(DEFAULT_SETTINGS["status_path"] if official else raw.get("status_path")),
        "keywords_path": _clean_path(
            DEFAULT_SETTINGS["keywords_path"] if official else raw.get("keywords_path")
        ),
        "prices_path": _clean_path(
            DEFAULT_SETTINGS["prices_path"] if official else raw.get("prices_path")
        ),
        "dispatch_hour": _clean_int(raw.get("dispatch_hour"), DEFAULT_SETTINGS["dispatch_hour"], 0, 23),
        "dispatch_minute": _clean_int(raw.get("dispatch_minute"), DEFAULT_SETTINGS["dispatch_minute"], 0, 59),
        "dry_run": bool(raw.get("dry_run", DEFAULT_SETTINGS["dry_run"])),
    }


def dry_run_enabled(db: Session) -> bool:
    """이번 전송을 실제로 보낼지 판단한다.

    기본은 관리자 화면에 저장된 설정이지만, 환경변수 REWARDPOP_DRY_RUN 이 지정되면
    그 값이 우선한다. 운영에서 화면 조작 실수로 실제 주문이 나가거나(false 강제),
    반대로 조용히 드라이런에 머무는 것(true 강제)을 배포 설정으로 못박기 위한 것이다.
    """
    override = get_app_settings().REWARDPOP_DRY_RUN
    if override is not None:
        return bool(override)
    return bool(get_settings(db).get("dry_run", True))


def get_settings(db: Session) -> dict:
    cfg = _get_config(db, REWARDPOP_SETTINGS)
    if not cfg or not cfg.config_value:
        return dict(DEFAULT_SETTINGS)
    try:
        return normalize_settings(json.loads(cfg.config_value))
    except (ValueError, TypeError):
        logger.warning("리워드팝 설정 JSON 파싱 실패 — 기본값을 사용한다")
        return dict(DEFAULT_SETTINGS)


def save_settings(db: Session, raw: dict) -> dict:
    """설정을 정규화해 저장하고 저장된 값을 돌려준다."""
    clean = normalize_settings(raw)
    cfg = _get_config(db, REWARDPOP_SETTINGS)
    if not cfg:
        cfg = SystemConfig(
            config_key=REWARDPOP_SETTINGS,
            description="리워드팝 연동 설정 (기준 URL, 인증 방식, 경로, 집행 시각, 드라이런)",
        )
        db.add(cfg)
    cfg.config_value = json.dumps(clean, ensure_ascii=False)
    cfg.is_enabled = True
    db.commit()
    return clean


# ─── HTTP 호출 ──────────────────────────────────────────────

def _auth_parts(api_key: str, settings: dict) -> tuple:
    """(headers, params) 를 만든다."""
    style = settings["auth_style"]
    if style == "bearer":
        return {"Authorization": f"Bearer {api_key}"}, {}
    if style == "header":
        return {settings["auth_header"] or "X-API-KEY": api_key}, {}
    return {}, {settings["auth_query"] or "api_key": api_key}


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
    timeout: float = REQUEST_TIMEOUT,
) -> Any:
    """리워드팝에 요청을 보내고 파싱된 본문을 돌려준다.

    실패는 전부 RewardpopError 로 통일하며, 재시도해도 소용없는 오류
    (400, 401, 403)와 잠시 후 다시 시도할 값이 있는 오류(타임아웃, 5xx, 429)를 구분한다.
    """
    # 키·설정 조회는 동기 DB 호출이라 스레드풀에서 처리한다.
    api_key, settings = await run_in_threadpool(_request_context, db)
    if not api_key:
        raise RewardpopError("리워드팝 API 키가 등록되지 않았습니다.")
    if not path:
        raise SpecMissing("호출 경로가 설정되지 않았습니다. 연동 설정에서 경로를 입력해주세요.")

    headers, auth_params = _auth_parts(api_key, settings)
    headers["Accept"] = "application/json"
    merged_params = dict(auth_params)
    merged_params.update(params or {})
    url = settings["base_url"] + path

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method.upper(), url,
                headers=headers,
                params=merged_params or None,
                json=json_body,
            )
    except httpx.TimeoutException:
        raise RewardpopError("리워드팝 응답이 지연되었습니다.", retryable=True)
    except Exception as exc:  # noqa: BLE001 — 네트워크 계열은 모두 재시도 대상
        logger.warning("리워드팝 연결 실패 (%s %s): %s", method, url, exc)
        raise RewardpopError("리워드팝 서버에 연결하지 못했습니다.", retryable=True)

    status = response.status_code
    if status == 401 or status == 403:
        raise RewardpopError("API 키가 올바르지 않거나 권한이 없습니다.", status=status)
    if status == 404:
        raise SpecMissing(f"경로를 찾을 수 없습니다 ({path}). 연동 설정의 경로를 확인해주세요.")
    if status == 429:
        raise RewardpopError("요청 한도를 초과했습니다.", retryable=True, status=status)
    if status >= 500:
        raise RewardpopError(f"리워드팝 서버 오류입니다. (HTTP {status})", retryable=True, status=status)
    if status >= 400:
        raise RewardpopError(_error_detail(response, status), status=status)

    try:
        return response.json()
    except ValueError:
        raise RewardpopError("리워드팝 응답을 해석하지 못했습니다 (JSON 아님).", status=status)


def _error_detail(response: httpx.Response, status: int) -> str:
    """오류 응답에서 사람이 읽을 메시지를 최대한 뽑아낸다."""
    try:
        body = response.json()
    except ValueError:
        return f"요청이 거절되었습니다. (HTTP {status})"
    if isinstance(body, dict):
        for key in ("message", "detail", "error", "msg"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return f"{value.strip()} (HTTP {status})"
    return f"요청이 거절되었습니다. (HTTP {status})"


# ─── 공개 동작 ──────────────────────────────────────────────

async def test_connection(db: Session) -> dict:
    """저장된 키로 실제 요청을 보내 연동 상태를 확인한다."""
    api_key, settings = await run_in_threadpool(_request_context, db)
    if not api_key:
        return {"ok": False, "detail": "등록된 API 키가 없습니다."}
    if not settings["ping_path"]:
        return {
            "ok": False,
            "detail": "연결 확인 경로가 아직 설정되지 않았습니다. "
                      "리워드팝 API 문서를 확인한 뒤 연동 설정에 입력해주세요.",
            "spec_missing": True,
        }
    try:
        await _request(db, "GET", settings["ping_path"])
    except SpecMissing as exc:
        return {"ok": False, "detail": exc.message, "spec_missing": True}
    except RewardpopError as exc:
        return {"ok": False, "detail": exc.message, "retryable": exc.retryable}
    return {"ok": True, "detail": "리워드팝 연결에 성공했습니다."}


def _find_number(node: Any, keys: tuple) -> Optional[float]:
    """중첩된 응답에서 잔액으로 보이는 숫자를 찾는다."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in keys and isinstance(value, (int, float)):
                return float(value)
        for value in node.values():
            found = _find_number(value, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_number(value, keys)
            if found is not None:
                return found
    return None


BALANCE_KEYS = ("balance", "pointbalance", "point", "points", "remain", "remaining", "amount")


async def get_balance(db: Session) -> dict:
    """리워드팝 포인트 잔액을 조회한다.

    공식 응답의 pointBalance를 포함해 중첩 계정 응답에서도 잔액을 찾고,
    관리 화면 진단을 위해 원본도 함께 돌려준다.
    """
    settings = await run_in_threadpool(get_settings, db)
    if not settings["balance_path"]:
        raise SpecMissing("잔액 조회 경로가 아직 설정되지 않았습니다.")
    body = await _request(db, "GET", settings["balance_path"])
    return {"balance": _find_number(body, BALANCE_KEYS), "raw": body}


# 공식 groupId를 우선하고, 테스트/호환 호스트 응답에는 아래 이름도 허용한다.
ORDER_ID_KEYS = (
    "external_order_id", "order_id", "orderid", "orderno", "order_no",
    "campaign_id", "campaignid", "id", "uid", "no",
)


def _find_identifier(node: Any, keys: tuple) -> Optional[str]:
    """중첩된 응답에서 주문번호로 보이는 값을 찾는다 (문자열/정수 모두 허용)."""
    normalized_keys = {str(candidate).lower().replace("_", "") for candidate in keys}
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower().replace("_", "") in normalized_keys and isinstance(value, (str, int)):
                text = str(value).strip()
                if text:
                    return text
        for value in node.values():
            found = _find_identifier(value, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_identifier(value, keys)
            if found is not None:
                return found
    return None


async def create_order(db: Session, ad_type: str, payload: dict) -> dict:
    """광고 주문을 접수한다.

    호출부(ad_dispatch)가 만든 요청 본문을 그대로 보내고, 응답에서 외부 주문번호와
    상태를 뽑아 돌려준다. 리워드팝이 어떤 이름으로 주문번호를 주는지는 명세에 따라
    다를 수 있어 흔한 이름들(ORDER_ID_KEYS)을 훑는다.

    돌려주는 형태:
        {"external_order_id": str, "status": str, "raw": dict}

    실패는 전부 RewardpopError(또는 하위 SpecMissing)로 올라간다.
    키가 없으면 _request() 안에서 "API 키가 등록되지 않았습니다" 로 막힌다.
    """
    settings = await run_in_threadpool(get_settings, db)
    if not settings["order_path"]:
        raise SpecMissing(
            "주문 생성 경로가 아직 설정되지 않았습니다. 연동 설정에서 경로를 입력해주세요."
        )

    try:
        body = await _request(
            db, "POST", settings["order_path"], json_body=payload,
            timeout=ORDER_REQUEST_TIMEOUT,
        )
    except RewardpopError as exc:
        # 공식 API는 외부 멱등키를 받지 않는다. 타임아웃/5xx 뒤 자동 재시도하면
        # 이미 접수된 캠페인이 중복될 수 있어 운영자 확인 전에는 재시도하지 않는다.
        if exc.retryable:
            raise RewardpopError(
                f"{exc.message} 주문 접수 여부를 리워드팝에서 확인한 뒤 재시도해주세요.",
                retryable=False,
                status=exc.status,
            )
        raise

    # 리워드팝 응답은 groupId(UUID)를 기준 식별자로 쓴다. 상태 조회도 groupId로 한다.
    external_order_id = (body.get("groupId") if isinstance(body, dict) else None) or _find_identifier(body, ORDER_ID_KEYS)
    if not external_order_id:
        # 주문은 접수됐을 수 있으므로 재시도 대상으로 두지 않는다.
        # 같은 주문이 두 번 나가는 것보다 사람이 확인하는 편이 낫다.
        logger.error("리워드팝 주문 응답에서 주문번호를 찾지 못했습니다: %s", body)
        raise RewardpopError(
            "주문은 전송했지만 응답에서 주문번호를 찾지 못했습니다. "
            "리워드팝 관리자 화면에서 접수 여부를 확인해주세요."
        )

    status, raw_status = map_external_status(body)
    return {
        "external_order_id": external_order_id,
        "status": status or "sent",
        "raw_status": raw_status,
        "counts": extract_counts(body),
        "raw": body,
    }


# 외부 상태 문자열을 우리 상태로 옮기는 표.
# 공식 상태 외의 값은 매핑하지 않는다. 모르는 값을 성공으로 간주하지 않는다.
# STOP(중지)은 실패가 아니다. 이미 접수돼 일부가 나갔을 수 있고, 리워드팝에는
# 취소 API 가 없어 되돌릴 수도 없다. 실패로 뭉뚱그리면 재집행 판정이 어긋난다.
EXTERNAL_STATUS_MAP = {
    "active": "running", "pending": "sent", "stop": "stopped", "stopped": "stopped",
    "done": "done", "complete": "done", "completed": "done", "finished": "done",
    "success": "done", "succeeded": "done",
    "running": "running", "progress": "running", "in_progress": "running",
    "processing": "running", "waiting": "running",
    "fail": "failed", "failed": "failed", "error": "failed",
    "cancel": "failed", "cancelled": "failed", "canceled": "failed", "rejected": "failed",
}
STATUS_KEYS = ("status", "state", "order_status", "campaign_status", "result")

# 공식 응답이 돌려주는 실제 진행 수치.
#   totalReqCount 전체 요청 수 / reqCount 이 건의 요청 수 / rewardCount 실제 적립 완료 수
# GET /ads 는 배열이라 workDays 가 여러 날이면 행이 여러 개 온다. 합산해서 본다.
COUNT_FIELDS = {
    "reqcount": "delivered_count",
    "rewardcount": "reward_count",
    "totalreqcount": "total_count",
    "keywordcount": "keyword_count",
}


def extract_counts(body) -> dict:
    """응답에서 실제 진행 수치를 뽑아 합산한다. 못 찾은 항목은 키 자체가 없다.

    합산 대상은 "광고 행"으로 보이는 dict — 위 필드를 하나라도 가진 dict 뿐이다.
    중첩 구조에서 같은 값을 두 번 더하지 않도록, 행을 찾으면 그 안쪽은 보지 않는다.
    """
    totals: dict = {}

    def _is_row(node) -> bool:
        return isinstance(node, dict) and any(
            k.lower().replace("_", "") in COUNT_FIELDS for k in node
        )

    def _add(node) -> None:
        for key, value in node.items():
            field = COUNT_FIELDS.get(key.lower().replace("_", ""))
            if field and isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[field] = totals.get(field, 0) + int(value)

    def _walk(node) -> None:
        if _is_row(node):
            _add(node)
            return
        if isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(body)
    return totals


def map_external_status(body) -> tuple:
    """외부 응답에서 상태 문자열을 찾아 우리 상태로 옮긴다.

    돌려주는 값: (우리 상태 또는 None, 찾아낸 원본 문자열 또는 None)
    상태를 찾지 못하면 (None, None) — 호출부가 기존 상태를 그대로 둔다.
    """
    def _find(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in STATUS_KEYS and isinstance(value, str) and value.strip():
                    return value.strip()
            for value in node.values():
                found = _find(value)
                if found:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = _find(value)
                if found:
                    return found
        return None

    raw = _find(body)
    if not raw:
        return None, None
    return EXTERNAL_STATUS_MAP.get(raw.lower().replace("-", "_")), raw


async def get_order_status(db: Session, external_order_id: str) -> dict:
    """접수된 주문의 진행 상태를 조회한다.

    공식 규격은 GET /ads?groupId=<등록 응답의 groupId> 이다.
    """
    settings = await run_in_threadpool(get_settings, db)
    path = settings["status_path"]
    if not path:
        raise SpecMissing("상태 조회 경로가 아직 설정되지 않았습니다.")
    if not external_order_id:
        raise RewardpopError("외부 주문번호가 없어 상태를 조회할 수 없습니다.")

    if "{id}" in path:
        body = await _request(db, "GET", path.replace("{id}", str(external_order_id)))
    else:
        body = await _request(db, "GET", path, params={"groupId": external_order_id})

    status, raw_status = map_external_status(body)
    return {
        "status": status,
        "raw_status": raw_status,
        "counts": extract_counts(body),
        "raw": body,
    }


async def get_ad_keywords(db: Session, external_order_id: str) -> dict:
    """등록된 전체 키워드를 조회한다 (공식: GET /ads/{groupId}/keywords).

    AUTO 모드는 리워드팝이 키워드를 직접 고르므로, 이걸 회수하지 않으면
    무엇이 나갔는지 ADPAY 에 기록이 남지 않는다. 요청한 개수보다 적게
    등록될 수 있어 keywordCount 도 함께 돌려준다.
    """
    settings = await run_in_threadpool(get_settings, db)
    path = settings.get("keywords_path") or ""
    if not path:
        raise SpecMissing("키워드 조회 경로가 설정되지 않았습니다.")
    if not external_order_id:
        raise RewardpopError("외부 주문번호가 없어 키워드를 조회할 수 없습니다.")

    filled = path.replace("{groupId}", str(external_order_id)).replace("{id}", str(external_order_id))
    body = await _request(db, "GET", filled)

    keywords: list = []

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() == "keywords" and isinstance(value, list):
                    keywords.extend(str(v).strip() for v in value if str(v).strip())
                else:
                    _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(body)
    # 순서를 지키면서 중복만 제거한다.
    seen, unique = set(), []
    for word in keywords:
        if word not in seen:
            seen.add(word)
            unique.append(word)
    counts = extract_counts(body)
    return {
        "keywords": unique,
        "keyword_count": counts.get("keyword_count", len(unique)),
        "raw": body,
    }


def _price_rows(node, out: list) -> None:
    """공급 단가 응답(중첩 계정 트리)에서 본인 계정의 prices 배열만 뽑는다."""
    if isinstance(node, dict):
        rows = node.get("prices")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    out.append(row)
            # 본인 단가를 찾았으면 하부 계정(children)까지 섞지 않는다.
            return
        for value in node.values():
            _price_rows(value, out)
    elif isinstance(node, list):
        for value in node:
            _price_rows(value, out)


async def get_prices(db: Session) -> dict:
    """미션별 공급 단가(원가)를 조회한다 (공식: GET /accounts/prices).

    돌려주는 형태:
        {"prices": [원본 행...],
         "by_mission": {"VISIT:FIND_PATH": 120, ...},
         "by_media": {"clo": [120.0], "cloblog": [28000.0], ...},
         "raw": 원본}

    단가가 설정되지 않은 미션은 unitPrice 가 null 이라 어느 쪽에도 넣지 않는다.

    by_media 가 따로 있는 이유
        플레이스가 아닌 매체(클로 블로그 등)는 missionCategory/missionAction 이 null 이라
        by_mission 만으로는 단가를 꺼낼 수 없다. 공식 문서도 mediaType 을
        "clo, blue, cloplus, cloblog, nstore 등"으로 안내한다.
        한 매체에 여러 행이 올 수 있어 값을 리스트로 모아 둔다 — 하나로 접는 판단은
        쓰는 쪽(ad_dispatch.supply_unit_price)에서 한다.
    """
    settings = await run_in_threadpool(get_settings, db)
    path = settings.get("prices_path") or ""
    if not path:
        raise SpecMissing("공급 단가 조회 경로가 설정되지 않았습니다.")
    body = await _request(db, "GET", path)

    rows: list = []
    _price_rows(body, rows)
    by_mission = {}
    by_media: dict = {}
    for row in rows:
        price = row.get("unitPrice")
        if price is None:
            continue
        try:
            value = float(price)
        except (TypeError, ValueError):
            continue

        media = (row.get("mediaType") or "").strip().lower()
        if media:
            bucket = by_media.setdefault(media, [])
            if value not in bucket:
                bucket.append(value)

        category = row.get("missionCategory")
        action = row.get("missionAction")
        if not category or not action:
            continue
        by_mission[f"{category}:{action}"] = value

    for values in by_media.values():
        values.sort()
    return {"prices": rows, "by_mission": by_mission, "by_media": by_media, "raw": body}


async def create_blog_order(db: Session, payload: dict) -> dict:
    """클로 블로그 광고 주문을 접수한다 (POST /ads/cloblog).

    호출부(ad_dispatch.dispatch_blog_monthly)가 만든 요청 본문을 그대로 보내고,
    응답에서 외부 주문번호와 상태를 뽑아 돌려준다.

    돌려주는 형태:
        {"external_order_id": str, "status": str, "raw": dict}

    실패는 전부 RewardpopError(또는 하위 SpecMissing)로 올라간다.
    """
    settings = await run_in_threadpool(get_settings, db)
    path = settings.get("blog_order_path") or ""
    if not path:
        raise SpecMissing(
            "블로그 주문 생성 경로가 아직 설정되지 않았습니다. 연동 설정에서 경로를 확인해주세요."
        )

    try:
        body = await _request(
            db, "POST", path, json_body=payload,
            timeout=ORDER_REQUEST_TIMEOUT,
        )
    except RewardpopError as exc:
        # 타임아웃/5xx 뒤 자동 재시도하면 이미 접수된 캠페인이 중복될 수 있어
        # 운영자 확인 전에는 재시도하지 않는다.
        if exc.retryable:
            raise RewardpopError(
                f"{exc.message} 블로그 주문 접수 여부를 리워드팝에서 확인한 뒤 재시도해주세요.",
                retryable=False,
                status=exc.status,
            )
        raise

    external_order_id = (
        (body.get("groupId") if isinstance(body, dict) else None)
        or _find_identifier(body, ORDER_ID_KEYS)
    )
    if not external_order_id:
        logger.error("리워드팝 블로그 주문 응답에서 주문번호를 찾지 못했습니다: %s", body)
        raise RewardpopError(
            "블로그 주문은 전송했지만 응답에서 주문번호를 찾지 못했습니다. "
            "리워드팝 관리자 화면에서 접수 여부를 확인해주세요."
        )

    status, raw_status = map_external_status(body)
    return {
        "external_order_id": external_order_id,
        "status": status or "sent",
        "raw_status": raw_status,
        "counts": extract_counts(body),
        "raw": body,
    }


def status_summary(db: Session) -> dict:
    """화면에 뿌릴 연동 상태 요약."""
    key = get_api_key(db)
    settings = get_settings(db)
    missing = [
        name for name, value in (
            ("연결 확인", settings["ping_path"]),
            ("잔액 조회", settings["balance_path"]),
            ("주문 생성", settings["order_path"]),
            ("상태 조회", settings["status_path"]),
        ) if not value
    ]
    effective_dry_run = dry_run_enabled(db)
    return {
        "configured": key is not None,
        "enabled": is_enabled(db),
        "masked_key": mask_api_key(key) if key else None,
        "settings": settings,
        # 환경변수로 덮어쓴 경우 화면에 저장값과 실효값을 함께 보여준다.
        "effective_dry_run": effective_dry_run,
        "dry_run_forced_by_env": get_app_settings().REWARDPOP_DRY_RUN is not None,
        "auth_styles": [{"code": c, "label": l} for c, l in AUTH_STYLES],
        "missing_paths": missing,
        "ready_for_dispatch": key is not None and not missing and not effective_dry_run,
    }
