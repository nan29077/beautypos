"""
영업수수료 표시 여부 헬퍼.

최고관리자(ADMIN)가 역할별로 ON/OFF 한다. 각 계정은 자기 하위 단계의
영업수수료를 ON 일 때만 조회할 수 있다. ADMIN 은 항상 전체 조회 가능.

기본값은 표시(True) — 관리자가 명시적으로 끄기 전까지는 기존 동작을 유지한다.
"""
from sqlalchemy.orm import Session

from app.models.system_config import (
    SystemConfig,
    COMMISSION_VISIBLE_TO_SALES,
    COMMISSION_VISIBLE_TO_OWNER,
    COMMISSION_VISIBLE_TO_DESIGNER,
)
from app.models.user import UserRole

_ROLE_KEY = {
    UserRole.SALES: COMMISSION_VISIBLE_TO_SALES,
    UserRole.OWNER: COMMISSION_VISIBLE_TO_OWNER,
    UserRole.DESIGNER: COMMISSION_VISIBLE_TO_DESIGNER,
}


def _get_flag(db: Session, key: str, default: bool = True) -> bool:
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if cfg is None:
        return default
    return bool(cfg.is_enabled)


def get_commission_visibility(db: Session) -> dict:
    """역할별 표시 여부 매트릭스 반환 (ADMIN 은 항상 True)."""
    return {
        "admin": True,
        "sales": _get_flag(db, COMMISSION_VISIBLE_TO_SALES),
        "owner": _get_flag(db, COMMISSION_VISIBLE_TO_OWNER),
        "designer": _get_flag(db, COMMISSION_VISIBLE_TO_DESIGNER),
    }


def commission_visible_for(db: Session, role) -> bool:
    """주어진 역할이 영업수수료를 볼 수 있는지."""
    if role == UserRole.ADMIN:
        return True
    key = _ROLE_KEY.get(role)
    if key is None:
        return False
    return _get_flag(db, key)
