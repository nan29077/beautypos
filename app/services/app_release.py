"""안드로이드 앱 배포본(APK) 파일·메타 처리.

APK 파일은 서버 디스크 uploads/apk/ 에 저장하고, 메타는 AppRelease 로우로 둔다.
라우트(공개 app_routes, 관리자 app_release_routes)는 이 모듈만 거친다.
"""
import os
import re
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.app_release import AppRelease

logger = logging.getLogger(__name__)

# 프로젝트 루트 기준 uploads/apk. (이 파일: app/services/app_release.py → 루트는 세 단계 위)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(_ROOT, "uploads", "apk")

MAX_APK_BYTES = 200 * 1024 * 1024   # 200MB 상한
ZIP_MAGIC = b"PK\x03\x04"           # APK 는 ZIP 컨테이너


def ensure_dir() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _safe_name(version_code: int) -> str:
    return f"beautypos-{int(version_code)}.apk"


def apk_path(filename: str) -> str:
    """저장 디렉토리 안의 안전한 절대 경로. 경로 이탈(../)은 막는다."""
    name = os.path.basename(filename or "")
    if not name or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ValueError("잘못된 파일명입니다.")
    return os.path.join(UPLOAD_DIR, name)


def save_apk(content: bytes, version_code: int) -> tuple:
    """APK 바이트를 저장한다. (filename, size) 반환.

    ZIP 매직으로 최소한의 형식 검증만 한다(온전한 APK 검증은 하지 않는다).
    """
    if not content:
        raise ValueError("빈 파일입니다.")
    if len(content) > MAX_APK_BYTES:
        raise ValueError("APK 크기가 상한(200MB)을 초과했습니다.")
    if content[:4] != ZIP_MAGIC:
        raise ValueError("APK 파일이 아닙니다 (ZIP 형식 아님).")
    ensure_dir()
    filename = _safe_name(version_code)
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(content)
    return filename, len(content)


def delete_apk_file(filename: str) -> None:
    try:
        path = apk_path(filename)
        if os.path.exists(path):
            os.remove(path)
    except (ValueError, OSError) as exc:
        logger.warning("APK 파일 삭제 실패(%s): %s", filename, exc)


def latest_active(db: Session) -> Optional[AppRelease]:
    """배포 노출 중(is_active)인 가장 높은 version_code 릴리스."""
    return (
        db.query(AppRelease)
        .filter(AppRelease.is_active == True)  # noqa: E712
        .order_by(AppRelease.version_code.desc())
        .first()
    )


def serialize(r: AppRelease, download_url: Optional[str] = None) -> dict:
    data = {
        "id": r.id,
        "version_code": r.version_code,
        "version_name": r.version_name,
        "file_size": r.file_size,
        "notes": r.notes,
        "is_mandatory": r.is_mandatory,
        "is_active": r.is_active,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    }
    if download_url is not None:
        data["download_url"] = download_url
    return data
