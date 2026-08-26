"""CRM 고객 CRUD, 타임라인, 방문 기록, 시술 메뉴, 예약 관리.

포인트 적립/차감(고객 자산)은 마케팅과 성격이 가까워 campaign_routes.py 에 있다.
"""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.staff import Staff
from app.models.crm import (
    CrmCustomer, CrmService, CrmServicePrice, CrmVisit, CrmReservation, CrmPointLog,
    CrmMessageLog, CrmCoupon,
    ReservationStatus, RESERVATION_STATUS_KR, MessageChannel, MessageStatus,
)
from app.utils.kst import today_kst
from app.api.crm._helpers import (
    CrmContext, get_crm_context,
    _staff_name_map, _effective_scope, _require_crm_management, _require_owner_admin,
    _customer_stats, _serialize_customer, _is_birthday_soon,
    _parse_dt, _parse_date,
    _assert_staff_in_merchant,
)

router = APIRouter()


# ─── 스키마 ─────────────────────────────────────────────────

class CustomerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    gender: Optional[str] = None
    birthday: Optional[str] = None
    anniversary: Optional[str] = None
    memo: Optional[str] = None
    allergy_memo: Optional[str] = None
    hair_memo: Optional[str] = None
    photo_url: Optional[str] = None
    tags: Optional[List[str]] = None
    assigned_staff_id: Optional[int] = None
    preferred_staff_id: Optional[int] = None
    preferred_service: Optional[str] = None


class CustomerUpdate(CustomerIn):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceIn(BaseModel):
    name: str
    category: Optional[str] = None
    price: float = 0
    duration_min: int = 60


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    duration_min: Optional[int] = None
    is_active: Optional[bool] = None


class ServicePriceIn(BaseModel):
    staff_id: int
    price: float


class VisitIn(BaseModel):
    customer_id: int
    staff_id: Optional[int] = None
    service_name: Optional[str] = None
    amount: float = 0
    memo: Optional[str] = None
    visit_date: Optional[str] = None
    points_earned: Optional[int] = None


class ReservationIn(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    staff_id: Optional[int] = None
    service_name: Optional[str] = None
    reserved_at: str
    duration_min: Optional[int] = None
    memo: Optional[str] = None
    force: bool = False   # 충돌 무시 강제 등록


class ReservationUpdate(BaseModel):
    status: Optional[str] = None
    staff_id: Optional[int] = None
    service_name: Optional[str] = None
    reserved_at: Optional[str] = None
    duration_min: Optional[int] = None
    memo: Optional[str] = None


# ─── Staff ──────────────────────────────────────────────────

@router.get("/staff")
def crm_staff(ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    rows = db.query(Staff).filter(Staff.merchant_id == ctx.merchant_id, Staff.is_active == True).all()
    return [{"id": s.id, "name": s.name, "staff_code": s.staff_code,
             "is_me": s.id == ctx.staff_id} for s in rows]


@router.get("/me")
def crm_me(ctx: CrmContext = Depends(get_crm_context)):
    return {"role": ctx.role.value, "merchant_id": ctx.merchant_id,
            "merchant_name": ctx.merchant.name, "staff_id": ctx.staff_id,
            "is_designer": ctx.is_designer}


# ─── Customers ──────────────────────────────────────────────

def _interval_trend_increasing(intervals: List[int]) -> bool:
    """방문 간격이 갈수록 길어지는 추세인지 판정 (전반부 평균 대비 후반부 평균 비교)."""
    if len(intervals) < 2:
        return False
    mid = len(intervals) // 2 or 1
    first_half = intervals[:mid]
    second_half = intervals[mid:] or intervals[mid - 1:]
    if not first_half or not second_half:
        return False
    return (sum(second_half) / len(second_half)) > (sum(first_half) / len(first_half))


@router.get("/customers")
def list_customers(
    search: Optional[str] = None,
    tag: Optional[str] = None,
    grade: Optional[str] = None,
    birthday_soon: Optional[bool] = Query(None, description="true: 7일 이내 생일 고객만"),
    sort: Optional[str] = Query(None, description="last_visit|total_spent|visit_count (미지정 시 기존 정렬 유지)"),
    scope: str = Query("auto", description="auto/mine/all"),
    ctx: CrmContext = Depends(get_crm_context),
    db: Session = Depends(get_db),
):
    q = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id)
    # 디자이너 권한 스코프: 기본은 본인 담당/선호 고객
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    if use_mine and ctx.staff_id:
        q = q.filter(or_(CrmCustomer.assigned_staff_id == ctx.staff_id,
                         CrmCustomer.preferred_staff_id == ctx.staff_id))
    if search:
        like = f"%{search}%"
        q = q.filter(or_(CrmCustomer.name.like(like), CrmCustomer.phone.like(like)))
    customers = q.order_by(CrmCustomer.created_at.desc()).all()
    now = datetime.utcnow()
    stats = _customer_stats(db, ctx.merchant_id)
    staff_names = _staff_name_map(db, ctx.merchant_id)
    result = [_serialize_customer(c, stats, staff_names, now) for c in customers]
    if tag:
        result = [c for c in result if tag in c["tags"] or tag in c["auto_tags"]]
    if grade:
        result = [c for c in result if c["grade"] == grade]
    if birthday_soon:
        today = today_kst()
        birthdays = {c.id: c.birthday for c in customers}
        result = [c for c in result if _is_birthday_soon(birthdays.get(c["id"]), today)]
    if sort == "last_visit":
        result.sort(key=lambda c: c["last_visit"] or "", reverse=True)
    elif sort == "total_spent":
        result.sort(key=lambda c: c["total_spent"], reverse=True)
    elif sort == "visit_count":
        result.sort(key=lambda c: c["visit_count"], reverse=True)
    return result


@router.post("/customers")
def create_customer(req: CustomerIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _assert_staff_in_merchant(db, ctx, req.assigned_staff_id, req.preferred_staff_id)
    c = CrmCustomer(
        merchant_id=ctx.merchant_id, name=req.name, phone=req.phone, gender=req.gender,
        birthday=_parse_date(req.birthday), anniversary=_parse_date(req.anniversary),
        memo=req.memo, allergy_memo=req.allergy_memo, hair_memo=req.hair_memo,
        photo_url=req.photo_url, tags=",".join(req.tags) if req.tags else None,
        assigned_staff_id=req.assigned_staff_id or (ctx.staff_id if ctx.is_designer else None),
        preferred_staff_id=req.preferred_staff_id, preferred_service=req.preferred_service,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serialize_customer(c, {}, _staff_name_map(db, ctx.merchant_id), datetime.utcnow())


@router.get("/customers/{cid}")
def get_customer(cid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    c = db.query(CrmCustomer).filter(CrmCustomer.id == cid, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    now = datetime.utcnow()
    stats = _customer_stats(db, ctx.merchant_id)
    staff_names = _staff_name_map(db, ctx.merchant_id)
    data = _serialize_customer(c, stats, staff_names, now)

    visits = db.query(CrmVisit).filter(CrmVisit.customer_id == cid, CrmVisit.merchant_id == ctx.merchant_id).order_by(CrmVisit.visit_date.desc()).all()
    data["visits"] = [{"id": v.id, "service_name": v.service_name, "amount": float(v.amount),
                       "staff_id": v.staff_id, "staff_name": staff_names.get(v.staff_id),
                       "memo": v.memo, "visit_date": str(v.visit_date)} for v in visits]

    reservations = db.query(CrmReservation).filter(CrmReservation.customer_id == cid, CrmReservation.merchant_id == ctx.merchant_id).order_by(CrmReservation.reserved_at.desc()).all()
    data["reservations"] = [{"id": r.id, "service_name": r.service_name, "reserved_at": str(r.reserved_at),
                             "status": r.status.value, "status_kr": RESERVATION_STATUS_KR.get(r.status.value),
                             "staff_name": staff_names.get(r.staff_id)} for r in reservations]

    plogs = db.query(CrmPointLog).filter(CrmPointLog.customer_id == cid, CrmPointLog.merchant_id == ctx.merchant_id).order_by(CrmPointLog.created_at.desc()).limit(50).all()
    data["point_logs"] = [{"id": p.id, "delta": p.delta, "reason": p.reason,
                           "balance_after": p.balance_after, "created_at": str(p.created_at)} for p in plogs]

    coupons = db.query(CrmCoupon).filter(CrmCoupon.customer_id == cid, CrmCoupon.merchant_id == ctx.merchant_id).order_by(CrmCoupon.created_at.desc()).all()
    data["coupons"] = [{"id": cp.id, "name": cp.name, "discount_type": cp.discount_type, "value": cp.value,
                        "status": cp.status.value, "expires_at": str(cp.expires_at) if cp.expires_at else None} for cp in coupons]

    msgs = db.query(CrmMessageLog).filter(CrmMessageLog.customer_id == cid, CrmMessageLog.merchant_id == ctx.merchant_id).order_by(CrmMessageLog.sent_at.desc()).limit(30).all()
    data["messages"] = [{"id": mm.id, "channel": mm.channel.value, "content": mm.content,
                         "status": mm.status.value, "campaign": mm.campaign, "sent_at": str(mm.sent_at)} for mm in msgs]
    return data


@router.get("/customers/{cid}/timeline")
def customer_timeline(cid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    c = db.query(CrmCustomer).filter(CrmCustomer.id == cid, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    staff_names = _staff_name_map(db, ctx.merchant_id)
    items = []
    for v in db.query(CrmVisit).filter(CrmVisit.customer_id == cid).all():
        items.append({"type": "visit", "at": str(v.visit_date),
                      "title": v.service_name or "방문", "amount": float(v.amount),
                      "staff_name": staff_names.get(v.staff_id), "memo": v.memo})
    for r in db.query(CrmReservation).filter(CrmReservation.customer_id == cid).all():
        items.append({"type": "reservation", "at": str(r.reserved_at),
                      "title": r.service_name or "예약", "status": r.status.value,
                      "status_kr": RESERVATION_STATUS_KR.get(r.status.value),
                      "staff_name": staff_names.get(r.staff_id)})
    for p in db.query(CrmPointLog).filter(CrmPointLog.customer_id == cid).all():
        items.append({"type": "point", "at": str(p.created_at),
                      "title": p.reason or "포인트", "delta": p.delta, "balance_after": p.balance_after})
    for mm in db.query(CrmMessageLog).filter(CrmMessageLog.customer_id == cid).all():
        items.append({"type": "message", "at": str(mm.sent_at),
                      "title": f"{mm.channel.value} 발송", "content": mm.content, "campaign": mm.campaign})
    for cp in db.query(CrmCoupon).filter(CrmCoupon.customer_id == cid).all():
        items.append({"type": "coupon", "at": str(cp.created_at),
                      "title": cp.name, "status": cp.status.value})
    items.sort(key=lambda x: x["at"], reverse=True)

    # 방문 간격 분석: 평균 방문 간격(일), 최근 3회 간격, 길어지는 추세 여부
    visits_asc = db.query(CrmVisit).filter(CrmVisit.customer_id == cid).order_by(CrmVisit.visit_date.asc()).all()
    dates = [v.visit_date for v in visits_asc]
    intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    if intervals:
        avg_interval_days = round(sum(intervals) / len(intervals), 1)
        recent_intervals = intervals[-3:]
        trend_increasing = _interval_trend_increasing(intervals)
    else:
        avg_interval_days = None
        recent_intervals = []
        trend_increasing = False

    return {
        "customer_id": cid, "customer_name": c.name, "items": items,
        "visit_interval_analysis": {
            "avg_interval_days": avg_interval_days,
            "recent_intervals": recent_intervals,
            "trend_increasing": trend_increasing,
        },
    }


@router.put("/customers/{cid}")
def update_customer(cid: int, req: CustomerUpdate, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    c = db.query(CrmCustomer).filter(CrmCustomer.id == cid, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    payload = req.model_dump(exclude_unset=True)
    _assert_staff_in_merchant(db, ctx, payload.get("assigned_staff_id"),
                              payload.get("preferred_staff_id"))
    if "tags" in payload:
        c.tags = ",".join(payload.pop("tags") or []) or None
    if "birthday" in payload:
        c.birthday = _parse_date(payload.pop("birthday"))
    if "anniversary" in payload:
        c.anniversary = _parse_date(payload.pop("anniversary"))
    for k, v in payload.items():
        setattr(c, k, v)
    c.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/customers/{cid}")
def delete_customer(cid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_owner_admin(ctx, "고객 삭제는 사장님 계정에서만 가능합니다.")
    c = db.query(CrmCustomer).filter(CrmCustomer.id == cid, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    db.query(CrmVisit).filter(CrmVisit.customer_id == cid).delete()
    db.query(CrmReservation).filter(CrmReservation.customer_id == cid).update({"customer_id": None})
    db.query(CrmPointLog).filter(CrmPointLog.customer_id == cid).delete()
    db.query(CrmCoupon).filter(CrmCoupon.customer_id == cid).delete()
    db.query(CrmMessageLog).filter(CrmMessageLog.customer_id == cid).update({"customer_id": None})
    db.delete(c)
    db.commit()
    return {"ok": True}


# ─── Services & 디자이너별 단가 ─────────────────────────────

@router.get("/services")
def list_services(ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    rows = db.query(CrmService).filter(CrmService.merchant_id == ctx.merchant_id).order_by(CrmService.category, CrmService.created_at).all()
    return [{"id": s.id, "name": s.name, "category": s.category, "price": float(s.price),
             "duration_min": s.duration_min, "is_active": s.is_active} for s in rows]


@router.post("/services")
def create_service(req: ServiceIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_crm_management(ctx)
    s = CrmService(merchant_id=ctx.merchant_id, name=req.name, category=req.category,
                   price=req.price, duration_min=req.duration_min)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id}


@router.put("/services/{sid}")
def update_service(sid: int, req: ServiceUpdate, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_crm_management(ctx)
    s = db.query(CrmService).filter(CrmService.id == sid, CrmService.merchant_id == ctx.merchant_id).first()
    if not s:
        raise HTTPException(404, "서비스를 찾을 수 없습니다")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/services/{sid}")
def delete_service(sid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_crm_management(ctx)
    s = db.query(CrmService).filter(CrmService.id == sid, CrmService.merchant_id == ctx.merchant_id).first()
    if not s:
        raise HTTPException(404, "서비스를 찾을 수 없습니다")
    db.query(CrmServicePrice).filter(CrmServicePrice.service_id == sid).delete()
    db.delete(s); db.commit()
    return {"ok": True}


@router.get("/services/{sid}/prices")
def list_service_prices(sid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    staff_names = _staff_name_map(db, ctx.merchant_id)
    rows = db.query(CrmServicePrice).filter(CrmServicePrice.service_id == sid, CrmServicePrice.merchant_id == ctx.merchant_id).all()
    return [{"id": p.id, "staff_id": p.staff_id, "staff_name": staff_names.get(p.staff_id),
             "price": float(p.price)} for p in rows]


@router.post("/services/{sid}/prices")
def set_service_price(sid: int, req: ServicePriceIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_crm_management(ctx)
    s = db.query(CrmService).filter(CrmService.id == sid, CrmService.merchant_id == ctx.merchant_id).first()
    if not s:
        raise HTTPException(404, "서비스를 찾을 수 없습니다")
    _assert_staff_in_merchant(db, ctx, req.staff_id)
    existing = db.query(CrmServicePrice).filter(CrmServicePrice.service_id == sid, CrmServicePrice.staff_id == req.staff_id).first()
    if existing:
        existing.price = req.price
    else:
        db.add(CrmServicePrice(merchant_id=ctx.merchant_id, service_id=sid, staff_id=req.staff_id, price=req.price))
    db.commit()
    return {"ok": True}


@router.delete("/service-prices/{pid}")
def delete_service_price(pid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_crm_management(ctx)
    p = db.query(CrmServicePrice).filter(CrmServicePrice.id == pid, CrmServicePrice.merchant_id == ctx.merchant_id).first()
    if not p:
        raise HTTPException(404, "단가를 찾을 수 없습니다")
    db.delete(p); db.commit()
    return {"ok": True}


# ─── Visits ─────────────────────────────────────────────────

@router.get("/visits")
def list_visits(
    customer_id: Optional[int] = None,
    scope: str = Query("auto"),
    limit: int = Query(100, ge=1, le=500),
    ctx: CrmContext = Depends(get_crm_context),
    db: Session = Depends(get_db),
):
    q = db.query(CrmVisit).filter(CrmVisit.merchant_id == ctx.merchant_id)
    if customer_id:
        q = q.filter(CrmVisit.customer_id == customer_id)
    scope = _effective_scope(ctx, scope)
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    if use_mine and ctx.staff_id:
        q = q.filter(CrmVisit.staff_id == ctx.staff_id)
    visits = q.order_by(CrmVisit.visit_date.desc()).limit(limit).all()
    staff_names = _staff_name_map(db, ctx.merchant_id)
    cust_names = {c.id: c.name for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id).all()}
    return [{"id": v.id, "customer_id": v.customer_id, "customer_name": cust_names.get(v.customer_id, "-"),
             "service_name": v.service_name, "amount": float(v.amount), "staff_id": v.staff_id,
             "staff_name": staff_names.get(v.staff_id), "memo": v.memo, "visit_date": str(v.visit_date)} for v in visits]


@router.post("/visits")
def create_visit(req: VisitIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    c = db.query(CrmCustomer).filter(CrmCustomer.id == req.customer_id, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    # 음수 금액 방지
    if (req.amount or 0) < 0:
        raise HTTPException(400, "금액은 0 이상이어야 합니다")
    _assert_staff_in_merchant(db, ctx, req.staff_id)
    staff_id = req.staff_id if req.staff_id is not None else (ctx.staff_id if ctx.is_designer else None)
    v = CrmVisit(merchant_id=ctx.merchant_id, customer_id=req.customer_id, staff_id=staff_id,
                 service_name=req.service_name, amount=req.amount or 0, memo=req.memo,
                 visit_date=_parse_dt(req.visit_date) or datetime.utcnow())
    db.add(v)
    earned = req.points_earned if req.points_earned is not None else int((req.amount or 0) * 0.05)
    if earned:
        # 잔액 음수 방지: 차감(음수 적립) 시에도 잔액이 0 미만으로 내려가지 않도록 클램프
        old_balance = c.points or 0
        new_balance = max(0, old_balance + earned)
        earned = new_balance - old_balance
        if earned:
            c.points = new_balance
            db.add(CrmPointLog(merchant_id=ctx.merchant_id, customer_id=c.id, delta=earned,
                               reason="방문 적립", balance_after=new_balance))
    db.commit(); db.refresh(v)
    return {"id": v.id, "points_earned": earned}


@router.delete("/visits/{vid}")
def delete_visit(vid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    v = db.query(CrmVisit).filter(CrmVisit.id == vid, CrmVisit.merchant_id == ctx.merchant_id).first()
    if not v:
        raise HTTPException(404, "방문 기록을 찾을 수 없습니다")
    # 포인트 무결성: 방문 등록 시 적립된 포인트를 회수한다.
    # 방문과 적립 로그는 같은 트랜잭션에서 생성되므로 created_at 이 근접한 "방문 적립" 로그를 찾는다.
    c = db.query(CrmCustomer).filter(CrmCustomer.id == v.customer_id,
                                     CrmCustomer.merchant_id == ctx.merchant_id).first()
    if c and v.created_at:
        window_start = v.created_at - timedelta(seconds=60)
        window_end = v.created_at + timedelta(seconds=60)
        earn_log = db.query(CrmPointLog).filter(
            CrmPointLog.merchant_id == ctx.merchant_id,
            CrmPointLog.customer_id == v.customer_id,
            CrmPointLog.reason == "방문 적립",
            CrmPointLog.created_at >= window_start,
            CrmPointLog.created_at <= window_end,
        ).first()
        if earn_log and earn_log.delta > 0:
            old_balance = c.points or 0
            new_balance = max(0, old_balance - earn_log.delta)
            reclaimed = old_balance - new_balance
            if reclaimed:
                c.points = new_balance
                db.add(CrmPointLog(merchant_id=ctx.merchant_id, customer_id=c.id, delta=-reclaimed,
                                   reason="방문 삭제 적립 회수", balance_after=new_balance))
    db.delete(v); db.commit()
    return {"ok": True}


# ─── Reservations ───────────────────────────────────────────

def _conflict_check(db, merchant_id, staff_id, start, end, exclude_id=None):
    if not staff_id or not start or not end:
        return None
    q = db.query(CrmReservation).filter(
        CrmReservation.merchant_id == merchant_id,
        CrmReservation.staff_id == staff_id,
        CrmReservation.status.in_([ReservationStatus.BOOKED, ReservationStatus.CONFIRMED]),
    )
    if exclude_id:
        q = q.filter(CrmReservation.id != exclude_id)
    for r in q.all():
        r_start = r.reserved_at
        r_end = r.end_at or (r.reserved_at + timedelta(minutes=r.duration_min or 60))
        if start < r_end and r_start < end:   # overlap
            return r
    return None


@router.get("/reservations")
def list_reservations(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    staff_id: Optional[int] = None,
    scope: str = Query("auto"),
    ctx: CrmContext = Depends(get_crm_context),
    db: Session = Depends(get_db),
):
    q = db.query(CrmReservation).filter(CrmReservation.merchant_id == ctx.merchant_id)
    if date_from:
        q = q.filter(CrmReservation.reserved_at >= _parse_dt(date_from))
    if date_to:
        q = q.filter(CrmReservation.reserved_at <= _parse_dt(date_to))
    if status:
        try:
            status_enum = ReservationStatus(status)
        except ValueError:
            raise HTTPException(400, f"유효하지 않은 예약 상태입니다: {status}")
        q = q.filter(CrmReservation.status == status_enum)
    if staff_id:
        q = q.filter(CrmReservation.staff_id == staff_id)
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    if use_mine and ctx.staff_id:
        q = q.filter(CrmReservation.staff_id == ctx.staff_id)
    rows = q.order_by(CrmReservation.reserved_at.asc()).all()
    staff_names = _staff_name_map(db, ctx.merchant_id)
    cust_names = {c.id: c.name for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id).all()}
    return [{"id": r.id, "customer_id": r.customer_id,
             "customer_name": cust_names.get(r.customer_id) or r.customer_name or "-",
             "phone": r.phone, "staff_id": r.staff_id, "staff_name": staff_names.get(r.staff_id),
             "service_name": r.service_name, "reserved_at": str(r.reserved_at),
             "end_at": str(r.end_at) if r.end_at else None, "duration_min": r.duration_min,
             "status": r.status.value, "status_kr": RESERVATION_STATUS_KR.get(r.status.value),
             "memo": r.memo} for r in rows]


@router.get("/reservations/calendar")
def reservations_calendar(
    date: str = Query(...),
    view: str = Query("day", pattern="^(day|week)$"),
    scope: str = Query("auto"),
    ctx: CrmContext = Depends(get_crm_context),
    db: Session = Depends(get_db),
):
    base = _parse_dt(date)
    if view == "day":
        start = base.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        days = 1
    else:
        start = (base - timedelta(days=base.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        days = 7
    q = db.query(CrmReservation).filter(
        CrmReservation.merchant_id == ctx.merchant_id,
        CrmReservation.reserved_at >= start, CrmReservation.reserved_at < end,
    )
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    if use_mine and ctx.staff_id:
        q = q.filter(CrmReservation.staff_id == ctx.staff_id)
    rows = q.order_by(CrmReservation.reserved_at.asc()).all()
    staff_names = _staff_name_map(db, ctx.merchant_id)
    cust_names = {c.id: c.name for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id).all()}
    staff_list = db.query(Staff).filter(Staff.merchant_id == ctx.merchant_id, Staff.is_active == True).all()
    if use_mine and ctx.staff_id:
        staff_list = [s for s in staff_list if s.id == ctx.staff_id]
    events = [{
        "id": r.id, "staff_id": r.staff_id, "staff_name": staff_names.get(r.staff_id) or "미지정",
        "customer_name": cust_names.get(r.customer_id) or r.customer_name or "-",
        "service_name": r.service_name, "reserved_at": str(r.reserved_at),
        "end_at": str(r.end_at) if r.end_at else None, "duration_min": r.duration_min or 60,
        "status": r.status.value, "status_kr": RESERVATION_STATUS_KR.get(r.status.value),
        "memo": r.memo,
    } for r in rows]
    return {
        "view": view, "start": start.strftime("%Y-%m-%d"), "days": days,
        "staff": [{"id": s.id, "name": s.name} for s in staff_list],
        "events": events,
    }


@router.post("/reservations")
def create_reservation(req: ReservationIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    cname, phone = req.customer_name, req.phone
    if req.customer_id:
        c = db.query(CrmCustomer).filter(CrmCustomer.id == req.customer_id, CrmCustomer.merchant_id == ctx.merchant_id).first()
        if not c:
            raise HTTPException(404, "고객을 찾을 수 없습니다")
        cname = cname or c.name
        phone = phone or c.phone
    _assert_staff_in_merchant(db, ctx, req.staff_id)
    staff_id = req.staff_id if req.staff_id is not None else (ctx.staff_id if ctx.is_designer else None)
    start = _parse_dt(req.reserved_at)
    dur = req.duration_min or 60
    end = start + timedelta(minutes=dur)
    if not req.force:
        conflict = _conflict_check(db, ctx.merchant_id, staff_id, start, end)
        if conflict:
            raise HTTPException(409, f"해당 담당자의 예약 시간이 겹칩니다 ({conflict.reserved_at:%m/%d %H:%M}). 시간을 변경하거나 강제 등록하세요.")
    r = CrmReservation(merchant_id=ctx.merchant_id, customer_id=req.customer_id, customer_name=cname,
                       phone=phone, staff_id=staff_id, service_name=req.service_name,
                       reserved_at=start, end_at=end, duration_min=dur, memo=req.memo)
    db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id}


@router.put("/reservations/{rid}")
def update_reservation(rid: int, req: ReservationUpdate, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    r = db.query(CrmReservation).filter(CrmReservation.id == rid, CrmReservation.merchant_id == ctx.merchant_id).first()
    if not r:
        raise HTTPException(404, "예약을 찾을 수 없습니다")
    payload = req.model_dump(exclude_unset=True)
    _assert_staff_in_merchant(db, ctx, payload.get("staff_id"))
    if payload.get("status"):
        try:
            r.status = ReservationStatus(payload.pop("status"))
        except ValueError:
            raise HTTPException(400, "유효하지 않은 예약 상태입니다")
    else:
        payload.pop("status", None)
    if payload.get("reserved_at"):
        r.reserved_at = _parse_dt(payload.pop("reserved_at"))
    else:
        payload.pop("reserved_at", None)
    for k, v in payload.items():
        setattr(r, k, v)
    # 종료시각 재계산
    r.end_at = r.reserved_at + timedelta(minutes=r.duration_min or 60)
    # 방문완료 시 자동 방문기록
    if r.status == ReservationStatus.DONE and r.customer_id:
        already = db.query(CrmVisit).filter(
            CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.customer_id == r.customer_id,
            CrmVisit.visit_date == r.reserved_at).first()
        if not already:
            db.add(CrmVisit(merchant_id=ctx.merchant_id, customer_id=r.customer_id, staff_id=r.staff_id,
                            service_name=r.service_name, amount=0, memo="예약 방문완료 자동기록",
                            visit_date=r.reserved_at))
    db.commit()
    return {"ok": True}


@router.delete("/reservations/{rid}")
def delete_reservation(rid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    r = db.query(CrmReservation).filter(CrmReservation.id == rid, CrmReservation.merchant_id == ctx.merchant_id).first()
    if not r:
        raise HTTPException(404, "예약을 찾을 수 없습니다")
    db.delete(r); db.commit()
    return {"ok": True}


@router.post("/reservations/{rid}/remind")
def send_reminder(rid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    r = db.query(CrmReservation).filter(CrmReservation.id == rid, CrmReservation.merchant_id == ctx.merchant_id).first()
    if not r:
        raise HTTPException(404, "예약을 찾을 수 없습니다")
    content = f"[{ctx.merchant.name}] {r.customer_name or '고객'}님, {r.reserved_at:%m월 %d일 %H:%M} 예약 안내드립니다. 방문 부탁드립니다."
    log = CrmMessageLog(merchant_id=ctx.merchant_id, customer_id=r.customer_id, channel=MessageChannel.SMS,
                        to_phone=r.phone, content=content, status=MessageStatus.SENT, campaign="reminder")
    db.add(log)
    r.reminder_sent_at = datetime.utcnow()
    if r.customer_id:
        c = db.query(CrmCustomer).filter(CrmCustomer.id == r.customer_id).first()
        if c:
            c.last_message_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "content": content}
