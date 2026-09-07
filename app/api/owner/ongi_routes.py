"""Owner routes — 온기(ONGI) QR 결제 내역 조회.

관리자가 QR ↔ 가맹점 매핑(ongi_qr_mappings)을 해둔 QR의 결제만 보인다.
매핑이 없으면 빈 결과와 mapped=false 를 내려 화면에서 안내한다.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.owner._helpers import _get_owner_merchant, require_owner
from app.database import get_db
from app.models.ongi_qr_mapping import OngiQrMapping
from app.models.user import User
from app.services import ongi_query

router = APIRouter()


@router.get("/ongi/transactions")
def list_owner_ongi_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (paid_at 기준, KST)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (paid_at 기준, KST)"),
    qr_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="완료 | 취소"),
    search: Optional[str] = Query(None, description="결제자 이름 / 주문번호 검색"),
    merchant_id: Optional[int] = Query(None, description="ADMIN 이 특정 가맹점을 지정할 때만 사용"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    """내 매장에 매핑된 QR의 온기 결제 내역을 조회한다."""
    merchant = _get_owner_merchant(user, db, merchant_id)
    mappings = (
        db.query(OngiQrMapping)
        .filter(OngiQrMapping.merchant_id == merchant.id)
        .order_by(OngiQrMapping.qr_id)
        .all()
    )
    my_qr_ids = [m.qr_id for m in mappings]

    # 특정 QR 필터는 내 매장에 매핑된 QR만 허용한다 (남의 QR 조회 방지).
    if qr_id is not None:
        qr_scope = [qr_id] if qr_id in my_qr_ids else []
    else:
        qr_scope = my_qr_ids

    try:
        result = ongi_query.list_transactions(
            db, page=page, limit=limit, start_date=start_date, end_date=end_date,
            status=status, search=search, qr_ids=qr_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result["mapped"] = bool(my_qr_ids)
    result["qrs"] = [{"qr_id": m.qr_id, "qr_name": m.qr_name} for m in mappings]
    return result
