"""Admin routes — 매장 광고 집행 키워드 관리와 승인.

매장(원장)이 등록한 키워드는 승인 대기 상태로 들어오며, 여기서 승인해야
자동 집행에 쓰인다. 관리자가 직접 등록한 키워드는 즉시 사용 가능하다.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.ad_keyword import (
    MerchantAdKeyword, KEYWORD_STATUSES, KEYWORD_STATUS_CODES, MAX_KEYWORDS_PER_MERCHANT,
)
from app.models.merchant import Merchant
from app.models.plan import AD_EXECUTION_TYPES
from app.models.user import User
from app.schemas.schemas import AdKeywordCreate, AdKeywordReject, AdKeywordUpdate
from app.services import ad_keyword

router = APIRouter()


def _with_merchant(db: Session, rows: list) -> list:
    """키워드 목록에 가맹점 이름을 붙인다."""
    if not rows:
        return []
    names = dict(
        db.query(Merchant.id, Merchant.name)
        .filter(Merchant.id.in_({r.merchant_id for r in rows}))
        .all()
    )
    out = []
    for row in rows:
        item = ad_keyword.to_dict(row)
        item["merchant_name"] = names.get(row.merchant_id, "-")
        out.append(item)
    return out


@router.get("/ad-keywords")
def list_ad_keywords(
    status: Optional[str] = Query(default=None, description="pending | approved | rejected"),
    merchant_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """키워드 목록. 승인 대기 건이 먼저 오도록 정렬한다."""
    if status and status not in KEYWORD_STATUS_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"상태가 올바르지 않습니다 ({', '.join(KEYWORD_STATUS_CODES)})",
        )
    q = db.query(MerchantAdKeyword)
    if status:
        q = q.filter(MerchantAdKeyword.status == status)
    if merchant_id:
        q = q.filter(MerchantAdKeyword.merchant_id == merchant_id)
    # 승인 대기(pending)가 approved/rejected 보다 앞에 오도록 상태명 오름차순 정렬 후
    # 최근 등록 순으로 본다.
    rows = q.order_by(
        MerchantAdKeyword.status.asc(),
        MerchantAdKeyword.created_at.desc(),
    ).all()
    return {
        "keywords": _with_merchant(db, rows),
        "pending_count": ad_keyword.pending_count(db),
        "statuses": [{"code": c, "label": l} for c, l in KEYWORD_STATUSES],
        "ad_types": [{"code": c, "label": l} for c, l in AD_EXECUTION_TYPES],
        "max_per_merchant": MAX_KEYWORDS_PER_MERCHANT,
    }


@router.post("/merchants/{merchant_id}/ad-keywords")
def create_ad_keyword(
    merchant_id: int,
    req: AdKeywordCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """관리자가 직접 키워드를 등록한다 (등록과 동시에 승인됨)."""
    if not db.query(Merchant).filter(Merchant.id == merchant_id).first():
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    kw = ad_keyword.create(db, merchant_id, req.keyword, req.ad_type, req.priority, admin)
    return ad_keyword.to_dict(kw)


@router.put("/ad-keywords/{keyword_id}")
def update_ad_keyword(
    keyword_id: int,
    req: AdKeywordUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    kw = ad_keyword.get_or_404(db, keyword_id)
    kw = ad_keyword.update(
        db, kw, admin,
        keyword=req.keyword, ad_type=req.ad_type,
        priority=req.priority, is_active=req.is_active,
    )
    return ad_keyword.to_dict(kw)


@router.post("/ad-keywords/{keyword_id}/approve")
def approve_ad_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """승인하면 다음 자동 집행부터 이 키워드가 쓰인다."""
    kw = ad_keyword.get_or_404(db, keyword_id)
    return ad_keyword.to_dict(ad_keyword.approve(db, kw, admin))


@router.post("/ad-keywords/{keyword_id}/reject")
def reject_ad_keyword(
    keyword_id: int,
    req: AdKeywordReject,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """반려한다. 사유를 남기면 매장 화면에 그대로 보인다."""
    kw = ad_keyword.get_or_404(db, keyword_id)
    return ad_keyword.to_dict(ad_keyword.reject(db, kw, admin, req.reason))


@router.delete("/ad-keywords/{keyword_id}")
def delete_ad_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    kw = ad_keyword.get_or_404(db, keyword_id)
    ad_keyword.remove(db, kw)
    return {"ok": True, "id": keyword_id}
