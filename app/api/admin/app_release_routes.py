"""Admin routes — 안드로이드 앱 배포본(APK) 업로드·관리.

새 APK 업로드, 배포 이력 조회, 활성/비활성 전환(롤백), 삭제를 담당한다.
파일 저장·검증은 app.services.app_release 를 거친다.

주의: 업로드하는 APK 는 반드시 릴리스 keystore 로 서명돼야 기존 설치본이
업데이트를 받는다(서명 불일치 시 안드로이드가 설치 거부).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.app_release import AppRelease
from app.models.user import User
from app.services import app_release as svc

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/app-releases")
def list_app_releases(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """배포 이력 (version_code 내림차순)."""
    rows = db.query(AppRelease).order_by(AppRelease.version_code.desc()).all()
    latest = svc.latest_active(db)
    return {
        "items": [svc.serialize(r, download_url=f"/api/app/download/{r.version_code}") for r in rows],
        "latest_version_code": latest.version_code if latest else None,
    }


@router.post("/app-releases")
async def upload_app_release(
    apk: UploadFile = File(...),
    version_code: int = Form(...),
    version_name: str = Form(...),
    notes: Optional[str] = Form(None),
    is_mandatory: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """새 APK 를 업로드한다. version_code 는 앱의 그것보다 커야 업데이트로 감지된다."""
    version_name = (version_name or "").strip()
    if version_code <= 0:
        raise HTTPException(status_code=400, detail="version_code 는 1 이상의 정수여야 합니다")
    if not version_name:
        raise HTTPException(status_code=400, detail="version_name 을 입력해주세요")
    if db.query(AppRelease).filter(AppRelease.version_code == version_code).first():
        raise HTTPException(status_code=409, detail=f"version_code {version_code} 는 이미 등록돼 있습니다")

    content = await apk.read()
    try:
        filename, size = svc.save_apk(content, version_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    row = AppRelease(
        version_code=version_code,
        version_name=version_name,
        apk_filename=filename,
        file_size=size,
        notes=(notes or "").strip() or None,
        is_mandatory=bool(is_mandatory),
        is_active=True,
        uploaded_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("새 앱 배포본 업로드: v%s (code=%s, %s bytes)", version_name, version_code, size)
    return svc.serialize(row, download_url=f"/api/app/download/{version_code}")


@router.put("/app-releases/{release_id}/active")
def set_release_active(
    release_id: int,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """배포 노출 스위치. 문제가 생긴 버전을 내려 이전 버전으로 롤백할 때 쓴다."""
    row = db.query(AppRelease).filter(AppRelease.id == release_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="배포본을 찾을 수 없습니다")
    row.is_active = bool(is_active)
    db.commit()
    db.refresh(row)
    return svc.serialize(row, download_url=f"/api/app/download/{row.version_code}")


@router.delete("/app-releases/{release_id}")
def delete_app_release(
    release_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """배포본을 삭제한다(메타 + APK 파일)."""
    row = db.query(AppRelease).filter(AppRelease.id == release_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="배포본을 찾을 수 없습니다")
    svc.delete_apk_file(row.apk_filename)
    db.delete(row)
    db.commit()
    return {"ok": True, "deleted_id": release_id}
