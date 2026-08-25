"""Admin routes — 리워드팝 광고 자동집행 연동 설정.

API 키 등록·삭제, 연동 설정(기준 URL·인증 방식·경로·집행 시각·드라이런),
연결 테스트, 포인트 잔액 조회를 담당한다. 실제 호출은 모두
app.services.rewardpop 어댑터를 거친다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.schemas import RewardpopApiKeyUpdate, RewardpopSettingsUpdate
from app.services import rewardpop

router = APIRouter()

# 키 형식 검증 — 리워드팝 키는 base64url 32바이트(43자)로 보이지만
# 발급 규칙이 바뀔 수 있으므로 길이 하한만 확인한다.
MIN_KEY_LENGTH = 20


@router.get("/rewardpop/config")
def get_rewardpop_config(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """연동 상태와 설정을 반환한다. API 키 평문은 절대 내보내지 않는다."""
    return rewardpop.status_summary(db)


@router.put("/rewardpop/config")
def update_rewardpop_config(
    req: RewardpopSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """연동 설정을 수정한다. 보내지 않은 항목은 기존 값을 유지한다."""
    current = rewardpop.get_settings(db)
    incoming = req.model_dump(exclude_unset=True)

    enabled = incoming.pop("enabled", None)
    if enabled is not None:
        if enabled and not rewardpop.get_api_key(db):
            raise HTTPException(
                status_code=400,
                detail="API 키를 먼저 등록해야 연동을 켤 수 있습니다",
            )
        rewardpop.set_enabled(db, enabled)

    if incoming.get("auth_style") and incoming["auth_style"] not in rewardpop.AUTH_STYLE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"인증 방식이 올바르지 않습니다 ({', '.join(rewardpop.AUTH_STYLE_CODES)})",
        )

    current.update({k: v for k, v in incoming.items() if v is not None})
    rewardpop.save_settings(db, current)
    return rewardpop.status_summary(db)


@router.post("/rewardpop/api-key")
def save_rewardpop_api_key(
    req: RewardpopApiKeyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """API 키를 암호화해 저장/갱신한다."""
    key = (req.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API 키를 입력해주세요")
    if len(key) < MIN_KEY_LENGTH:
        raise HTTPException(status_code=400, detail="API 키가 너무 짧습니다. 값을 다시 확인해주세요")
    rewardpop.save_api_key(db, key)
    return rewardpop.status_summary(db)


@router.delete("/rewardpop/api-key")
def delete_rewardpop_api_key(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """저장된 API 키를 삭제하고 연동을 끈다."""
    if not rewardpop.delete_api_key(db):
        raise HTTPException(status_code=404, detail="등록된 API 키가 없습니다")
    return rewardpop.status_summary(db)


@router.get("/rewardpop/test")
async def test_rewardpop_connection(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """저장된 키로 실제 요청을 보내 연동 상태를 확인한다."""
    return await rewardpop.test_connection(db)


@router.get("/rewardpop/balance")
async def get_rewardpop_balance(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """리워드팝 포인트 잔액을 조회한다."""
    if not await run_in_threadpool(rewardpop.get_api_key, db):
        raise HTTPException(status_code=400, detail="API 키가 등록되지 않았습니다")
    try:
        return {"ok": True, **await rewardpop.get_balance(db)}
    except rewardpop.SpecMissing as exc:
        return {"ok": False, "spec_missing": True, "detail": exc.message}
    except rewardpop.RewardpopError as exc:
        return {"ok": False, "retryable": exc.retryable, "detail": exc.message}
