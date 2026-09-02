"""점검에서 나온 결함들에 대한 회귀 테스트.

- 리워드팝 create_order 가 드라이런 예외 대신 실제 호출을 한다
- 광고 주문 반려 시 차감했던 크레딧이 되돌아온다
- 단말기 등록/수정/삭제 API 와 지문 기반 인증
- 취소 거래가 매출 집계에서 빠진다
- 로그인 실패 제한
- ADMIN 이 원장 API 에서 404 대신 대상 가맹점을 지정할 수 있다
- CRM 이 남의 미용실 직원을 붙이지 못한다
"""
import asyncio
import importlib
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "fixes.db"
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


def _auth(client, role):
    token = client.post(f"/api/auth/test-login?role={role}").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _session():
    from app.database import SessionLocal
    return SessionLocal()


# ─── 리워드팝 ────────────────────────────────────────────────

def test_create_order_uses_official_path_and_requires_key(client):
    """공식 /ads 경로를 기본 사용하며 키가 없으면 외부 호출 전에 차단한다."""
    from app.services import rewardpop

    db = _session()
    try:
        with pytest.raises(rewardpop.RewardpopError) as exc:
            asyncio.run(rewardpop.create_order(db, "blog_review", {"count": 1}))
        assert "API 키" in exc.value.message
        assert rewardpop.get_settings(db)["order_path"] == "/ads"
    finally:
        db.close()


def test_official_settings_override_legacy_paths(client):
    """공식 호스트에서는 과거 사용자 입력보다 검증된 OpenAPI 경로를 사용한다."""
    response = client.put(
        "/api/admin/rewardpop/config",
        json={"status_path": "/v1/campaigns/{id}"},
        headers=_auth(client, "admin"),
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["auth_style"] == "header"
    assert settings["auth_header"] == "x-api-key"
    assert settings["ping_path"] == "/accounts/points"
    assert settings["balance_path"] == "/accounts/points"
    assert settings["order_path"] == "/ads"
    assert settings["status_path"] == "/ads"


def test_dry_run_can_be_forced_by_env():
    """환경변수로 드라이런을 강제할 수 있어야 한다."""
    from app.config import get_settings as get_app_settings
    from app.services import rewardpop

    db = _session()
    try:
        rewardpop.save_settings(db, {**rewardpop.get_settings(db), "dry_run": False})
        assert rewardpop.dry_run_enabled(db) is False

        app_settings = get_app_settings()
        app_settings.REWARDPOP_DRY_RUN = True
        try:
            assert rewardpop.dry_run_enabled(db) is True
        finally:
            app_settings.REWARDPOP_DRY_RUN = None
    finally:
        db.close()


def test_rewardpop_official_http_contract(monkeypatch):
    """공식 x-api-key, /ads, groupId, /accounts/points 규격을 그대로 사용한다."""
    import httpx
    from app.services import rewardpop

    db = _session()
    calls = []
    original_client = rewardpop.httpx.AsyncClient

    def handler(request):
        calls.append(request)
        if request.method == "POST" and request.url.path == "/ads":
            return httpx.Response(201, json={"groupId": "GROUP-1", "status": "PENDING"})
        if request.method == "GET" and request.url.path == "/ads":
            return httpx.Response(200, json=[{"groupId": "GROUP-1", "status": "ACTIVE"}])
        if request.method == "GET" and request.url.path == "/accounts/points":
            return httpx.Response(200, json={"pointBalance": 123456, "children": []})
        return httpx.Response(404, json={})

    def client_factory(*args, **kwargs):
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=kwargs.get("timeout"),
        )

    try:
        rewardpop.save_api_key(db, "test-rewardpop-api-key-1234567890")
        monkeypatch.setattr(rewardpop.httpx, "AsyncClient", client_factory)
        created = asyncio.run(rewardpop.create_order(db, "place_traffic", {
            "placeCode": 1750900108,
            "missionCategory": "VISIT",
            "missionAction": "FIND_PATH",
            "startDate": "2026-09-02",
            "workDays": 1,
            "dailyQuantity": 100,
            "keywordMode": "MANUAL",
            "keywords": "강남미용실",
        }))
        status = asyncio.run(rewardpop.get_order_status(db, created["external_order_id"]))
        balance = asyncio.run(rewardpop.get_balance(db))

        assert created["external_order_id"] == "GROUP-1"
        assert created["status"] == "sent"
        assert status["status"] == "running"
        assert balance["balance"] == 123456
        assert all(request.headers["x-api-key"] == "test-rewardpop-api-key-1234567890" for request in calls)
        assert calls[1].url.params["groupId"] == "GROUP-1"
    finally:
        rewardpop.delete_api_key(db)
        db.close()


def test_approved_place_order_is_dispatched_to_rewardpop(client, monkeypatch):
    """추가 플레이스 주문은 관리자 집행 시 order 출처 원장으로 한 번만 전송된다."""
    from app.models.ad import AdOrder, AdOrderPlaceTrafficDetail, AdOrderStatus, AdOrderType
    from app.models.ad_dispatch import AdDispatch
    from app.models.merchant import Merchant
    from app.models.merchant_ad_config import MerchantAdConfig
    from app.models.user import User
    from app.services import rewardpop

    db = _session()
    try:
        merchant = db.query(Merchant).first()
        admin = db.query(User).filter(User.email == "admin@test.com").first()
        merchant.place_code = "1750900108"
        config = MerchantAdConfig(
            merchant_id=merchant.id,
            ad_type="place_traffic",
            mission_category="VISIT",
            mission_action="FIND_PATH",
            keyword_mode="MANUAL",
        )
        order = AdOrder(
            merchant_id=merchant.id,
            type=AdOrderType.PLACE_TRAFFIC,
            status=AdOrderStatus.REVIEWING,
            created_by=admin.id,
        )
        db.add_all([config, order])
        db.flush()
        db.add(AdOrderPlaceTrafficDetail(
            order_id=order.id,
            place_name_or_id="애드페이 강남점",
            search_keywords_json=json.dumps(["강남 미용실", "헤어샵"]),
            order_count=100,
            unit_price=100,
            est_total_cost=10000,
        ))
        rewardpop.save_api_key(db, "test-rewardpop-api-key-1234567890")
        rewardpop.save_settings(db, {**rewardpop.get_settings(db), "dry_run": False})
        db.commit()
        order_id = order.id
    finally:
        db.close()

    captured = []

    async def fake_create_order(_db, ad_type, payload):
        captured.append((ad_type, payload))
        return {"external_order_id": "GROUP-ORDER-1", "status": "sent", "raw": {"status": "PENDING"}}

    monkeypatch.setattr(rewardpop, "create_order", fake_create_order)
    response = client.put(
        f"/api/admin/ad/orders/{order_id}/execute?status=running",
        headers=_auth(client, "admin"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["external_order_id"] == "GROUP-ORDER-1"
    assert captured[0][0] == "place_traffic"
    assert captured[0][1]["placeCode"] == 1750900108
    assert captured[0][1]["dailyQuantity"] == 100
    assert captured[0][1]["keywords"] == "강남 미용실|헤어샵"

    db = _session()
    try:
        dispatch = db.query(AdDispatch).filter(AdDispatch.ad_order_id == order_id).one()
        assert dispatch.source == "order"
        assert dispatch.external_order_id == "GROUP-ORDER-1"
        assert db.query(AdOrder).filter(AdOrder.id == order_id).one().status == AdOrderStatus.RUNNING
    finally:
        rewardpop.delete_api_key(db)
        db.close()


def test_invalid_order_transition_does_not_dispatch_to_rewardpop(client, monkeypatch):
    """내부 상태 전환이 잘못되면 되돌릴 수 없는 외부 POST를 먼저 보내지 않는다."""
    from app.models.ad import AdOrder, AdOrderPlaceTrafficDetail, AdOrderStatus, AdOrderType
    from app.models.merchant import Merchant
    from app.models.merchant_ad_config import MerchantAdConfig
    from app.models.user import User
    from app.services import rewardpop

    db = _session()
    try:
        merchant = db.query(Merchant).first()
        admin = db.query(User).filter(User.email == "admin@test.com").first()
        merchant.place_code = "1750900108"
        config = db.query(MerchantAdConfig).filter(
            MerchantAdConfig.merchant_id == merchant.id,
            MerchantAdConfig.ad_type == "place_traffic",
        ).first()
        if config is None:
            config = MerchantAdConfig(merchant_id=merchant.id, ad_type="place_traffic")
            db.add(config)
        config.mission_category = "VISIT"
        config.mission_action = "FIND_PATH"
        config.keyword_mode = "MANUAL"
        order = AdOrder(
            merchant_id=merchant.id,
            type=AdOrderType.PLACE_TRAFFIC,
            status=AdOrderStatus.REQUESTED,
            created_by=admin.id,
        )
        db.add(order)
        db.flush()
        db.add(AdOrderPlaceTrafficDetail(
            order_id=order.id,
            place_name_or_id="애드페이 강남점",
            search_keywords_json=json.dumps(["강남 미용실"]),
            order_count=10,
            unit_price=100,
            est_total_cost=1000,
        ))
        rewardpop.save_api_key(db, "test-rewardpop-api-key-1234567890")
        rewardpop.save_settings(db, {**rewardpop.get_settings(db), "dry_run": False})
        db.commit()
        order_id = order.id
    finally:
        db.close()

    calls = []

    async def fake_create_order(_db, ad_type, payload):
        calls.append((ad_type, payload))
        return {"external_order_id": "SHOULD-NOT-EXIST", "status": "sent", "raw": {}}

    monkeypatch.setattr(rewardpop, "create_order", fake_create_order)
    response = client.put(
        f"/api/admin/ad/orders/{order_id}/execute?status=running",
        headers=_auth(client, "admin"),
    )
    assert response.status_code == 409, response.text
    assert calls == []

    db = _session()
    try:
        rewardpop.delete_api_key(db)
    finally:
        db.close()


# ─── 광고 주문 반려 → 크레딧 환급 ────────────────────────────

def test_rejecting_credit_order_returns_the_credit(client):
    """크레딧으로 결제한 광고 주문을 반려하면 광고비가 되돌아와야 한다."""
    from app.models.ad import AdOrder, AdOrderStatus, AdOrderType
    from app.models.merchant import Merchant
    from app.models.user import User
    from app.services import ad_credit

    admin_headers = _auth(client, "admin")
    db = _session()
    try:
        merchant = db.query(Merchant).first()
        admin = db.query(User).filter(User.email == "admin@test.com").first()
        ad_credit.charge(db, merchant.id, 100000, "테스트 충전", admin.id)
        before = ad_credit.balance_of(db, merchant.id)

        order = AdOrder(
            merchant_id=merchant.id, type=AdOrderType.BLOG,
            status=AdOrderStatus.REQUESTED, created_by=admin.id,
            payment_source="credit", credit_amount=30000,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        ad_credit.use(db, merchant.id, 30000, order.id, "테스트 주문", admin.id)
        assert ad_credit.balance_of(db, merchant.id) == before - 30000
        order_id = order.id
    finally:
        db.close()

    # requested → reviewing → rejected
    assert client.put(
        f"/api/admin/ad/orders/{order_id}/execute?status=reviewing",
        headers=admin_headers,
    ).status_code == 200
    rejected = client.put(
        f"/api/admin/ad/orders/{order_id}/execute?status=rejected",
        headers=admin_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["credit_refunded"] is True

    db = _session()
    try:
        from app.models.merchant import Merchant as M
        merchant_id = db.query(M).first().id
        assert ad_credit.balance_of(db, merchant_id) == before

        # 같은 반려를 다시 처리해도 중복 환급되지 않는다 (반려 → 검토 → 반려).
        client.put(f"/api/admin/ad/orders/{order_id}/execute?status=reviewing",
                   headers=admin_headers)
        assert ad_credit.balance_of(db, merchant_id) == before - 30000
        client.put(f"/api/admin/ad/orders/{order_id}/execute?status=rejected",
                   headers=admin_headers)
        assert ad_credit.balance_of(db, merchant_id) == before
    finally:
        db.close()


# ─── 단말기 관리 ─────────────────────────────────────────────

def test_terminal_can_be_registered_updated_and_deleted(client):
    """시드 데이터 없이 운영에서 단말기를 등록할 수 있어야 한다."""
    headers = _auth(client, "admin")
    merchant_id = client.get("/api/admin/merchants", headers=headers).json()[0]["id"]

    created = client.post("/api/admin/terminals", json={
        "merchant_id": merchant_id,
        "terminal_serial": "TERM-NEW-001",
        "memo": "2번 카운터",
    }, headers=headers)
    assert created.status_code == 201
    body = created.json()
    api_key = body["api_key"]
    tid = body["id"]
    assert api_key and len(api_key) >= 20

    # 같은 일련번호는 다시 등록할 수 없다
    assert client.post("/api/admin/terminals", json={
        "merchant_id": merchant_id, "terminal_serial": "TERM-NEW-001",
    }, headers=headers).status_code == 409

    # 발급받은 키로 실제 결제가 들어간다
    txn = client.post("/api/terminal/transactions", json={
        "terminal_id": "TERM-NEW-001", "merchant_id": merchant_id, "amount": 15000,
    }, headers={"X-Terminal-Key": api_key})
    assert txn.status_code == 200, txn.text

    # 조회·수정
    assert client.get(f"/api/admin/terminals/{tid}", headers=headers).json()["memo"] == "2번 카운터"
    updated = client.put(f"/api/admin/terminals/{tid}",
                         json={"memo": "창구", "is_active": False}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["memo"] == "창구"
    assert updated.json()["is_active"] is False

    # 거래가 있으면 삭제 대신 사용 중지
    deleted = client.delete(f"/api/admin/terminals/{tid}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is False

    # 거래가 없는 단말기는 삭제된다
    tmp = client.post("/api/admin/terminals", json={
        "merchant_id": merchant_id, "terminal_serial": "TERM-TMP-001",
    }, headers=headers).json()
    assert client.delete(f"/api/admin/terminals/{tmp['id']}", headers=headers).json()["deleted"] is True

    # 목록/상세 어디에도 키가 새지 않는다
    for row in client.get("/api/admin/terminals", headers=headers).json():
        assert "api_key" not in row and "api_key_hash" not in row


def test_terminal_key_rotation_invalidates_the_old_key(client):
    headers = _auth(client, "admin")
    merchant_id = client.get("/api/admin/merchants", headers=headers).json()[0]["id"]
    created = client.post("/api/admin/terminals", json={
        "merchant_id": merchant_id, "terminal_serial": "TERM-ROTATE-001",
    }, headers=headers).json()
    old_key = created["api_key"]

    new_key = client.post(f"/api/admin/terminals/{created['id']}/rotate-key",
                          headers=headers).json()["api_key"]
    assert new_key != old_key

    payload = {"terminal_id": "TERM-ROTATE-001", "merchant_id": merchant_id, "amount": 1000}
    assert client.post("/api/terminal/transactions", json=payload,
                       headers={"X-Terminal-Key": old_key}).status_code == 401
    assert client.post("/api/terminal/transactions", json=payload,
                       headers={"X-Terminal-Key": new_key}).status_code == 200


def test_terminal_auth_finds_the_device_by_fingerprint():
    """시리얼 없이도 전체 순회가 아니라 지문 한 방으로 찾아야 한다."""
    from app.models.terminal import TerminalDevice
    from app.services import terminal_auth

    db = _session()
    try:
        key = "term-api-key-001"  # 시드 단말기 키
        found = terminal_auth.find_terminal(db, key)
        assert found is not None and found.terminal_serial == "TERM001"
        assert found.api_key_fingerprint == terminal_auth.fingerprint(key)
        assert terminal_auth.find_terminal(db, "wrong-key") is None

        # 지문이 없는 레거시 행도 찾아내고 그때 지문을 채운다
        legacy = db.query(TerminalDevice).filter(
            TerminalDevice.terminal_serial == "TERM001").first()
        legacy.api_key_fingerprint = None
        db.commit()
        assert terminal_auth.find_terminal(db, key) is not None
        db.refresh(legacy)
        assert legacy.api_key_fingerprint == terminal_auth.fingerprint(key)
    finally:
        db.close()


# ─── 취소 거래 집계 제외 ─────────────────────────────────────

def test_cancelled_transactions_are_excluded_from_sales(client):
    admin_headers = _auth(client, "admin")
    merchant_id = client.get("/api/admin/merchants", headers=admin_headers).json()[0]["id"]

    terminal = client.post("/api/admin/terminals", json={
        "merchant_id": merchant_id, "terminal_serial": "TERM-CANCEL-001",
    }, headers=admin_headers).json()

    before = client.get("/api/admin/stats/landing", headers=admin_headers).json()
    txn = client.post("/api/terminal/transactions", json={
        "terminal_id": "TERM-CANCEL-001", "merchant_id": merchant_id,
        "amount": 77000, "approval_code": "CANCELME1",
    }, headers={"X-Terminal-Key": terminal["api_key"]}).json()

    after_paid = client.get("/api/admin/stats/landing", headers=admin_headers).json()
    assert after_paid["today_sales"] == before["today_sales"] + 77000

    cancelled = client.post(f"/api/terminal/transactions/{txn['id']}/cancel",
                            headers=admin_headers, json={"cancel_reason": "테스트 취소"})
    assert cancelled.status_code == 200

    after_cancel = client.get("/api/admin/stats/landing", headers=admin_headers).json()
    assert after_cancel["today_sales"] == before["today_sales"]
    assert after_cancel["total_volume"] == before["total_volume"]
    assert all(r["id"] != txn["id"] for r in after_cancel["recent_transactions"])

    # 단말기 목록의 거래 건수도 취소분을 세지 않는다
    row = client.get(f"/api/admin/terminals/{terminal['id']}", headers=admin_headers).json()
    assert row["transaction_count"] == 0


# ─── 로그인 실패 제한 ────────────────────────────────────────

def test_login_locks_out_after_repeated_failures(client):
    from app.services import login_guard

    login_guard.reset()
    try:
        for _ in range(5):
            bad = client.post("/api/auth/login",
                              json={"email": "owner@test.com", "password": "wrong-password"})
            assert bad.status_code == 401

        blocked = client.post("/api/auth/login",
                              json={"email": "owner@test.com", "password": "Test1234!"})
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

        # 다른 계정은 영향을 받지 않는다
        login_guard.reset()
        ok = client.post("/api/auth/login",
                         json={"email": "owner@test.com", "password": "Test1234!"})
        assert ok.status_code == 200
    finally:
        login_guard.reset()


# ─── ADMIN 의 원장 API 접근 ──────────────────────────────────

def test_admin_can_reach_owner_apis_with_merchant_id(client):
    admin_headers = _auth(client, "admin")
    merchant_id = client.get("/api/admin/merchants", headers=admin_headers).json()[0]["id"]

    # 대상을 지정하지 않으면 404 가 아니라 무엇이 빠졌는지 알려준다
    missing = client.get("/api/owner/settlement-breakdown", headers=admin_headers)
    assert missing.status_code == 400
    assert "merchant_id" in missing.json()["detail"]

    ok = client.get(f"/api/owner/settlement-breakdown?merchant_id={merchant_id}",
                    headers=admin_headers)
    assert ok.status_code == 200

    assert client.get(f"/api/owner/dashboard-stats?merchant_id={merchant_id}",
                      headers=admin_headers).status_code == 200
    assert client.get("/api/owner/settlements?merchant_id=999999",
                      headers=admin_headers).status_code == 404

    # 원장은 merchant_id 를 넘겨도 자기 매장만 본다
    owner_headers = _auth(client, "owner")
    mine = client.get("/api/owner/dashboard-stats?merchant_id=999999", headers=owner_headers)
    assert mine.status_code == 200


# ─── CRM staff_id 소속 검증 ──────────────────────────────────

def test_crm_rejects_staff_from_another_merchant(client):
    from app.models.merchant import Merchant
    from app.models.staff import Staff

    db = _session()
    try:
        mine = db.query(Merchant).first()
        other = Merchant(name="남의 미용실", owner_user_id=mine.owner_user_id)
        db.add(other)
        db.flush()
        outsider = Staff(merchant_id=other.id, name="남의 디자이너", staff_code="Z9")
        db.add(outsider)
        db.commit()
        outsider_id = outsider.id
        assert outsider_id not in {
            s.id for s in db.query(Staff).filter(Staff.merchant_id == mine.id).all()
        }
    finally:
        db.close()

    headers = _auth(client, "owner")
    blocked = client.post("/api/crm/customers",
                          json={"name": "홍길동", "assigned_staff_id": outsider_id},
                          headers=headers)
    assert blocked.status_code == 400
    assert "소속" in blocked.json()["detail"]

    created = client.post("/api/crm/customers", json={"name": "홍길동"}, headers=headers)
    assert created.status_code == 200
    customer_id = created.json()["id"]

    assert client.post("/api/crm/visits", json={
        "customer_id": customer_id, "staff_id": outsider_id, "amount": 10000,
    }, headers=headers).status_code == 400

    assert client.post("/api/crm/reservations", json={
        "customer_id": customer_id, "staff_id": outsider_id,
        "reserved_at": "2026-09-01 10:00",
    }, headers=headers).status_code == 400
