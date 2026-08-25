"""매장 광고 키워드 등록·승인·조회 서비스.

승인 규칙
    매장(원장)이 등록·수정하면 '승인 대기'로 들어간다.
    최고관리자가 등록하면 즉시 '승인됨'이 된다 (등록자가 곧 승인자).
    자동 집행은 '승인됨 + 사용중'인 키워드만 쓴다.

키워드 순환
    매일 같은 키워드만 집행하면 패턴이 규칙적이라 눈에 띈다.
    pick_for_date() 가 날짜를 기준으로 등록 순서를 돌려가며 고른다.
"""
import re
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ad_keyword import (
    MerchantAdKeyword,
    AD_TYPE_ALL,
    KEYWORD_APPROVED,
    KEYWORD_MAX_LENGTH,
    KEYWORD_PENDING,
    KEYWORD_REJECTED,
    KEYWORD_STATUS_LABELS,
    MAX_KEYWORDS_PER_MERCHANT,
)
from app.models.plan import AD_EXECUTION_TYPE_CODES, AD_EXECUTION_TYPE_LABELS
from app.models.user import User, UserRole
from app.utils.kst import fmt_kst, today_kst

_WHITESPACE = re.compile(r"\s+")


def normalize_keyword(raw: str) -> str:
    """앞뒤 공백을 없애고 사이 공백을 하나로 줄인다.

    '강남  미용실 ' 과 '강남 미용실' 이 다른 키워드로 중복 등록되는 것을 막는다.
    """
    text = _WHITESPACE.sub(" ", (raw or "").strip())
    if not text:
        raise HTTPException(status_code=400, detail="키워드를 입력해주세요")
    if len(text) > KEYWORD_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"키워드는 {KEYWORD_MAX_LENGTH}자를 넘을 수 없습니다",
        )
    return text


def normalize_ad_type(raw: Optional[str]) -> str:
    """빈 값이면 '모든 광고 공통'을 뜻하는 빈 문자열로 둔다."""
    text = (raw or "").strip()
    if not text:
        return AD_TYPE_ALL
    if text not in AD_EXECUTION_TYPE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"광고 종류가 올바르지 않습니다 ({', '.join(AD_EXECUTION_TYPE_CODES)})",
        )
    return text


def ad_type_label(ad_type: str) -> str:
    return AD_EXECUTION_TYPE_LABELS.get(ad_type, "모든 광고") if ad_type else "모든 광고"


def to_dict(kw: MerchantAdKeyword) -> dict:
    return {
        "id": kw.id,
        "merchant_id": kw.merchant_id,
        "keyword": kw.keyword,
        "ad_type": kw.ad_type or "",
        "ad_type_label": ad_type_label(kw.ad_type),
        "priority": kw.priority,
        "is_active": bool(kw.is_active),
        "status": kw.status,
        "status_label": KEYWORD_STATUS_LABELS.get(kw.status, kw.status),
        "reject_reason": kw.reject_reason,
        "created_by_role": kw.created_by_role,
        "approved_at": fmt_kst(kw.approved_at),
        "created_at": fmt_kst(kw.created_at),
        "usable": kw.is_usable,
    }


# ─── 조회 ───────────────────────────────────────────────────

def get_or_404(db: Session, keyword_id: int) -> MerchantAdKeyword:
    kw = db.query(MerchantAdKeyword).filter(MerchantAdKeyword.id == keyword_id).first()
    if not kw:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")
    return kw


def list_for_merchant(db: Session, merchant_id: int, status: Optional[str] = None) -> list:
    q = db.query(MerchantAdKeyword).filter(MerchantAdKeyword.merchant_id == merchant_id)
    if status:
        q = q.filter(MerchantAdKeyword.status == status)
    return q.order_by(
        MerchantAdKeyword.priority.asc(), MerchantAdKeyword.id.asc()
    ).all()


def usable_keywords(db: Session, merchant_id: int, ad_type: str = "") -> list:
    """자동 집행에 쓸 수 있는 키워드. 해당 광고 전용 + 모든 광고 공통을 함께 돌려준다.

    P3 집행 엔진이 부르는 함수다. 여기서 걸러진 결과가 비면 그 매장은 집행 보류된다.
    """
    q = db.query(MerchantAdKeyword).filter(
        MerchantAdKeyword.merchant_id == merchant_id,
        MerchantAdKeyword.is_active == True,  # noqa: E712
        MerchantAdKeyword.status == KEYWORD_APPROVED,
    )
    if ad_type:
        q = q.filter(MerchantAdKeyword.ad_type.in_([ad_type, AD_TYPE_ALL]))
    return q.order_by(
        MerchantAdKeyword.priority.asc(), MerchantAdKeyword.id.asc()
    ).all()


def pick_for_date(keywords: list, target_date: Optional[date] = None, count: int = 1) -> list:
    """날짜를 기준으로 키워드를 돌려가며 고른다.

    매일 목록의 시작 지점을 하루씩 밀어, 같은 키워드만 반복 집행되지 않게 한다.
    등록 개수보다 많이 요청하면 있는 만큼만 돌려준다.
    """
    if not keywords:
        return []
    target_date = target_date or today_kst()
    count = max(1, min(count, len(keywords)))
    offset = target_date.toordinal() % len(keywords)
    rotated = keywords[offset:] + keywords[:offset]
    return rotated[:count]


# ─── 등록·수정 ──────────────────────────────────────────────

def _assert_capacity(db: Session, merchant_id: int) -> None:
    used = db.query(MerchantAdKeyword).filter(
        MerchantAdKeyword.merchant_id == merchant_id
    ).count()
    if used >= MAX_KEYWORDS_PER_MERCHANT:
        raise HTTPException(
            status_code=400,
            detail=f"키워드는 매장당 최대 {MAX_KEYWORDS_PER_MERCHANT}개까지 등록할 수 있습니다",
        )


def _assert_unique(db: Session, merchant_id: int, ad_type: str, keyword: str,
                   exclude_id: Optional[int] = None) -> None:
    q = db.query(MerchantAdKeyword).filter(
        MerchantAdKeyword.merchant_id == merchant_id,
        MerchantAdKeyword.ad_type == ad_type,
        MerchantAdKeyword.keyword == keyword,
    )
    if exclude_id:
        q = q.filter(MerchantAdKeyword.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=400, detail="이미 등록된 키워드입니다")


def create(
    db: Session,
    merchant_id: int,
    keyword: str,
    ad_type: Optional[str],
    priority: Optional[int],
    user: User,
) -> MerchantAdKeyword:
    """키워드를 등록한다. 관리자가 등록하면 승인 절차 없이 바로 쓸 수 있다."""
    clean_keyword = normalize_keyword(keyword)
    clean_type = normalize_ad_type(ad_type)
    _assert_capacity(db, merchant_id)
    _assert_unique(db, merchant_id, clean_type, clean_keyword)

    is_admin = user.role == UserRole.ADMIN
    kw = MerchantAdKeyword(
        merchant_id=merchant_id,
        keyword=clean_keyword,
        ad_type=clean_type,
        priority=max(0, int(priority or 0)),
        is_active=True,
        status=KEYWORD_APPROVED if is_admin else KEYWORD_PENDING,
        created_by=user.id,
        created_by_role="admin" if is_admin else "owner",
    )
    if is_admin:
        kw.approved_by = user.id
        kw.approved_at = _utcnow()
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


def update(
    db: Session,
    kw: MerchantAdKeyword,
    user: User,
    keyword: Optional[str] = None,
    ad_type: Optional[str] = None,
    priority: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> MerchantAdKeyword:
    """키워드를 수정한다.

    내용(키워드 문구·광고 종류)이 바뀌면 승인이 무의미해지므로
    매장이 수정한 경우 다시 '승인 대기'로 되돌린다.
    사용 여부·우선순위만 바꾸는 것은 승인 상태에 영향을 주지 않는다.
    """
    is_admin = user.role == UserRole.ADMIN
    content_changed = False

    if keyword is not None:
        clean = normalize_keyword(keyword)
        if clean != kw.keyword:
            _assert_unique(db, kw.merchant_id, kw.ad_type, clean, exclude_id=kw.id)
            kw.keyword = clean
            content_changed = True
    if ad_type is not None:
        clean_type = normalize_ad_type(ad_type)
        if clean_type != kw.ad_type:
            _assert_unique(db, kw.merchant_id, clean_type, kw.keyword, exclude_id=kw.id)
            kw.ad_type = clean_type
            content_changed = True
    if priority is not None:
        kw.priority = max(0, int(priority))
    if is_active is not None:
        kw.is_active = bool(is_active)

    if content_changed:
        if is_admin:
            kw.status = KEYWORD_APPROVED
            kw.approved_by = user.id
            kw.approved_at = _utcnow()
            kw.reject_reason = None
        else:
            kw.status = KEYWORD_PENDING
            kw.approved_by = None
            kw.approved_at = None
            kw.reject_reason = None

    db.commit()
    db.refresh(kw)
    return kw


def approve(db: Session, kw: MerchantAdKeyword, admin: User) -> MerchantAdKeyword:
    kw.status = KEYWORD_APPROVED
    kw.approved_by = admin.id
    kw.approved_at = _utcnow()
    kw.reject_reason = None
    db.commit()
    db.refresh(kw)
    return kw


def reject(db: Session, kw: MerchantAdKeyword, admin: User, reason: Optional[str]) -> MerchantAdKeyword:
    kw.status = KEYWORD_REJECTED
    kw.approved_by = admin.id
    kw.approved_at = _utcnow()
    kw.reject_reason = (reason or "").strip()[:255] or None
    db.commit()
    db.refresh(kw)
    return kw


def remove(db: Session, kw: MerchantAdKeyword) -> None:
    db.delete(kw)
    db.commit()


def pending_count(db: Session, merchant_id: Optional[int] = None) -> int:
    q = db.query(MerchantAdKeyword).filter(MerchantAdKeyword.status == KEYWORD_PENDING)
    if merchant_id:
        q = q.filter(MerchantAdKeyword.merchant_id == merchant_id)
    return q.count()


def _utcnow():
    from datetime import datetime
    return datetime.utcnow()
