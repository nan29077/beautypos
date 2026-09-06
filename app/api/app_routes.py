"""안드로이드 앱용 공개 라우터 (인증 불필요).

앱은 로그인 전에도 업데이트를 확인·다운로드해야 하므로 이 두 엔드포인트는
JWT 를 요구하지 않는다. 노출 정보는 버전 메타와 APK 바이너리뿐이다.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.app_release import AppRelease
from app.services import app_release as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/app", tags=["app"])


@router.get("/latest-version")
def latest_version(db: Session = Depends(get_db)):
    """최신 활성 배포본 정보. 없으면 available=false.

    앱은 이 version_code 를 자신의 BuildConfig.VERSION_CODE 와 비교한다.
    """
    r = svc.latest_active(db)
    if not r:
        return {"available": False}
    return {
        "available": True,
        "version_code": r.version_code,
        "version_name": r.version_name,
        "notes": r.notes,
        "mandatory": r.is_mandatory,
        "file_size": r.file_size,
        "download_url": f"/api/app/download/{r.version_code}",
    }


def _apk_response(r: AppRelease) -> FileResponse:
    try:
        path = svc.apk_path(r.apk_filename)
    except ValueError:
        raise HTTPException(status_code=500, detail="release file record is invalid")
    import os
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="APK file not found on server")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=f"beautypos-{r.version_name}.apk",
    )


@router.get("/download/latest")
def download_latest(db: Session = Depends(get_db)):
    r = svc.latest_active(db)
    if not r:
        raise HTTPException(status_code=404, detail="no release available")
    return _apk_response(r)


@router.get("/download/{version_code}")
def download_version(version_code: int, db: Session = Depends(get_db)):
    r = db.query(AppRelease).filter(AppRelease.version_code == version_code).first()
    if not r:
        raise HTTPException(status_code=404, detail="release not found")
    return _apk_response(r)
