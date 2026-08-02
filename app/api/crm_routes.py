"""
미용실 CRM (고객관리프로그램) API — 고도화 버전.

원장(OWNER): 본인 미용실 전체 데이터.
디자이너(DESIGNER): 본인 소속 미용실 데이터 (기본은 본인 고객/실적 위주, scope=all 로 전체 조회 가능).
관리자(ADMIN): 지원용.

모든 데이터는 merchant_id 로 격리된다.
"""
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.staff import Staff
from app.models.crm import (
    CrmCustomer, CrmService, CrmServicePrice, CrmVisit, CrmReservation, CrmPointLog,
    CrmMessageTemplate, CrmMessageLog, CrmCoupon,
    ReservationStatus, RESERVATION_STATUS_KR,
    MessageChannel, MessageStatus, CouponStatus,
)
from app.auth.dependencies import require_roles

router = APIRouter(prefix="/api/crm", tags=["crm"])

require_crm = require_roles([UserRole.ADMIN, UserRole.OWNER, UserRole.DESIGNER])

REVISIT_DORMANT_DAYS = 30
DORMANT_CAMPAIGN_DAYS = 60


# ─── Context ────────────────────────────────────────────────

class CrmContext:
    def __init__(self, merchant: Merchant, role: UserRole, staff_id: Optional[int]):
        self.merchant = merchant
        self.merchant_id = merchant.id
        self.role = role
        self.staff_id = staff_id          # 디자이너 본인 staff.id
        self.is_designer = role == UserRole.DESIGNER


def get_crm_context(
    merchant_id: Optional[int] = Query(None, description="관리자 전용: 대상 미용실 ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_crm),
) -> CrmContext:
    if user.role == UserRole.OWNER:
        m = db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()
        if not m:
            raise HTTPException(404, "원장님 소유 미용실을 찾을 수 없습니다")
        return CrmContext(m, user.role, None)
    if user.role == UserRole.DESIGNER:
        staff = db.query(Staff).filter(Staff.user_id == user.id, Staff.is_active == True).first()
        if not staff:
            raise HTTPException(404, "디자이너 소속 미용실을 찾을 수 없습니다")
        m = db.query(Merchant).filter(Merchant.id == staff.merchant_id).first()
        if not m:
            raise HTTPException(404, "소속 미용실을 찾을 수 없습니다")
        return CrmContext(m, user.role, staff.id)
    # ADMIN
    q = db.query(Merchant)
    m = q.filter(Merchant.id == merchant_id).first() if merchant_id else q.order_by(Merchant.id).first()
    if not m:
        raise HTTPException(404, "미용실을 찾을 수 없습니다")
    return CrmContext(m, user.role, None)


# ─── 공통 유틸 ──────────────────────────────────────────────

def _staff_name_map(db: Session, merchant_id: int) -> dict:
    rows = db.query(Staff).filter(Staff.merchant_id == merchant_id).all()
    return {s.id: s.name for s in rows}


def _require_crm_management(ctx: CrmContext) -> None:
    """Keep merchant-wide configuration changes owner/admin only."""
    if ctx.is_designer or ctx.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="매장 공통 설정은 원장 계정에서 관리해 주세요.")


def _require_owner_admin(ctx: CrmContext, message: str) -> None:
    """고객 자산(포인트/쿠폰)·일괄 발송·영구 삭제는 원장/관리자만 수행한다."""
    if ctx.is_designer or ctx.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail=message)


def _effective_scope(ctx: CrmContext, scope: str) -> str:
    """디자이너는 매출/실적 조회 범위를 본인 것으로 강제한다 (scope=all 권한 상승 차단)."""
    if ctx.is_designer:
        return "mine"
    return scope


def _customer_grade(visit_count: int, total_spent: float) -> str:
    if total_spent >= 1_000_000 or visit_count >= 20:
        return "VIP"
    if total_spent >= 500_000 or visit_count >= 10:
        return "GOLD"
    if total_spent >= 200_000 or visit_count >= 5:
        return "SILVER"
    if visit_count >= 1:
        return "BRONZE"
    return "NEW"


def _customer_stats(db: Session, merchant_id: int):
    rows = db.query(
        CrmVisit.customer_id,
        func.count(CrmVisit.id).label("cnt"),
        func.coalesce(func.sum(CrmVisit.amount), 0).label("total"),
        func.max(CrmVisit.visit_date).label("last"),
        func.min(CrmVisit.visit_date).label("first"),
    ).filter(CrmVisit.merchant_id == merchant_id).group_by(CrmVisit.customer_id).all()
    out = {}
    for r in rows:
        out[r.customer_id] = {
            "visit_count": int(r.cnt or 0),
            "total_spent": float(r.total or 0),
            "last_visit": r.last,
            "first_visit": r.first,
        }
    return out


def _tags_list(tags: Optional[str]) -> List[str]:
    if not tags:
        return []
    return [t.strip() for t in tags.split(",") if t.strip()]


def _auto_tags(st: dict, customer: CrmCustomer, now: datetime) -> List[str]:
    tags = []
    vc = st.get("visit_count", 0)
    total = st.get("total_spent", 0)
    last = st.get("last_visit")
    if vc == 0:
        tags.append("신규")
    if total >= 1_000_000 or vc >= 20:
        tags.append("VIP")
    elif vc >= 10 or total >= 500_000:
        tags.append("단골")
    if last and (now - last).days >= DORMANT_CAMPAIGN_DAYS:
        tags.append("휴면")
    if customer.birthday and customer.birthday.month == now.month:
        tags.append("이달생일")
    return tags


def _visit_cycle_days(st: dict) -> Optional[int]:
    vc = st.get("visit_count", 0)
    first = st.get("first_visit")
    last = st.get("last_visit")
    if vc >= 2 and first and last and last > first:
        return round((last - first).days / (vc - 1))
    return None


def _serialize_customer(c: CrmCustomer, stats: dict, staff_names: dict, now: datetime) -> dict:
    st = stats.get(c.id, {"visit_count": 0, "total_spent": 0.0, "last_visit": None, "first_visit": None})
    cycle = _visit_cycle_days(st)
    last = st["last_visit"]
    next_expected = None
    if last and cycle:
        next_expected = (last + timedelta(days=cycle)).strftime("%Y-%m-%d")
    return {
        "id": c.id, "name": c.name, "phone": c.phone, "gender": c.gender,
        "birthday": str(c.birthday) if c.birthday else None,
        "anniversary": str(c.anniversary) if c.anniversary else None,
        "memo": c.memo, "allergy_memo": c.allergy_memo, "hair_memo": c.hair_memo,
        "photo_url": c.photo_url,
        "tags": _tags_list(c.tags),
        "auto_tags": _auto_tags(st, c, now),
        "assigned_staff_id": c.assigned_staff_id,
        "assigned_staff_name": staff_names.get(c.assigned_staff_id) if c.assigned_staff_id else None,
        "preferred_staff_id": c.preferred_staff_id,
        "preferred_staff_name": staff_names.get(c.preferred_staff_id) if c.preferred_staff_id else None,
        "preferred_service": c.preferred_service,
        "points": c.points, "is_active": c.is_active,
        "visit_count": st["visit_count"], "total_spent": st["total_spent"],
        "avg_ticket": round(st["total_spent"] / st["visit_count"]) if st["visit_count"] else 0,
        "last_visit": str(last) if last else None,
        "first_visit": str(st["first_visit"]) if st["first_visit"] else None,
        "visit_cycle_days": cycle,
        "next_expected_visit": next_expected,
        "grade": _customer_grade(st["visit_count"], st["total_spent"]),
        "last_message_at": str(c.last_message_at) if c.last_message_at else None,
        "created_at": str(c.created_at),
    }


def _parse_dt(s: Optional[str]):
    if not s:
        return None
    s = s.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise HTTPException(400, f"날짜 형식이 올바르지 않습니다: {s}")


def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, f"날짜 형식이 올바르지 않습니다(YYYY-MM-DD): {s}")


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


class PointAdjust(BaseModel):
    delta: int
    reason: Optional[str] = None


class TemplateIn(BaseModel):
    name: str
    channel: str = "sms"
    category: Optional[str] = None
    body: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    category: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None


class SendMessageIn(BaseModel):
    customer_ids: Optional[List[int]] = None
    segment: Optional[str] = None     # all/dormant/birthday/vip
    template_id: Optional[int] = None
    content: Optional[str] = None
    channel: str = "sms"
    campaign: Optional[str] = None


class CouponIn(BaseModel):
    customer_id: Optional[int] = None
    name: str
    discount_type: str = "amount"
    value: int = 0
    expires_at: Optional[str] = None
    memo: Optional[str] = None


class CouponBulkIn(BaseModel):
    segment: str = "all"   # all/dormant/birthday/vip
    name: str
    discount_type: str = "amount"
    value: int = 0
    expires_at: Optional[str] = None


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

@router.get("/customers")
def list_customers(
    search: Optional[str] = None,
    tag: Optional[str] = None,
    grade: Optional[str] = None,
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
    return result


@router.post("/customers")
def create_customer(req: CustomerIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
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
    return {"customer_id": cid, "customer_name": c.name, "items": items}


@router.put("/customers/{cid}")
def update_customer(cid: int, req: CustomerUpdate, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    c = db.query(CrmCustomer).filter(CrmCustomer.id == cid, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    payload = req.model_dump(exclude_unset=True)
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
    _require_owner_admin(ctx, "고객 삭제는 원장 계정에서만 가능합니다.")
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


@router.post("/customers/{cid}/points")
def adjust_points(cid: int, req: PointAdjust, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_owner_admin(ctx, "포인트 적립/차감은 원장 계정에서만 가능합니다.")
    c = db.query(CrmCustomer).filter(CrmCustomer.id == cid, CrmCustomer.merchant_id == ctx.merchant_id).first()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    new_balance = max(0, (c.points or 0) + req.delta)
    c.points = new_balance
    db.add(CrmPointLog(merchant_id=ctx.merchant_id, customer_id=cid, delta=req.delta,
                       reason=req.reason, balance_after=new_balance))
    db.commit()
    return {"ok": True, "points": new_balance}


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
        raise HTTPException(404, "시술을 찾을 수 없습니다")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/services/{sid}")
def delete_service(sid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_crm_management(ctx)
    s = db.query(CrmService).filter(CrmService.id == sid, CrmService.merchant_id == ctx.merchant_id).first()
    if not s:
        raise HTTPException(404, "시술을 찾을 수 없습니다")
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
        raise HTTPException(404, "시술을 찾을 수 없습니다")
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
    staff_id = req.staff_id if req.staff_id is not None else (ctx.staff_id if ctx.is_designer else None)
    v = CrmVisit(merchant_id=ctx.merchant_id, customer_id=req.customer_id, staff_id=staff_id,
                 service_name=req.service_name, amount=req.amount or 0, memo=req.memo,
                 visit_date=_parse_dt(req.visit_date) or datetime.utcnow())
    db.add(v)
    earned = req.points_earned if req.points_earned is not None else int((req.amount or 0) * 0.05)
    if earned:
        new_balance = (c.points or 0) + earned
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
        q = q.filter(CrmReservation.status == ReservationStatus(status))
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
    staff_id = req.staff_id if req.staff_id is not None else (ctx.staff_id if ctx.is_designer else None)
    start = _parse_dt(req.reserved_at)
    dur = req.duration_min or 60
    end = start + timedelta(minutes=dur)
    if not req.force:
        conflict = _conflict_check(db, ctx.merchant_id, staff_id, start, end)
        if conflict:
            raise HTTPException(409, f"해당 디자이너의 예약 시간이 겹칩니다 ({conflict.reserved_at:%m/%d %H:%M}). 시간을 변경하거나 강제 등록하세요.")
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
    if payload.get("status"):
        r.status = ReservationStatus(payload.pop("status"))
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


# ─── Stats & Analytics ──────────────────────────────────────

def _range_bounds(range_str: str):
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_str == "day":
        return today, now
    if range_str == "week":
        return today - timedelta(days=today.weekday()), now
    if range_str == "month":
        return today.replace(day=1), now
    if range_str == "year":
        return today.replace(month=1, day=1), now
    return datetime(2000, 1, 1), now


def _visit_scope(q, ctx, scope):
    scope = _effective_scope(ctx, scope)
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    if use_mine and ctx.staff_id:
        q = q.filter(CrmVisit.staff_id == ctx.staff_id)
    return q


@router.get("/stats")
def crm_stats(scope: str = Query("auto"), ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    scope = _effective_scope(ctx, scope)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)
    tomorrow = today_start + timedelta(days=1)
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    sid = ctx.staff_id if (use_mine and ctx.staff_id) else None

    cust_q = db.query(func.count(CrmCustomer.id)).filter(CrmCustomer.merchant_id == ctx.merchant_id)
    if sid:
        cust_q = cust_q.filter(or_(CrmCustomer.assigned_staff_id == sid, CrmCustomer.preferred_staff_id == sid))
    total_customers = cust_q.scalar() or 0

    new_q = db.query(func.count(CrmCustomer.id)).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.created_at >= month_start)
    if sid:
        new_q = new_q.filter(or_(CrmCustomer.assigned_staff_id == sid, CrmCustomer.preferred_staff_id == sid))
    new_this_month = new_q.scalar() or 0

    def vq():
        q = db.query(CrmVisit).filter(CrmVisit.merchant_id == ctx.merchant_id)
        return _visit_scope(q, ctx, scope)

    visits_today = vq().filter(CrmVisit.visit_date >= today_start, CrmVisit.visit_date < tomorrow).count()
    revenue_today = _visit_scope(db.query(func.coalesce(func.sum(CrmVisit.amount), 0)).filter(CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.visit_date >= today_start, CrmVisit.visit_date < tomorrow), ctx, scope).scalar() or 0
    visits_month = vq().filter(CrmVisit.visit_date >= month_start).count()
    revenue_month = _visit_scope(db.query(func.coalesce(func.sum(CrmVisit.amount), 0)).filter(CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.visit_date >= month_start), ctx, scope).scalar() or 0
    revenue_total = _visit_scope(db.query(func.coalesce(func.sum(CrmVisit.amount), 0)).filter(CrmVisit.merchant_id == ctx.merchant_id), ctx, scope).scalar() or 0
    avg_ticket_month = round(float(revenue_month) / visits_month) if visits_month else 0

    rq = db.query(CrmReservation).filter(CrmReservation.merchant_id == ctx.merchant_id)
    if sid:
        rq = rq.filter(CrmReservation.staff_id == sid)
    reservations_today = rq.filter(CrmReservation.reserved_at >= today_start, CrmReservation.reserved_at < tomorrow).count()
    reservations_upcoming = rq.filter(CrmReservation.reserved_at >= now, CrmReservation.status.in_([ReservationStatus.BOOKED, ReservationStatus.CONFIRMED])).count()

    # 인기 시술 TOP5 (이번달)
    tq = db.query(CrmVisit.service_name, func.count(CrmVisit.id).label("cnt"), func.coalesce(func.sum(CrmVisit.amount), 0).label("total")).filter(
        CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.service_name.isnot(None), CrmVisit.visit_date >= month_start)
    tq = _visit_scope(tq, ctx, scope)
    top_rows = tq.group_by(CrmVisit.service_name).order_by(func.count(CrmVisit.id).desc()).limit(5).all()
    top_services = [{"name": r.service_name, "count": int(r.cnt), "revenue": float(r.total)} for r in top_rows]

    # 디자이너별 이번달 매출 (원장 뷰)
    staff_names = _staff_name_map(db, ctx.merchant_id)
    staff_sales = []
    if not sid:
        srows = db.query(CrmVisit.staff_id, func.count(CrmVisit.id).label("cnt"), func.coalesce(func.sum(CrmVisit.amount), 0).label("total")).filter(
            CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.visit_date >= month_start).group_by(CrmVisit.staff_id).all()
        staff_sales = [{"staff_id": r.staff_id, "staff_name": staff_names.get(r.staff_id, "미지정"),
                        "count": int(r.cnt), "revenue": float(r.total)} for r in srows]
        staff_sales.sort(key=lambda x: x["revenue"], reverse=True)

    # 최근 6개월 매출
    monthly = []
    months = []
    cur = month_start
    for _ in range(6):
        months.append(cur)
        cur = (cur - timedelta(days=1)).replace(day=1)
    for ms in reversed(months):
        me = (ms + timedelta(days=32)).replace(day=1)
        rev = _visit_scope(db.query(func.coalesce(func.sum(CrmVisit.amount), 0)).filter(CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.visit_date >= ms, CrmVisit.visit_date < me), ctx, scope).scalar() or 0
        monthly.append({"month": ms.strftime("%Y-%m"), "revenue": float(rev)})

    # 재방문 대상 수
    dormant_cut = now - timedelta(days=REVISIT_DORMANT_DAYS)
    stats_map = _customer_stats(db, ctx.merchant_id)
    revisit_due = sum(1 for st in stats_map.values() if st["last_visit"] and st["last_visit"] < dormant_cut)

    # 이번달 생일 고객 수
    bq = db.query(func.count(CrmCustomer.id)).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.birthday.isnot(None))
    birthdays = sum(1 for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.birthday.isnot(None)).all() if c.birthday and c.birthday.month == now.month)

    return {
        "merchant_name": ctx.merchant.name, "scope_mine": bool(sid),
        "total_customers": int(total_customers), "new_this_month": int(new_this_month),
        "visits_today": int(visits_today), "revenue_today": float(revenue_today),
        "visits_month": int(visits_month), "revenue_month": float(revenue_month),
        "revenue_total": float(revenue_total), "avg_ticket_month": avg_ticket_month,
        "reservations_today": int(reservations_today), "reservations_upcoming": int(reservations_upcoming),
        "revisit_due": revisit_due, "birthdays_this_month": birthdays,
        "top_services": top_services, "staff_sales": staff_sales, "monthly_revenue": monthly,
    }


@router.get("/stats/analytics")
def crm_analytics(range_: str = Query("month", alias="range", pattern="^(week|month|year|all)$"),
                  scope: str = Query("auto"),
                  ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    scope = _effective_scope(ctx, scope)
    start, end = _range_bounds(range_)
    q = db.query(CrmVisit).filter(CrmVisit.merchant_id == ctx.merchant_id,
                                  CrmVisit.visit_date >= start, CrmVisit.visit_date <= end)
    q = _visit_scope(q, ctx, scope)
    visits = q.all()
    staff_names = _staff_name_map(db, ctx.merchant_id)

    total_rev = sum(float(v.amount) for v in visits)
    total_cnt = len(visits)
    avg_ticket = round(total_rev / total_cnt) if total_cnt else 0

    # 신규 vs 재방문 (해당 기간 첫 방문이 기간 내면 신규)
    first_visit_map = {}
    for cid, st in _customer_stats(db, ctx.merchant_id).items():
        first_visit_map[cid] = st["first_visit"]
    new_cnt = revisit_cnt = 0
    for v in visits:
        fv = first_visit_map.get(v.customer_id)
        if fv and fv >= start:
            new_cnt += 1
        else:
            revisit_cnt += 1

    # 시술별
    by_service = {}
    for v in visits:
        k = v.service_name or "기타"
        d = by_service.setdefault(k, {"name": k, "count": 0, "revenue": 0.0})
        d["count"] += 1; d["revenue"] += float(v.amount)
    by_service = sorted(by_service.values(), key=lambda x: x["revenue"], reverse=True)

    # 디자이너별
    by_staff = {}
    for v in visits:
        d = by_staff.setdefault(v.staff_id, {"staff_id": v.staff_id, "staff_name": staff_names.get(v.staff_id, "미지정"), "count": 0, "revenue": 0.0})
        d["count"] += 1; d["revenue"] += float(v.amount)
    by_staff = sorted(by_staff.values(), key=lambda x: x["revenue"], reverse=True)

    # 요일별 / 시간대별
    weekday_labels = ["월", "화", "수", "목", "금", "토", "일"]
    by_weekday = [{"label": weekday_labels[i], "count": 0, "revenue": 0.0} for i in range(7)]
    by_hour = [{"hour": h, "count": 0, "revenue": 0.0} for h in range(24)]
    for v in visits:
        wd = v.visit_date.weekday()
        by_weekday[wd]["count"] += 1; by_weekday[wd]["revenue"] += float(v.amount)
        h = v.visit_date.hour
        by_hour[h]["count"] += 1; by_hour[h]["revenue"] += float(v.amount)
    # 영업시간대만(9~22) 압축
    by_hour = [x for x in by_hour if 9 <= x["hour"] <= 22]

    # 일별 매출 추이 (최대 31포인트)
    daily = {}
    for v in visits:
        k = v.visit_date.strftime("%Y-%m-%d")
        daily[k] = daily.get(k, 0) + float(v.amount)
    daily_series = [{"date": k, "revenue": daily[k]} for k in sorted(daily.keys())]

    return {
        "range": range_, "total_revenue": total_rev, "total_visits": total_cnt, "avg_ticket": avg_ticket,
        "new_count": new_cnt, "revisit_count": revisit_cnt,
        "new_ratio": round(new_cnt / total_cnt * 100, 1) if total_cnt else 0,
        "by_service": by_service, "by_staff": by_staff,
        "by_weekday": by_weekday, "by_hour": by_hour, "daily": daily_series,
    }


# ─── Marketing / Retention ──────────────────────────────────

@router.get("/revisit")
def revisit_targets(days: int = Query(REVISIT_DORMANT_DAYS, ge=7, le=365),
                    scope: str = Query("auto"),
                    ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    cut = now - timedelta(days=days)
    stats = _customer_stats(db, ctx.merchant_id)
    staff_names = _staff_name_map(db, ctx.merchant_id)
    cq = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.is_active == True)
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)
    if use_mine and ctx.staff_id:
        cq = cq.filter(or_(CrmCustomer.assigned_staff_id == ctx.staff_id, CrmCustomer.preferred_staff_id == ctx.staff_id))
    out = []
    for c in cq.all():
        st = stats.get(c.id)
        if not st or not st["last_visit"]:
            continue
        if st["last_visit"] < cut:
            d = _serialize_customer(c, stats, staff_names, now)
            d["days_since_visit"] = (now - st["last_visit"]).days
            out.append(d)
    out.sort(key=lambda x: x["days_since_visit"], reverse=True)
    return {"days": days, "count": len(out), "customers": out}


@router.get("/birthdays")
def birthday_customers(month: Optional[int] = None, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    m = month or now.month
    stats = _customer_stats(db, ctx.merchant_id)
    staff_names = _staff_name_map(db, ctx.merchant_id)
    customers = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.is_active == True).all()
    bdays, annivs = [], []
    for c in customers:
        if c.birthday and c.birthday.month == m:
            d = _serialize_customer(c, stats, staff_names, now)
            d["event_day"] = c.birthday.day
            bdays.append(d)
        if c.anniversary and c.anniversary.month == m:
            d = _serialize_customer(c, stats, staff_names, now)
            d["event_day"] = c.anniversary.day
            annivs.append(d)
    bdays.sort(key=lambda x: x["event_day"])
    annivs.sort(key=lambda x: x["event_day"])
    return {"month": m, "birthdays": bdays, "anniversaries": annivs}


def _segment_customers(db, ctx, segment):
    now = datetime.utcnow()
    stats = _customer_stats(db, ctx.merchant_id)
    customers = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.is_active == True).all()
    out = []
    for c in customers:
        st = stats.get(c.id, {"visit_count": 0, "total_spent": 0, "last_visit": None})
        if segment == "all":
            out.append(c)
        elif segment == "dormant":
            if st["last_visit"] and (now - st["last_visit"]).days >= DORMANT_CAMPAIGN_DAYS:
                out.append(c)
        elif segment == "birthday":
            if c.birthday and c.birthday.month == now.month:
                out.append(c)
        elif segment == "vip":
            if _customer_grade(st["visit_count"], st["total_spent"]) in ("VIP", "GOLD"):
                out.append(c)
    return out


# ─── Coupons ────────────────────────────────────────────────

@router.get("/coupons")
def list_coupons(status: Optional[str] = None, customer_id: Optional[int] = None,
                 ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    q = db.query(CrmCoupon).filter(CrmCoupon.merchant_id == ctx.merchant_id)
    if status:
        q = q.filter(CrmCoupon.status == CouponStatus(status))
    if customer_id:
        q = q.filter(CrmCoupon.customer_id == customer_id)
    rows = q.order_by(CrmCoupon.created_at.desc()).all()
    cust_names = {c.id: c.name for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id).all()}
    return [{"id": cp.id, "customer_id": cp.customer_id, "customer_name": cust_names.get(cp.customer_id) or "(공통)",
             "name": cp.name, "discount_type": cp.discount_type, "value": cp.value, "status": cp.status.value,
             "expires_at": str(cp.expires_at) if cp.expires_at else None, "memo": cp.memo,
             "created_at": str(cp.created_at)} for cp in rows]


@router.post("/coupons")
def create_coupon(req: CouponIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    cp = CrmCoupon(merchant_id=ctx.merchant_id, customer_id=req.customer_id, name=req.name,
                   discount_type=req.discount_type, value=req.value, memo=req.memo,
                   expires_at=_parse_date(req.expires_at))
    db.add(cp); db.commit(); db.refresh(cp)
    return {"id": cp.id}


@router.post("/coupons/bulk")
def issue_coupons_bulk(req: CouponBulkIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    _require_owner_admin(ctx, "쿠폰 일괄 발급은 원장 계정에서만 가능합니다.")
    targets = _segment_customers(db, ctx, req.segment)
    exp = _parse_date(req.expires_at)
    n = 0
    for c in targets:
        db.add(CrmCoupon(merchant_id=ctx.merchant_id, customer_id=c.id, name=req.name,
                         discount_type=req.discount_type, value=req.value, expires_at=exp,
                         memo=f"{req.segment} 일괄발급"))
        n += 1
    db.commit()
    return {"ok": True, "issued": n, "segment": req.segment}


@router.put("/coupons/{cpid}")
def update_coupon(cpid: int, status: Optional[str] = None, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    cp = db.query(CrmCoupon).filter(CrmCoupon.id == cpid, CrmCoupon.merchant_id == ctx.merchant_id).first()
    if not cp:
        raise HTTPException(404, "쿠폰을 찾을 수 없습니다")
    if status:
        cp.status = CouponStatus(status)
        if cp.status == CouponStatus.USED:
            cp.used_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/coupons/{cpid}")
def delete_coupon(cpid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    cp = db.query(CrmCoupon).filter(CrmCoupon.id == cpid, CrmCoupon.merchant_id == ctx.merchant_id).first()
    if not cp:
        raise HTTPException(404, "쿠폰을 찾을 수 없습니다")
    db.delete(cp); db.commit()
    return {"ok": True}


# ─── Messages ───────────────────────────────────────────────

def _render_message(body: str, customer: Optional[CrmCustomer], merchant_name: str) -> str:
    out = body.replace("{매장명}", merchant_name)
    if customer:
        out = out.replace("{고객명}", customer.name or "고객")
        out = out.replace("{포인트}", str(customer.points or 0))
    else:
        out = out.replace("{고객명}", "고객")
    return out


@router.get("/message-templates")
def list_templates(ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    rows = db.query(CrmMessageTemplate).filter(CrmMessageTemplate.merchant_id == ctx.merchant_id).order_by(CrmMessageTemplate.created_at).all()
    return [{"id": t.id, "name": t.name, "channel": t.channel.value, "category": t.category,
             "body": t.body, "is_active": t.is_active} for t in rows]


@router.post("/message-templates")
def create_template(req: TemplateIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    t = CrmMessageTemplate(merchant_id=ctx.merchant_id, name=req.name,
                           channel=MessageChannel(req.channel), category=req.category, body=req.body)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id}


@router.put("/message-templates/{tid}")
def update_template(tid: int, req: TemplateUpdate, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    t = db.query(CrmMessageTemplate).filter(CrmMessageTemplate.id == tid, CrmMessageTemplate.merchant_id == ctx.merchant_id).first()
    if not t:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")
    payload = req.model_dump(exclude_unset=True)
    if payload.get("channel"):
        t.channel = MessageChannel(payload.pop("channel"))
    else:
        payload.pop("channel", None)
    for k, v in payload.items():
        setattr(t, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/message-templates/{tid}")
def delete_template(tid: int, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    t = db.query(CrmMessageTemplate).filter(CrmMessageTemplate.id == tid, CrmMessageTemplate.merchant_id == ctx.merchant_id).first()
    if not t:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")
    db.delete(t); db.commit()
    return {"ok": True}


@router.get("/messages")
def list_messages(limit: int = Query(100, ge=1, le=500), ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    rows = db.query(CrmMessageLog).filter(CrmMessageLog.merchant_id == ctx.merchant_id).order_by(CrmMessageLog.sent_at.desc()).limit(limit).all()
    cust_names = {c.id: c.name for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id).all()}
    return [{"id": mm.id, "customer_id": mm.customer_id, "customer_name": cust_names.get(mm.customer_id) or "-",
             "channel": mm.channel.value, "to_phone": mm.to_phone, "content": mm.content,
             "status": mm.status.value, "campaign": mm.campaign, "sent_at": str(mm.sent_at)} for mm in rows]


@router.post("/messages/send")
def send_messages(req: SendMessageIn, ctx: CrmContext = Depends(get_crm_context), db: Session = Depends(get_db)):
    # 세그먼트(전체/휴면/생일/VIP) 일괄 발송은 원장/관리자만
    if req.segment and not req.customer_ids:
        _require_owner_admin(ctx, "고객 일괄 문자 발송은 원장 계정에서만 가능합니다.")

    # 발송 대상 결정
    targets = []
    if req.customer_ids:
        targets = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.id.in_(req.customer_ids)).all()
    elif req.segment:
        targets = _segment_customers(db, ctx, req.segment)
    if not targets:
        raise HTTPException(400, "발송 대상이 없습니다")

    body = req.content
    if req.template_id:
        t = db.query(CrmMessageTemplate).filter(CrmMessageTemplate.id == req.template_id, CrmMessageTemplate.merchant_id == ctx.merchant_id).first()
        if not t:
            raise HTTPException(404, "템플릿을 찾을 수 없습니다")
        body = t.body
        channel = t.channel
    else:
        channel = MessageChannel(req.channel)
    if not body:
        raise HTTPException(400, "발송 내용이 없습니다")

    now = datetime.utcnow()
    n = 0
    for c in targets:
        content = _render_message(body, c, ctx.merchant.name)
        db.add(CrmMessageLog(merchant_id=ctx.merchant_id, customer_id=c.id, template_id=req.template_id,
                             channel=channel, to_phone=c.phone, content=content,
                             status=MessageStatus.SENT, campaign=req.campaign or (req.segment or "manual")))
        c.last_message_at = now
        n += 1
    db.commit()
    return {"ok": True, "sent": n, "note": "목업 발송(실제 문자 미발송) — 발송 내역만 기록됩니다."}
