"""로그인 실패 제한.

같은 계정(이메일)으로 연속 실패가 쌓이면 일정 시간 잠근다. 비밀번호 대입 공격이
bcrypt 검증을 무한히 두드리는 것을 막는 것이 목적이다.

기록은 프로세스 메모리에 둔다. 이 앱은 단일 uvicorn 프로세스로 뜨므로(ecosystem.config.cjs,
Dockerfile 모두 워커 1개) 충분하다. 워커를 여러 개로 늘리면 Redis 같은 공용 저장소로
옮겨야 한다 — 그때 바꿀 곳이 이 파일 하나로 끝나도록 모아 두었다.

키는 이메일과 클라이언트 IP 를 함께 본다. 한 계정을 여러 곳에서 두드리는 경우와
한 곳에서 여러 계정을 훑는 경우를 모두 잡기 위한 것이다.
"""
import threading
import time
from typing import Optional, Tuple

from fastapi import HTTPException, Request

from app.config import get_settings

# key -> (연속 실패 횟수, 마지막 실패 시각(epoch))
_failures: dict = {}
_lock = threading.Lock()

# 마지막 실패로부터 이 시간이 지나면 실패 기록을 잊는다 (잠금 시간의 2배).
_FORGET_MULTIPLIER = 2

# 기록이 무한정 쌓이지 않도록 정리 주기를 둔다.
_MAX_ENTRIES = 10_000


def _now() -> float:
    return time.monotonic()


def client_ip(request: Optional[Request]) -> str:
    """요청자 IP. 프록시 뒤라면 X-Forwarded-For 의 첫 값을 쓴다."""
    if request is None:
        return "-"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


def _keys(email: str, ip: str) -> Tuple[str, ...]:
    email = (email or "").strip().lower()
    return (f"email:{email}", f"ip:{ip}|email:{email}")


def _prune(now: float, forget_after: float) -> None:
    if len(_failures) <= _MAX_ENTRIES:
        return
    stale = [k for k, (_, last) in _failures.items() if now - last > forget_after]
    for k in stale:
        _failures.pop(k, None)


def check(email: str, ip: str) -> None:
    """잠긴 상태면 429 로 막는다. 로그인 검증 **전에** 부른다."""
    settings = get_settings()
    max_attempts = max(1, settings.LOGIN_MAX_ATTEMPTS)
    lockout = max(1, settings.LOGIN_LOCKOUT_SECONDS)
    now = _now()

    with _lock:
        for key in _keys(email, ip):
            count, last = _failures.get(key, (0, 0.0))
            if count < max_attempts:
                continue
            elapsed = now - last
            if elapsed >= lockout:
                # 잠금 시간이 지났다 — 기록을 지우고 다시 기회를 준다.
                _failures.pop(key, None)
                continue
            remain = int(lockout - elapsed) + 1
            raise HTTPException(
                status_code=429,
                detail=f"로그인 시도가 너무 많습니다. {remain}초 후에 다시 시도해주세요",
                headers={"Retry-After": str(remain)},
            )


def record_failure(email: str, ip: str) -> None:
    """로그인 실패를 기록한다."""
    settings = get_settings()
    forget_after = max(1, settings.LOGIN_LOCKOUT_SECONDS) * _FORGET_MULTIPLIER
    now = _now()
    with _lock:
        _prune(now, forget_after)
        for key in _keys(email, ip):
            count, last = _failures.get(key, (0, 0.0))
            if now - last > forget_after:
                count = 0
            _failures[key] = (count + 1, now)


def record_success(email: str, ip: str) -> None:
    """로그인에 성공하면 그 계정의 실패 기록을 지운다."""
    with _lock:
        for key in _keys(email, ip):
            _failures.pop(key, None)


def reset() -> None:
    """테스트용 — 모든 기록을 지운다."""
    with _lock:
        _failures.clear()
