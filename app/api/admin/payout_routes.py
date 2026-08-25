"""Admin routes — payout-requests 관련."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from datetime import datetime

from app.utils.kst import fmt_kst
from app.database import get_db
from app.models.user import User
from app.models.settlement import PayoutRequest, PayoutStatus
from app.auth.dependencies import require_admin
from app.services.settlement_service import get_available_payout

router = APIRouter()


# ─── Payout Requests ────────────────────────────────────────

@router.get("/payout-requests")
def list_payout_requests(db: Session = Depends(get_db), _=Depends(require_admin)):
    reqs = db.query(PayoutRequest).order_by(PayoutRequest.created_at.desc()).all()
    # 신청자 이름은 한 번에 읽는다 (요청 수만큼 조회하지 않도록).
    requester_names = dict(
        db.query(User.id, User.name)
        .filter(User.id.in_({r.requester_user_id for r in reqs})).all()
    ) if reqs else {}
    results = []
    for r in reqs:
        requester_name = requester_names.get(r.requester_user_id)
        # 이 요청 자체는 차감에서 빼서, amount 와 바로 비교할 수 있는 잔액을 보여준다.
        available = get_available_payout(db, r.requester_user_id, r.role, exclude_payout_id=r.id)
        results.append({
            "id": r.id, "requester_user_id": r.requester_user_id,
            "requester_name": requester_name,
            "role": r.role, "amount": float(r.amount),
            "available_balance": float(available),
            "bank_info": r.bank_info, "memo": r.memo,
            "status": r.status.value if r.status else None,
            # DB 는 naive UTC 로 저장하고 화면에는 KST 로 내려준다 (app/utils/kst.py 규약).
            "created_at": fmt_kst(r.created_at),
            "reviewed_at": fmt_kst(r.reviewed_at),
        })
    return results


@router.post("/payout-requests/{pid}/approve")
def approve_payout(pid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pr = db.query(PayoutRequest).filter(PayoutRequest.id == pid).first()
    if not pr:
        raise HTTPException(status_code=404)
    if pr.status != PayoutStatus.PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 페이아웃 요청입니다.")
    # M-3: 승인 시점 잔액 재검증 (다른 요청이 먼저 처리됐을 수 있음)
    available = get_available_payout(db, pr.requester_user_id, pr.role, exclude_payout_id=pr.id)
    from decimal import Decimal
    if Decimal(str(pr.amount)) > available:
        raise HTTPException(status_code=400, detail=f"출금 가능 잔액({available:,.0f}원)이 부족해 승인할 수 없습니다")
    pr.status = PayoutStatus.APPROVED
    pr.reviewed_at = datetime.utcnow()
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "approved", "reviewed_at": fmt_kst(pr.reviewed_at)}


@router.post("/payout-requests/{pid}/reject")
def reject_payout(pid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pr = db.query(PayoutRequest).filter(PayoutRequest.id == pid).first()
    if not pr:
        raise HTTPException(status_code=404)
    if pr.status != PayoutStatus.PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 페이아웃 요청입니다.")
    pr.status = PayoutStatus.REJECTED
    pr.reviewed_at = datetime.utcnow()
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "rejected", "reviewed_at": fmt_kst(pr.reviewed_at)}
