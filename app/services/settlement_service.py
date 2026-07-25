"""
정산 분배 계산 서비스 (미용실 등 직원관리 업종).

분배 흐름:
    결제액(gross)
      └─ PG 수수료(pg_fee) = gross × pg_fee_rate
            ├─ 영업 몫(sales_commission) = gross × commission_rate
            └─ ADPAY 플랫폼 몫(platform_amount) = pg_fee - sales_commission
      = 분배가능액(distributable) = gross - pg_fee
         ├─ 디자이너 몫  = distributable × staff.share_rate   (디자이너별 비율)
         └─ 원장 몫      = distributable × (1 - staff.share_rate)

영업수수료는 PG 수수료에 포함된 개념이라 분배가능액에서 별도 차감하지 않는다.
거래는 staff_id 로 디자이너에게 귀속된다. 직원 미귀속 거래의 분배가능액은 전액 원장 몫.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.settlement import FeePolicy, MerchantSalesAssignment
from app.models.staff import Staff


def get_fee_rates(db: Session, merchant_id: int):
    """(pg_fee_rate, vat_inclusive_rate) 반환. 정책 없으면 기본값."""
    fp = db.query(FeePolicy).filter(FeePolicy.merchant_id == merchant_id).first()
    pg_fee_rate = float(fp.pg_fee_rate) if fp else 0.035
    vat_inclusive_rate = (
        float(fp.vat_inclusive_rate) if fp and fp.vat_inclusive_rate
        else round(pg_fee_rate * 1.1, 4)
    )
    return pg_fee_rate, vat_inclusive_rate


def get_sales_commission_rate(db: Session, merchant_id: int) -> float:
    """가맹점에 배정된 영업관리자(딜러) 커미션율. 미배정 시 0."""
    assign = db.query(MerchantSalesAssignment).filter(
        MerchantSalesAssignment.merchant_id == merchant_id,
        MerchantSalesAssignment.is_active == True,  # noqa: E712
    ).first()
    return float(assign.commission_rate) if assign else 0.0


def compute_distribution(db: Session, merchant_id: int, txns) -> dict:
    """거래 목록으로 디자이너/원장 분배 내역을 계산한다.

    반환:
        {
          gross, pg_fee, sales_commission, platform_amount, distributable,
          owner_amount, designer_total,
          pg_fee_rate, sales_commission_rate, vat_inclusive_rate,
          designers: [ {staff_id, name, share_rate, gross, pg_fee,
                        sales_commission, platform_amount, distributable,
                        designer_amount, owner_amount, count} ],
          unassigned: {gross, distributable, owner_amount, count}
        }
    모든 금액은 원 단위 정수(반올림).
    """
    pg_fee_rate, vat_inclusive_rate = get_fee_rates(db, merchant_id)
    commission_rate = get_sales_commission_rate(db, merchant_id)

    staff_rows = db.query(Staff).filter(Staff.merchant_id == merchant_id).all()
    staff_by_id = {s.id: s for s in staff_rows}

    # staff_id 별 거래 그룹핑
    groups = {}            # staff_id -> list[txn]
    unassigned = []
    for t in txns:
        if t.staff_id and t.staff_id in staff_by_id:
            groups.setdefault(t.staff_id, []).append(t)
        else:
            unassigned.append(t)

    def _split(amount_sum: float, share_rate: float):
        pg = round(amount_sum * pg_fee_rate)
        comm = round(amount_sum * commission_rate)
        platform = pg - comm
        dist = amount_sum - pg
        designer = round(dist * share_rate)
        owner = dist - designer
        return pg, comm, platform, dist, designer, owner

    designers = []
    designer_total = 0
    owner_amount = 0
    total_gross = 0
    total_pg = 0
    total_comm = 0
    total_platform = 0

    for sid, ts in groups.items():
        s = staff_by_id[sid]
        g = sum(float(t.amount) for t in ts)
        share_rate = float(s.share_rate) if s.share_rate is not None else 0.5
        pg, comm, platform, dist, designer, owner = _split(g, share_rate)
        designers.append({
            "staff_id": sid,
            "name": s.name,
            "staff_code": s.staff_code,
            "share_rate": share_rate,
            "gross": int(g),
            "pg_fee": pg,
            "sales_commission": comm,
            "platform_amount": platform,
            "distributable": dist,
            "designer_amount": designer,
            "owner_amount": owner,
            "count": len(ts),
        })
        designer_total += designer
        owner_amount += owner
        total_gross += g
        total_pg += pg
        total_comm += comm
        total_platform += platform

    # 미귀속 거래 → 전액 원장
    un_gross = sum(float(t.amount) for t in unassigned)
    un_pg = round(un_gross * pg_fee_rate)
    un_comm = round(un_gross * commission_rate)
    un_platform = un_pg - un_comm
    un_dist = un_gross - un_pg
    owner_amount += un_dist
    total_gross += un_gross
    total_pg += un_pg
    total_comm += un_comm
    total_platform += un_platform

    distributable = total_gross - total_pg

    return {
        "gross": int(total_gross),
        "pg_fee": int(total_pg),
        "sales_commission": int(total_comm),
        "platform_amount": int(total_platform),
        "distributable": int(distributable),
        "owner_amount": int(owner_amount),
        "designer_total": int(designer_total),
        "pg_fee_rate": pg_fee_rate,
        "sales_commission_rate": commission_rate,
        "vat_inclusive_rate": vat_inclusive_rate,
        "designers": sorted(designers, key=lambda d: d["gross"], reverse=True),
        "unassigned": {
            "gross": int(un_gross),
            "distributable": int(un_dist),
            "owner_amount": int(un_dist),
            "count": len(unassigned),
        },
    }
