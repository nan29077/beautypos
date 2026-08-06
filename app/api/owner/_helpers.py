"""Shared helpers for the owner API route modules.

Split out of the original monolithic app/api/owner_routes.py so that every
sub-router (dashboard, staff, ad, review, misc) can reuse the same
merchant-lookup / date-range / role-check helpers without duplicating code.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.utils.kst import now_kst
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.auth.dependencies import require_roles

require_owner = require_roles([UserRole.ADMIN, UserRole.OWNER])


def _get_owner_merchant(user: User, db: Session) -> Merchant:
    """Get the merchant owned by this user."""
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
