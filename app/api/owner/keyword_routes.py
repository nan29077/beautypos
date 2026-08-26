"""Owner routes — 내 매장의 광고 집행 키워드.

여기서 등록·수정한 키워드는 '승인 대기' 상태로 들어가며,
최고관리자가 승인해야 자동 집행에 쓰인다.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.owner._helpers import _get_owner_merchant, require_owner
from app.database import get_db
from app.models.ad_keyword import (
    MerchantAdKeyword, KEYWORD_STATUSES, MAX_KEYWORDS_PER_MERCHANT,
)
from app.models.plan import AD_EXECUTION_TYPES
from app.models.user import User
from app.schemas.schemas import AdKeywordCreate, AdKeywordUpdate
from app.services import ad_keyword

router = APIRouter()


def _own_keyword(db: Session, keyword_id: int, merchant_id: int) -> MerchantAdKeyword:
    """다른 매장의 키워드를 건드리지 못하게 소유를 확인한다."""
    kw = ad_keyword.get_or_404(db, keyword_id)
    if kw.merchant_id != merchant_id:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")
    return kw


@router.get("/ad/keywords")
def list_my_keywords(db: Session = Depends(get_db), user: User = Depends(require_owner),
    merchant_id: Optional[int] = Query(None, description="최고관리자 전용: 대상 가맹점 ID"),
):
    """내 매장 키워드 목록과 승인 현황."""
    merchant = _get_owner_merchant(user, db, merchant_id)
    rows = ad_keyword.list_for_merchant(db, merchant.id)
    usable = [k for k in rows if k.is_usable]
    return {
        "keywords": [ad_keyword.to_dict(k) for k in rows],
        "usable_count": len(usable),
        "pending_count": ad_keyword.pending_count(db, merchant.id),
        "statuses": [{"code": c, "label": l} for c, l in KEYWORD_STATUSES],
        "ad_types": [{"code": c, "label": l} for c, l in AD_EXECUTION_TYPES],
        "max_per_merchant": MAX_KEYWORDS_PER_MERCHANT,
        # 승인된 키워드가 하나도 없으면 자동 집행이 보류된다 — 화면에서 크게 안내한다.
        "dispatch_blocked": len(usable) == 0,
    }


@router.post("/ad/keywords")
def create_my_keyword(
    req: AdKeywordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """키워드를 등록한다. 관리자 승인 후 집행에 쓰인다."""
    merchant = _get_owner_merchant(user, db)
    kw = ad_keyword.create(db, merchant.id, req.keyword, req.ad_type, req.priority, user)
    return ad_keyword.to_dict(kw)


@router.put("/ad/keywords/{keyword_id}")
def update_my_keyword(
    keyword_id: int,
    req: AdKeywordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """키워드를 수정한다. 문구나 광고 종류를 바꾸면 다시 승인을 받아야 한다."""
    merchant = _get_owner_merchant(user, db)
    kw = _own_keyword(db, keyword_id, merchant.id)
    kw = ad_keyword.update(
        db, kw, user,
        keyword=req.keyword, ad_type=req.ad_type,
        priority=req.priority, is_active=req.is_active,
    )
    return ad_keyword.to_dict(kw)


@router.delete("/ad/keywords/{keyword_id}")
def delete_my_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    merchant = _get_owner_merchant(user, db)
    kw = _own_keyword(db, keyword_id, merchant.id)
    ad_keyword.remove(db, kw)
    return {"ok": True, "id": keyword_id}
