"""CRM 분석/통계 엔드포인트: 대시보드 요약, 세부 분석, 디자이너별 실적."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models.staff import Staff
from app.models.crm import CrmCustomer, CrmVisit, CrmReservation, ReservationStatus
from app.utils.kst import today_kst
from app.api.crm._helpers import (
    CrmContext, get_crm_context,
    _staff_name_map, _effective_scope,
    _customer_stats, _customer_grade, _visit_cycle_days,
    REVISIT_DORMANT_DAYS,
)

router = APIRouter()


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

    # 최근 6개월 매출 + 월별 신규 고객수
    monthly = []
    new_customers_monthly = []
    months = []
    cur = month_start
    for _ in range(6):
        months.append(cur)
        cur = (cur - timedelta(days=1)).replace(day=1)
    for ms in reversed(months):
        me = (ms + timedelta(days=32)).replace(day=1)
        rev = _visit_scope(db.query(func.coalesce(func.sum(CrmVisit.amount), 0)).filter(CrmVisit.merchant_id == ctx.merchant_id, CrmVisit.visit_date >= ms, CrmVisit.visit_date < me), ctx, scope).scalar() or 0
        monthly.append({"month": ms.strftime("%Y-%m"), "revenue": float(rev)})
        nc_q = db.query(func.count(CrmCustomer.id)).filter(
            CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.created_at >= ms, CrmCustomer.created_at < me)
        if sid:
            nc_q = nc_q.filter(or_(CrmCustomer.assigned_staff_id == sid, CrmCustomer.preferred_staff_id == sid))
        new_customers_monthly.append({"month": ms.strftime("%Y-%m"), "count": int(nc_q.scalar() or 0)})

    # 재방문 대상 수
    dormant_cut = now - timedelta(days=REVISIT_DORMANT_DAYS)
    stats_map = _customer_stats(db, ctx.merchant_id)
    revisit_due = sum(1 for st in stats_map.values() if st["last_visit"] and st["last_visit"] < dormant_cut)

    # 이번달 생일 고객 수
    birthdays = sum(1 for c in db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id, CrmCustomer.birthday.isnot(None)).all() if c.birthday and c.birthday.month == now.month)

    # 재방문율 / 평균 방문주기 / 등급별 분포
    all_cust_q = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id)
    if sid:
        all_cust_q = all_cust_q.filter(or_(CrmCustomer.assigned_staff_id == sid, CrmCustomer.preferred_staff_id == sid))
    all_customers = all_cust_q.all()
    today = today_kst()
    visited_cnt = 0
    revisited_cnt = 0
    cycle_values = []
    grade_dist = {"VIP": 0, "골드": 0, "실버": 0, "일반": 0, "휴면": 0}
    for c in all_customers:
        cst = stats_map.get(c.id, {"visit_count": 0, "total_spent": 0.0, "last_visit": None, "first_visit": None})
        vcnt = cst["visit_count"]
        if vcnt >= 1:
            visited_cnt += 1
        if vcnt >= 2:
            revisited_cnt += 1
        cyc = _visit_cycle_days(cst)
        if cyc:
            cycle_values.append(cyc)
        g = _customer_grade(vcnt, cst["total_spent"], cst["last_visit"], today)
        grade_dist[g] = grade_dist.get(g, 0) + 1
    revisit_rate = round(revisited_cnt / visited_cnt * 100, 1) if visited_cnt else 0.0
    avg_visit_cycle_days = round(sum(cycle_values) / len(cycle_values), 1) if cycle_values else None

    return {
        "merchant_name": ctx.merchant.name, "scope_mine": bool(sid),
        "total_customers": int(total_customers), "new_this_month": int(new_this_month),
        "visits_today": int(visits_today), "revenue_today": float(revenue_today),
        "visits_month": int(visits_month), "revenue_month": float(revenue_month),
        "revenue_total": float(revenue_total), "avg_ticket_month": avg_ticket_month,
        "reservations_today": int(reservations_today), "reservations_upcoming": int(reservations_upcoming),
        "revisit_due": revisit_due, "birthdays_this_month": birthdays,
        "top_services": top_services, "staff_sales": staff_sales, "monthly_revenue": monthly,
        # ↓ 고도화로 추가된 필드
        "new_customers_monthly": new_customers_monthly,
        "revisit_rate": revisit_rate,
        "avg_visit_cycle_days": avg_visit_cycle_days,
        "grade_distribution": grade_dist,
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


@router.get("/staff-performance")
def staff_performance(
    scope: str = Query("auto", description="auto/mine/all"),
    ctx: CrmContext = Depends(get_crm_context),
    db: Session = Depends(get_db),
):
    """디자이너별 실적: 담당 고객수, 담당 고객 평균 매출, 재방문율(2회 이상 방문 고객 비율)."""
    scope = _effective_scope(ctx, scope)
    use_mine = (scope == "mine") or (scope == "auto" and ctx.is_designer)

    staff_q = db.query(Staff).filter(Staff.merchant_id == ctx.merchant_id, Staff.is_active == True)
    if use_mine and ctx.staff_id:
        staff_q = staff_q.filter(Staff.id == ctx.staff_id)
    staff_rows = staff_q.all()

    stats = _customer_stats(db, ctx.merchant_id)
    customers = db.query(CrmCustomer).filter(CrmCustomer.merchant_id == ctx.merchant_id).all()

    by_staff = {}
    for c in customers:
        if not c.assigned_staff_id:
            continue
        st = stats.get(c.id, {"visit_count": 0, "total_spent": 0.0})
        d = by_staff.setdefault(c.assigned_staff_id, {
            "customer_count": 0, "total_spent": 0.0, "visited_count": 0, "revisit_count": 0,
        })
        d["customer_count"] += 1
        d["total_spent"] += st.get("total_spent", 0.0)
        vc = st.get("visit_count", 0)
        if vc >= 1:
            d["visited_count"] += 1
        if vc >= 2:
            d["revisit_count"] += 1

    result = []
    for s in staff_rows:
        d = by_staff.get(s.id, {"customer_count": 0, "total_spent": 0.0, "visited_count": 0, "revisit_count": 0})
        cnt = d["customer_count"]
        avg_customer_spent = round(d["total_spent"] / cnt) if cnt else 0
        revisit_rate = round(d["revisit_count"] / d["visited_count"] * 100, 1) if d["visited_count"] else 0.0
        result.append({
            "staff_id": s.id, "staff_name": s.name,
            "customer_count": cnt,
            "avg_customer_spent": avg_customer_spent,
            "revisit_rate": revisit_rate,
        })
    result.sort(key=lambda x: x["avg_customer_spent"], reverse=True)
    return {"scope_mine": bool(use_mine and ctx.staff_id), "staff": result}
