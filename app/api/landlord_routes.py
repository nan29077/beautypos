"""
Landlord (임대인) API routes — 방긋페이
임차인 관리, QR코드 발급, 결제내역 조회, 대시보드 통계 등.
"""
import uuid
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Form
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from app.database import get_db
from app.models.user import User, UserRole
from app.models.landlord import (
    LandlordProfile, Tenant, RentPayment,
    PropertyType, PROPERTY_TYPE_KR,
    RentPaymentStatus, RentPaymentMethod,
)
from app.auth.dependencies import get_current_user, require_landlord

router = APIRouter(prefix="/api/landlord", tags=["landlord"])


def _get_profile(user: User, db: Session) -> LandlordProfile:
    profile = db.query(LandlordProfile).filter(LandlordProfile.user_id == user.id).first()
    if not profile:
        # Auto-create profile
        profile = LandlordProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


# ─── Dashboard Stats ──────────────────────────────────────
@router.get("/dashboard-stats")
def landlord_dashboard_stats(db: Session = Depends(get_db), user: User = Depends(require_landlord)):
    profile = _get_profile(user, db)
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    tenant_count = db.query(func.count(Tenant.id)).filter(
        Tenant.landlord_user_id == user.id, Tenant.is_active == True
    ).scalar()

    total_monthly_rent = db.query(func.coalesce(func.sum(Tenant.monthly_rent), 0)).filter(
        Tenant.landlord_user_id == user.id, Tenant.is_active == True
    ).scalar()

    this_month_str = now.strftime("%Y-%m")
    month_collected = db.query(func.coalesce(func.sum(RentPayment.amount), 0)).filter(
        RentPayment.landlord_user_id == user.id,
        RentPayment.payment_month == this_month_str,
        RentPayment.status == RentPaymentStatus.PAID,
    ).scalar()

    month_paid_count = db.query(func.count(RentPayment.id)).filter(
        RentPayment.landlord_user_id == user.id,
        RentPayment.payment_month == this_month_str,
        RentPayment.status == RentPaymentStatus.PAID,
    ).scalar()

    total_collected = db.query(func.coalesce(func.sum(RentPayment.amount), 0)).filter(
        RentPayment.landlord_user_id == user.id,
        RentPayment.status == RentPaymentStatus.PAID,
    ).scalar()

    # 최근 결제 5건
    recent = db.query(RentPayment).filter(
        RentPayment.landlord_user_id == user.id
    ).order_by(RentPayment.paid_at.desc()).limit(5).all()
    recent_list = []
    for r in recent:
        t = db.query(Tenant).filter(Tenant.id == r.tenant_id).first()
        recent_list.append({
            "id": r.id, "amount": r.amount, "status": r.status.value,
            "payment_month": r.payment_month, "card_brand": r.card_brand,
            "paid_at": str(r.paid_at),
            "tenant_name": t.name if t else "-",
            "unit": f"{t.property_name} {t.unit_number}" if t else "-",
        })

    # 월별 수금 추이 (최근 6개월)
    monthly_trend = []
    for i in range(5, -1, -1):
        m_date = now - timedelta(days=30 * i)
        m_str = m_date.strftime("%Y-%m")
        m_total = db.query(func.coalesce(func.sum(RentPayment.amount), 0)).filter(
            RentPayment.landlord_user_id == user.id,
            RentPayment.payment_month == m_str,
            RentPayment.status == RentPaymentStatus.PAID,
        ).scalar()
        monthly_trend.append({"month": m_str, "amount": float(m_total)})

    return {
        "building_name": profile.building_name or "내 건물",
        "address": profile.address,
        "tenant_count": tenant_count,
        "total_monthly_rent": float(total_monthly_rent),
        "month_collected": float(month_collected),
        "month_paid_count": month_paid_count,
        "collection_rate": round(month_collected / total_monthly_rent * 100, 1) if total_monthly_rent > 0 else 0,
        "total_collected": float(total_collected),
        "recent_payments": recent_list,
        "monthly_trend": monthly_trend,
    }


# ─── Profile ──────────────────────────────────────────────
@router.get("/profile")
def get_profile(db: Session = Depends(get_db), user: User = Depends(require_landlord)):
    p = _get_profile(user, db)
    # 등록된 임대물건명 목록 (프로필에 저장된 목록 + 임차인에서 추출한 고유값 합산)
    saved_names = []
    if p.property_names_list:
        try:
            saved_names = json.loads(p.property_names_list)
        except: saved_names = []
    tenant_properties = db.query(Tenant.property_name).filter(
        Tenant.landlord_user_id == user.id
    ).distinct().all()
    tenant_names = [tp[0] for tp in tenant_properties if tp[0]]
    property_names = sorted(set(saved_names + tenant_names))
    return {
        "building_name": p.building_name, "business_no": p.business_no,
        "address": p.address, "phone": p.phone,
        "bank_name": p.bank_name, "bank_account": p.bank_account, "bank_holder": p.bank_holder,
        "property_names": property_names,
    }

@router.put("/profile")
def update_profile(
    building_name: Optional[str] = Form(None), address: Optional[str] = Form(None),
    phone: Optional[str] = Form(None), business_no: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None), bank_account: Optional[str] = Form(None),
    bank_holder: Optional[str] = Form(None),
    property_names_list: Optional[str] = Form(None),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    p = _get_profile(user, db)
    if building_name is not None: p.building_name = building_name
    if address is not None: p.address = address
    if phone is not None: p.phone = phone
    if business_no is not None: p.business_no = business_no
    if bank_name is not None: p.bank_name = bank_name
    if bank_account is not None: p.bank_account = bank_account
    if bank_holder is not None: p.bank_holder = bank_holder
    if property_names_list is not None:
        # JSON array string으로 저장
        try:
            names = json.loads(property_names_list)
            p.property_names_list = json.dumps(names, ensure_ascii=False)
        except:
            p.property_names_list = property_names_list
    db.commit()
    return {"ok": True}


@router.post("/property-names")
def add_property_name(
    name: str = Form(...),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    """임대물건명 추가"""
    p = _get_profile(user, db)
    existing = []
    if p.property_names_list:
        try:
            existing = json.loads(p.property_names_list)
        except: existing = []
    name = name.strip()
    if name and name not in existing:
        existing.append(name)
        p.property_names_list = json.dumps(existing, ensure_ascii=False)
        db.commit()
    return {"ok": True, "property_names": existing}


@router.delete("/property-names")
def delete_property_name(
    name: str = Query(...),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    """임대물건명 삭제"""
    p = _get_profile(user, db)
    existing = []
    if p.property_names_list:
        try:
            existing = json.loads(p.property_names_list)
        except: existing = []
    if name in existing:
        existing.remove(name)
        p.property_names_list = json.dumps(existing, ensure_ascii=False)
        db.commit()
    return {"ok": True, "property_names": existing}


# ─── Tenants CRUD ─────────────────────────────────────────
@router.get("/tenants")
def list_tenants(db: Session = Depends(get_db), user: User = Depends(require_landlord)):
    tenants = db.query(Tenant).filter(Tenant.landlord_user_id == user.id).order_by(Tenant.created_at.desc()).all()
    result = []
    for t in tenants:
        # 이번달 납부 여부
        this_month = datetime.utcnow().strftime("%Y-%m")
        paid_this_month = db.query(RentPayment).filter(
            RentPayment.tenant_id == t.id,
            RentPayment.payment_month == this_month,
            RentPayment.status == RentPaymentStatus.PAID,
        ).first()
        result.append({
            "id": t.id, "name": t.name, "phone": t.phone, "email": t.email,
            "property_type": t.property_type.value,
            "property_type_kr": PROPERTY_TYPE_KR.get(t.property_type.value, "기타"),
            "property_name": t.property_name, "unit_number": t.unit_number,
            "monthly_rent": t.monthly_rent, "deposit": t.deposit,
            "rent_due_day": t.rent_due_day, "qr_token": t.qr_token,
            "is_recurring": t.is_recurring, "is_active": t.is_active,
            "memo": t.memo,
            "paid_this_month": bool(paid_this_month),
            "contract_start": str(t.contract_start) if t.contract_start else None,
            "contract_end": str(t.contract_end) if t.contract_end else None,
            "created_at": str(t.created_at),
        })
    return result

@router.post("/tenants")
def create_tenant(
    name: str = Form(...), phone: Optional[str] = Form(None), email: Optional[str] = Form(None),
    property_type: str = Form("officetel"), property_name: str = Form(...),
    unit_number: str = Form(...), monthly_rent: float = Form(...),
    deposit: float = Form(0), rent_due_day: int = Form(25),
    is_recurring: bool = Form(False), memo: Optional[str] = Form(None),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    tenant = Tenant(
        landlord_user_id=user.id, name=name, phone=phone, email=email,
        property_type=PropertyType(property_type), property_name=property_name,
        unit_number=unit_number, monthly_rent=monthly_rent, deposit=deposit,
        rent_due_day=rent_due_day, is_recurring=is_recurring, memo=memo,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {"ok": True, "id": tenant.id, "qr_token": tenant.qr_token}

@router.put("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: int,
    name: Optional[str] = Form(None), phone: Optional[str] = Form(None),
    property_name: Optional[str] = Form(None), unit_number: Optional[str] = Form(None),
    monthly_rent: Optional[float] = Form(None), rent_due_day: Optional[int] = Form(None),
    is_recurring: Optional[bool] = Form(None), memo: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    t = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.landlord_user_id == user.id).first()
    if not t: raise HTTPException(404, "임차인을 찾을 수 없습니다")
    if name is not None: t.name = name
    if phone is not None: t.phone = phone
    if property_name is not None: t.property_name = property_name
    if unit_number is not None: t.unit_number = unit_number
    if monthly_rent is not None: t.monthly_rent = monthly_rent
    if rent_due_day is not None: t.rent_due_day = rent_due_day
    if is_recurring is not None: t.is_recurring = is_recurring
    if memo is not None: t.memo = memo
    if is_active is not None: t.is_active = is_active
    db.commit()
    return {"ok": True}

@router.delete("/tenants/{tenant_id}")
def delete_tenant(tenant_id: int, db: Session = Depends(get_db), user: User = Depends(require_landlord)):
    t = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.landlord_user_id == user.id).first()
    if not t: raise HTTPException(404, "임차인을 찾을 수 없습니다")
    t.is_active = False
    db.commit()
    return {"ok": True}

@router.post("/tenants/{tenant_id}/regenerate-qr")
def regenerate_qr(tenant_id: int, db: Session = Depends(get_db), user: User = Depends(require_landlord)):
    t = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.landlord_user_id == user.id).first()
    if not t: raise HTTPException(404)
    t.qr_token = uuid.uuid4().hex[:16]
    db.commit()
    return {"ok": True, "qr_token": t.qr_token}


# ─── Payments ─────────────────────────────────────────────
@router.get("/payments")
def list_payments(
    tenant_id: Optional[int] = Query(None),
    month: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    q = db.query(RentPayment).filter(RentPayment.landlord_user_id == user.id)
    if tenant_id: q = q.filter(RentPayment.tenant_id == tenant_id)
    if month: q = q.filter(RentPayment.payment_month == month)
    if date_from:
        try:
            q = q.filter(RentPayment.paid_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except: pass
    if date_to:
        try:
            q = q.filter(RentPayment.paid_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except: pass
    if status and status != 'all':
        try:
            q = q.filter(RentPayment.status == RentPaymentStatus(status))
        except: pass
    payments = q.order_by(RentPayment.paid_at.desc()).all()
    result = []
    for p in payments:
        t = db.query(Tenant).filter(Tenant.id == p.tenant_id).first()
        result.append({
            "id": p.id, "amount": p.amount, "status": p.status.value,
            "payment_method": p.payment_method.value,
            "card_brand": p.card_brand, "approval_code": p.approval_code,
            "payment_month": p.payment_month, "memo": p.memo,
            "paid_at": str(p.paid_at),
            "tenant_id": p.tenant_id,
            "tenant_name": t.name if t else "-",
            "property_info": f"{t.property_name} {t.unit_number}" if t else "-",
        })
    return result


@router.get("/payment-summary")
def payment_summary(
    group_by: str = Query("month"),
    tenant_id: Optional[int] = Query(None),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    """결제 요약 - 월별/일별 그룹핑"""
    q = db.query(RentPayment).filter(
        RentPayment.landlord_user_id == user.id,
        RentPayment.status == RentPaymentStatus.PAID,
    )
    if tenant_id:
        q = q.filter(RentPayment.tenant_id == tenant_id)
    payments = q.order_by(RentPayment.paid_at.desc()).all()

    summary = {}
    for p in payments:
        if group_by == "day":
            key = str(p.paid_at)[:10] if p.paid_at else "unknown"
        else:
            key = p.payment_month or "unknown"
        if key not in summary:
            summary[key] = {"period": key, "count": 0, "amount": 0}
        summary[key]["count"] += 1
        summary[key]["amount"] += p.amount

    sorted_summary = sorted(summary.values(), key=lambda x: x["period"], reverse=True)
    return sorted_summary


@router.get("/monthly-status")
def landlord_monthly_status(
    month: str = Query(...),
    db: Session = Depends(get_db), user: User = Depends(require_landlord),
):
    """Get payment status for all tenants for a specific month (landlord view)."""
    tenants = db.query(Tenant).filter(
        Tenant.landlord_user_id == user.id, Tenant.is_active == True
    ).all()
    result = []
    for t in tenants:
        payment = db.query(RentPayment).filter(
            RentPayment.tenant_id == t.id,
            RentPayment.payment_month == month,
        ).first()
        result.append({
            "tenant_id": t.id,
            "tenant_name": t.name,
            "property_info": f"{t.property_name} {t.unit_number}",
            "monthly_rent": t.monthly_rent,
            "status": payment.status.value if payment else "unpaid",
            "paid_amount": payment.amount if payment else 0,
            "paid_at": str(payment.paid_at) if payment and payment.paid_at else None,
        })
    return result
