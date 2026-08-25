"""단말기 API 키 발급 · 검증.

기존 구조는 X-Terminal-Key 를 받으면 활성 단말기를 **전부** 꺼내 bcrypt 로 하나씩
대조했다. bcrypt 는 일부러 느리게 만든 해시라 단말기가 늘수록 결제 한 건의
인증 시간이 선형으로 늘어난다(단말기 500대면 요청 하나에 bcrypt 500회).

그래서 조회용 지문(fingerprint)을 따로 둔다.
    api_key_fingerprint = HMAC-SHA256(JWT_SECRET_KEY, 평문 키)  — 결정적, 인덱스 조회용
    api_key_hash        = bcrypt(평문 키)                        — 실제 검증용 (그대로 유지)

지문으로 후보 한 행을 찾고 그 행만 bcrypt 로 검증한다. 지문은 서버 비밀(JWT_SECRET_KEY)
이 섞인 HMAC 이라, DB 만 유출돼도 사전 대입으로 원본 키를 되찾기 어렵다.

지문이 아직 없는 레거시 행은 예전처럼 전체 순회로 찾아내고, 찾은 순간 지문을 채워
다음 요청부터는 빠른 경로를 타게 한다.
"""
import hashlib
import hmac
import logging
import secrets
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.terminal import TerminalDevice

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 발급 키 길이 (URL-safe base64 문자 수는 이보다 길어진다)
API_KEY_BYTES = 32


def generate_api_key() -> str:
    """새 단말기 API 키를 만든다. 평문은 발급 응답에서 한 번만 보여준다."""
    return secrets.token_urlsafe(API_KEY_BYTES)


def fingerprint(api_key: str) -> str:
    """조회용 지문. 같은 키는 항상 같은 값이 나온다."""
    secret = get_settings().JWT_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, (api_key or "").encode("utf-8"), hashlib.sha256).hexdigest()


def hash_api_key(api_key: str) -> str:
    return pwd_context.hash(api_key)


def apply_api_key(terminal: TerminalDevice, api_key: str) -> None:
    """단말기 행에 새 키의 해시와 지문을 함께 심는다."""
    terminal.api_key_hash = hash_api_key(api_key)
    terminal.api_key_fingerprint = fingerprint(api_key)


def _verify(terminal: TerminalDevice, api_key: str) -> bool:
    try:
        return bool(terminal.api_key_hash and pwd_context.verify(api_key, terminal.api_key_hash))
    except ValueError:
        # 해시 형식이 깨진 행. 그 행만 건너뛰고 전체 인증이 500 이 되지 않게 한다.
        return False


def find_terminal(
    db: Session, api_key: str, serial: Optional[str] = None
) -> Optional[TerminalDevice]:
    """API 키로 단말기를 찾는다. 못 찾으면 None.

    조회 순서
        1) serial 이 있으면 그 단말기 하나만 검증한다 (bcrypt 1회).
        2) 지문으로 바로 찾는다 (인덱스 조회 + bcrypt 1회).
        3) 지문이 없는 레거시 행만 순회한다. 찾으면 지문을 채워 넣는다.
    """
    if not api_key:
        return None

    if serial:
        terminal = db.query(TerminalDevice).filter(
            TerminalDevice.terminal_serial == serial,
            TerminalDevice.is_active == True,  # noqa: E712
        ).first()
        if terminal and _verify(terminal, api_key):
            _backfill_fingerprint(db, terminal, api_key)
            return terminal
        return None

    fp = fingerprint(api_key)
    terminal = db.query(TerminalDevice).filter(
        TerminalDevice.api_key_fingerprint == fp,
        TerminalDevice.is_active == True,  # noqa: E712
    ).first()
    if terminal and _verify(terminal, api_key):
        return terminal

    # 레거시 행(지문 미기록)만 순회한다. 마이그레이션 직후 한 번씩만 지나가는 경로다.
    legacy = db.query(TerminalDevice).filter(
        TerminalDevice.is_active == True,  # noqa: E712
        TerminalDevice.api_key_fingerprint.is_(None),
    ).all()
    for row in legacy:
        if _verify(row, api_key):
            _backfill_fingerprint(db, row, api_key)
            return row
    return None


def _backfill_fingerprint(db: Session, terminal: TerminalDevice, api_key: str) -> None:
    if terminal.api_key_fingerprint:
        return
    terminal.api_key_fingerprint = fingerprint(api_key)
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — 지문 채우기는 실패해도 인증 자체는 성공이다
        db.rollback()
        logger.warning("단말기 #%s 지문 backfill 실패", terminal.id)
