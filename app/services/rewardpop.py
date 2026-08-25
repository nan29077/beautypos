"""
리워드팝(RewardPop) 연동 어댑터.

외부 광고 플랫폼을 아는 유일한 파일이다. 다른 모듈은 이 파일의 함수만 호출하며,
리워드팝의 URL·인증 방식·응답 형태를 직접 알지 못한다. 명세가 바뀌어도
수정 범위가 여기서 멈추도록 하기 위한 것이다.

키는 OpenAI 키와 동일하게 Fernet 으로 암호화해 SystemConfig 에 저장한다.
나머지 설정(기준 URL, 인증 방식, 경로, 집행 시각, 드라이런)은 JSON 한 건으로 묶어
같은 테이블에 둔다. 관리자가 화면에서 바로 바꿀 수 있어야 재발급·명세 변경에
서버 재시작이 필요 없다.

[명세 확보 전 상태]
create_order() 는 아직 요청 본문 규격을 모르므로 호출하면 SpecMissing 을 던진다.
연결 테스트와 잔액 조회는 경로만 맞으면 동작하도록 만들어 두었다.
"""
import json
import logging
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.system_config import (
    SystemConfig,
    REWARDPOP_API_KEY,
    REWARDPOP_SETTINGS,
)
from app.services.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0

# 인증 방식 — 명세를 받으면 이 중 하나로 설정한다.
AUTH_STYLES = [
    ("bearer", "Authorization: Bearer <키>"),
    ("header", "지정한 헤더에 키를 그대로"),
    ("query", "쿼리 파라미터로 키 전달"),
]
AUTH_STYLE_CODES = [code for code, _ in AUTH_STYLES]

DEFAULT_SETTINGS = {
    "base_url": "https://api.rewardpop.kr",
    "auth_style": "bearer",          # AUTH_STYLE_CODES 중 하나
    "auth_header": "X-API-KEY",      # auth_style == "header" 일 때 사용
    "auth_query": "api_key",         # auth_style == "query" 일 때 사용
    "ping_path": "",                 # 연결 확인용 GET 경로 (명세 확인 후 입력)
    "balance_path": "",              # 포인트 잔액 조회 GET 경로
    "order_path": "",                # 주문 생성 POST 경로
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


def normalize_settings(raw: Optional[dict]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    style = str(raw.get("auth_style") or DEFAULT_SETTINGS["auth_style"]).strip()
    if style not in AUTH_STYLE_CODES:
        style = DEFAULT_SETTINGS["auth_style"]
    base = str(raw.get("base_url") or DEFAULT_SETTINGS["base_url"]).strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = DEFAULT_SETTINGS["base_url"]
    return {
        "base_url": base,
        "auth_style": style,
        "auth_header": str(raw.get("auth_header") or DEFAULT_SETTINGS["auth_header"]).strip(),
        "auth_query": str(raw.get("auth_query") or DEFAULT_SETTINGS["auth_query"]).strip(),
        "ping_path": _clean_path(raw.get("ping_path")),
        "balance_path": _clean_path(raw.get("balance_path")),
        "order_path": _clean_path(raw.get("order_path")),
        "dispatch_hour": _clean_int(raw.get("dispatch_hour"), DEFAULT_SETTINGS["dispatch_hour"], 0, 23),
        "dispatch_minute": _clean_int(raw.get("dispatch_minute"), DEFAULT_SETTINGS["dispatch_minute"], 0, 59),
        "dry_run": bool(raw.get("dry_run", DEFAULT_SETTINGS["dry_run"])),
    }


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


async def _request(
    db: Session,
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> Any:
    """리워드팝에 요청을 보내고 파싱된 본문을 돌려준다.

    실패는 전부 RewardpopError 로 통일하며, 재시도해도 소용없는 오류
    (400, 401, 403)와 잠시 후 다시 시도할 값이 있는 오류(타임아웃, 5xx, 429)를 구분한다.
    """
    api_key = get_api_key(db)
    if not api_key:
        raise RewardpopError("리워드팝 API 키가 등록되지 않았습니다.")
    if not path:
        raise SpecMissing("호출 경로가 설정되지 않았습니다. 연동 설정에서 경로를 입력해주세요.")

    settings = get_settings(db)
    headers, auth_params = _auth_parts(api_key, settings)
    headers["Accept"] = "application/json"
    merged_params = dict(auth_params)
    merged_params.update(params or {})
    url = settings["base_url"] + path

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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
    if not get_api_key(db):
        return {"ok": False, "detail": "등록된 API 키가 없습니다."}
    settings = get_settings(db)
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


BALANCE_KEYS = ("balance", "point", "points", "remain", "remaining", "amount")


async def get_balance(db: Session) -> dict:
    """리워드팝 포인트 잔액을 조회한다.

    응답 형태가 확정되지 않아, 흔한 이름의 숫자 필드를 찾아 balance 로 올려주고
    원본도 함께 돌려준다. 명세를 받으면 이 추정 로직을 정확한 매핑으로 바꾼다.
    """
    settings = get_settings(db)
    if not settings["balance_path"]:
        raise SpecMissing("잔액 조회 경로가 아직 설정되지 않았습니다.")
    body = await _request(db, "GET", settings["balance_path"])
    return {"balance": _find_number(body, BALANCE_KEYS), "raw": body}


async def create_order(db: Session, ad_type: str, payload: dict) -> dict:
    """광고 주문을 접수한다.

    [미구현] 요청 본문 규격과 응답의 주문 ID 위치를 아직 몰라 호출할 수 없다.
    명세를 확보하면 이 함수 안에서만 매핑을 채우면 되고,
    호출부(ad_dispatch)는 손대지 않아도 된다.

    돌려줄 형태:
        {"external_order_id": str, "status": str, "raw": dict}
    """
    settings = get_settings(db)
    if not settings["order_path"]:
        raise SpecMissing("주문 생성 경로가 아직 설정되지 않았습니다.")
    raise SpecMissing(
        "주문 생성 규격이 아직 확정되지 않았습니다. "
        "리워드팝 API 문서를 확보한 뒤 rewardpop.create_order() 의 매핑을 채워야 합니다."
    )


def status_summary(db: Session) -> dict:
    """화면에 뿌릴 연동 상태 요약."""
    key = get_api_key(db)
    settings = get_settings(db)
    missing = [
        name for name, value in (
            ("연결 확인", settings["ping_path"]),
            ("잔액 조회", settings["balance_path"]),
            ("주문 생성", settings["order_path"]),
        ) if not value
    ]
    return {
        "configured": key is not None,
        "enabled": is_enabled(db),
        "masked_key": mask_api_key(key) if key else None,
        "settings": settings,
        "auth_styles": [{"code": c, "label": l} for c, l in AUTH_STYLES],
        "missing_paths": missing,
        "ready_for_dispatch": key is not None and not missing and not settings["dry_run"],
    }
