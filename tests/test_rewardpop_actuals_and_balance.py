"""리워드팝 연동 2차 보강분에 대한 회귀 테스트.

- 집행 전 포인트 잔액 게이트 (부족하면 그날 전부 보류, 드라이런은 막지 않음)
- 잔액 조회 실패는 집행을 막지 않는다
- 공급 단가(GET /accounts/prices) 파싱과 포인트 소요액 계산
- 외부 STOP 상태를 실패와 분리하고, 재집행되지 않게 막는다
- 실제 진행 수치(reqCount / rewardCount / keywordCount) 기록
- AUTO 모드에서 리워드팝이 고른 키워드 회수
"""
import asyncio
import importlib
import json
import os
import sys
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "actuals.db"
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


def _auth(client, role):
    token = client.post(f"/api/auth/test-login?role={role}").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


API_KEY = "test-rewardpop-api-key-1234567890"


def _mock_client(handler):
    """httpx.AsyncClient 를 MockTransport 로 바꿔치기하는 팩토리."""
    import httpx as _httpx
    original = _httpx.AsyncClient

    def factory(*args, **kwargs):
        return original(transport=_httpx.MockTransport(handler), timeout=kwargs.get("timeout"))
    return factory


# ─── 집행 대상 한 건을 만드는 준비 ───────────────────────────

def _prepare_dispatchable_merchant(monthly=3100, unit_price=100):
    """플랜·목표·집행설정·placeCode·승인 키워드·단가를 모두 갖춘 매장 1곳."""
    from app.models.merchant import Merchant
    from app.models.merchant_ad_config import MerchantAdConfig
    from app.models.plan import Plan, MerchantPlan, MerchantAdOverride
    from app.models.ad_keyword import MerchantAdKeyword, KEYWORD_APPROVED
    from app.services import ad_pricing

    db = _session()
    try:
        merchant = db.query(Merchant).first()
        merchant.place_code = "1750900108"

        plan = db.query(Plan).filter(Plan.code == "test-basic").first()
        if plan is None:
            plan = Plan(name="테스트", code="test-basic")
            db.add(plan)
            db.flush()
        if not db.query(MerchantPlan).filter(MerchantPlan.merchant_id == merchant.id).first():
            db.add(MerchantPlan(merchant_id=merchant.id, plan_id=plan.id))

        if not db.query(MerchantAdOverride).filter(
            MerchantAdOverride.merchant_id == merchant.id,
            MerchantAdOverride.ad_type == "place_traffic",
        ).first():
            db.add(MerchantAdOverride(
                merchant_id=merchant.id, ad_type="place_traffic", monthly_override=monthly))

        if not db.query(MerchantAdConfig).filter(
            MerchantAdConfig.merchant_id == merchant.id,
            MerchantAdConfig.ad_type == "place_traffic",
        ).first():
            db.add(MerchantAdConfig(
                merchant_id=merchant.id, ad_type="place_traffic",
                mission_category="VISIT", mission_action="FIND_PATH",
                keyword_mode="MANUAL",
            ))

        if not db.query(MerchantAdKeyword).filter(
            MerchantAdKeyword.merchant_id == merchant.id
        ).first():
            db.add(MerchantAdKeyword(
                merchant_id=merchant.id, keyword="강남 미용실", ad_type="place_traffic",
                status=KEYWORD_APPROVED, is_active=True,
            ))

        pricing = ad_pricing.get_ad_pricing(db)
        pricing["place_traffic_unit_price"] = unit_price
        ad_pricing.save_ad_pricing(db, pricing)
        db.commit()
        return merchant.id
    finally:
        db.close()


# ─── 잔액 게이트 ─────────────────────────────────────────────

def test_low_balance_holds_the_whole_day(client, monkeypatch):
    """포인트가 모자라면 그날 집행 대상이 전부 보류되고, 실제 호출은 없다."""
    from app.models.ad_dispatch import SKIP_LOW_BALANCE, STATUS_SKIPPED, AdDispatch
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    db = _session()
    rewardpop.save_api_key(db, API_KEY)
    rewardpop.save_settings(db, {**rewardpop.get_settings(db), "dry_run": False})
    db.close()

    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/accounts/points":
            return httpx.Response(200, json={"pointBalance": 1, "children": []})
        if request.url.path == "/accounts/prices":
            return httpx.Response(200, json={"prices": [{
                "mediaType": "clo", "missionCategory": "VISIT",
                "missionAction": "FIND_PATH", "unitPrice": 120}], "children": []})
        return httpx.Response(500, json={})

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.run(
            db, target_date=date(2026, 9, 15), merchant_id=merchant_id, dry_run=False))
    finally:
        db.close()

    assert result["low_balance"] is True
    assert result["dispatched_count"] == 0
    assert result["skipped_count"] >= 1
    assert result["balance_basis"] == "supply_price"
    # 공급 단가 120 × 일별 목표만큼이 필요액이어야 한다 (잔액 1P 로는 어림없다)
    assert result["required_points"] > 1
    # 잔액/단가 조회 외에 /ads 로 나간 요청이 없어야 한다
    assert not [c for c in calls if c.url.path == "/ads"]

    db = _session()
    try:
        row = db.query(AdDispatch).filter(
            AdDispatch.merchant_id == merchant_id,
            AdDispatch.execution_date == date(2026, 9, 15),
        ).first()
        assert row is not None
        assert row.status == STATUS_SKIPPED
        assert row.skip_reason == SKIP_LOW_BALANCE
        assert "포인트 부족" in (row.error_message or "")
    finally:
        db.close()


def test_dry_run_reports_shortfall_but_does_not_hold(client, monkeypatch):
    """드라이런은 포인트를 쓰지 않는다 — 숫자는 보여주되 보류시키지 않는다."""
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()

    def handler(request):
        if request.url.path == "/accounts/points":
            return httpx.Response(200, json={"pointBalance": 1, "children": []})
        if request.url.path == "/accounts/prices":
            return httpx.Response(200, json={"prices": [], "children": []})
        return httpx.Response(500, json={})

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.run(
            db, target_date=date(2026, 9, 16), merchant_id=merchant_id, dry_run=True))
    finally:
        db.close()

    assert result["low_balance"] is True        # 부족하다는 사실은 알려준다
    assert result["dispatched_count"] >= 1      # 그래도 드라이런은 진행한다
    assert result["balance_basis"] == "sale_price"  # 단가가 비어 판매가로 추정


def test_balance_lookup_failure_does_not_block_dispatch(client, monkeypatch):
    """잔액을 못 읽었다고 하루 집행을 통째로 막지는 않는다. 경고만 남긴다."""
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    db = _session()
    rewardpop.save_settings(db, {**rewardpop.get_settings(db), "dry_run": False})
    db.close()

    def handler(request):
        if request.url.path in ("/accounts/points", "/accounts/prices"):
            return httpx.Response(503, json={"message": "점검 중"})
        if request.method == "POST" and request.url.path == "/ads":
            return httpx.Response(201, json={"groupId": "GROUP-NOBAL", "status": "PENDING"})
        return httpx.Response(404, json={})

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.run(
            db, target_date=date(2026, 9, 17), merchant_id=merchant_id, dry_run=False))
    finally:
        db.close()

    assert result["low_balance"] is False
    assert result["balance_error"]
    assert result["dispatched_count"] >= 1


def test_sufficient_balance_lets_dispatch_through(client, monkeypatch):
    """잔액이 넉넉하면 평소대로 나가고, 응답의 실측 수치가 기록된다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_SENT
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()

    def handler(request):
        if request.url.path == "/accounts/points":
            return httpx.Response(200, json={"pointBalance": 9_000_000, "children": []})
        if request.url.path == "/accounts/prices":
            return httpx.Response(200, json={"prices": [{
                "missionCategory": "VISIT", "missionAction": "FIND_PATH", "unitPrice": 120}]})
        if request.method == "POST" and request.url.path == "/ads":
            return httpx.Response(201, json={
                "groupId": "GROUP-OK", "status": "PENDING",
                "totalReqCount": 100, "reqCount": 100, "rewardCount": 0, "keywordCount": 1})
        return httpx.Response(404, json={})

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.run(
            db, target_date=date(2026, 9, 18), merchant_id=merchant_id, dry_run=False))
    finally:
        db.close()

    assert result["low_balance"] is False
    assert result["dispatched_count"] == 1

    db = _session()
    try:
        row = db.query(AdDispatch).filter(
            AdDispatch.execution_date == date(2026, 9, 18)).one()
        assert row.status == STATUS_SENT
        assert row.external_order_id == "GROUP-OK"
        assert row.external_status == "PENDING"
        assert row.delivered_count == 100
        assert row.reward_count == 0
    finally:
        db.close()


# ─── 공급 단가 ───────────────────────────────────────────────

def test_supply_prices_use_own_account_not_children(client, monkeypatch):
    """공급 단가는 본인 계정 것만 읽는다. 하부 계정 단가가 섞이면 계산이 틀어진다."""
    from app.services import rewardpop

    def handler(request):
        assert request.headers["x-api-key"] == API_KEY
        return httpx.Response(200, json={
            "accountId": 12, "role": "대행사",
            "prices": [
                {"missionCategory": "VISIT", "missionAction": "FIND_PATH", "unitPrice": 120},
                {"missionCategory": "SAVE", "missionAction": "PLACE_SAVE", "unitPrice": None},
            ],
            "children": [{
                "accountId": 99,
                "prices": [{"missionCategory": "VISIT", "missionAction": "FIND_PATH", "unitPrice": 999}],
                "children": [],
            }],
        })

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(rewardpop.get_prices(db))
    finally:
        db.close()

    assert result["by_mission"] == {"VISIT:FIND_PATH": 120.0}   # 999 도 None 도 들어오지 않는다
    assert len(result["prices"]) == 2


def test_prices_endpoint_is_reachable_for_admin(client):
    res = client.get("/api/admin/rewardpop/prices", headers=_auth(client, "admin"))
    assert res.status_code == 200
    # 키는 등록돼 있고 실제 호출은 실패하므로 ok=False 라도 400 이 아니어야 한다
    assert "ok" in res.json()


# ─── 실측 수량 · 상태 ────────────────────────────────────────

def test_extract_counts_sums_rows_without_double_counting():
    from app.services import rewardpop

    body = [
        {"groupId": "G", "reqCount": 100, "rewardCount": 30, "totalReqCount": 300, "keywordCount": 5},
        {"groupId": "G", "reqCount": 100, "rewardCount": 45, "totalReqCount": 300, "keywordCount": 5},
    ]
    counts = rewardpop.extract_counts(body)
    assert counts["delivered_count"] == 200
    assert counts["reward_count"] == 75
    # 값이 아예 없으면 키도 없어야 한다 (0 으로 덮어써 실적을 지우면 안 된다)
    assert rewardpop.extract_counts({"status": "ACTIVE"}) == {}


def test_stop_is_mapped_to_stopped_not_failed():
    from app.services import rewardpop

    assert rewardpop.map_external_status({"status": "STOP"})[0] == "stopped"
    assert rewardpop.map_external_status({"status": "ERROR"})[0] == "failed"
    assert rewardpop.map_external_status({"status": "COMPLETED"})[0] == "done"
    assert rewardpop.map_external_status({"status": "ACTIVE"})[0] == "running"
    # 모르는 값은 매핑하지 않는다 — 완료로 오인하면 실적이 부풀려진다
    assert rewardpop.map_external_status({"status": "WHATEVER"})[0] is None


def test_refresh_records_actuals_and_stopped_state(client, monkeypatch):
    """상태 갱신이 STOP 을 실패로 만들지 않고, 실제 수치를 기록한다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_SENT, STATUS_STOPPED, EXECUTED_STATUSES
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    day = date(2026, 9, 20)
    db = _session()
    try:
        row = AdDispatch(
            merchant_id=merchant_id, ad_type="place_traffic", execution_date=day,
            source="auto", idempotency_key=f"auto:{merchant_id}:place_traffic:{day}",
            requested_count=100, status=STATUS_SENT, external_order_id="GROUP-STOP",
            dry_run=False,
        )
        db.add(row)
        db.commit()
        row_id = row.id
    finally:
        db.close()

    def handler(request):
        if request.method == "GET" and request.url.path == "/ads":
            assert request.url.params["groupId"] == "GROUP-STOP"
            return httpx.Response(200, json=[{
                "groupId": "GROUP-STOP", "status": "STOP",
                "totalReqCount": 100, "reqCount": 100, "rewardCount": 62, "keywordCount": 3}])
        return httpx.Response(404, json={})

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.refresh_statuses(db, day))
    finally:
        db.close()

    assert result["updated"] == 1
    db = _session()
    try:
        row = db.query(AdDispatch).filter(AdDispatch.id == row_id).one()
        assert row.status == STATUS_STOPPED
        assert row.retryable is False           # 중지는 재시도 대상이 아니다
        assert row.reward_count == 62
        assert row.delivered_count == 100
        assert row.keyword_count == 3
        assert row.external_status == "STOP"
        assert row.effective_count == 62
        # 중지 상태도 "이미 나간 건"이라 같은 날 다시 나가면 안 된다
        assert STATUS_STOPPED in EXECUTED_STATUSES
        assert ad_dispatch._already_executed(db, merchant_id, "place_traffic", day) is True
    finally:
        db.close()


def test_stopped_dispatch_is_not_dispatched_again(client, monkeypatch):
    """중지된 건이 있는 날은 같은 매장에 주문이 한 번 더 나가지 않는다."""
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    posted = []

    def handler(request):
        if request.url.path == "/accounts/points":
            return httpx.Response(200, json={"pointBalance": 9_000_000})
        if request.url.path == "/accounts/prices":
            return httpx.Response(200, json={"prices": []})
        if request.method == "POST" and request.url.path == "/ads":
            posted.append(request)
            return httpx.Response(201, json={"groupId": "SHOULD-NOT-HAPPEN", "status": "PENDING"})
        return httpx.Response(404, json={})

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.run(
            db, target_date=date(2026, 9, 20), merchant_id=merchant_id, dry_run=False))
    finally:
        db.close()

    assert posted == []
    assert result["dispatched_count"] == 0


def test_refresh_updates_counts_even_when_status_is_unchanged(client, monkeypatch):
    """상태가 그대로여도 적립 수는 계속 늘어난다 — 수량만 바뀌어도 기록한다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_RUNNING
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    day = date(2026, 9, 21)
    db = _session()
    try:
        row = AdDispatch(
            merchant_id=merchant_id, ad_type="place_traffic", execution_date=day,
            source="auto", idempotency_key=f"auto:{merchant_id}:place_traffic:{day}",
            requested_count=100, status=STATUS_RUNNING, external_order_id="GROUP-RUN",
            dry_run=False, reward_count=10,
        )
        db.add(row)
        db.commit()
        row_id = row.id
    finally:
        db.close()

    def handler(request):
        return httpx.Response(200, json=[{
            "groupId": "GROUP-RUN", "status": "ACTIVE", "reqCount": 100, "rewardCount": 55}])

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        result = asyncio.run(ad_dispatch.refresh_statuses(db, day))
    finally:
        db.close()

    assert result["updated"] == 1
    db = _session()
    try:
        assert db.query(AdDispatch).filter(AdDispatch.id == row_id).one().reward_count == 55
    finally:
        db.close()


# ─── AUTO 모드 키워드 회수 ───────────────────────────────────

def test_auto_mode_collects_the_keywords_rewardpop_chose(client, monkeypatch):
    """AUTO 로 나간 건은 리워드팝이 고른 키워드를 받아 적는다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_SENT
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    day = date(2026, 9, 22)
    db = _session()
    try:
        row = AdDispatch(
            merchant_id=merchant_id, ad_type="place_traffic", execution_date=day,
            source="auto", idempotency_key=f"auto:{merchant_id}:place_traffic:{day}",
            requested_count=100, status=STATUS_SENT, external_order_id="GROUP-AUTO",
            dry_run=False,
        )
        db.add(row)
        db.commit()
        row_id = row.id
    finally:
        db.close()

    def handler(request):
        assert request.url.path == "/ads/GROUP-AUTO/keywords"
        return httpx.Response(200, json={
            "groupId": "GROUP-AUTO", "placeCode": 1750900108,
            "keywordCount": 3, "keywords": ["강남미용실", "강남헤어", "강남미용실"],
        })

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        row = db.query(AdDispatch).filter(AdDispatch.id == row_id).one()
        asyncio.run(ad_dispatch._collect_auto_keywords(
            db, row, {"ad_config": {"keyword_mode": "AUTO"}}))
    finally:
        db.close()

    db = _session()
    try:
        row = db.query(AdDispatch).filter(AdDispatch.id == row_id).one()
        # 중복은 제거하되 순서는 지킨다
        assert json.loads(row.keywords_json) == ["강남미용실", "강남헤어"]
        assert row.keyword_count == 3
        assert "강남미용실" in row.keyword
    finally:
        db.close()


def test_keyword_collection_failure_does_not_break_the_dispatch(client, monkeypatch):
    """키워드 회수가 실패해도 집행 자체는 성공으로 남는다."""
    from app.models.ad_dispatch import AdDispatch, STATUS_SENT
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    day = date(2026, 9, 23)
    db = _session()
    try:
        row = AdDispatch(
            merchant_id=merchant_id, ad_type="place_traffic", execution_date=day,
            source="auto", idempotency_key=f"auto:{merchant_id}:place_traffic:{day}",
            requested_count=100, status=STATUS_SENT, external_order_id="GROUP-FAIL",
            dry_run=False,
        )
        db.add(row)
        db.commit()
        row_id = row.id
    finally:
        db.close()

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient",
                        _mock_client(lambda r: httpx.Response(500, json={})))
    db = _session()
    try:
        row = db.query(AdDispatch).filter(AdDispatch.id == row_id).one()
        asyncio.run(ad_dispatch._collect_auto_keywords(
            db, row, {"ad_config": {"keyword_mode": "AUTO"}}))
    finally:
        db.close()

    db = _session()
    try:
        row = db.query(AdDispatch).filter(AdDispatch.id == row_id).one()
        assert row.status == STATUS_SENT
        assert row.keywords_json is None
    finally:
        db.close()


# ─── 화면에 내려가는 값 ──────────────────────────────────────

def test_status_summary_exposes_effective_dry_run(client):
    """화면 배지가 볼 실효 드라이런 값과 환경변수 덮어쓰기 여부가 내려간다."""
    res = client.get("/api/admin/rewardpop/config", headers=_auth(client, "admin"))
    assert res.status_code == 200
    body = res.json()
    assert "effective_dry_run" in body
    assert "dry_run_forced_by_env" in body
    # 공식 경로 2종이 기본값으로 채워져 있어야 AUTO 키워드·단가 조회가 동작한다
    assert body["settings"]["keywords_path"] == "/ads/{groupId}/keywords"
    assert body["settings"]["prices_path"] == "/accounts/prices"


def test_report_separates_requested_from_rewarded(client):
    from app.services import ad_dispatch

    db = _session()
    try:
        report = ad_dispatch.report(db, date(2026, 9, 1), date(2026, 9, 30))
    finally:
        db.close()

    for key in ("total_count", "total_rewarded", "total_delivered",
                "measured_dispatches", "stopped_dispatches"):
        assert key in report
    # 위 테스트들에서 STOP 1건이 잡혀 있어야 한다
    assert report["stopped_dispatches"] >= 1
    assert report["total_rewarded"] >= 62


def test_repeated_refresh_with_same_numbers_is_a_no_op(client, monkeypatch):
    """수치가 그대로면 '변화 없음'으로 세야 한다 (0 을 변화로 오인하지 않는다)."""
    from app.models.ad_dispatch import AdDispatch, STATUS_RUNNING
    from app.services import ad_dispatch, rewardpop

    merchant_id = _prepare_dispatchable_merchant()
    day = date(2026, 9, 24)
    db = _session()
    try:
        db.add(AdDispatch(
            merchant_id=merchant_id, ad_type="place_traffic", execution_date=day,
            source="auto", idempotency_key=f"auto:{merchant_id}:place_traffic:{day}",
            requested_count=100, status=STATUS_RUNNING, external_order_id="GROUP-IDEM",
            dry_run=False,
        ))
        db.commit()
    finally:
        db.close()

    def handler(request):
        # rewardCount 가 0 인 상태 — 아직 아무도 적립하지 않았다
        return httpx.Response(200, json=[{
            "groupId": "GROUP-IDEM", "status": "ACTIVE", "reqCount": 100, "rewardCount": 0}])

    monkeypatch.setattr(rewardpop.httpx, "AsyncClient", _mock_client(handler))
    db = _session()
    try:
        first = asyncio.run(ad_dispatch.refresh_statuses(db, day))
        second = asyncio.run(ad_dispatch.refresh_statuses(db, day))
    finally:
        db.close()

    assert first["updated"] == 1        # 처음엔 0 을 기록한다
    assert second["updated"] == 0       # 두 번째는 건드릴 게 없다
    assert second["unchanged"] == 1
