"""
정산 분배 계산 서비스 (미용실 등 직원관리 업종).

수수료 구조:
    결제액(gross)
      ├─ 미용실 수수료(merchant_fee) = gross × merchant_fee_rate  ← 미용실이 내는 금액
      │     ├─ PG 실비용(pg_cost) = gross × pg_fee_rate
      │     ├─ 플랫폼 수익(platform_income) = merchant_fee - pg_cost
      │     │     ├─ 영업 커미션(sales_commission) = gross × sales_commission_rate
      │     │     │     (영업담당자 미배정 가맹점은 0원)
      │     │     └─ 회사 순수익(company_profit) = platform_income - sales_commission
      │     │           (영업담당자 미배정 시 platform_income 전액)
      └─ 미용실 실수령액(net_payout) = gross - merchant_fee
           ├─ 디자이너 몫 = net_payout × staff.share_rate
           └─ 원장 몫    = net_payout × (1 - staff.share_rate)

수수료율 우선순위:
    merchant_fee_rate / pg_fee_rate: 가맹점 오버라이드 → 전역 기본값 → 하드코딩 기본값
    sales_commission_rate:
        활성 영업배정이 없는 가맹점 → 0% (플랫폼 수익 전액이 회사 순수익)
        배정이 있으면 영업관리자 오버라이드 → 전역 기본값 → 배정값 → 하드코딩 기본값

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
DEFAULT_SALES_COMMISSION_RATE = 0.01  # 1% (영업배정이 있을 때만 폴백으로 사용)

# 활성 영업배정이 없는 가맹점의 커미션율 — 0%.
# 이 경우 플랫폼 수익(merchant_fee_rate - pg_fee_rate) 전액이 회사 순수익이 된다.
NO_SALES_COMMISSION_RATE = 0.0

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
    sales_commission_rate:
        활성 MerchantSalesAssignment 가 없는 가맹점 → NO_SALES_COMMISSION_RATE(0%).
        전역 SalesCommissionPolicy 가 있어도 배정이 없으면 적용하지 않는다.
        배정이 있으면 영업관리자 오버라이드 → 전역 정책 → 배정값 → DEFAULT_SALES_COMMISSION_RATE.
        merchant_id 가 None 인 전역 기본값 조회에는 0% 규칙을 적용하지 않는다.

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

    # 영업 커미션율 — 활성 영업배정이 없는 가맹점은 커미션 0%.
    # 이 경우 플랫폼 수익 전액이 회사 순수익이 된다 (전역 정책·기본값을 적용하지 않는다).
    # merchant_id 가 None 인 전역 기본값 조회에는 이 규칙을 적용하지 않는다.
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first() if merchant_id else None

    if merchant_id and assign is None:
        return merchant_fee_rate, pg_fee_rate, NO_SALES_COMMISSION_RATE

    # 배정이 있는 경우: SalesCommissionPolicy 오버라이드 → 전역 → 배정의 commission_rate → 기본값
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


# 하위 호환용 — 현재 호출처 없음
def get_fee_rates(db: Session, merchant_id: int):
    """(pg_fee_rate, 부가세 포함 pg_fee_rate) 반환 (하위 호환용).

    VAT 배수를 직접 쓰지 않고 apply_vat() 를 경유해 다른 경로와 어긋나지 않게 한다.
    """
    merchant_fee_rate, pg_fee_rate, _ = get_effective_fee_rates(db, merchant_id)
    return pg_fee_rate, round(apply_vat(pg_fee_rate), 4)


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


def _allocate_with_remainder(total: int, weights: list) -> list:
    """정수 total 을 weights 비율로 배분한다. 합계는 항상 total 과 정확히 일치한다.

    마지막 항목이 나머지를 흡수한다(last-person adjustment). 각 항목을 개별로
    반올림해서 더하면 총액과 최대 (항목 수)원 만큼 어긋나므로, 총액을 먼저 확정하고
    거기서 쪼개는 방식을 쓴다.

    weights 합이 0이면(매출이 모두 0) 마지막 항목에 전액을 넣는다.
    """
    n = len(weights)
    if n == 0:
        return []
    weight_sum = sum(weights)
    if weight_sum <= 0:
        out = [0] * n
        out[-1] = total
        return out

    out = []
    running = 0
    for w in weights[:-1]:
        v = int(round(total * (w / weight_sum)))
        out.append(v)
        running += v
    out.append(total - running)  # 마지막 항목 = 나머지
    return out


def compute_distribution(db: Session, merchant_id: int, txns) -> dict:
    """거래 목록으로 디자이너/원장 분배 내역을 계산한다.

    계산 순서 (누적 반올림 오차 방지):
        1) 전체 매출 합계로 compute_fee_distribution() 을 한 번 호출해 총액을 확정한다.
           → settlements/calculate 가 만드는 확정 정산 금액과 항상 일치한다.
        2) 확정된 총액을 디자이너별 매출 비율로 쪼갠다. 마지막 배분 단위가 나머지를
           흡수하므로(_allocate_with_remainder) 디자이너별 금액의 합은 항상 총액과 같다.
        3) 미귀속 거래가 있으면 그것이 마지막 단위가 되어 잔액이 원장 몫으로 흡수된다.

    보장되는 항등식:
        sum(designers[].merchant_fee) + unassigned.merchant_fee == merchant_fee
        sum(designers[].pg_cost)      + unassigned.pg_cost      == pg_cost
        sum(designers[].sales_commission) + unassigned.sales_commission == sales_commission
        sum(designers[].net_payout)   + unassigned.net_payout   == net_payout
        designer_total + owner_amount == net_payout

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

    # ── 1) 총액 기준으로 수수료를 먼저 확정한다 ──────────────────
    # settlements/calculate 가 쓰는 계산과 동일한 입력(전체 매출 합계)이므로
    # 여기서 나온 총액이 확정 정산 금액과 항상 일치한다.
    total_gross = sum(float(t.amount) for t in txns)
    totals = compute_fee_distribution(
        total_gross, merchant_fee_rate, pg_fee_rate, commission_rate
    )

    # ── 2) 배분 단위 구성 (디자이너 매출 큰 순 → 미귀속 마지막) ──
    # 나머지 보정은 마지막 단위가 흡수한다. 미귀속 거래가 있으면 그것이 마지막이 되어
    # 잔액이 원장 몫으로 흡수되고, 디자이너 몫은 왜곡되지 않는다.
    gross_by_staff = {sid: sum(float(t.amount) for t in ts) for sid, ts in groups.items()}
    ordered_staff = sorted(groups.keys(), key=lambda sid: (-gross_by_staff[sid], sid))

    un_gross = sum(float(t.amount) for t in unassigned_txns)
    alloc_units = [(sid, groups[sid], gross_by_staff[sid]) for sid in ordered_staff]
    if unassigned_txns:
        alloc_units.append((None, unassigned_txns, un_gross))

    weights = [g for _, _, g in alloc_units]
    mf_alloc = _allocate_with_remainder(totals["merchant_fee"], weights)
    pg_alloc = _allocate_with_remainder(totals["pg_cost"], weights)
    comm_alloc = _allocate_with_remainder(totals["sales_commission"], weights)

    # 실수령액은 행 단위로 gross - merchant_fee 가 성립하도록 유도한 뒤,
    # 마지막 단위에서 잔액을 흡수해 총 실수령액과 정확히 맞춘다.
    net_alloc = [int(g) - mf for (_, _, g), mf in zip(alloc_units, mf_alloc)]
    if net_alloc:
        net_alloc[-1] += totals["net_payout"] - sum(net_alloc)

    # ── 3) 단위별 분배 ──────────────────────────────────────────
    designers = []
    designer_total = 0
    owner_amount = 0
    un_row = {
        "gross": int(un_gross), "count": len(unassigned_txns),
        "merchant_fee": 0, "pg_cost": 0, "pg_fee": 0, "platform_income": 0,
        "sales_commission": 0, "company_profit": 0,
        "net_payout": 0, "distributable": 0, "owner_amount": 0,
    }

    for i, (sid, ts, g) in enumerate(alloc_units):
        mf, pg, comm_amt, net = mf_alloc[i], pg_alloc[i], comm_alloc[i], net_alloc[i]
        platform = mf - pg
        company = platform - comm_amt

        if sid is None:
            # 미귀속 거래 → 실수령액 전액 원장
            owner_amount += net
            un_row.update({
                "merchant_fee": mf, "pg_cost": pg, "pg_fee": pg,
                "platform_income": platform, "sales_commission": comm_amt,
                "company_profit": company,
                "net_payout": net, "distributable": net, "owner_amount": net,
            })
            continue

        s = staff_by_id[sid]
        share_rate = float(s.share_rate) if s.share_rate is not None else 0.5
        designer = round(net * share_rate)
        owner = net - designer
        designers.append({
            "staff_id": sid,
            "name": s.name,
            "staff_code": s.staff_code,
            "share_rate": share_rate,
            "gross": int(g),
            "merchant_fee": mf,
            "pg_cost": pg,
            "platform_income": platform,
            "sales_commission": comm_amt,
            "company_profit": company,
            "net_payout": net,
            "designer_amount": designer,
            "owner_amount": owner,
            "count": len(ts),
            # 하위 호환
            "pg_fee": pg,
            "distributable": net,
            "platform_amount": platform,
        })
        designer_total += designer
        owner_amount += owner

    total_net_payout = totals["net_payout"]

    return {
        "gross": int(total_gross),
        "merchant_fee": totals["merchant_fee"],
        "pg_cost": totals["pg_cost"],
        "platform_income": totals["platform_income"],
        "sales_commission": totals["sales_commission"],
        "company_profit": totals["company_profit"],
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
        "pg_fee": totals["pg_cost"],
        "distributable": total_net_payout,
        "platform_amount": totals["platform_income"],
        "commission_amount": totals["sales_commission"],
        "vat_inclusive_rate": round(apply_vat(pg_fee_rate), 4),
        "designers": sorted(designers, key=lambda d: d["gross"], reverse=True),
        "unassigned": un_row,
    }
