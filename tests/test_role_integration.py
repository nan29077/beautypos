"""계정별(ADMIN/SALES/OWNER/DESIGNER) 연동·격리 회귀 테스트.

전체 메뉴 점검의 2번 항목 "계정별 연동 검증"을 코드가 아니라 실제 요청으로 확인한다.
"""
import importlib
import os
import sys
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "integration.db"
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


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def second_store(client):
    """두 번째 원장/가맹점을 만들어 데이터 격리를 검증할 수 있게 한다."""
    registered = client.post("/api/auth/register", json={
        "email": "owner2@test.com", "password": "Test1234!", "name": "제2원장",
    })
    assert registered.status_code == 200
    owner2_token = registered.json()["access_token"]
    owner2_id = registered.json()["user"]["id"]

    created = client.post("/api/admin/merchants", json={
        "name": "제2미용실", "owner_user_id": owner2_id, "phone": "02-000-0000",
    }, headers=_auth(client, "admin"))
    assert created.status_code == 200
    return {"token": owner2_token, "user_id": owner2_id, "merchant_id": created.json()["id"]}


# ─── 1. 가맹점 등록 → 원장 로그인 흐름 ────────────────────────

def test_admin_registers_merchant_and_owner_can_log_in(client, second_store):
    """회원가입한 원장에게 관리자가 가맹점을 붙이면 원장 화면이 곧바로 열린다."""
    info = client.get("/api/owner/merchant-info", headers=_bearer(second_store["token"]))
    assert info.status_code == 200
    assert info.json()["name"] == "제2미용실"

    login = client.post("/api/auth/login", json={"email": "owner2@test.com", "password": "Test1234!"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "owner"


def test_merchant_owner_must_be_an_owner_account(client):
    """원장이 아닌 계정(영업/디자이너)에는 가맹점을 붙일 수 없어야 한다."""
    admin = _auth(client, "admin")
    sales_user_id = client.get("/api/auth/me", headers=_auth(client, "sales")).json()["id"]
    response = client.post("/api/admin/merchants", json={
        "name": "잘못된 소유자 가맹점", "owner_user_id": sales_user_id,
    }, headers=admin)
    assert response.status_code == 400


def test_one_owner_cannot_hold_two_merchants(client, second_store):
    """원장 조회는 첫 가맹점만 보므로 중복 소유를 애초에 막는다."""
    response = client.post("/api/admin/merchants", json={
        "name": "중복 소유 가맹점", "owner_user_id": second_store["user_id"],
    }, headers=_auth(client, "admin"))
    assert response.status_code == 400


# ─── 2. 관리자 정산 계산 → 원장 정산 내역 조회 ────────────────

def test_admin_settlement_shows_up_for_the_owner(client):
    owner = _auth(client, "owner")
    admin = _auth(client, "admin")
    merchant_id = client.get("/api/crm/me", headers=owner).json()["merchant_id"]

    today = date.today()
    start = (today - timedelta(days=60)).isoformat()
    created = client.post(
        f"/api/admin/settlements/calculate?merchant_id={merchant_id}"
        f"&period_start={start}&period_end={today.isoformat()}",
        headers=admin,
    )
    assert created.status_code == 200

    listed = client.get("/api/owner/settlements", headers=owner)
    assert listed.status_code == 200
    rows = listed.json()
    assert rows, "관리자가 계산한 정산이 원장 화면에도 보여야 한다"
    assert rows[0]["gross_amount"] == created.json()["gross_amount"]
    # 원장에게는 플랫폼/영업 몫이 아니라 본인 정산액이 보여야 한다.
    assert "net_amount" in rows[0]


def test_owner_settlements_are_isolated_between_stores(client, second_store):
    """다른 가맹점의 정산이 섞여 보이면 안 된다."""
    rows = client.get("/api/owner/settlements", headers=_bearer(second_store["token"])).json()
    assert rows == []


# ─── 3. 관리자 광고 승인/거절 → 원장 상태 반영 ────────────────

def test_ad_order_status_flows_from_admin_to_owner(client):
    admin = _auth(client, "admin")
    owner = _auth(client, "owner")

    orders = client.get("/api/admin/ad/orders", headers=admin).json()
    target = next(o for o in orders if o["status"] == "requested")

    moved = client.post(f"/api/admin/ad/orders/{target['id']}/status",
                        json={"status": "reviewing", "admin_memo": "검토 시작"}, headers=admin)
    assert moved.status_code == 200

    owner_view = client.get("/api/owner/ad/orders", headers=owner).json()
    mine = next(o for o in owner_view if o["id"] == target["id"])
    assert mine["status"] == "reviewing"
    assert mine["admin_memo"] == "검토 시작"

    # 요청됨 → 완료 처럼 단계를 건너뛰는 전이는 막는다.
    skipped = client.post(f"/api/admin/ad/orders/{target['id']}/status",
                          json={"status": "done"}, headers=admin)
    assert skipped.status_code == 409

    rejected = client.post(f"/api/admin/ad/orders/{target['id']}/status",
                           json={"status": "rejected"}, headers=admin)
    assert rejected.status_code == 200
    owner_view = client.get("/api/owner/ad/orders", headers=owner).json()
    assert next(o for o in owner_view if o["id"] == target["id"])["status"] == "rejected"


# ─── 4. 원장 데이터 격리 ──────────────────────────────────────

def test_owner_only_sees_their_own_store_data(client, second_store):
    owner2 = _bearer(second_store["token"])
    assert client.get("/api/owner/transactions", headers=owner2).json() == []
    assert client.get("/api/owner/staff", headers=owner2).json() == []
    assert client.get("/api/owner/ad/orders", headers=owner2).json() == []
    assert client.get("/api/owner/dashboard-stats", headers=owner2).json()["merchant_id"] \
        == second_store["merchant_id"]


def test_owner_cannot_touch_another_stores_staff(client, second_store):
    owner1 = _auth(client, "owner")
    staff = client.get("/api/owner/staff", headers=owner1).json()
    assert staff, "시드 매장에 직원이 있어야 한다"
    foreign_staff_id = staff[0]["id"]

    blocked = client.put(f"/api/owner/staff/{foreign_staff_id}", json={"is_active": False},
                         headers=_bearer(second_store["token"]))
    assert blocked.status_code == 404
    sales = client.get(f"/api/owner/staff/{foreign_staff_id}/sales",
                       headers=_bearer(second_store["token"]))
    assert sales.status_code == 404


def test_owner_cannot_reach_admin_or_sales_apis(client):
    owner = _auth(client, "owner")
    assert client.get("/api/admin/merchants", headers=owner).status_code == 403
    assert client.get("/api/admin/users", headers=owner).status_code == 403
    assert client.get("/api/sales/merchants", headers=owner).status_code == 403


# ─── 5. 영업 담당 가맹점 격리 ─────────────────────────────────

def test_sales_sees_only_assigned_merchants(client, second_store):
    sales = _auth(client, "sales")
    merchants = client.get("/api/sales/merchants", headers=sales).json()
    assert second_store["merchant_id"] not in [m["id"] for m in merchants]

    blocked = client.get(f"/api/sales/merchants/{second_store['merchant_id']}/stats", headers=sales)
    assert blocked.status_code == 403
    blocked = client.get(f"/api/sales/merchants/{second_store['merchant_id']}/breakdown", headers=sales)
    assert blocked.status_code == 403


# ─── 6. 디자이너 본인 실적만 ──────────────────────────────────

def test_designer_only_sees_their_own_sales(client):
    designer = _auth(client, "designer")
    from app.database import SessionLocal
    from app.models.staff import Staff
    from app.models.transaction import Transaction
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "designer@test.com").first()
        staff = db.query(Staff).filter(Staff.user_id == user.id).first()
        my_staff_id = staff.id
        other_ids = {
            t.staff_id for t in db.query(Transaction).all()
            if t.staff_id and t.staff_id != my_staff_id
        }
    finally:
        db.close()
    assert other_ids, "다른 디자이너 거래가 있어야 격리를 확인할 수 있다"

    stats = client.get("/api/designer/dashboard-stats", headers=designer).json()
    txns = client.get("/api/designer/transactions?range=all", headers=designer).json()
    assert stats["total_transactions"] == len(txns)

    settlement = client.get("/api/designer/settlement?range=all", headers=designer).json()
    assert settlement["gross"] == int(sum(t["amount"] for t in txns))

    # 디자이너는 원장/관리자 화면에 접근할 수 없다.
    assert client.get("/api/owner/transactions", headers=designer).status_code == 403
    assert client.get("/api/admin/stats/landing", headers=designer).status_code == 403


# ─── 7. 인증/권한 ─────────────────────────────────────────────

def test_missing_forged_and_expired_tokens_are_rejected(client):
    from app.auth.jwt_handler import create_access_token

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=_bearer("not-a-token")).status_code == 401
    # 서명이 다른 토큰 (위조)
    from jose import jwt
    forged = jwt.encode({"sub": "1", "type": "access"}, "another-secret", algorithm="HS256")
    assert client.get("/api/auth/me", headers=_bearer(forged)).status_code == 401
    # 만료된 토큰
    expired = create_access_token({"sub": "1", "role": "admin"}, expires_delta=timedelta(minutes=-5))
    assert client.get("/api/auth/me", headers=_bearer(expired)).status_code == 401
    # refresh 토큰으로는 API 를 호출할 수 없다.
    refresh = client.post("/api/auth/test-login?role=admin").json()["refresh_token"]
    assert client.get("/api/auth/me", headers=_bearer(refresh)).status_code == 401


def test_deactivated_user_loses_access_immediately(client):
    admin = _auth(client, "admin")
    users = client.get("/api/admin/users?role=designer", headers=admin).json()
    victim = next(u for u in users if u["email"] == "designer2@test.com")
    token = None

    from app.auth.jwt_handler import create_access_token
    token = create_access_token({"sub": str(victim["id"]), "role": "designer"})
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 200

    client.put(f"/api/admin/users/{victim['id']}/toggle-active", headers=admin)
    try:
        assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401
    finally:
        client.put(f"/api/admin/users/{victim['id']}/toggle-active", headers=admin)


# ─── 8. 단말기 인증 ───────────────────────────────────────────

def test_terminal_key_authentication(client):
    owner = _auth(client, "owner")
    merchant_id = client.get("/api/crm/me", headers=owner).json()["merchant_id"]
    payload = {"merchant_id": merchant_id, "amount": 42000, "staff_code": "1",
               "card_brand": "VISA", "approval_code": "APR-TERMTEST"}

    assert client.post("/api/terminal/transactions", json=payload).status_code == 422
    assert client.post("/api/terminal/transactions", json=payload,
                       headers={"X-Terminal-Key": "wrong-key"}).status_code == 401

    ok = client.post("/api/terminal/transactions", json=payload,
                     headers={"X-Terminal-Key": "term-api-key-001"})
    assert ok.status_code == 200
    assert ok.json()["assigned_to"] == "staff"

    # 다른 가맹점 거래를 밀어 넣으려 하면 거부된다.
    foreign = dict(payload, merchant_id=999999)
    assert client.post("/api/terminal/transactions", json=foreign,
                       headers={"X-Terminal-Key": "term-api-key-001"}).status_code == 400


# ─── 9. 원장 출금요청 ─────────────────────────────────────────

def test_owner_can_request_a_payout_and_admin_reviews_it(client, second_store):
    owner = _auth(client, "owner")
    admin = _auth(client, "admin")

    created = client.post("/api/owner/payout-requests",
                          json={"amount": 150000, "bank_info": "국민 123-456", "memo": "정산 출금"},
                          headers=owner)
    assert created.status_code == 200
    payout_id = created.json()["id"]

    mine = client.get("/api/owner/payout-requests", headers=owner).json()
    assert [r["id"] for r in mine] == [payout_id]

    # 다른 원장의 출금요청은 보이지 않는다.
    assert client.get("/api/owner/payout-requests",
                      headers=_bearer(second_store["token"])).json() == []

    admin_view = client.get("/api/admin/payout-requests", headers=admin).json()
    row = next(r for r in admin_view if r["id"] == payout_id)
    assert row["role"] == "owner"

    approved = client.post(f"/api/admin/payout-requests/{payout_id}/approve", headers=admin)
    assert approved.status_code == 200
    assert client.get("/api/owner/payout-requests", headers=owner).json()[0]["status"] == "approved"


def test_payout_amount_must_be_positive(client):
    owner = _auth(client, "owner")
    assert client.post("/api/owner/payout-requests", json={"amount": 0}, headers=owner).status_code == 422
    assert client.post("/api/sales/payout-requests", json={"amount": -1},
                       headers=_auth(client, "sales")).status_code == 422
