"""
정산 분배 계산 서비스 (미용실 등 직원관리 업종).

수수료 구조:
    결제액(gross)
      ├─ 미용실 수수료(merchant_fee) = gross × merchant_fee_rate  ← 미용실이 내는 금액
      │     ├─ PG 실비용(pg_cost) = gross × pg_fee_rate
      │     ├─ 플랫폼 수익(platform_income) = merchant_fee - pg_cost
      │     │     ├─ 영업 커미션(sales_commission) = gross × sales_commission_rate
      │     │     └─ 회사 순수익(company_profit) = platform_income - sales_commission
      └─ 미용실 실수령액(net_payout) = gross - merchant_fee
           ├─ 디자이너 몫 = net_payout × staff.share_rate
           └─ 원장 몫    = net_payout × (1 - staff.share_rate)

수수료율 우선순위:
    merchant_fee_rate / pg_fee_rate: 가맹점 오버라이드 → 전역 기본값 → 하드코딩 기본값
    sales_commission_rate: 영업관리자 오버라이드 → 전역 기본값 → 하드코딩 기본값

부가세(VAT) 처리:
    DB에 저장되는 merchant_fee_rate / pg_fee_rate 는 **부가세 별도** 기준이다.
    실제 금액 계산 시에는 VAT_MULTIPLIER(1.1)를 곱한 값을 사용한다.
        예) pg_fee_rate 3.00% 저장 → 실제 적용 3.30%
            merchant_fee_rate 5.00% 저장 → 실제 적용 5.50%
    sales_commission_rate 는 부가세 대상이 아니므로 저장값을 그대로 사용한다.
    VAT 적용은 apply_vat() 한 곳에서만 수행하며, 금액 계산은
    compute_fee_distribution() 이 단일 진입점이다.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.settlement import FeePolicy, SalesCommissionPolicy, MerchantSalesAssignment
from app.models.staff import Staff

# 하드코딩 기본값 (DB에 전역 설정이 없을 때 사용) — 모두 부가세 별도 기준
DEFAULT_MERCHANT_FEE_RATE = 0.05   # 5%
DEFAULT_PG_FEE_RATE = 0.03         # 3%
DEFAULT_SALES_COMMISSION_RATE = 0.01  # 1%

# 부가세 — 저장된 수수료율(부가세 별도)에 곱해서 실제 적용 수수료율을 얻는다.
VAT_RATE = 0.1
VAT_MULTIPLIER = 1.0 + VAT_RATE  # 1.1

# 프론트/응답에서 공통으로 쓰는 안내 문구
VAT_NOTICE = "설정값은 부가세 별도 기준이며, 실제 적용율은 입력값 × 1.1입니다."
VAT_EXCLUSIVE_SUFFIX = "(부가세 별도)"


def apply_vat(rate: float) -> float:
    """부가세 별도 수수료율 → 부가세 포함(실제 적용) 수수료율."""
    return round(float(rate) * VAT_MULTIPLIER, 6)


def format_rate_excl_vat(rate: float) -> str:
    """'3.00% (부가세 별도)' 형태로 표시."""
    return f"{float(rate) * 100:.2f}% {VAT_EXCLUSIVE_SUFFIX}"


def format_rate_with_vat(rate: float) -> str:
    """'3.00% (부가세 별도) → 실제 적용 3.30%' 형태로 표시."""
    return (
        f"{float(rate) * 100:.2f}% {VAT_EXCLUSIVE_SUFFIX}"
        f" → 실제 적용 {apply_vat(rate) * 100:.2f}%"
    )


def get_effective_fee_rates(
    db: Session,
    merchant_id: int,
    sales_manager_user_id: int = None,
) -> tuple[float, float, float]:
    """(merchant_fee_rate, pg_fee_rate, sales_commission_rate) 반환.

    merchant_fee_rate: 가맹점 오버라이드 → 전역 기본값 → DEFAULT_MERCHANT_FEE_RATE
    pg_fee_rate:       가맹점 오버라이드 → 전역 기본값 → DEFAULT_PG_FEE_RATE
    sales_commission_rate: 영업관리자 오버라이드 → 전역 기본값 → DEFAULT_SALES_COMMISSION_RATE

    반환되는 merchant_fee_rate / pg_fee_rate 는 **저장값 그대로(부가세 별도)** 이다.
    실제 적용율이 필요하면 get_effective_fee_rates_with_vat() 를 사용한다.
    """
    fp_merchant = db.query(FeePolicy).filter(
        FeePolicy.merchant_id == merchant_id
    ).first() if merchant_id else None
    fp_global = db.query(FeePolicy).filter(
        FeePolicy.merchant_id.is_(None)
    ).first()

    def _fp_rate(attr, default):
        for fp in [fp_merchant, fp_global]:
            if fp and getattr(fp, attr) is not None:
                return float(getattr(fp, attr))
        return default

    merchant_fee_rate = _fp_rate("merchant_fee_rate", DEFAULT_MERCHANT_FEE_RATE)
    pg_fee_rate = _fp_rate("pg_fee_rate", DEFAULT_PG_FEE_RATE)

    # 영업관리자 커미션: SalesCommissionPolicy 오버라이드 → 전역 → 배정의 commission_rate → 기본값
    scp = None
    if sales_manager_user_id:
        scp = db.query(SalesCommissionPolicy).filter(
            SalesCommissionPolicy.sales_manager_user_id == sales_manager_user_id
        ).first()
    if not scp:
        scp = db.query(SalesCommissionPolicy).filter(
            SalesCommissionPolicy.sales_manager_user_id.is_(None)
        ).first()

    if scp:
        commission_rate = float(scp.commission_rate)
    else:
        # SalesCommissionPolicy 없으면 MerchantSalesAssignment.commission_rate 폴백
        assign = db.query(MerchantSalesAssignment).filter(
            MerchantSalesAssignment.merchant_id == merchant_id,
            MerchantSalesAssignment.is_active == True,  # noqa: E712
        ).first()
        commission_rate = float(assign.commission_rate) if assign else DEFAULT_SALES_COMMISSION_RATE

    return merchant_fee_rate, pg_fee_rate, commission_rate


def get_effective_fee_rates_with_vat(
    db: Session,
    merchant_id: int,
    sales_manager_user_id: int = None,
) -> tuple[float, float, float]:
    """부가세가 적용된 실제 적용 수수료율을 반환한다.

    (merchant_fee_rate × 1.1, pg_fee_rate × 1.1, sales_commission_rate)
    영업 커미션율은 부가세 대상이 아니므로 그대로 반환한다.
    금액 계산·화면 표시에서 "실제 적용율"이 필요할 때 사용한다.
    """
    mfr, pgr, comm = get_effective_fee_rates(db, merchant_id, sales_manager_user_id)
    return apply_vat(mfr), apply_vat(pgr), comm


# 하위 호환용 — 기존 코드에서 사용 중
def get_fee_rates(db: Session, merchant_id: int):
    """(pg_fee_rate, vat_inclusive_rate) 반환 (하위 호환용)."""
    merchant_fee_rate, pg_fee_rate, _ = get_effective_fee_rates(db, merchant_id)
    return pg_fee_rate, round(pg_fee_rate * 1.1, 4)


def get_sales_commission_rate(db: Session, merchant_id: int) -> float:
    """가맹점 영업관리자 커미션율 반환 (하위 호환용)."""
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None
    _, _, commission_rate = get_effective_fee_rates(db, merchant_id, sales_manager_user_id)
    return commission_rate


def compute_fee_distribution(
    gross_amount: float,
    merchant_fee_rate: float,
    pg_fee_rate: float,
    sales_commission_rate: float,
) -> dict:
    """단일 금액에 대한 수수료 분배 계산 (순수 함수).

    merchant_fee_rate / pg_fee_rate 는 **부가세 별도** 기준으로 받아,
    내부에서 apply_vat() 로 실제 적용율(× 1.1)을 구해 금액을 계산한다.
    sales_commission_rate 는 부가세 대상이 아니므로 그대로 사용한다.

    검증: sales_commission_rate <= (merchant_fee_rate - pg_fee_rate) 를 초과하면 ValueError.
    검증은 기존과 동일하게 부가세 별도 기준으로 수행한다 (더 보수적인 기준).
    """
    platform_rate = merchant_fee_rate - pg_fee_rate
    if sales_commission_rate > platform_rate + 1e-9:
        raise ValueError(
            f"영업 커미션율({sales_commission_rate*100:.2f}%)이 플랫폼 수익률"
            f"({platform_rate*100:.2f}%)을 초과합니다"
        )

    # 실제 적용 수수료율 (부가세 포함)
    merchant_fee_rate_vat = apply_vat(merchant_fee_rate)
    pg_fee_rate_vat = apply_vat(pg_fee_rate)

    merchant_fee = round(gross_amount * merchant_fee_rate_vat)
    pg_cost = round(gross_amount * pg_fee_rate_vat)
    platform_income = merchant_fee - pg_cost
    sales_commission = round(gross_amount * sales_commission_rate)
    company_profit = platform_income - sales_commission
    net_payout = int(gross_amount) - merchant_fee

    return {
        "merchant_fee": merchant_fee,
        "pg_cost": pg_cost,
        "platform_income": platform_income,
        "sales_commission": sales_commission,
        "company_profit": company_profit,
        "net_payout": net_payout,
        # 계산에 쓰인 수수료율 (부가세 별도 / 실제 적용)
        "merchant_fee_rate": merchant_fee_rate,
        "pg_fee_rate": pg_fee_rate,
        "merchant_fee_rate_with_vat": merchant_fee_rate_vat,
        "pg_fee_rate_with_vat": pg_fee_rate_vat,
        "vat_applied": True,
    }


def compute_distribution(db: Session, merchant_id: int, txns) -> dict:
    """거래 목록으로 디자이너/원장 분배 내역을 계산한다.

    반환:
        {
          gross, merchant_fee, pg_cost, platform_income, sales_commission,
          company_profit, net_payout, owner_amount, designer_total,
          merchant_fee_rate, pg_fee_rate, sales_commission_rate,        # 부가세 별도
          merchant_fee_rate_with_vat, pg_fee_rate_with_vat,             # 실제 적용
          vat_rate, fee_rate_vat_exclusive, vat_notice,
          designers: [ {staff_id, name, share_rate, gross, merchant_fee, pg_cost,
                        platform_income, sales_commission, company_profit,
                        net_payout, designer_amount, owner_amount, count} ],
          unassigned: {gross, net_payout, owner_amount, count},
          # 하위 호환 필드
          pg_fee, distributable, platform_amount, commission_amount, vat_inclusive_rate
        }
    """
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    sales_manager_user_id = assign.sales_manager_user_id if assign else None

    merchant_fee_rate, pg_fee_rate, commission_rate = get_effective_fee_rates(
        db, merchant_id, sales_manager_user_id
    )

    staff_rows = db.query(Staff).filter(Staff.merchant_id == merchant_id).all()
    staff_by_id = {s.id: s for s in staff_rows}

    groups = {}
    unassigned_txns = []
    for t in txns:
        if t.staff_id and t.staff_id in staff_by_id:
            groups.setdefault(t.staff_id, []).append(t)
        else:
            unassigned_txns.append(t)

    def _split(gross_amt: float, share_rate: float):
        d = compute_fee_distribution(gross_amt, merchant_fee_rate, pg_fee_rate, commission_rate)
        net = d["net_payout"]
        designer = round(net * share_rate)
        owner = net - designer
        return d, designer, owner

    designers = []
    designer_total = 0
    owner_amount = 0
    total_gross = 0.0
    total_merchant_fee = 0
    total_pg_cost = 0
    total_comm = 0
    total_platform = 0
    total_company_profit = 0

    for sid, ts in groups.items():
        s = staff_by_id[sid]
        g = sum(float(t.amount) for t in ts)
        share_rate = float(s.share_rate) if s.share_rate is not None else 0.5
        d, designer, owner = _split(g, share_rate)
        designers.append({
            "staff_id": sid,
            "name": s.name,
            "staff_code": s.staff_code,
            "share_rate": share_rate,
            "gross": int(g),
            "merchant_fee": d["merchant_fee"],
            "pg_cost": d["pg_cost"],
            "platform_income": d["platform_income"],
            "sales_commission": d["sales_commission"],
            "company_profit": d["company_profit"],
            "net_payout": d["net_payout"],
            "designer_amount": designer,
            "owner_amount": owner,
            "count": len(ts),
            # 하위 호환
            "pg_fee": d["pg_cost"],
            "distributable": d["net_payout"],
            "platform_amount": d["platform_income"],
        })
        designer_total += designer
        owner_amount += owner
        total_gross += g
        total_merchant_fee += d["merchant_fee"]
        total_pg_cost += d["pg_cost"]
        total_comm += d["sales_commission"]
        total_platform += d["platform_income"]
        total_company_profit += d["company_profit"]

    # 미귀속 거래 → 전액 원장
    un_gross = sum(float(t.amount) for t in unassigned_txns)
    if un_gross > 0:
        un_d, _, _ = _split(un_gross, 0.0)
    else:
        un_d = {"merchant_fee": 0, "pg_cost": 0, "platform_income": 0,
                "sales_commission": 0, "company_profit": 0, "net_payout": 0}
    owner_amount += un_d["net_payout"]
    total_gross += un_gross
    total_merchant_fee += un_d["merchant_fee"]
    total_pg_cost += un_d["pg_cost"]
    total_comm += un_d["sales_commission"]
    total_platform += un_d["platform_income"]
    total_company_profit += un_d["company_profit"]

    total_net_payout = int(total_gross) - total_merchant_fee

    return {
        "gross": int(total_gross),
        "merchant_fee": total_merchant_fee,
        "pg_cost": total_pg_cost,
        "platform_income": total_platform,
        "sales_commission": total_comm,
        "company_profit": total_company_profit,
        "net_payout": total_net_payout,
        "owner_amount": int(owner_amount),
        "designer_total": int(designer_total),
        "merchant_fee_rate": merchant_fee_rate,
        "pg_fee_rate": pg_fee_rate,
        "sales_commission_rate": commission_rate,
        # 실제 적용 수수료율 (부가세 포함) — 위 rate 필드는 부가세 별도 기준
        "merchant_fee_rate_with_vat": apply_vat(merchant_fee_rate),
        "pg_fee_rate_with_vat": apply_vat(pg_fee_rate),
        "vat_rate": VAT_RATE,
        "fee_rate_vat_exclusive": True,
        "vat_notice": VAT_NOTICE,
        # 하위 호환 필드
        "pg_fee": total_pg_cost,
        "distributable": total_net_payout,
        "platform_amount": total_platform,
        "commission_amount": total_comm,
        "vat_inclusive_rate": round(pg_fee_rate * 1.1, 4),
        "designers": sorted(designers, key=lambda d: d["gross"], reverse=True),
        "unassigned": {
            "gross": int(un_gross),
            "net_payout": un_d["net_payout"],
            "distributable": un_d["net_payout"],
            "owner_amount": un_d["net_payout"],
            "count": len(unassigned_txns),
        },
    }
