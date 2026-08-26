"""Shared helpers for the owner API route modules.

Split out of the original monolithic app/api/owner_routes.py so that every
sub-router (dashboard, staff, ad, review, misc) can reuse the same
merchant-lookup / date-range / role-check helpers without duplicating code.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.utils.kst import now_kst
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.auth.dependencies import require_roles

require_owner = require_roles([UserRole.ADMIN, UserRole.OWNER])


def _get_owner_merchant(
    user: User, db: Session, merchant_id: Optional[int] = None
) -> Merchant:
    """이 요청이 다룰 가맹점을 정한다.

    OWNER  — 본인 소유 가맹점. merchant_id 를 보내도 무시한다(남의 매장 조회 방지).
    ADMIN  — 소유한 가맹점이 없으므로 merchant_id 로 대상을 지정한다.
             지정하지 않으면 404("가맹점 없음")가 아니라 400 으로 무엇이 빠졌는지 알린다.

    원장 API 는 require_owner = [ADMIN, OWNER] 라 최고관리자도 들어올 수 있는데,
    예전에는 ADMIN 이 소유 가맹점이 없어 무조건 404 를 받았다.
    """
    if user.role == UserRole.ADMIN:
        if merchant_id is not None:
            m = db.query(Merchant).filter(Merchant.id == merchant_id).first()
            if not m:
                raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
            return m
        # 관리자 계정이 직접 가맹점을 소유한 경우(테스트 계정 등)는 그대로 쓴다.
        owned = db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()
        if owned:
            return owned
        raise HTTPException(
            status_code=400,
            detail="최고관리자는 조회할 가맹점을 merchant_id 로 지정해야 합니다",
        )

    m = db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="No merchant found for this owner")
    return m


def _date_range(range_str: str):
    now = now_kst().astimezone(timezone.utc).replace(tzinfo=None)
    if range_str == "day":
        return now - timedelta(days=1), now
    elif range_str == "week":
        return now - timedelta(weeks=1), now
    elif range_str == "month":
        return now - timedelta(days=30), now
    else:  # all
        return datetime(2000, 1, 1), now
