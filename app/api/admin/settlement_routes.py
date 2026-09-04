"""Admin routes — fee-policy, fee-policy-overview, settlements, sales-assignments,
sales-managers, transactions, staff 분배율, commission-visibility 등 payout 을 제외한
정산/수수료 관련 전부."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.transaction import Transaction, TransactionStatus
from app.models.settlement import FeePolicy, SalesCommissionPolicy, MerchantSalesAssignment, Settlement
from app.models.staff import Staff
from app.models.system_config import (
    SystemConfig,
    COMMISSION_VISIBLE_TO_SALES, COMMISSION_VISIBLE_TO_OWNER, COMMISSION_VISIBLE_TO_DESIGNER,
)
from app.auth.dependencies import require_admin
from app.services.settlement_service import (
    compute_distribution, get_effective_fee_rates, compute_fee_distribution,
    DEFAULT_MERCHANT_FEE_RATE, DEFAULT_PG_FEE_RATE, DEFAULT_SALES_COMMISSION_RATE,
    apply_vat, format_rate_excl_vat, format_rate_with_vat,
    VAT_RATE, VAT_NOTICE,
)
from app.schemas.schemas import (
    FeePolicyUpdate, GlobalFeeSettingsUpdate, MerchantFeeOverrideUpdate, SalesCommissionOverrideUpdate,
    SalesAssignmentCreate, SalesAssignmentUpdate,
    CommissionVisibilityUpdate, StaffShareRateUpdate,
)
from app.api.admin._helpers import _validate_commission_rate, _validate_merchant_commission_fit
from app.utils.kst import KST, kst_day_start_utc

router = APIRouter()


def _parse_kst_bound(value: str, *, next_day: bool = False) -> datetime:
    """조회 조건으로 들어온 날짜/일시 문자열을 KST 로 해석해 naive UTC 로 변환한다.

    DB 에는 naive UTC 로 저장되므로, "YYYY-MM-DD" 만 들어오면 그 날의
    00:00 KST 를 UTC 로 환산해야 한국 기준 하루 경계와 맞는다.
    next_day=True 면 다음 날 00:00 KST (상한 경계) 를 돌려준다.

    ValueError 는 호출부에서 400 으로 변환한다.
    """
    text = value.strip()
    parsed = datetime.fromisoformat(text)
    if len(text) <= 10:  # 날짜만 (YYYY-MM-DD)
        day = parsed.date() + (timedelta(days=1) if next_day else timedelta(0))
        return kst_day_start_utc(day)
    # 시각까지 들어온 경우 — KST 로 간주하고 UTC 로 환산
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    utc_naive = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_naive + timedelta(days=1) if next_day else utc_naive


# ─── Transactions ────────────────────────────────────────────

@router.get("/transactions")
def list_all_transactions(
    merchant_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200, offset: int = 0,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    try:
        # 입력은 KST 기준 날짜, DB 는 naive UTC — 경계를 KST 로 맞춘다.
        dt_from = _parse_kst_bound(date_from) if date_from else None
        dt_to = _parse_kst_bound(date_to, next_day=True) if date_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")

    q = db.query(Transaction).filter(Transaction.status == TransactionStatus.APPROVED)
    if merchant_id:
        q = q.filter(Transaction.merchant_id == merchant_id)
    if dt_from:
        q = q.filter(Transaction.created_at >= dt_from)
    if dt_to:
        q = q.filter(Transaction.created_at < dt_to)
    total_count = q.count()
    # Calculate total from filtered query
    amount_q = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.status == TransactionStatus.APPROVED
    )
    if merchant_id:
        amount_q = amount_q.filter(Transaction.merchant_id == merchant_id)
    if dt_from:
        amount_q = amount_q.filter(Transaction.created_at >= dt_from)
    if dt_to:
        amount_q = amount_q.filter(Transaction.created_at < dt_to)
    total_amount = float(amount_q.scalar())

    txns = q.order_by(Transaction.created_at.desc()).offset(offset).limit(limit).all()

    # 거래마다 직원·가맹점을 다시 읽으면 목록 크기만큼 쿼리가 늘어난다.
    staff_names = dict(
        db.query(Staff.id, Staff.name)
        .filter(Staff.id.in_({t.staff_id for t in txns if t.staff_id})).all()
    ) if txns else {}
    merchant_names = dict(
        db.query(Merchant.id, Merchant.name)
        .filter(Merchant.id.in_({t.merchant_id for t in txns})).all()
    ) if txns else {}

    results = []
    for t in txns:
        staff_name = staff_names.get(t.staff_id) if t.staff_id else None
        results.append({
            "id": t.id, "merchant_id": t.merchant_id,
            "merchant_name": merchant_names.get(t.merchant_id, f"가맹점#{t.merchant_id}"),
            "terminal_id": t.terminal_id,
            "staff_id": t.staff_id, "staff_name": staff_name,
            "amount": float(t.amount), "installment_months": t.installment_months,
            "card_brand": t.card_brand, "approval_code": t.approval_code,
            "staff_code_input": t.staff_code_input,
            "approved_at": str(t.approved_at) if t.approved_at else None,
            "created_at": str(t.created_at),
        })
    return {"transactions": results, "total_count": total_count, "total_amount": total_amount}


# ─── Fee Policies ────────────────────────────────────────────

@router.get("/merchants/{mid}/fee-policy")
def get_fee_policy(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == mid,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None
    mfr, pgr, comm_rate = get_effective_fee_rates(db, mid, sales_manager_user_id)

    sales_info = None
    if assign:
        sales_user = db.query(User).filter(User.id == assign.sales_manager_user_id).first()
        sales_info = {
            "assignment_id": assign.id,
            "sales_manager_id": assign.sales_manager_user_id,
            "sales_manager_name": sales_user.name if sales_user else None,
            "commission_rate": comm_rate,
            "commission_rate_pct": round(comm_rate * 100, 2),
            "memo": assign.memo,
        }

    # 실제 적용율 (부가세 포함) — 금액은 이 값으로 계산된다.
    mfr_vat = apply_vat(mfr)
    pgr_vat = apply_vat(pgr)

    sample = 10000
    sim_merchant_fee = round(sample * mfr_vat)
    sim_pg_cost = round(sample * pgr_vat)
    sim_platform = sim_merchant_fee - sim_pg_cost
    sim_commission = round(sample * comm_rate)
    sim_company = sim_platform - sim_commission
    sim_net = sample - sim_merchant_fee

    return {
        "merchant_id": mid,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": mfr,
        "pg_fee_rate": pgr,
        "has_fee_policy": fp is not None,
        "has_sales_manager": assign is not None,
        "sales_info": sales_info,
        # 실제 적용율 (부가세 포함)
        "merchant_fee_rate_with_vat": mfr_vat,
        "pg_fee_rate_with_vat": pgr_vat,
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_label": format_rate_with_vat(mfr),
        "pg_fee_rate_label": format_rate_with_vat(pgr),
        # 하위 호환 필드
        "vat_inclusive_rate": pgr_vat,
        "pg_fee_rate_excl_vat": pgr,
        "description": (
            f"미용실수수료 {format_rate_excl_vat(mfr)} / PG비용 {format_rate_excl_vat(pgr)}"
            f" / 영업커미션 {comm_rate*100:.2f}%"
            f" — 실제 적용: 미용실 {mfr_vat*100:.2f}% / PG {pgr_vat*100:.2f}%"
        ),
        "simulation": {
            "sample_amount": sample,
            "merchant_fee_amount": sim_merchant_fee,
            "pg_cost": sim_pg_cost,
            "platform_income": sim_platform,
            "commission_amount": sim_commission,
            "company_profit": sim_company,
            "net_amount": int(sim_net),
            # 하위 호환
            "pg_fee_amount": sim_pg_cost,
            "vat_included": True,
            "breakdown": (
                f"결제 {sample:,}원 → 미용실수수료 {sim_merchant_fee:,}원"
                f" (PG {sim_pg_cost:,}원 + 플랫폼 {sim_platform:,}원"
                + (f" = 영업 {sim_commission:,}원 + 회사 {sim_company:,}원" if assign else "")
                + f") → 미용실수령액 {int(sim_net):,}원"
                + " (수수료 금액은 부가세 포함)"
            ),
        },
    }


@router.post("/merchants/{mid}/fee-policy")
def set_fee_policy(mid: int, req: FeePolicyUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """하위 호환 엔드포인트 — pg_fee_rate 만 저장. 신규는 PUT /merchants/{mid}/fee-override 사용 권장.

    req.pg_fee_rate 는 **부가세 별도** 기준으로 그대로 저장하고, 정산 계산 시 × 1.1 이 적용된다.
    """
    pgr = float(req.pg_fee_rate)
    pgr_vat = apply_vat(pgr)
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    mfr_global, _, _ = get_effective_fee_rates(db, None)

    # 저장 전 교차 검증 — 변경 후 플랫폼 수익률이 기존 커미션율을 감당하는지 확인한다.
    new_mfr = float(fp.merchant_fee_rate) if fp and fp.merchant_fee_rate is not None else mfr_global
    _validate_merchant_commission_fit(db, mid, new_mfr, pgr)

    # pg_fee_rate 는 부가세 별도 저장값, vat_inclusive_rate 는 실제 적용율(× 1.1)
    if fp:
        fp.pg_fee_rate = pgr
        fp.vat_inclusive_rate = round(pgr_vat, 4)
    else:
        fp = FeePolicy(merchant_id=mid, pg_fee_rate=pgr, merchant_fee_rate=mfr_global,
                       vat_inclusive_rate=round(pgr_vat, 4))
        db.add(fp)
    db.commit()
    return {
        "ok": True,
        "pg_fee_rate": pgr,
        "pg_fee_rate_with_vat": pgr_vat,
        "vat_inclusive_rate": pgr_vat,
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "pg_fee_rate_label": format_rate_with_vat(pgr),
        "example": (
            f"10,000원 결제 시 PG수수료 {int(10000 * pgr_vat):,}원"
            f" (입력 {pgr*100:.2f}% 부가세 별도 → 실제 적용 {pgr_vat*100:.2f}%)"
            f" / 미용실수령액 {int(10000 * (1 - pgr_vat)):,}원"
        ),
    }


# ─── 통합 수수료 현황 (모든 가맹점 + 영업관리자 배정 한번에) ──

@router.get("/fee-policy-overview")
def fee_policy_overview(db: Session = Depends(get_db), _=Depends(require_admin)):
    """모든 가맹점의 수수료정책 + 영업관리자 배정 현황을 일괄 조회"""
    merchants = db.query(Merchant).filter(Merchant.is_active == True).all()
    results = []
    for m in merchants:
        fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == m.id).first()
        assign = db.query(MerchantSalesAssignment).filter(
            MerchantSalesAssignment.merchant_id == m.id,
            MerchantSalesAssignment.is_active == True,  # noqa: E712
        ).first()
        sales_manager_user_id = assign.sales_manager_user_id if assign else None

        mfr, pgr, comm_rate = get_effective_fee_rates(db, m.id, sales_manager_user_id)
        platform_rate = mfr - pgr
        company_rate = platform_rate - comm_rate

        # 실제 적용율 (부가세 포함) — 금액은 이 값으로 계산된다.
        mfr_vat = apply_vat(mfr)
        pgr_vat = apply_vat(pgr)

        sales_name = None
        if assign:
            su = db.query(User).filter(User.id == assign.sales_manager_user_id).first()
            sales_name = su.name if su else None

        sample = 10000
        sim_merchant_fee = round(sample * mfr_vat)
        sim_pg_cost = round(sample * pgr_vat)
        sim_platform = sim_merchant_fee - sim_pg_cost
        sim_commission = round(sample * comm_rate)
        sim_company = sim_platform - sim_commission
        sim_net = sample - sim_merchant_fee

        results.append({
            "merchant_id": m.id,
            "merchant_name": m.name,
            "category": m.display_category if hasattr(m, 'display_category') else None,
            "has_fee_policy": fp is not None,
            "has_sales_manager": assign is not None,
            "sales_manager_name": sales_name,
            "merchant_fee_rate": mfr,
            "merchant_fee_rate_pct": round(mfr * 100, 2),
            "pg_fee_rate": pgr,
            "pg_fee_rate_pct": round(pgr * 100, 2),
            "platform_rate": round(platform_rate, 4),
            "commission_rate": comm_rate,
            "commission_rate_pct": round(comm_rate * 100, 2),
            "company_profit_rate": round(company_rate, 4),
            "assignment_id": assign.id if assign else None,
            # 실제 적용율 (부가세 포함) — 위 rate 필드는 부가세 별도 저장값
            "merchant_fee_rate_with_vat": mfr_vat,
            "merchant_fee_rate_with_vat_pct": round(mfr_vat * 100, 2),
            "pg_fee_rate_with_vat": pgr_vat,
            "pg_fee_rate_with_vat_pct": round(pgr_vat * 100, 2),
            "vat_rate": VAT_RATE,
            "fee_rate_vat_exclusive": True,
            # 하위 호환 필드
            "pg_fee_rate_excl_vat": pgr,
            "pg_fee_rate_excl_vat_pct": round(pgr * 100, 2),
            "vat_inclusive_rate": pgr_vat,
            "vat_inclusive_rate_pct": round(pgr_vat * 100, 2),
            # 시뮬레이션 (10,000원 기준)
            "sim_merchant_fee": sim_merchant_fee,
            "sim_pg_fee": sim_pg_cost,
            "sim_platform": sim_platform,
            "sim_commission": sim_commission,
            "sim_company": sim_company,
            "sim_net": int(sim_net),
        })
    return results


# ─── Sales Assignments (영업관리자 연결) ─────────────────────

@router.get("/sales-assignments")
def list_sales_assignments(db: Session = Depends(get_db), _=Depends(require_admin)):
    assigns = db.query(MerchantSalesAssignment).all()
    results = []
    for a in assigns:
        user = db.query(User).filter(User.id == a.sales_manager_user_id).first()
        merchant = db.query(Merchant).filter(Merchant.id == a.merchant_id).first()
        results.append({
            "id": a.id, "merchant_id": a.merchant_id,
            "merchant_name": merchant.name if merchant else None,
            "sales_manager_user_id": a.sales_manager_user_id,
            "sales_manager_name": user.name if user else None,
            "commission_rate": float(a.commission_rate),
            "memo": a.memo if hasattr(a, 'memo') else None,
            "is_active": a.is_active if hasattr(a, 'is_active') else True,
        })
    return results


@router.post("/sales-assignments")
def create_sales_assignment(req: SalesAssignmentCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    # 영업관리자 역할 확인
    sales_user = db.query(User).filter(User.id == req.sales_manager_user_id).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=400, detail="영업관리자 역할의 사용자만 배정할 수 있습니다.")
    # 가맹점 확인
    merchant = db.query(Merchant).filter(Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다.")
    # 한 가맹점에 활성 배정 1개만 허용
    active_existing = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == req.merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    if active_existing:
        raise HTTPException(
            status_code=400,
            detail="이미 해당 가맹점에 활성 영업관리자 배정이 존재합니다. 기존 배정을 해제 후 시도해주세요.",
        )
    # 커미션율 검증 (유효 수수료율 기준)
    mfr, pgr, _ = get_effective_fee_rates(db, req.merchant_id)
    platform_rate = mfr - pgr
    if req.commission_rate < 0 or req.commission_rate > platform_rate + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=f"영업 커미션율은 0% ~ 플랫폼 수익률({platform_rate*100:.2f}%) 이하여야 합니다. 입력값: {req.commission_rate*100:.2f}%",
        )
    a = MerchantSalesAssignment(
        merchant_id=req.merchant_id,
        sales_manager_user_id=req.sales_manager_user_id,
        commission_rate=req.commission_rate,
        memo=req.memo,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "commission_rate": float(a.commission_rate)}


@router.put("/sales-assignments/{aid}")
def update_sales_assignment(aid: int, req: SalesAssignmentUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    a = db.query(MerchantSalesAssignment).filter(MerchantSalesAssignment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="영업배정을 찾을 수 없습니다.")
    if req.commission_rate is not None:
        # 커미션율 검증 (생성 시와 동일하게 유효 수수료율 기준)
        mfr, pgr, _ = get_effective_fee_rates(db, a.merchant_id)
        _validate_commission_rate(req.commission_rate, mfr, pgr)
        a.commission_rate = req.commission_rate
    if req.memo is not None:
        a.memo = req.memo
    if req.is_active is not None:
        if req.is_active and not a.is_active:
            # M-2: 재활성화 시 동일 가맹점에 이미 활성 배정이 있으면 중복 방지
            duplicate = db.query(MerchantSalesAssignment).filter(
                MerchantSalesAssignment.merchant_id == a.merchant_id,
                MerchantSalesAssignment.is_active == True,
                MerchantSalesAssignment.id != a.id,
            ).first()
            if duplicate:
                raise HTTPException(status_code=409, detail="해당 가맹점에 이미 활성화된 영업 배정이 있습니다")
        a.is_active = req.is_active
    db.commit()
    return {"ok": True}


@router.delete("/sales-assignments/{aid}")
def delete_sales_assignment(aid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    a = db.query(MerchantSalesAssignment).filter(MerchantSalesAssignment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="영업배정을 찾을 수 없습니다.")
    db.delete(a)
    db.commit()
    return {"ok": True}


# 영업관리자 목록 조회 (dropdown용)
@router.get("/sales-managers")
def list_sales_managers(db: Session = Depends(get_db), _=Depends(require_admin)):
    users = db.query(User).filter(User.role == UserRole.SALES, User.is_active == True).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "referral_code": u.referral_code} for u in users]


# ─── Settlements ─────────────────────────────────────────────

@router.get("/settlements")
def list_settlements(
    merchant_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    q = db.query(Settlement)
    if merchant_id:
        q = q.filter(Settlement.merchant_id == merchant_id)
    settlements = q.order_by(Settlement.created_at.desc()).all()
    merchant_names = {m.id: m.name for m in db.query(Merchant).all()}
    return [{
        "id": s.id, "merchant_id": s.merchant_id,
        "merchant_name": merchant_names.get(s.merchant_id, f"가맹점#{s.merchant_id}"),
        "period_start": str(s.period_start), "period_end": str(s.period_end),
        "gross_amount": float(s.gross_amount), "pg_fee_amount": float(s.pg_fee_amount),
        "net_amount": float(s.net_amount), "commission_amount": float(s.commission_amount),
        "created_at": str(s.created_at),
    } for s in settlements]


@router.post("/settlements/calculate")
def calculate_settlement(
    merchant_id: int = Query(...),
    period_start: str = Query(...),
    period_end: str = Query(...),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """가맹점 정산 계산 및 Settlement 생성.

    수수료 체계 (새 구조):
    - 미용실 수수료(merchant_fee) = 결제액 × merchant_fee_rate (미용실이 내는 총 수수료)
    - PG 실비용(pg_cost) = 결제액 × pg_fee_rate (PG사에 지불)
    - 플랫폼 수익 = merchant_fee - pg_cost
    - 영업 커미션 = 결제액 × sales_commission_rate
    - 회사 순수익 = 플랫폼 수익 - 영업 커미션
    - 미용실 실수령액(net) = 결제액 - merchant_fee
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    try:
        # 정산 기간은 KST 기준으로 받고 naive UTC 경계로 환산한다.
        start = _parse_kst_bound(period_start)
        end_exclusive = _parse_kst_bound(period_end, next_day=True)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (ISO 8601: YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM:SS)")
    if start >= end_exclusive:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다")
    # 저장/중복검사에 쓰는 종료 시각은 기간 마지막 순간 (경계 미포함 값 - 1μs)
    end = end_exclusive - timedelta(microseconds=1)

    # 같은 기간으로 재호출 시 Settlement 중복 생성 방지 (기간 겹침 검사)
    existing = db.query(Settlement).filter(
        Settlement.merchant_id == merchant_id,
        Settlement.period_start <= end,
        Settlement.period_end >= start,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 해당 기간에 정산이 존재합니다.")

    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant_id,
        Transaction.created_at >= start,
        Transaction.created_at < end_exclusive,
        Transaction.status == TransactionStatus.APPROVED,
    ).all()

    gross = sum(float(t.amount) for t in txns)

    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None

    merchant_fee_rate, pg_fee_rate, commission_rate = get_effective_fee_rates(
        db, merchant_id, sales_manager_user_id
    )

    dist = compute_fee_distribution(gross, merchant_fee_rate, pg_fee_rate, commission_rate)

    settlement = Settlement(
        merchant_id=merchant_id,
        sales_manager_user_id=sales_manager_user_id,
        period_start=start,
        period_end=end,
        gross_amount=round(gross, 2),
        merchant_fee_amount=dist["merchant_fee"],
        pg_fee_amount=dist["pg_cost"],
        net_amount=dist["net_payout"],
        commission_amount=dist["sales_commission"],
        company_profit_amount=dist["company_profit"],
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)
    return {
        "id": settlement.id,
        "merchant_name": merchant.name,
        "gross_amount": gross,
        "merchant_fee_amount": dist["merchant_fee"],
        "pg_fee_amount": dist["pg_cost"],
        "platform_income": dist["platform_income"],
        "commission_amount": dist["sales_commission"],
        "company_profit_amount": dist["company_profit"],
        "net_amount": dist["net_payout"],
        "transactions_count": len(txns),
        # 저장값 (부가세 별도)
        "merchant_fee_rate": merchant_fee_rate,
        "pg_fee_rate": pg_fee_rate,
        "sales_commission_rate": commission_rate,
        # 실제 적용율 (부가세 포함) — 위 금액은 이 값으로 계산됨
        "merchant_fee_rate_with_vat": dist["merchant_fee_rate_with_vat"],
        "pg_fee_rate_with_vat": dist["pg_fee_rate_with_vat"],
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
    }


# ═══════════════════════════════════════════════════════════
# 전역/가맹점별/영업관리자별 수수료 설정
# ═══════════════════════════════════════════════════════════

@router.get("/fee-settings")
def get_fee_settings(db: Session = Depends(get_db), _=Depends(require_admin)):
    """전역 기본 수수료 설정 조회 (merchant_id=NULL 레코드).

    merchant_fee_rate / pg_fee_rate 는 부가세 별도 기준 저장값이며,
    *_with_vat 필드가 실제 적용율(× 1.1)이다.
    """
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id.is_(None)).first()
    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id.is_(None)
    ).first()

    mfr = float(fp.merchant_fee_rate) if fp else DEFAULT_MERCHANT_FEE_RATE
    pgr = float(fp.pg_fee_rate) if fp else DEFAULT_PG_FEE_RATE
    scr = float(scp.commission_rate) if scp else DEFAULT_SALES_COMMISSION_RATE
    platform_rate = mfr - pgr
    company_rate = platform_rate - scr

    # 실제 적용율 (부가세 포함) — 금액은 이 값으로 계산된다.
    mfr_vat = apply_vat(mfr)
    pgr_vat = apply_vat(pgr)

    # 시뮬레이션 — compute_fee_distribution() 과 동일한 계산 순서 (부가세 포함 적용율 기준).
    # 조회 엔드포인트이므로 커미션율 검증(ValueError)을 타지 않도록 직접 계산한다.
    sample = 10000
    sim_merchant_fee = round(sample * mfr_vat)
    sim_pg_cost = round(sample * pgr_vat)
    sim_platform = sim_merchant_fee - sim_pg_cost
    sim_commission = round(sample * scr)
    sim_company = sim_platform - sim_commission
    sim_net = sample - sim_merchant_fee
    return {
        # 저장값 (부가세 별도)
        "merchant_fee_rate": mfr,
        "pg_fee_rate": pgr,
        "sales_commission_rate": scr,
        "platform_rate": round(platform_rate, 4),
        "company_profit_rate": round(company_rate, 4),
        "has_global_fee_policy": fp is not None,
        "has_global_commission_policy": scp is not None,
        # 부가세 (VAT 10% 별도)
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_with_vat": mfr_vat,
        "pg_fee_rate_with_vat": pgr_vat,
        "merchant_fee_rate_label": format_rate_with_vat(mfr),
        "pg_fee_rate_label": format_rate_with_vat(pgr),
        "sales_commission_rate_label": f"{scr * 100:.2f}% (부가세 미적용)",
        "simulation": {
            "sample_amount": sample,
            "merchant_fee": sim_merchant_fee,
            "pg_cost": sim_pg_cost,
            "platform_income": sim_platform,
            "sales_commission": sim_commission,
            "company_profit": sim_company,
            "net_payout": int(sim_net),
            "vat_included": True,
            "note": "금액은 부가세 포함 실제 적용율 기준입니다.",
        },
    }


@router.put("/fee-settings")
def update_fee_settings(req: GlobalFeeSettingsUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """전역 기본 수수료 설정 저장/갱신.

    입력값(merchant_fee_rate / pg_fee_rate)은 **부가세 별도** 기준으로 그대로 저장하고,
    실제 정산 계산 시 × 1.1 이 적용된다. 검증은 부가세 별도 기준으로 수행한다.
    """
    _validate_commission_rate(req.sales_commission_rate, req.merchant_fee_rate, req.pg_fee_rate)

    # FeePolicy 전역 레코드 (merchant_id=NULL)
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id.is_(None)).first()
    if fp:
        fp.merchant_fee_rate = req.merchant_fee_rate
        fp.pg_fee_rate = req.pg_fee_rate
    else:
        fp = FeePolicy(
            merchant_id=None,
            merchant_fee_rate=req.merchant_fee_rate,
            pg_fee_rate=req.pg_fee_rate,
        )
        db.add(fp)

    # SalesCommissionPolicy 전역 레코드 (sales_manager_user_id=NULL)
    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id.is_(None)
    ).first()
    if scp:
        scp.commission_rate = req.sales_commission_rate
    else:
        scp = SalesCommissionPolicy(
            sales_manager_user_id=None,
            commission_rate=req.sales_commission_rate,
        )
        db.add(scp)

    db.commit()
    return {
        "ok": True,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": req.merchant_fee_rate,
        "pg_fee_rate": req.pg_fee_rate,
        "sales_commission_rate": req.sales_commission_rate,
        # 실제 적용율 (부가세 포함)
        "merchant_fee_rate_with_vat": apply_vat(req.merchant_fee_rate),
        "pg_fee_rate_with_vat": apply_vat(req.pg_fee_rate),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_label": format_rate_with_vat(req.merchant_fee_rate),
        "pg_fee_rate_label": format_rate_with_vat(req.pg_fee_rate),
    }


@router.get("/merchants/{mid}/fee-override")
def get_merchant_fee_override(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """가맹점 개별 수수료 오버라이드 조회 (수수료율은 모두 부가세 별도 기준)."""
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    mfr, pgr, _ = get_effective_fee_rates(db, mid)
    return {
        "merchant_id": mid,
        "merchant_name": merchant.name,
        "has_override": fp is not None,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": float(fp.merchant_fee_rate) if fp else None,
        "pg_fee_rate": float(fp.pg_fee_rate) if fp else None,
        "effective_merchant_fee_rate": mfr,
        "effective_pg_fee_rate": pgr,
        # 실제 적용율 (부가세 포함)
        "effective_merchant_fee_rate_with_vat": apply_vat(mfr),
        "effective_pg_fee_rate_with_vat": apply_vat(pgr),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "effective_merchant_fee_rate_label": format_rate_with_vat(mfr),
        "effective_pg_fee_rate_label": format_rate_with_vat(pgr),
    }


@router.put("/merchants/{mid}/fee-override")
def update_merchant_fee_override(
    mid: int, req: MerchantFeeOverrideUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """가맹점 개별 수수료 오버라이드 설정 (None 값이면 해당 필드 전역값 사용).

    입력값은 **부가세 별도** 기준으로 그대로 저장하고, 정산 계산 시 × 1.1 이 적용된다.
    """
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")

    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == mid).first()
    mfr_default, pgr_default, _ = get_effective_fee_rates(db, None)

    # 오버라이드 값이 없으면 기존 레코드 삭제 (전역값 사용)
    if req.merchant_fee_rate is None and req.pg_fee_rate is None:
        if fp:
            # 전역값으로 되돌려도 기존 커미션율이 수용 가능해야 한다.
            _validate_merchant_commission_fit(db, mid, mfr_default, pgr_default)
            db.delete(fp)
            db.commit()
        return {"ok": True, "action": "reset_to_global", "vat_notice": VAT_NOTICE}

    # 저장 전 교차 검증 — 변경 후 유효 수수료율로 기존 커미션율을 확인한다.
    new_mfr = float(req.merchant_fee_rate) if req.merchant_fee_rate is not None else (
        float(fp.merchant_fee_rate) if fp and fp.merchant_fee_rate is not None else mfr_default
    )
    new_pgr = float(req.pg_fee_rate) if req.pg_fee_rate is not None else (
        float(fp.pg_fee_rate) if fp and fp.pg_fee_rate is not None else pgr_default
    )
    _validate_merchant_commission_fit(db, mid, new_mfr, new_pgr)

    if fp:
        if req.merchant_fee_rate is not None:
            fp.merchant_fee_rate = req.merchant_fee_rate
        if req.pg_fee_rate is not None:
            fp.pg_fee_rate = req.pg_fee_rate
    else:
        # 새 레코드 생성 (미지정 필드는 전역값에서 채움)
        fp = FeePolicy(
            merchant_id=mid,
            merchant_fee_rate=req.merchant_fee_rate if req.merchant_fee_rate is not None else mfr_default,
            pg_fee_rate=req.pg_fee_rate if req.pg_fee_rate is not None else pgr_default,
        )
        db.add(fp)

    db.commit()
    saved_mfr = float(fp.merchant_fee_rate)
    saved_pgr = float(fp.pg_fee_rate)
    return {
        "ok": True,
        # 저장값 (부가세 별도)
        "merchant_fee_rate": saved_mfr,
        "pg_fee_rate": saved_pgr,
        # 실제 적용율 (부가세 포함)
        "merchant_fee_rate_with_vat": apply_vat(saved_mfr),
        "pg_fee_rate_with_vat": apply_vat(saved_pgr),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        "merchant_fee_rate_label": format_rate_with_vat(saved_mfr),
        "pg_fee_rate_label": format_rate_with_vat(saved_pgr),
    }


@router.get("/sales/{uid}/commission-override")
def get_sales_commission_override(uid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """영업관리자 개별 커미션율 조회."""
    sales_user = db.query(User).filter(User.id == uid).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=404, detail="영업관리자를 찾을 수 없습니다")
    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id == uid
    ).first()
    global_scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id.is_(None)
    ).first()
    return {
        "sales_manager_user_id": uid,
        "sales_manager_name": sales_user.name,
        "has_override": scp is not None,
        "commission_rate": float(scp.commission_rate) if scp else None,
        "effective_commission_rate": (
            float(scp.commission_rate) if scp
            else (float(global_scp.commission_rate) if global_scp else DEFAULT_SALES_COMMISSION_RATE)
        ),
    }


@router.put("/sales/{uid}/commission-override")
def update_sales_commission_override(
    uid: int, req: SalesCommissionOverrideUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """영업관리자 개별 커미션율 설정 (commission_rate=None이면 전역값 사용으로 초기화)."""
    sales_user = db.query(User).filter(User.id == uid).first()
    if not sales_user or sales_user.role.value != 'sales':
        raise HTTPException(status_code=404, detail="영업관리자를 찾을 수 없습니다")

    scp = db.query(SalesCommissionPolicy).filter(
        SalesCommissionPolicy.sales_manager_user_id == uid
    ).first()

    if req.commission_rate is None:
        if scp:
            db.delete(scp)
            db.commit()
        return {"ok": True, "action": "reset_to_global"}

    # 전역 수수료 설정으로 플랫폼 수익률 계산해서 검증
    mfr, pgr, _ = get_effective_fee_rates(db, None)
    _validate_commission_rate(req.commission_rate, mfr, pgr)

    if scp:
        scp.commission_rate = req.commission_rate
    else:
        scp = SalesCommissionPolicy(
            sales_manager_user_id=uid,
            commission_rate=req.commission_rate,
        )
        db.add(scp)

    db.commit()
    return {"ok": True, "commission_rate": float(scp.commission_rate)}


# ═══════════════════════════════════════════════════════════
# 영업수수료 표시 설정 (역할별 ON/OFF)
# ═══════════════════════════════════════════════════════════

def _get_config_default(db: Session, key: str, default: bool = True) -> SystemConfig:
    """설정값 가져오기 (없으면 default 로 생성)."""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if not cfg:
        cfg = SystemConfig(config_key=key, is_enabled=default)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/commission-visibility")
def get_commission_visibility(db: Session = Depends(get_db), _=Depends(require_admin)):
    """역할별 영업수수료 표시 여부 조회 (기본값 표시=True)."""
    return {
        "admin": True,  # 최고관리자는 항상 표시
        "sales": _get_config_default(db, COMMISSION_VISIBLE_TO_SALES).is_enabled,
        "owner": _get_config_default(db, COMMISSION_VISIBLE_TO_OWNER).is_enabled,
        "designer": _get_config_default(db, COMMISSION_VISIBLE_TO_DESIGNER).is_enabled,
    }


@router.put("/commission-visibility")
def update_commission_visibility(
    req: CommissionVisibilityUpdate, db: Session = Depends(get_db), _=Depends(require_admin),
):
    """역할별 영업수수료 표시 여부 변경."""
    mapping = {
        "sales": COMMISSION_VISIBLE_TO_SALES,
        "owner": COMMISSION_VISIBLE_TO_OWNER,
        "designer": COMMISSION_VISIBLE_TO_DESIGNER,
    }
    for field, key in mapping.items():
        value = getattr(req, field)
        if value is not None:
            cfg = _get_config_default(db, key)
            cfg.is_enabled = value
    db.commit()
    return {
        "ok": True,
        "admin": True,
        "sales": _get_config_default(db, COMMISSION_VISIBLE_TO_SALES).is_enabled,
        "owner": _get_config_default(db, COMMISSION_VISIBLE_TO_OWNER).is_enabled,
        "designer": _get_config_default(db, COMMISSION_VISIBLE_TO_DESIGNER).is_enabled,
    }


# ═══════════════════════════════════════════════════════════
# 디자이너 분배율 관리 (관리자도 설정 가능)
# ═══════════════════════════════════════════════════════════

@router.get("/merchants/{mid}/staff")
def admin_list_merchant_staff(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """가맹점 직원(디자이너) 목록 + 분배율."""
    staff_list = db.query(Staff).filter(Staff.merchant_id == mid).all()
    return [{
        "id": s.id, "name": s.name, "staff_code": s.staff_code,
        "user_id": s.user_id, "is_active": s.is_active,
        "share_rate": float(s.share_rate) if s.share_rate is not None else 0.5,
    } for s in staff_list]


@router.put("/staff/{sid}/share-rate")
def admin_update_staff_share_rate(
    sid: int, req: StaffShareRateUpdate, db: Session = Depends(get_db), _=Depends(require_admin),
):
    """디자이너 분배율 설정 (0~1)."""
    s = db.query(Staff).filter(Staff.id == sid).first()
    if not s:
        raise HTTPException(status_code=404, detail="Staff not found")
    s.share_rate = max(0.0, min(1.0, req.share_rate))
    db.commit()
    return {"id": s.id, "name": s.name, "share_rate": float(s.share_rate)}


@router.get("/merchants/{mid}/settlement-breakdown")
def admin_settlement_breakdown(
    mid: int,
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """관리자용 디자이너/원장 분배 내역 (전체 항목 노출)."""
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404)
    q = db.query(Transaction).filter(
        Transaction.merchant_id == mid,
        Transaction.status == TransactionStatus.APPROVED,
    )
    try:
        if period_start:
            q = q.filter(Transaction.created_at >= datetime.fromisoformat(period_start))
        if period_end:
            q = q.filter(Transaction.created_at <= datetime.fromisoformat(period_end))
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    txns = q.all()
    result = compute_distribution(db, mid, txns)
    result["merchant_name"] = merchant.name
    result["show_sales_commission"] = True
    return result
