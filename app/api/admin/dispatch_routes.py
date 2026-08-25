"""Admin routes — 광고 자동 집행 실행·조회.

미리보기(무엇이 나갈지), 수동 실행, 집행 이력, 실패 건 재시도를 담당한다.
실제 계산과 전송은 app.services.ad_dispatch 가 한다.
"""
from datetime import date as date_cls, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.ad_dispatch import (
    AdDispatch, DISPATCH_STATUSES, DISPATCH_STATUS_CODES, SKIP_REASON_LABELS,
)
from app.models.merchant import Merchant
from app.models.user import User
from app.schemas.schemas import AdDispatchRun
from app.services import ad_dispatch, rewardpop
from app.utils.kst import today_kst

router = APIRouter()


def _parse_date(value: Optional[str]) -> date_cls:
    if not value:
        return today_kst()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD 입니다")


def _with_merchant_names(db: Session, rows: list) -> list:
    if not rows:
        return []
    names = dict(
        db.query(Merchant.id, Merchant.name)
        .filter(Merchant.id.in_({r.merchant_id for r in rows}))
        .all()
    )
    return [ad_dispatch.to_dict(r, names.get(r.merchant_id, "-")) for r in rows]


@router.get("/ad-dispatch/preview")
def preview_dispatch(
    date: Optional[str] = Query(default=None, description="기준일 (YYYY-MM-DD, 기본 오늘)"),
    merchant_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """오늘 무엇이 나갈지 계산해서 보여준다. 아무것도 전송하지 않는다."""
    return ad_dispatch.build_plan(db, _parse_date(date), merchant_id)


@router.post("/ad-dispatch/run")
async def run_dispatch(
    req: AdDispatchRun,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """집행을 지금 실행한다.

    멱등하므로 여러 번 눌러도 같은 날 같은 가맹점에 두 번 나가지 않는다.
    dry_run 을 지정하지 않으면 연동 설정에 저장된 값을 따른다.
    """
    return await ad_dispatch.run(
        db,
        target_date=req.execution_date or today_kst(),
        merchant_id=req.merchant_id,
        dry_run=req.dry_run,
        actor_id=admin.id,
    )


@router.get("/ad-dispatch")
def list_dispatches(
    date: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    merchant_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """집행 이력. 기본은 기준일 하루치를 본다."""
    if status and status not in DISPATCH_STATUS_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"상태가 올바르지 않습니다 ({', '.join(DISPATCH_STATUS_CODES)})",
        )
    q = db.query(AdDispatch).filter(AdDispatch.execution_date == _parse_date(date))
    if status:
        q = q.filter(AdDispatch.status == status)
    if merchant_id:
        q = q.filter(AdDispatch.merchant_id == merchant_id)
    rows = q.order_by(AdDispatch.id.desc()).limit(limit).all()

    settings = rewardpop.get_settings(db)
    return {
        "date": str(_parse_date(date)),
        "dispatches": _with_merchant_names(db, rows),
        "statuses": [{"code": c, "label": l} for c, l in DISPATCH_STATUSES],
        "skip_reason_labels": SKIP_REASON_LABELS,
        "dry_run": bool(settings.get("dry_run", True)),
        "integration_enabled": rewardpop.is_enabled(db),
    }


@router.post("/ad-dispatch/{dispatch_id}/retry")
async def retry_dispatch(
    dispatch_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """실패한 집행을 다시 시도한다 (드라이런이 아닌 실제 전송)."""
    row = db.query(AdDispatch).filter(AdDispatch.id == dispatch_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="집행 기록을 찾을 수 없습니다")
    if not row.retryable:
        raise HTTPException(
            status_code=400,
            detail="재시도할 수 있는 상태가 아닙니다 (실패 상태이며 재시도 한도 이내여야 합니다)",
        )
    row = await ad_dispatch.retry(db, row, admin.id)
    return ad_dispatch.to_dict(row, row.merchant.name if row.merchant else None)
