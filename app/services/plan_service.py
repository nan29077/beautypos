"""플랜 배정 · 광고 집행 집계 헬퍼."""
from calendar import monthrange
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.plan import (
    Plan, MerchantPlan, AdExecution,
    AD_EXECUTION_TYPES, AD_EXECUTION_TYPE_CODES, AD_EXECUTION_TYPE_LABELS,
)

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


def plan_payload(plan: Plan) -> dict:
    """Plan → JSON 직렬화 가능한 dict."""
    data = {
        "id": plan.id,
        "name": plan.name,
        "code": plan.code,
        "merchant_fee_rate": float(plan.merchant_fee_rate or 0),
        "created_at": str(plan.created_at) if plan.created_at else None,
        "updated_at": str(plan.updated_at) if plan.updated_at else None,
    }
    for code, _label in AD_EXECUTION_TYPES:
        data[f"{code}_daily"] = plan.target(code, "daily")
        data[f"{code}_monthly"] = plan.target(code, "monthly")
    return data


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

    results = []
    for m in merchants:
        plan = plan_by_merchant.get(m.id)
        items = []
        for ad_type, label in AD_EXECUTION_TYPES:
            daily_target = plan.target(ad_type, "daily") if plan else 0
            monthly_target = plan.target(ad_type, "monthly") if plan else 0
            today_executed = today_map.get((m.id, ad_type), 0)
            month_total = month_map.get((m.id, ad_type), 0)
            daily_remaining = daily_target - today_executed
            monthly_remaining = monthly_target - month_total
            items.append({
                "ad_type": ad_type,
                "ad_type_label": label,
                "daily_target": daily_target,
                "monthly_target": monthly_target,
                "today_executed": today_executed,
                "month_total": month_total,
                "daily_remaining": daily_remaining,
                "monthly_remaining": monthly_remaining,
                # 일 목표 미달성이거나 월 잔여가 음수면 경고(깜빡임) 대상
                "is_behind": daily_remaining > 0 or monthly_remaining < 0,
                "is_over": monthly_remaining < 0,
            })
        results.append({
            "merchant_id": m.id,
            "merchant_name": m.name,
            "plan_id": plan.id if plan else None,
            "plan_code": plan.code if plan else None,
            "plan_name": plan.name if plan else "미배정",
            "items": items,
        })
    return results
