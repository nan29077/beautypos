from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - 모든 관계 테이블을 메타데이터에 등록
from app.database import Base
from app.models.merchant import Merchant
from app.models.plan import Plan
from app.models.plan import MerchantPlan
from app.models.settlement import FeePolicy
from app.models.user import User, UserRole
from app.services.plan_service import (
    daily_target_description,
    daily_target_for_date,
    plan_payload,
)
from app.services.settlement_service import get_effective_fee_rates


def _month_targets(monthly: int, year: int, month: int, days: int) -> list[int]:
    return [daily_target_for_date(monthly, date(year, month, day)) for day in range(1, days + 1)]


def test_ten_monthly_targets_are_spread_about_every_three_days():
    targets = _month_targets(10, 2026, 4, 30)

    assert sum(targets) == 10
    assert [day for day, value in enumerate(targets, start=1) if value] == list(range(3, 31, 3))
    assert daily_target_description(10, date(2026, 4, 1)) == "약 3일마다 1건"


def test_four_hundred_monthly_targets_sum_exactly_with_13_or_14_each_day():
    targets = _month_targets(400, 2026, 4, 30)

    assert sum(targets) == 400
    assert set(targets) == {13, 14}


def test_plan_payload_marks_fee_as_vat_exclusive_and_exposes_actual_rate():
    plan = Plan(
        id=1,
        name="베이직",
        code="basic",
        merchant_fee_rate=5.5,
        blog_review_monthly=10,
    )

    payload = plan_payload(plan, date(2026, 4, 3))

    assert payload["merchant_fee_rate"] == 5.5
    assert payload["merchant_fee_rate_with_vat"] == 6.05
    assert payload["fee_rate_vat_exclusive"] is True
    assert payload["blog_review_daily"] == 1
    assert payload["blog_review_monthly"] == 10


def test_assigned_plan_fee_is_used_before_global_fee_and_is_vat_exclusive():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        owner = User(email="plan-owner@example.com", name="원장", role=UserRole.OWNER)
        db.add(owner)
        db.flush()
        merchant = Merchant(name="플랜 매장", owner_user_id=owner.id)
        plan = Plan(name="베이직", code="basic", merchant_fee_rate=5.5)
        db.add_all([merchant, plan])
        db.flush()
        db.add_all([
            MerchantPlan(merchant_id=merchant.id, plan_id=plan.id),
            FeePolicy(merchant_id=None, merchant_fee_rate=0.05, pg_fee_rate=0.03),
        ])
        db.commit()

        merchant_rate, pg_rate, commission_rate = get_effective_fee_rates(db, merchant.id)

        assert merchant_rate == 0.055
        assert pg_rate == 0.03
        assert commission_rate == 0
    finally:
        db.close()
        engine.dispose()
