"""전체 메뉴 점검에서 발견된 결함에 대한 회귀 테스트."""
import importlib
import os
import sys
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "audit.db"
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


def test_admin_dashboard_stats_require_authentication(client):
    """매출 총액·최근 결제가 담긴 통계는 인증 없이 열려 있으면 안 된다."""
    assert client.get("/api/admin/stats/landing").status_code == 401
    assert client.get("/api/stats/landing").status_code == 404
    assert client.get("/api/admin/stats/landing", headers=_auth(client, "admin")).status_code == 200
    assert client.get("/api/admin/stats/landing", headers=_auth(client, "owner")).status_code == 403


def test_terminal_list_is_available_and_hides_api_key(client):
    """'단말기 관리' 메뉴가 실제 데이터를 받을 수 있어야 한다."""
    response = client.get("/api/admin/terminals", headers=_auth(client, "admin"))
    assert response.status_code == 200
    terminals = response.json()
    assert terminals, "시드 단말기가 조회되어야 한다"

    row = terminals[0]
    assert row["terminal_serial"] == "TERM001"
    assert row["merchant_name"]
    assert row["transaction_count"] >= 0
    # API 키(및 해시)는 어떤 형태로도 노출되지 않는다.
    assert not any("api_key" in key for key in row)

    assert client.get("/api/admin/terminals", headers=_auth(client, "sales")).status_code == 403


def test_settlement_includes_the_final_day_of_the_period(client):
    """종료일을 날짜로만 넘겨도 그날 거래가 정산에서 빠지지 않아야 한다."""
    admin = _auth(client, "admin")
    merchant_id = client.get("/api/crm/me", headers=_auth(client, "owner")).json()["merchant_id"]

    # 종료일 당일 낮에 발생한 거래를 하나 만든다.
    from app.database import SessionLocal
    from app.models.terminal import TerminalDevice
    from app.models.transaction import Transaction

    today = date.today()
    db = SessionLocal()
    try:
        terminal = db.query(TerminalDevice).filter(TerminalDevice.merchant_id == merchant_id).first()
        db.add(Transaction(
            merchant_id=merchant_id,
            terminal_id=terminal.id,
            amount=33000,
            approval_code="APR-LASTDAY",
            approved_at=datetime.combine(today, datetime.min.time()) + timedelta(hours=13),
            created_at=datetime.combine(today, datetime.min.time()) + timedelta(hours=13),
        ))
        db.commit()
    finally:
        db.close()

    result = client.post(
        f"/api/admin/settlements/calculate?merchant_id={merchant_id}"
        f"&period_start={today.isoformat()}&period_end={today.isoformat()}",
        headers=admin,
    )
    assert result.status_code == 200
    body = result.json()
    assert body["transactions_count"] >= 1
    assert body["gross_amount"] >= 33000
    assert body["merchant_name"]

    listed = client.get("/api/admin/settlements", headers=admin)
    assert listed.status_code == 200
    assert listed.json()[0]["merchant_name"] == body["merchant_name"]


def test_settlement_rejects_unknown_merchant(client):
    today = date.today().isoformat()
    response = client.post(
        f"/api/admin/settlements/calculate?merchant_id=999999"
        f"&period_start={today}&period_end={today}",
        headers=_auth(client, "admin"),
    )
    assert response.status_code == 404


def test_sales_views_use_the_admin_global_fee_rate(client):
    """최고관리자가 정한 전역 PG 수수료가 영업 화면 계산에도 동일하게 적용된다."""
    from app.database import SessionLocal
    from app.models.settlement import FeePolicy

    admin = _auth(client, "admin")
    configured_pg_rate = 0.027
    configured_pg_rate_with_vat = configured_pg_rate * 1.1
    saved = client.put(
        "/api/admin/fee-settings",
        headers=admin,
        json={
            "merchant_fee_rate": 0.05,
            "pg_fee_rate": configured_pg_rate,
            "sales_commission_rate": 0.01,
        },
    )
    assert saved.status_code == 200

    sales = _auth(client, "sales")
    merchants = client.get("/api/sales/merchants", headers=sales).json()
    assert merchants, "시드 영업관리자에게 배정된 가맹점이 있어야 한다"
    merchant_id = merchants[0]["id"]

    db = SessionLocal()
    try:
        policy = db.query(FeePolicy).filter(FeePolicy.merchant_id == merchant_id).first()
        if policy:
            db.delete(policy)
            db.commit()
    finally:
        db.close()

    stats = client.get(f"/api/sales/merchants/{merchant_id}/stats?range=all", headers=sales).json()
    breakdown = client.get(
        f"/api/sales/merchants/{merchant_id}/breakdown?range=all", headers=sales
    ).json()

    assert breakdown["pg_fee_rate"] == configured_pg_rate
    assert breakdown["pg_fee_rate_with_vat"] == pytest.approx(configured_pg_rate_with_vat)
    assert stats["pg_fee"] == pytest.approx(
        stats["gross_amount"] * configured_pg_rate_with_vat,
        abs=1.0,
    )


def test_deactivated_sales_assignment_revokes_access(client):
    """배정을 비활성화하면 담당 가맹점 목록과 통계에서 즉시 빠져야 한다."""
    from app.database import SessionLocal
    from app.models.settlement import MerchantSalesAssignment

    sales = _auth(client, "sales")
    merchants = client.get("/api/sales/merchants", headers=sales).json()
    merchant_id = merchants[0]["id"]

    db = SessionLocal()
    try:
        assignment = db.query(MerchantSalesAssignment).filter(
            MerchantSalesAssignment.merchant_id == merchant_id,
        ).first()
        assignment_id = assignment.id
        assignment.is_active = False
        db.commit()
    finally:
        db.close()

    try:
        assert client.get("/api/sales/merchants", headers=sales).json() == []
        assert client.get(
            f"/api/sales/merchants/{merchant_id}/stats?range=all", headers=sales
        ).status_code == 403
        assert client.get("/api/sales/dashboard-stats", headers=sales).json()["merchant_count"] == 0
    finally:
        db = SessionLocal()
        try:
            restored = db.query(MerchantSalesAssignment).filter(
                MerchantSalesAssignment.id == assignment_id,
            ).first()
            restored.is_active = True
            db.commit()
        finally:
            db.close()
