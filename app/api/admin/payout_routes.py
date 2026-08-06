"""Admin routes — payout-requests 관련."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.utils.kst import now_kst
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
    results = []
    for r in reqs:
        user = db.query(User).filter(User.id == r.requester_user_id).first()
        # 이 요청 자체는 차감에서 빼서, amount 와 바로 비교할 수 있는 잔액을 보여준다.
        available = get_available_payout(db, r.requester_user_id, r.role, exclude_payout_id=r.id)
        results.append({
            "id": r.id, "requester_user_id": r.requester_user_id,
            "requester_name": user.name if user else None,
            "role": r.role, "amount": float(r.amount),
            "available_balance": float(available),
            "bank_info": r.bank_info, "memo": r.memo,
            "status": r.status.value if r.status else None,
            "created_at": str(r.created_at),
            "reviewed_at": str(r.reviewed_at) if r.reviewed_at else None,
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
    pr.reviewed_at = now_kst().replace(tzinfo=None)
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "approved"}


@router.post("/payout-requests/{pid}/reject")
def reject_payout(pid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pr = db.query(PayoutRequest).filter(PayoutRequest.id == pid).first()
    if not pr:
        raise HTTPException(status_code=404)
    if pr.status != PayoutStatus.PENDING:
        raise HTTPException(status_code=400, detail="이미 처리된 페이아웃 요청입니다.")
    pr.status = PayoutStatus.REJECTED
    pr.reviewed_at = now_kst().replace(tzinfo=None)
    pr.reviewed_by = admin.id
    db.commit()
    return {"ok": True, "status": "rejected"}
