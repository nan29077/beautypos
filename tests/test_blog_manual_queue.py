"""블로그 배포 수동 접수 큐 회귀 테스트.

리워드팝에는 클로 블로그 상품과 단가가 있지만 등록 API 가 없다(/ads/cloblog → 404).
그래서 블로그는 "자동 배분 + 사람이 접수"로 돌린다. 이 파일이 지키는 것:

- 월 목표가 일 단위로 쪼개지고, 그 달 일별 합계가 월 목표와 정확히 같다
- 블로그는 자동 전송 계획(preview)에 절대 끼지 않는다
- 완료 처리한 건만 진도표(AdExecution)에 실적으로 들어간다
- 완료 버튼을 두 번 눌러도 실적이 두 배가 되지 않는다 (멱등키)
- 되돌리면 실적에서 빠지고, 원장의 행은 남는다
- 자동 전송이 되는 광고(place_traffic)는 수동 완료 처리를 거부한다
"""
import importlib
import os
import sys
from calendar import monthrange
from datetime import date

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "manualqueue.db"
    os.environ["DATABASE_URL_OVERRIDE"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["APP_ENV"] = "test"
    os.environ["DEV_MODE"] = "true"
    os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-at-least-32-characters"

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    app_module = importlib.import_module("app.main")
    with TestClient(app_module.app) as test_client:
        yield test_client


def _session():
    from app.database import SessionLocal
    return SessionLocal()


def _auth(client, role="admin"):
    token = client.post(f"/api/auth/test-login?role={role}").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


DAY = date(2026, 9, 10)          # 30일 달의 10일
MONTHLY = 90                     # 30일로 나누면 하루 3건


def _prepare_blog_merchant(monthly=MONTHLY, unit_price=30000):
    """플랜·블로그 월 목표·단가를 갖춘 매장 1곳."""
    from app.models.merchant import Merchant
    from app.models.plan import Plan, MerchantPlan, MerchantAdOverride
    from app.services import ad_pricing

    db = _session()
    try:
        merchant = db.query(Merchant).first()
        merchant.place_code = "1750900108"

        plan = db.query(Plan).filter(Plan.code == "blog-basic").first()
        if plan is None:
            plan = Plan(name="블로그 테스트", code="blog-basic")
            db.add(plan)
            db.flush()
        if not db.query(MerchantPlan).filter(MerchantPlan.merchant_id == merchant.id).first():
            db.add(MerchantPlan(merchant_id=merchant.id, plan_id=plan.id))

        row = db.query(MerchantAdOverride).filter(
            MerchantAdOverride.merchant_id == merchant.id,
            MerchantAdOverride.ad_type == "blog_review",
        ).first()
        if row is None:
            db.add(MerchantAdOverride(
                merchant_id=merchant.id, ad_type="blog_review", monthly_override=monthly))
        else:
            row.monthly_override = monthly

        pricing = ad_pricing.get_ad_pricing(db)
        pricing["blog_unit_price"] = unit_price
        ad_pricing.save_ad_pricing(db, pricing)
        db.commit()
        return merchant.id
    finally:
        db.close()


# ─── 월 → 일 분배 ────────────────────────────────────────────

def test_monthly_target_splits_across_the_month_without_losing_a_single_unit():
    """일별 목표를 그 달 전체로 더하면 월 목표와 정확히 같아야 한다."""
    from app.services import plan_service

    for monthly in (1, 7, 30, 90, 100, 1000):
        for year, month in ((2026, 2), (2026, 9), (2026, 12)):
            days = monthrange(year, month)[1]
            total = sum(
                plan_service.daily_target_for_date(monthly, date(year, month, d))
                for d in range(1, days + 1)
            )
            assert total == monthly, (monthly, year, month, total)


def test_manual_queue_uses_the_same_daily_split_as_place_traffic(client):
    """블로그 큐의 '오늘 접수'는 플레이스와 같은 분배 함수를 쓴다."""
    from app.services import ad_dispatch, plan_service

    _prepare_blog_merchant()
    db = _session()
    try:
        queue = ad_dispatch.build_manual_queue(db, DAY)
    finally:
        db.close()

    item = next(i for i in queue["items"] if i["ad_type"] == "blog_review")
    assert item["target"] == plan_service.daily_target_for_date(MONTHLY, DAY) == 3
    assert item["monthly_target"] == MONTHLY
    # 9월 10일까지면 90 * 10 // 30 = 30건이 쌓여 있어야 한다
    assert item["month_expected"] == 30
    assert item["state"] == ad_dispatch.MANUAL_STATE_TODO
    assert queue["todo_total"] == 3


# ─── 자동 전송에는 절대 끼지 않는다 ──────────────────────────

def test_blog_never_appears_in_the_automatic_dispatch_plan(client):
    """리워드팝에 블로그 등록 API 가 없으므로 자동 전송 계획에 들어가면 안 된다."""
    from app.services import ad_dispatch

    _prepare_blog_merchant()
    assert "blog_review" not in ad_dispatch.DISPATCHABLE_AD_TYPES
    assert "blog_review" in ad_dispatch.MANUAL_AD_TYPES

    db = _session()
    try:
        plan = ad_dispatch.build_plan(db, DAY)
    finally:
        db.close()
    assert all(i["ad_type"] != "blog_review" for i in plan["items"])


def test_manual_completion_is_refused_for_ad_types_that_dispatch_automatically(client):
    """플레이스처럼 자동 전송되는 광고는 수동 완료 처리를 받지 않는다."""
    from app.services import ad_dispatch

    merchant_id = _prepare_blog_merchant()
    db = _session()
    try:
        with pytest.raises(ValueError):
            ad_dispatch.complete_manual(db, merchant_id, "place_traffic", DAY, count=1)
    finally:
        db.close()


# ─── 완료 처리 → 실적 반영 ───────────────────────────────────

def _execution_count(merchant_id, day):
    from app.models.plan import AdExecution
    db = _session()
    try:
        row = db.query(AdExecution).filter(
            AdExecution.merchant_id == merchant_id,
            AdExecution.ad_type == "blog_review",
            AdExecution.execution_date == day,
        ).first()
        return int(row.executed_count) if row else 0
    finally:
        db.close()


def test_completing_the_queue_records_the_execution_and_stays_idempotent(client):
    """완료 처리한 만큼만 진도표에 들어가고, 두 번 눌러도 두 배가 되지 않는다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_MANUAL_DONE, SOURCE_MANUAL
    from app.services import ad_dispatch

    merchant_id = _prepare_blog_merchant()
    headers = _auth(client)

    # 완료 처리 전에는 실적이 없다
    assert _execution_count(merchant_id, DAY) == 0

    body = {
        "merchant_id": merchant_id,
        "ad_type": "blog_review",
        "execution_date": str(DAY),
        "count": 3,
        "external_order_id": "RP-BLOG-0001",
        "note": "리워드팝 어드민에서 접수함",
    }
    res = client.post("/api/admin/ad-dispatch/manual-queue/complete", json=body, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == STATUS_MANUAL_DONE
    assert res.json()["is_manual"] is True
    assert _execution_count(merchant_id, DAY) == 3

    # 두 번 눌러도 행은 하나, 실적도 그대로
    res2 = client.post("/api/admin/ad-dispatch/manual-queue/complete", json=body, headers=headers)
    assert res2.status_code == 200, res2.text
    assert _execution_count(merchant_id, DAY) == 3

    db = _session()
    try:
        rows = db.query(AdDispatch).filter(
            AdDispatch.merchant_id == merchant_id,
            AdDispatch.ad_type == "blog_review",
            AdDispatch.execution_date == DAY,
        ).all()
        assert len(rows) == 1
        assert rows[0].source == SOURCE_MANUAL
        assert rows[0].external_order_id == "RP-BLOG-0001"
        # 사람이 확인한 수라 요청 수 = 실제 나간 수로 본다
        assert rows[0].delivered_count == 3
        assert float(rows[0].cost_amount) == 3 * 30000
        # 재시도 대상이 아니다 — 우리가 보낸 요청이 아니다
        assert rows[0].retryable is False
    finally:
        db.close()

    # 큐를 다시 읽으면 완료로 보인다
    queue = client.get(f"/api/admin/ad-dispatch/manual-queue?date={DAY}", headers=headers).json()
    item = next(i for i in queue["items"] if i["merchant_id"] == merchant_id)
    assert item["state"] == ad_dispatch.MANUAL_STATE_DONE
    assert item["done_count"] == 3
    assert item["month_done"] == 3
    assert item["note"] == "리워드팝 어드민에서 접수함"


def test_completing_with_a_different_count_overwrites_instead_of_adding(client):
    """실제로 접수한 수가 목표와 다르면 그 값으로 덮어쓴다."""
    merchant_id = _prepare_blog_merchant()
    headers = _auth(client)
    day = date(2026, 9, 11)

    for count in (3, 5, 2):
        res = client.post("/api/admin/ad-dispatch/manual-queue/complete", json={
            "merchant_id": merchant_id, "ad_type": "blog_review",
            "execution_date": str(day), "count": count,
        }, headers=headers)
        assert res.status_code == 200, res.text
        assert _execution_count(merchant_id, day) == count


def test_reverting_removes_the_execution_but_keeps_the_ledger_row(client):
    """되돌리면 실적에서 빠지고, 누가 눌렀는지 원장에는 남는다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_MANUAL_QUEUED

    merchant_id = _prepare_blog_merchant()
    headers = _auth(client)
    day = date(2026, 9, 12)

    client.post("/api/admin/ad-dispatch/manual-queue/complete", json={
        "merchant_id": merchant_id, "ad_type": "blog_review",
        "execution_date": str(day), "count": 4,
    }, headers=headers)
    assert _execution_count(merchant_id, day) == 4

    res = client.post("/api/admin/ad-dispatch/manual-queue/revert", json={
        "merchant_id": merchant_id, "ad_type": "blog_review", "execution_date": str(day),
    }, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == STATUS_MANUAL_QUEUED
    assert _execution_count(merchant_id, day) == 0

    db = _session()
    try:
        row = db.query(AdDispatch).filter(
            AdDispatch.merchant_id == merchant_id,
            AdDispatch.ad_type == "blog_review",
            AdDispatch.execution_date == day,
        ).one()
        assert row.status == STATUS_MANUAL_QUEUED
        assert row.response_json and "reverted" in row.response_json
    finally:
        db.close()


def test_reverting_something_that_was_never_completed_is_a_404(client):
    merchant_id = _prepare_blog_merchant()
    res = client.post("/api/admin/ad-dispatch/manual-queue/revert", json={
        "merchant_id": merchant_id, "ad_type": "blog_review",
        "execution_date": "2026-09-20",
    }, headers=_auth(client))
    assert res.status_code == 404


# ─── 큐에서 빠지는 경우 ──────────────────────────────────────

def test_zero_monthly_target_means_nothing_to_file(client):
    """월 목표를 넣기 전에는 접수할 것이 없다 — 플레이스와 같은 규칙."""
    from app.services import ad_dispatch

    _prepare_blog_merchant(monthly=0)
    db = _session()
    try:
        queue = ad_dispatch.build_manual_queue(db, DAY)
    finally:
        db.close()
    item = next(i for i in queue["items"] if i["ad_type"] == "blog_review")
    assert item["state"] == ad_dispatch.MANUAL_STATE_SKIP
    assert item["skip_reason"] == "zero_target"
    assert queue["todo_total"] == 0


def test_missing_unit_price_is_flagged_instead_of_silently_costing_nothing(client):
    """단가가 0이면 접수 대상으로 올리지 않고 사유를 보여준다."""
    from app.services import ad_dispatch

    _prepare_blog_merchant(unit_price=0)
    db = _session()
    try:
        queue = ad_dispatch.build_manual_queue(db, DAY)
    finally:
        db.close()
    item = next(i for i in queue["items"] if i["ad_type"] == "blog_review")
    assert item["state"] == ad_dispatch.MANUAL_STATE_SKIP
    assert item["skip_reason"] == "no_price"


def test_manual_queue_requires_admin(client):
    assert client.get("/api/admin/ad-dispatch/manual-queue").status_code in (401, 403)
    assert client.post("/api/admin/ad-dispatch/manual-queue/complete", json={
        "merchant_id": 1, "ad_type": "blog_review",
    }).status_code in (401, 403)


# ─── 리워드팝 공급 단가(클로 블로그 원가) ────────────────────
#
# cloblog 행은 missionCategory/missionAction 이 null 이라 by_mission 으로는 못 찾는다.
# mediaType 으로 찾는 by_media 경로가 이 테스트들의 대상이다.

API_KEY = "test-rewardpop-api-key-1234567890"

PRICE_BODY = {
    "accountId": 1, "parentId": None,
    "prices": [
        {"mediaType": "clo", "missionCategory": "VISIT",
         "missionAction": "FIND_PATH", "unitPrice": 120},
        # 실제 응답 모양 — 블로그는 미션이 매핑되지 않아 둘 다 null 이다
        {"mediaType": "cloblog", "missionCategory": None,
         "missionAction": None, "unitPrice": 28000},
        # 단가가 안 잡힌 매체는 무시돼야 한다
        {"mediaType": "nstore", "missionCategory": None,
         "missionAction": None, "unitPrice": None},
    ],
    "children": [
        # 하부 계정 단가가 본인 단가를 덮어쓰면 안 된다
        {"accountId": 2, "parentId": 1, "prices": [
            {"mediaType": "cloblog", "missionCategory": None,
             "missionAction": None, "unitPrice": 99000}]},
    ],
}


def _use_price_mock(monkeypatch, body=PRICE_BODY, status=200):
    """httpx.AsyncClient 를 MockTransport 로 바꿔 /accounts/prices 응답을 흉내낸다."""
    import httpx
    original = httpx.AsyncClient
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/prices"):
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"pointBalance": 10_000_000, "children": []})

    def factory(*args, **kwargs):
        return original(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return seen


def _enable_rewardpop():
    from app.services import rewardpop
    db = _session()
    try:
        rewardpop.save_api_key(db, API_KEY)
        rewardpop.save_settings(db, {**rewardpop.get_settings(db), "dry_run": False})
    finally:
        db.close()


def test_supply_price_is_found_by_media_type_not_by_mission():
    """cloblog 는 미션이 null 이라 mediaType 으로만 찾을 수 있다."""
    from app.services import ad_dispatch

    by_media = {"clo": [120.0], "cloblog": [28000.0]}
    found = ad_dispatch.supply_unit_price(by_media, "blog_review")
    assert found == {"media_type": "cloblog", "price": 28000.0, "ambiguous": False}
    # 매핑이 없는 광고 종류, 단가가 없는 경우는 조용히 None
    assert ad_dispatch.supply_unit_price(by_media, "place_traffic") is None
    assert ad_dispatch.supply_unit_price({}, "blog_review") is None
    assert ad_dispatch.supply_unit_price(None, "blog_review") is None


def test_ambiguous_supply_price_takes_the_highest_not_the_lowest():
    """단가가 여러 개면 넉넉한 쪽으로 잡는다 — 모자라는 게 남는 것보다 나쁘다."""
    from app.services import ad_dispatch

    found = ad_dispatch.supply_unit_price({"cloblog": [20000.0, 28000.0]}, "blog_review")
    assert found["price"] == 28000.0
    assert found["ambiguous"] is True


def test_price_parser_keeps_own_account_and_ignores_children(client, monkeypatch):
    """하부 계정 단가(99,000)가 본인 단가(28,000)를 덮어쓰면 안 된다."""
    import asyncio
    from app.services import rewardpop

    _enable_rewardpop()
    _use_price_mock(monkeypatch)
    db = _session()
    try:
        result = asyncio.get_event_loop().run_until_complete(rewardpop.get_prices(db))
    finally:
        db.close()

    assert result["by_media"]["cloblog"] == [28000.0]
    assert result["by_mission"]["VISIT:FIND_PATH"] == 120.0
    # 단가가 null 인 매체는 어느 쪽에도 없다
    assert "nstore" not in result["by_media"]


def test_manual_queue_reports_required_points_and_margin(client, monkeypatch):
    """큐가 원가·필요 포인트·마진을 함께 계산한다."""
    import asyncio
    from app.services import ad_dispatch

    # 앞선 테스트가 완료 처리해 둔 날과 겹치지 않게 다른 날을 쓴다
    day = date(2026, 9, 13)
    merchant_id = _prepare_blog_merchant(monthly=MONTHLY, unit_price=40000)
    _enable_rewardpop()
    _use_price_mock(monkeypatch)

    db = _session()
    try:
        queue = asyncio.get_event_loop().run_until_complete(
            ad_dispatch.manual_queue(db, day))
    finally:
        db.close()

    item = next(i for i in queue["items"] if i["merchant_id"] == merchant_id)
    assert item["target"] == 3
    assert item["supply_unit_price"] == 28000.0
    assert item["required_points"] == 3 * 28000          # 리워드팝에서 빠질 포인트
    assert item["est_cost"] == 3 * 40000                 # 매장에 청구할 금액
    assert item["margin"] == 3 * (40000 - 28000)
    assert queue["required_points"] == 3 * 28000
    assert queue["unpriced_count"] == 0
    assert queue["supply_price_error"] is None


def test_manual_queue_survives_a_price_lookup_failure(client, monkeypatch):
    """단가 조회가 실패해도 접수 목록과 수량은 그대로 나온다."""
    import asyncio
    from app.services import ad_dispatch

    day = date(2026, 9, 14)
    merchant_id = _prepare_blog_merchant()
    _enable_rewardpop()
    _use_price_mock(monkeypatch, body={"detail": "boom"}, status=500)

    db = _session()
    try:
        queue = asyncio.get_event_loop().run_until_complete(
            ad_dispatch.manual_queue(db, day))
    finally:
        db.close()

    item = next(i for i in queue["items"] if i["merchant_id"] == merchant_id)
    assert item["target"] == 3                  # 접수해야 할 수량은 멀쩡하다
    assert item["state"] == ad_dispatch.MANUAL_STATE_TODO
    assert item["supply_unit_price"] is None    # 원가만 비어 있다
    assert item["required_points"] is None
    assert queue["required_points"] is None
    assert queue["unpriced_count"] == 1
    assert queue["supply_price_error"]
