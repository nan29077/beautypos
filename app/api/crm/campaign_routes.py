"""CRM 쿠폰/포인트/마케팅(재방문·생일 타겟, 메시지 발송) 라우트."""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.crm import (
    CrmCustomer, CrmPointLog, CrmMessageTemplate, CrmMessageLog, CrmCoupon,
    MessageChannel, MessageStatus, CouponStatus,
)
from app.api.crm._helpers import (
    CrmContext, get_crm_context,
    _staff_name_map, _require_owner_admin,
    _customer_stats, _customer_grade, _serialize_customer,
    _parse_date,
    REVISIT_DORMANT_DAYS, DORMANT_CAMPAIGN_DAYS,
)

router = APIRouter()


# ─── 스키마 ─────────────────────────────────────────────────

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


# ─── Points (고객 자산) ──────────────────────────────────────

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
            # 등급상 "휴면" 여부와 무관하게, 누적 실적 기준 상위 고객(VIP/골드)을 대상으로 한다.
            if _customer_grade(st["visit_count"], st["total_spent"]) in ("VIP", "골드"):
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
