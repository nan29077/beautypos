"""플랜 배정 · 광고 집행 집계 헬퍼."""
from calendar import monthrange
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.plan import (
    Plan, MerchantPlan, MerchantAdOverride, AdExecution,
    AD_EXECUTION_TYPES, AD_EXECUTION_TYPE_CODES, AD_EXECUTION_TYPE_LABELS,
)
from app.services.settlement_service import VAT_NOTICE, VAT_RATE
from app.utils.kst import today_kst

DEFAULT_PLAN_CODE = "basic"


def get_plan_by_code(db: Session, code: str) -> Optional[Plan]:
    return db.query(Plan).filter(Plan.code == code).first()


def get_current_plan(db: Session, merchant_id: int) -> Optional[Plan]:
    """가맹점의 현재 플랜. 배정 이력이 없으면 None."""
    mp = current_assignment(db, merchant_id)
    return mp.plan if mp else None


def current_assignment(db: Session, merchant_id: int) -> Optional[MerchantPlan]:
    """가장 최근 배정 레코드."""
    return (
        db.query(MerchantPlan)
        .filter(MerchantPlan.merchant_id == merchant_id)
        .order_by(MerchantPlan.assigned_at.desc(), MerchantPlan.id.desc())
        .first()
    )


def assign_plan(db: Session, merchant_id: int, plan_id: int, assigned_by: Optional[int] = None) -> MerchantPlan:
    """가맹점에 플랜을 배정한다 (이력 추가). flush 까지만 하고 commit 은 호출자 책임."""
    mp = MerchantPlan(merchant_id=merchant_id, plan_id=plan_id, assigned_by=assigned_by)
    db.add(mp)
    db.flush()
    return mp


def ensure_default_plan(db: Session, merchant_id: int, assigned_by: Optional[int] = None) -> Optional[MerchantPlan]:
    """가맹점에 배정된 플랜이 없으면 베이직을 배정한다.

    플랜 테이블이 아직 비어 있으면(시드 전) 조용히 넘어간다 — 가맹점 생성이 실패하면 안 된다.
    """
    if current_assignment(db, merchant_id):
        return None
    basic = get_plan_by_code(db, DEFAULT_PLAN_CODE)
    if not basic:
        return None
    return assign_plan(db, merchant_id, basic.id, assigned_by)


def month_bounds(day: date) -> tuple[date, date]:
    """day 가 속한 달의 (1일, 말일)."""
    last = monthrange(day.year, day.month)[1]
    return date(day.year, day.month, 1), date(day.year, day.month, last)


def daily_target_for_date(monthly_target: int, target_date: date) -> int:
    """월 목표를 해당 월의 날짜에 정수 단위로 고르게 분배한다.

    누적 비율의 차이를 사용하므로 모든 일별 목표의 합은 월 목표와 정확히 같다.
    예: 30일인 달의 10건 → 3·6·9…30일에 각 1건.
    """
    monthly = max(0, int(monthly_target or 0))
    days = monthrange(target_date.year, target_date.month)[1]
    previous = ((target_date.day - 1) * monthly) // days
    current = (target_date.day * monthly) // days
    return current - previous


def expected_target_through_date(monthly_target: int, target_date: date) -> int:
    """기준일까지 달성해야 할 월 누적 목표."""
    monthly = max(0, int(monthly_target or 0))
    days = monthrange(target_date.year, target_date.month)[1]
    return (target_date.day * monthly) // days


def daily_target_description(monthly_target: int, target_date: date) -> str:
    """관리자가 월 목표를 입력할 때 보여줄 쉬운 자동 배분 설명."""
    monthly = max(0, int(monthly_target or 0))
    days = monthrange(target_date.year, target_date.month)[1]
    if monthly == 0:
        return "월 목표 없음"
    if monthly < days:
        interval = max(1, round(days / monthly))
        return f"약 {interval}일마다 1건"
    low, remainder = divmod(monthly, days)
    high = low + (1 if remainder else 0)
    return f"일자별 {low}~{high}건" if high != low else f"매일 {low}건"


def plan_payload(plan: Plan, target_date: Optional[date] = None) -> dict:
    """Plan → JSON 직렬화 가능한 dict."""
    target_date = target_date or today_kst()
    fee_exclusive = float(plan.merchant_fee_rate or 0)
    data = {
        "id": plan.id,
        "name": plan.name,
        "code": plan.code,
        # 플랜 수수료는 퍼센트 단위의 부가세 별도 공급가다.
        "merchant_fee_rate": fee_exclusive,
        "merchant_fee_rate_with_vat": round(fee_exclusive * (1 + VAT_RATE), 2),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "created_at": str(plan.created_at) if plan.created_at else None,
        "updated_at": str(plan.updated_at) if plan.updated_at else None,
    }
    for code, _label in AD_EXECUTION_TYPES:
        monthly = plan.target(code, "monthly")
        data[f"{code}_monthly"] = monthly
        data[f"{code}_daily"] = daily_target_for_date(monthly, target_date)
        data[f"{code}_daily_average"] = round(monthly / monthrange(target_date.year, target_date.month)[1], 2)
        data[f"{code}_daily_description"] = daily_target_description(monthly, target_date)
    return data


def get_override_map(db: Session, merchant_id: int) -> dict:
    """가맹점의 광고 타입별 monthly_override 맵. 없는 타입은 포함하지 않는다."""
    rows = (
        db.query(MerchantAdOverride)
        .filter(MerchantAdOverride.merchant_id == merchant_id)
        .all()
    )
    return {r.ad_type: r.monthly_override for r in rows if r.monthly_override is not None}


def effective_monthly_target(db: Session, merchant_id: int, ad_type: str, plan: Optional[Plan]) -> int:
    """오버라이드가 있으면 오버라이드 값, 없으면 플랜 기본값을 반환한다."""
    row = (
        db.query(MerchantAdOverride)
        .filter(
            MerchantAdOverride.merchant_id == merchant_id,
            MerchantAdOverride.ad_type == ad_type,
        )
        .first()
    )
    if row and row.monthly_override is not None:
        return int(row.monthly_override)
    return plan.target(ad_type, "monthly") if plan else 0


def set_override(db: Session, merchant_id: int, ad_type: str, monthly: Optional[int]) -> None:
    """오버라이드를 저장한다. monthly=None 이면 해당 타입 오버라이드를 제거한다."""
    row = (
        db.query(MerchantAdOverride)
        .filter(
            MerchantAdOverride.merchant_id == merchant_id,
            MerchantAdOverride.ad_type == ad_type,
        )
        .first()
    )
    if monthly is None:
        if row:
            db.delete(row)
    else:
        if row:
            row.monthly_override = monthly
        else:
            db.add(MerchantAdOverride(
                merchant_id=merchant_id,
                ad_type=ad_type,
                monthly_override=monthly,
            ))


def build_summary(db: Session, target_date: date, merchants: list) -> list[dict]:
    """가맹점별 × 광고종류별 집행 현황 요약.

    반환: [{merchant_id, merchant_name, plan_code, plan_name, items: [...]}, ...]
    """
    if not merchants:
        return []

    merchant_ids = [m.id for m in merchants]
    month_start, month_end = month_bounds(target_date)

    # 오늘 집행량
    today_rows = (
        db.query(AdExecution.merchant_id, AdExecution.ad_type, func.sum(AdExecution.executed_count))
        .filter(AdExecution.merchant_id.in_(merchant_ids), AdExecution.execution_date == target_date)
        .group_by(AdExecution.merchant_id, AdExecution.ad_type)
        .all()
    )
    today_map = {(mid, at): int(total or 0) for mid, at, total in today_rows}

    # 이번 달 누적 (기준일이 속한 달 전체)
    month_rows = (
        db.query(AdExecution.merchant_id, AdExecution.ad_type, func.sum(AdExecution.executed_count))
        .filter(
            AdExecution.merchant_id.in_(merchant_ids),
            AdExecution.execution_date >= month_start,
            AdExecution.execution_date <= month_end,
        )
        .group_by(AdExecution.merchant_id, AdExecution.ad_type)
        .all()
    )
    month_map = {(mid, at): int(total or 0) for mid, at, total in month_rows}

    # 현재 플랜 (가맹점별 최신 배정 1건)
    assignments = (
        db.query(MerchantPlan)
        .filter(MerchantPlan.merchant_id.in_(merchant_ids))
        .order_by(MerchantPlan.assigned_at.asc(), MerchantPlan.id.asc())
        .all()
    )
    plan_by_merchant = {mp.merchant_id: mp.plan for mp in assignments}  # 뒤에 온 것이 최신

    # 가맹점별 오버라이드 (한 번에 조회)
    override_rows = (
        db.query(MerchantAdOverride)
        .filter(MerchantAdOverride.merchant_id.in_(merchant_ids))
        .all()
    )
    # {merchant_id: {ad_type: monthly_override}}
    override_map: dict = {}
    for r in override_rows:
        if r.monthly_override is not None:
            override_map.setdefault(r.merchant_id, {})[r.ad_type] = int(r.monthly_override)

    results = []
    for m in merchants:
        plan = plan_by_merchant.get(m.id)
        items = []
        for ad_type, label in AD_EXECUTION_TYPES:
            plan_monthly = plan.target(ad_type, "monthly") if plan else 0
            monthly_target = override_map.get(m.id, {}).get(ad_type, plan_monthly)
            daily_target = daily_target_for_date(monthly_target, target_date)
            expected_to_date = expected_target_through_date(monthly_target, target_date)
            today_executed = today_map.get((m.id, ad_type), 0)
            month_total = month_map.get((m.id, ad_type), 0)
            daily_remaining = max(0, daily_target - today_executed)
            monthly_remaining = monthly_target - month_total
            pace_remaining = max(0, expected_to_date - month_total)
            items.append({
                "ad_type": ad_type,
                "ad_type_label": label,
                "daily_target": daily_target,
                "daily_average": round(
                    monthly_target / monthrange(target_date.year, target_date.month)[1], 2
                ),
                "daily_description": daily_target_description(monthly_target, target_date),
                "expected_to_date": expected_to_date,
                "monthly_target": monthly_target,
                "today_executed": today_executed,
                "month_total": month_total,
                "daily_remaining": daily_remaining,
                "pace_remaining": pace_remaining,
                "monthly_remaining": monthly_remaining,
                # 오늘 한 건이 없는 저빈도 플랜도 월 누적 진도로 정확히 미달 여부를 판단한다.
                # 목표 초과 달성은 미달이 아니다 (is_over 로 별도 표시).
                "is_behind": pace_remaining > 0,
                "is_over": monthly_remaining < 0,
            })
        results.append({
            "merchant_id": m.id,
            "merchant_name": m.name,
            "plan_id": plan.id if plan else None,
            "plan_code": plan.code if plan else None,
            "plan_name": plan.name if plan else "미배정",
            "has_override": bool(override_map.get(m.id)),
            "items": items,
        })
    return results

# KST import (appended to avoid circular import issues at module top)
