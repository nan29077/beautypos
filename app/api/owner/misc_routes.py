"""Owner misc routes: payout requests, merchant info, affiliate malls.

Split out of the original app/api/owner_routes.py.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.kst import fmt_kst
from app.models.user import User, UserRole
from app.models.settlement import PayoutRequest
from app.models.affiliate_mall import AffiliateMall
from app.services.settlement_service import get_available_payout
from app.schemas.schemas import PayoutRequestCreate

from app.api.owner._helpers import require_owner, _get_owner_merchant

router = APIRouter()


# ─── Payout Requests (원장 출금요청) ──────────────────────────

@router.get("/payout-requests")
def list_owner_payout_requests(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """본인이 신청한 출금요청 내역만 조회한다."""
    reqs = db.query(PayoutRequest).filter(
        PayoutRequest.requester_user_id == user.id,
    ).order_by(PayoutRequest.created_at.desc()).all()
    return [{
        "id": r.id, "amount": float(r.amount),
        "bank_info": r.bank_info, "memo": r.memo,
        "status": r.status.value if r.status else None,
        # DB 는 naive UTC 로 저장하고 화면에는 KST 로 내려준다.
        "created_at": fmt_kst(r.created_at),
        "reviewed_at": fmt_kst(r.reviewed_at),
    } for r in reqs]


@router.post("/payout-requests")
def create_owner_payout_request(
    req: PayoutRequestCreate, db: Session = Depends(get_db), user: User = Depends(require_owner),
):
    """정산금 출금을 신청한다. 최고관리자가 승인/거절한다."""
    _get_owner_merchant(user, db)  # 가맹점이 없는 계정은 신청할 수 없다
    available = get_available_payout(db, user.id, user.role)
    if Decimal(str(req.amount)) > available:
        raise HTTPException(status_code=400, detail=f"출금 가능 금액({available:,.0f}원)을 초과했습니다")
    pr = PayoutRequest(
        requester_user_id=user.id,
        role=user.role.value if isinstance(user.role, UserRole) else user.role,
        amount=req.amount,
        bank_info=req.bank_info,
        memo=req.memo,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return {"id": pr.id, "amount": float(pr.amount), "status": pr.status.value}


# ─── Merchant Info Update ──────────────────────────────────

@router.get("/merchant-info")
def get_merchant_info(db: Session = Depends(get_db), user: User = Depends(require_owner),
    merchant_id: Optional[int] = Query(None, description="최고관리자 전용: 대상 가맹점 ID"),
):
    """매장 상세 정보 조회"""
    merchant = _get_owner_merchant(user, db, merchant_id)
    return {
        "id": merchant.id,
        "name": merchant.name,
        "business_no": merchant.business_no,
        "address": merchant.address,
        "phone": merchant.phone,
        "category": merchant.category,
        "category_custom": merchant.category_custom,
        "place_url": merchant.place_url,
        "is_active": merchant.is_active,
        "display_category": merchant.display_category,
        "needs_staff_management": merchant.needs_staff_management,
        "created_at": str(merchant.created_at),
    }


@router.put("/merchant-info")
def update_merchant_info(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
    name: Optional[str] = None,
    business_no: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    category: Optional[str] = None,
    category_custom: Optional[str] = None,
    place_url: Optional[str] = None,
):
    """매장 정보 업데이트 (분야, 플레이스 URL 등)"""
    merchant = _get_owner_merchant(user, db)
    if name is not None:
        merchant.name = name
    if business_no is not None:
        merchant.business_no = business_no
    if address is not None:
        merchant.address = address
    if phone is not None:
        merchant.phone = phone
    if category is not None:
        merchant.category = category
    if category_custom is not None:
        merchant.category_custom = category_custom
    if place_url is not None:
        merchant.place_url = place_url
    db.commit()
    db.refresh(merchant)
    return {
        "ok": True,
        "category": merchant.category,
        "display_category": merchant.display_category,
        "needs_staff_management": merchant.needs_staff_management,
    }


# ═══════════════════════════════════════════════════════════
# AFFILIATE MALLS (제휴중개몰) — 골드회원 조회
# ═══════════════════════════════════════════════════════════

@router.get("/affiliate-malls")
def list_owner_affiliate_malls(
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """활성 제휴중개몰 목록 (원장용)"""
    malls = db.query(AffiliateMall).filter(
        AffiliateMall.is_active == True
    ).order_by(AffiliateMall.sort_order, AffiliateMall.id).all()
    return [{
        "id": m.id, "name": m.name, "logo_url": m.logo_url,
        "website_url": m.website_url, "description": m.description,
        "category": m.category, "commission_rate": m.commission_rate,
    } for m in malls]
