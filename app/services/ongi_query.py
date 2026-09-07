"""ongi_query — 온기(ONGI) 결제 로컬 사본 조회 (admin·owner 공용).

관리자 화면과 사장님 화면이 같은 필터·합계 로직을 쓰되, 사장님은 자기 매장에
매핑된 QR(qr_ids)로 범위가 제한된다는 점만 다르다. 잘못된 날짜 형식은
ValueError 를 던지고, 각 라우트가 HTTP 400 으로 변환한다.
"""
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.ongi_transaction import (
    OngiTransaction, ONGI_STATUS_CANCELLED, ONGI_STATUS_COMPLETED,
)


def serialize_transaction(row: OngiTransaction) -> dict:
    return {
        "id": row.id,
        "ongi_payment_id": row.ongi_payment_id,
        "payment_code": row.payment_code,
        "order_code": row.order_code,
        "status": row.status,
        "amount": int(row.amount) if row.amount is not None else None,
        "pay_price": int(row.pay_price) if row.pay_price is not None else None,
        "discount_price": int(row.discount_price) if row.discount_price is not None else None,
        "payment_type": row.payment_type,
        "division": row.division,
        "member_name": row.member_name,
        "qr_id": row.qr_id,
        "qr_name": row.qr_name,
        "auth_no": row.auth_no,
        "transaction_no": row.transaction_no,
        "paid_at": row.paid_at.strftime("%Y-%m-%d %H:%M:%S") if row.paid_at else None,
        "synced_at": row.synced_at.strftime("%Y-%m-%d %H:%M:%S") if row.synced_at else None,
    }


def _empty_result(page: int, limit: int) -> dict:
    return {
        "items": [],
        "pagination": {"current_page": page, "per_page": limit, "total": 0, "last_page": 1},
        "summary": {"completed_count": 0, "completed_amount": 0, "cancelled_count": 0},
    }


def list_transactions(
    db: Session,
    *,
    page: int = 1,
    limit: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    qr_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    qr_ids: Optional[Sequence[int]] = None,
) -> dict:
    """동기화된 온기 결제 내역을 페이지로 반환한다.

    qr_ids 가 주어지면 그 QR들의 결제만 본다 (OWNER 매장 범위 제한용).
    빈 시퀀스면 매핑된 QR이 없다는 뜻이므로 곧바로 빈 결과를 준다.
    합계(summary)는 페이지가 아니라 필터 전체 기준이다.
    """
    if qr_ids is not None and len(qr_ids) == 0:
        return _empty_result(page, limit)

    query = db.query(OngiTransaction)
    if qr_ids is not None:
        query = query.filter(OngiTransaction.qr_id.in_(list(qr_ids)))
    if start_date:
        try:
            query = query.filter(
                OngiTransaction.paid_at >= datetime.strptime(start_date, "%Y-%m-%d")
            )
        except ValueError:
            raise ValueError("start_date 형식은 YYYY-MM-DD 입니다")
    if end_date:
        try:
            query = query.filter(
                OngiTransaction.paid_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            )
        except ValueError:
            raise ValueError("end_date 형식은 YYYY-MM-DD 입니다")
    if qr_id is not None:
        query = query.filter(OngiTransaction.qr_id == qr_id)
    if status:
        query = query.filter(OngiTransaction.status == status)
    if search:
        keyword = f"%{search.strip()}%"
        query = query.filter(
            OngiTransaction.member_name.like(keyword)
            | OngiTransaction.order_code.like(keyword)
        )

    total = query.count()
    # FILTER 절은 MariaDB 가 지원하지 않으므로 CASE 로 집계한다.
    is_completed = OngiTransaction.status == ONGI_STATUS_COMPLETED
    is_cancelled = OngiTransaction.status == ONGI_STATUS_CANCELLED
    completed_sum, completed_count, cancelled_count = (
        query.with_entities(
            func.coalesce(
                func.sum(case((is_completed, OngiTransaction.pay_price), else_=0)), 0),
            func.coalesce(func.sum(case((is_completed, 1), else_=0)), 0),
            func.coalesce(func.sum(case((is_cancelled, 1), else_=0)), 0),
        ).one()
    )

    rows = (
        query.order_by(OngiTransaction.paid_at.desc(), OngiTransaction.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "items": [serialize_transaction(r) for r in rows],
        "pagination": {
            "current_page": page,
            "per_page": limit,
            "total": total,
            "last_page": max(1, -(-total // limit)),
        },
        "summary": {
            "completed_count": int(completed_count),
            "completed_amount": int(completed_sum),
            "cancelled_count": int(cancelled_count),
        },
    }
