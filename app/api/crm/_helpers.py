"""CRM 라우터 공통 헬퍼.

- CrmContext / get_crm_context : 원장·디자이너·관리자 권한 스코프 판정
- 권한 체크 헬퍼 (_require_crm_management, _require_owner_admin, _effective_scope)
- 고객 등급/자동태그/직렬화 로직 (_customer_grade, _auto_tags, _serialize_customer)
- 날짜 파싱 유틸 (_parse_dt, _parse_date)

customer_routes.py / analytics_routes.py / campaign_routes.py 가 공통으로 사용한다.
"""
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.staff import Staff
from app.models.crm import CrmCustomer, CrmVisit
from app.auth.dependencies import require_roles
from app.utils.kst import today_kst

require_crm = require_roles([UserRole.ADMIN, UserRole.OWNER, UserRole.DESIGNER])

REVISIT_DORMANT_DAYS = 30
DORMANT_CAMPAIGN_DAYS = 60           # 마케팅 "휴면" 태그/세그먼트 기준
DORMANT_GRADE_DAYS = 180             # 등급상 "휴면" 판정 기준 (마지막 방문 180일 이상)
CHURN_RISK_CYCLE_MULTIPLIER = 1.5    # 이탈위험 판정 배수 (평균 방문주기 대비)
LONG_ABSENCE_DAYS = 90               # 장기미방문 태그 기준
BIRTHDAY_SOON_DAYS = 7               # 생일임박 기준(연도 무시)


def _assert_staff_in_merchant(db: Session, ctx: "CrmContext", *staff_ids) -> None:
    """넘어온 staff_id 들이 모두 이 미용실 소속인지 확인한다.

    검증이 없으면 다른 미용실의 staff.id 를 그대로 넣어 고객·방문·예약을
    남의 직원에게 붙일 수 있다 (매출 귀속과 예약 충돌 검사가 어긋난다).
    None 은 '미지정'이라 통과시킨다.
    """
    wanted = {int(sid) for sid in staff_ids if sid is not None}
    if not wanted:
        return
    found = {
        row[0] for row in db.query(Staff.id).filter(
            Staff.id.in_(wanted), Staff.merchant_id == ctx.merchant_id
        ).all()
    }
    missing = wanted - found
    if missing:
        raise HTTPException(400, "해당 매장 소속 직원이 아닙니다 "
                                 f"(staff_id={', '.join(str(i) for i in sorted(missing))})")


# ─── Context ────────────────────────────────────────────────

class CrmContext:
    def __init__(self, merchant: Merchant, role: UserRole, staff_id: Optional[int]):
        self.merchant = merchant
        self.merchant_id = merchant.id
        self.role = role
        self.staff_id = staff_id          # 디자이너 본인 staff.id
        self.is_designer = role == UserRole.DESIGNER


def get_crm_context(
    merchant_id: Optional[int] = Query(None, description="관리자 전용: 대상 매장 ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_crm),
) -> CrmContext:
    if user.role == UserRole.OWNER:
        m = db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()
        if not m:
            raise HTTPException(404, "사장님 소유 매장을 찾을 수 없습니다")
        return CrmContext(m, user.role, None)
    if user.role == UserRole.DESIGNER:
        staff = db.query(Staff).filter(Staff.user_id == user.id, Staff.is_active == True).first()
        if not staff:
            raise HTTPException(404, "직원 소속 매장을 찾을 수 없습니다")
        m = db.query(Merchant).filter(Merchant.id == staff.merchant_id).first()
        if not m:
            raise HTTPException(404, "소속 매장을 찾을 수 없습니다")
        return CrmContext(m, user.role, staff.id)
    # ADMIN
    q = db.query(Merchant)
    m = q.filter(Merchant.id == merchant_id).first() if merchant_id else q.order_by(Merchant.id).first()
    if not m:
        raise HTTPException(404, "매장을 찾을 수 없습니다")
    return CrmContext(m, user.role, None)


# ─── 공통 유틸 ──────────────────────────────────────────────

def _staff_name_map(db: Session, merchant_id: int) -> dict:
    rows = db.query(Staff).filter(Staff.merchant_id == merchant_id).all()
    return {s.id: s.name for s in rows}


def _require_crm_management(ctx: CrmContext) -> None:
    """Keep merchant-wide configuration changes owner/admin only."""
    if ctx.is_designer or ctx.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="매장 공통 설정은 사장님 계정에서 관리해 주세요.")


def _require_owner_admin(ctx: CrmContext, message: str) -> None:
    """고객 자산(포인트/쿠폰)·일괄 발송·영구 삭제는 원장/관리자만 수행한다."""
    if ctx.is_designer or ctx.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail=message)


def _effective_scope(ctx: CrmContext, scope: str) -> str:
    """디자이너는 매출/실적 조회 범위를 본인 것으로 강제한다 (scope=all 권한 상승 차단)."""
    if ctx.is_designer:
        return "mine"
    return scope


def _customer_grade(
    visit_count: int,
    total_spent: float,
    last_visit: Optional[datetime] = None,
    today: Optional[date] = None,
) -> str:
    """고객 등급 산정.

    우선순위(등급 판정보다 "휴면"이 우선):
      휴면  : 마지막 방문 후 180일 이상 경과
      VIP   : 방문 20회 이상 또는 누적 100만원 이상
      골드  : 방문 10회 이상 또는 누적 50만원 이상
      실버  : 방문 5회 이상 또는 누적 20만원 이상
      일반  : 그 외
    """
    if today is None:
        today = today_kst()
    if last_visit is not None:
        last_date = last_visit.date() if isinstance(last_visit, datetime) else last_visit
        if (today - last_date).days >= DORMANT_GRADE_DAYS:
            return "휴면"
    if total_spent >= 1_000_000 or visit_count >= 20:
        return "VIP"
    if total_spent >= 500_000 or visit_count >= 10:
        return "골드"
    if total_spent >= 200_000 or visit_count >= 5:
        return "실버"
    return "일반"


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


def _is_birthday_soon(birthday: Optional[date], today: date, window_days: int = BIRTHDAY_SOON_DAYS) -> bool:
    """생일이 오늘부터 window_days 이내인지 판정 (연도 무시, 연말/연초 경계 처리)."""
    if not birthday:
        return False
    for year_offset in (0, 1):
        try:
            bday_this_year = birthday.replace(year=today.year + year_offset)
        except ValueError:
            # 2/29 생일이 평년일 때
            bday_this_year = birthday.replace(year=today.year + year_offset, day=28)
        delta = (bday_this_year - today).days
        if 0 <= delta <= window_days:
            return True
    return False


def _visit_cycle_days(st: dict) -> Optional[int]:
    vc = st.get("visit_count", 0)
    first = st.get("first_visit")
    last = st.get("last_visit")
    if vc >= 2 and first and last and last > first:
        return round((last - first).days / (vc - 1))
    return None


def _auto_tags(st: dict, customer: CrmCustomer, now: datetime) -> List[str]:
    tags = []
    vc = st.get("visit_count", 0)
    total = st.get("total_spent", 0)
    last = st.get("last_visit")
    today = today_kst()
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

    # 이탈위험: 방문 3회 이상 고객 중, 마지막 방문 후 경과일이 평균 방문주기의 1.5배 초과
    cycle = _visit_cycle_days(st)
    if vc >= 3 and cycle and last:
        days_since = (today - last.date()).days
        if days_since > cycle * CHURN_RISK_CYCLE_MULTIPLIER:
            tags.append("이탈위험")

    # 장기미방문: 90일 이상 미방문
    if last and (today - last.date()).days >= LONG_ABSENCE_DAYS:
        tags.append("장기미방문")

    # 생일임박: 7일 이내 생일 (연도 무시, 연말/연초 경계 처리)
    if _is_birthday_soon(customer.birthday, today):
        tags.append("생일임박")

    return tags


def _serialize_customer(c: CrmCustomer, stats: dict, staff_names: dict, now: datetime) -> dict:
    st = stats.get(c.id, {"visit_count": 0, "total_spent": 0.0, "last_visit": None, "first_visit": None})
    cycle = _visit_cycle_days(st)
    last = st["last_visit"]
    today = today_kst()
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
        "grade": _customer_grade(st["visit_count"], st["total_spent"], last, today),
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
