"""Admin routes — 온기(ONGI) QR 결제 연동 설정.

API 키·노티 시크릿 등록/삭제, 연동 설정(기준 URL·API MID·동기화 주기),
연결 테스트, 결제 내역 조회(온기 실시간 프록시 + 로컬 사본), 수동 동기화를
담당한다. 온기 호출은 모두 app.services.ongi 어댑터를 거친다.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.ongi_transaction import (
    OngiTransaction, ONGI_STATUS_CANCELLED, ONGI_STATUS_COMPLETED,
)
from app.models.user import User
from app.schemas.schemas import OngiApiKeyUpdate, OngiNotifySecretUpdate, OngiSettingsUpdate
from app.services import ongi, ongi_sync

router = APIRouter()

# 발급 규칙이 바뀔 수 있으므로 길이 하한만 확인한다.
MIN_KEY_LENGTH = 20


@router.get("/ongi/config")
def get_ongi_config(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """연동 상태와 설정을 반환한다. API 키·시크릿 평문은 절대 내보내지 않는다."""
    return ongi.status_summary(db)


@router.put("/ongi/config")
def update_ongi_config(
    req: OngiSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """연동 설정을 수정한다. 보내지 않은 항목은 기존 값을 유지한다."""
    current = ongi.get_settings(db)
    incoming = req.model_dump(exclude_unset=True)

    enabled = incoming.pop("enabled", None)
    if enabled is not None:
        if enabled and not ongi.get_api_key(db):
            raise HTTPException(
                status_code=400,
                detail="API 키를 먼저 등록해야 연동을 켤 수 있습니다",
            )
        ongi.set_enabled(db, enabled)

    current.update({k: v for k, v in incoming.items() if v is not None})
    ongi.save_settings(db, current)
    return ongi.status_summary(db)


@router.post("/ongi/api-key")
def save_ongi_api_key(
    req: OngiApiKeyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """API 키를 암호화해 저장/갱신한다."""
    key = (req.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API 키를 입력해주세요")
    if len(key) < MIN_KEY_LENGTH:
        raise HTTPException(status_code=400, detail="API 키가 너무 짧습니다. 값을 다시 확인해주세요")
    ongi.save_api_key(db, key)
    return ongi.status_summary(db)


@router.delete("/ongi/api-key")
def delete_ongi_api_key(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """저장된 API 키를 삭제하고 연동을 끈다."""
    if not ongi.delete_api_key(db):
        raise HTTPException(status_code=404, detail="등록된 API 키가 없습니다")
    return ongi.status_summary(db)


@router.post("/ongi/notify-secret")
def save_ongi_notify_secret(
    req: OngiNotifySecretUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """결제 노티 HMAC 시크릿(ongi_nt_…)을 암호화해 저장/갱신한다."""
    secret = (req.secret or "").strip()
    if not secret:
        raise HTTPException(status_code=400, detail="시크릿 키를 입력해주세요")
    ongi.save_notify_secret(db, secret)
    return ongi.status_summary(db)


@router.delete("/ongi/notify-secret")
def delete_ongi_notify_secret(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """저장된 노티 시크릿을 삭제한다."""
    if not ongi.delete_notify_secret(db):
        raise HTTPException(status_code=404, detail="등록된 시크릿이 없습니다")
    return ongi.status_summary(db)


@router.get("/ongi/test")
async def test_ongi_connection(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """저장된 키로 결제 내역 1건을 조회해 연동 상태를 확인한다."""
    return await ongi.test_connection(db)


@router.get("/ongi/payments")
async def list_ongi_payments(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    qr_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None, description="완료 | 취소"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """온기 결제 내역을 실시간 조회한다 (온기 API 프록시)."""
    try:
        return await ongi.list_payments(
            db, page=page, limit=limit,
            start_date=start_date, end_date=end_date, qr_id=qr_id, state=state,
        )
    except ongi.OngiError as exc:
        raise HTTPException(status_code=502 if exc.retryable else 400, detail=exc.message)


@router.get("/ongi/payments/{payment_id}")
async def get_ongi_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """온기 결제 내역 단건을 실시간 조회한다."""
    try:
        return await ongi.get_payment(db, payment_id)
    except ongi.OngiError as exc:
        raise HTTPException(status_code=502 if exc.retryable else 400, detail=exc.message)


@router.post("/ongi/sync")
async def run_ongi_sync(_: User = Depends(require_admin)):
    """온기 결제 동기화를 즉시 실행한다 (주기·잠금 무시)."""
    return await ongi_sync.run_once(force=True)


def _serialize_transaction(row: OngiTransaction) -> dict:
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


@router.get("/ongi/transactions")
def list_ongi_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (paid_at 기준, KST)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (paid_at 기준, KST)"),
    qr_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="완료 | 취소"),
    search: Optional[str] = Query(None, description="결제자 이름 / 주문번호 검색"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """로컬에 동기화된 온기 결제 내역을 조회한다 (대시보드 데이터 소스).

    합계(summary)는 페이지가 아니라 필터 전체 기준이다.
    """
    query = db.query(OngiTransaction)
    if start_date:
        try:
            query = query.filter(
                OngiTransaction.paid_at >= datetime.strptime(start_date, "%Y-%m-%d")
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 형식은 YYYY-MM-DD 입니다")
    if end_date:
        try:
            query = query.filter(
                OngiTransaction.paid_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 형식은 YYYY-MM-DD 입니다")
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
        "items": [_serialize_transaction(r) for r in rows],
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


@router.get("/ongi/qrs")
async def list_ongi_qrs(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    status: Optional[str] = Query(None, description="활성 | 비활성"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """온기 QR 코드 목록을 조회한다 (결제 내역의 qrId 이름 매핑용)."""
    try:
        return await ongi.list_qrs(db, page=page, limit=limit, status=status, search=search)
    except ongi.OngiError as exc:
        raise HTTPException(status_code=502 if exc.retryable else 400, detail=exc.message)
