"""Owner receipt review management routes.

Split out of the original app/api/owner_routes.py.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.receipt_review import ReceiptReviewConfig, ReceiptReview

from app.api.owner._helpers import require_owner, _get_owner_merchant

router = APIRouter()


# ─── Receipt Review Management ────────────────────────────

@router.get("/receipt-review/config")
def get_receipt_review_config(db: Session = Depends(get_db), user: User = Depends(require_owner),
    merchant_id: Optional[int] = Query(None, description="최고관리자 전용: 대상 가맹점 ID"),
):
    """매장의 영수증 리뷰 설정 조회"""
    merchant = _get_owner_merchant(user, db, merchant_id)
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.merchant_id == merchant.id
    ).first()
    if not config:
        return {"exists": False}
    return {
        "exists": True,
        "id": config.id,
        "token": config.token,
        "place_url": config.place_url,
        "welcome_message": config.welcome_message,
        "is_active": config.is_active,
        "created_at": str(config.created_at),
        "review_url": f"/static/review.html?t={config.token}",
    }


@router.post("/receipt-review/config")
def create_or_update_receipt_review_config(
    place_url: Optional[str] = None,
    welcome_message: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """영수증 리뷰 설정 생성 또는 업데이트 (QR/NFC 토큰 발급)"""
    merchant = _get_owner_merchant(user, db)
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.merchant_id == merchant.id
    ).first()

    if not config:
        config = ReceiptReviewConfig(
            merchant_id=merchant.id,
            token=ReceiptReviewConfig.generate_token(),
            place_url=place_url or merchant.place_url,
            welcome_message=welcome_message or "방문해주셔서 감사합니다! 영수증 리뷰를 남겨주세요.",
        )
        db.add(config)
    else:
        if place_url is not None:
            config.place_url = place_url
        if welcome_message is not None:
            config.welcome_message = welcome_message
        config.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(config)
    return {
        "id": config.id,
        "token": config.token,
        "place_url": config.place_url,
        "welcome_message": config.welcome_message,
        "review_url": f"/static/review.html?t={config.token}",
    }


@router.post("/receipt-review/config/regenerate-token")
def regenerate_review_token(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """QR/NFC 토큰 재발급"""
    merchant = _get_owner_merchant(user, db)
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.merchant_id == merchant.id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="리뷰 설정이 없습니다. 먼저 설정을 생성하세요.")
    config.token = ReceiptReviewConfig.generate_token()
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return {"token": config.token, "review_url": f"/static/review.html?t={config.token}"}


@router.get("/receipt-review/list")
def list_receipt_reviews(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
    merchant_id: Optional[int] = Query(None, description="최고관리자 전용: 대상 가맹점 ID"),
):
    """영수증 리뷰 목록 조회"""
    merchant = _get_owner_merchant(user, db, merchant_id)
    q = db.query(ReceiptReview).filter(ReceiptReview.merchant_id == merchant.id)
    if status:
        q = q.filter(ReceiptReview.status == status)
    reviews = q.order_by(ReceiptReview.created_at.desc()).limit(limit).all()
    return [{
        "id": r.id,
        "customer_name": r.customer_name,
        "customer_phone": r.customer_phone,
        "receipt_image_url": r.receipt_image_url,
        "status": r.status,
        "review_completed": r.review_completed,
        "memo": r.memo,
        "created_at": str(r.created_at),
    } for r in reviews]


@router.put("/receipt-review/{review_id}/status")
def update_review_status(
    review_id: int,
    status: str = Query(..., pattern="^(pending|approved|rejected)$"),
    memo: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """영수증 리뷰 상태 변경 (승인/반려)"""
    merchant = _get_owner_merchant(user, db)
    review = db.query(ReceiptReview).filter(
        ReceiptReview.id == review_id,
        ReceiptReview.merchant_id == merchant.id,
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")
    review.status = status
    if memo is not None:
        review.memo = memo
    review.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": review.status}
