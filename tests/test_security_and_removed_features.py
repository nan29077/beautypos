import importlib
import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
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


def test_public_registration_cannot_choose_privileged_role(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "escalation-attempt@example.com",
            "password": "SafePass123!",
            "name": "권한테스트",
            "role": "admin",
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "owner"


@pytest.mark.parametrize("role", ["admin", "sales", "owner", "designer"])
def test_development_test_login_supports_expected_roles(client, role):
    response = client.post(f"/api/auth/test-login?role={role}")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == role


def test_removed_role_and_routes_are_unavailable(client):
    assert client.post("/api/auth/test-login?role=landlord").status_code == 400
    route_paths = {route.path for route in client.app.routes}
    assert not any("landlord" in path for path in route_paths)
    assert not any("banggut" in path for path in route_paths)
    assert not any("rent-qr" in path for path in route_paths)
    assert not any("luxury" in path for path in route_paths)


def test_login_page_exposes_all_safe_development_shortcuts(client):
    html = client.get("/static/login.html").text
    for role in ("admin", "sales", "owner", "designer"):
        assert f"testLogin('{role}')" in html
    assert "regRole" not in html
    assert "testLogin('landlord')" not in html


def test_insecure_production_defaults_are_rejected():
    from app.config import Settings

    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEV_MODE=False,
            JWT_SECRET_KEY="change-me",
        )


def _auth(client, role):
    token = client.post(f"/api/auth/test-login?role={role}").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_owner_sales_ads_and_crm_flows(client):
    owner = _auth(client, "owner")
    admin = _auth(client, "admin")
    designer = _auth(client, "designer")

    # Daily payments, staff sales and settlement distribution remain callable.
    staff = client.get("/api/owner/staff", headers=owner)
    assert staff.status_code == 200 and staff.json()
    staff_id = staff.json()[0]["id"]
    assert client.get(f"/api/owner/staff/{staff_id}/sales?range=month", headers=owner).status_code == 200
    assert client.get("/api/owner/settlement-breakdown?range=month", headers=owner).status_code == 200
    today = date.today()
    assert client.get(
        f"/api/owner/calendar-monthly?year={today.year}&month={today.month}", headers=owner
    ).status_code == 200
    assert client.get(f"/api/owner/calendar-daily?date={today.isoformat()}", headers=owner).status_code == 200

    # API-level feature flags cannot be bypassed.
    flags_url = (
        "/api/admin/ad-feature-flags?"
        "ad_order_mgmt_enabled=false&ad_blog_enabled=false&ad_place_traffic_enabled=false"
    )
    assert client.put(flags_url, headers=admin).status_code == 200
    blog_payload = {
        "campaign_name": "여름 헤어 캠페인",
        "links": [],
        "main_keywords": ["강남 미용실"],
        "hashtags": ["헤어"],
    }
    assert client.post("/api/owner/ad/blog-orders", json=blog_payload, headers=owner).status_code == 403

    flags_url = (
        "/api/admin/ad-feature-flags?"
        "ad_order_mgmt_enabled=true&ad_blog_enabled=true&ad_place_traffic_enabled=true"
    )
    assert client.put(flags_url, headers=admin).status_code == 200
    created = client.post("/api/owner/ad/blog-orders", json=blog_payload, headers=owner)
    assert created.status_code == 200
    order_id = created.json()["id"]

    # Orders must follow the review -> running -> done workflow.
    assert client.post(
        f"/api/admin/ad/orders/{order_id}/status",
        json={"status": "done"},
        headers=admin,
    ).status_code == 409
    for status in ("reviewing", "running", "done"):
        response = client.post(
            f"/api/admin/ad/orders/{order_id}/status",
            json={"status": status},
            headers=admin,
        )
        assert response.status_code == 200

    # Owner registers both sides; admin records same-keyword measurements.
    own_url = "https://m.place.naver.com/hairshop/beautypos-test"
    competitor_url = "https://m.place.naver.com/hairshop/beautypos-rival"
    assert client.post(
        "/api/owner/ad/place-profiles",
        json={
            "place_url": own_url,
            "nickname": "테스트 우리매장",
            "analysis_keyword": "강남 미용실",
        },
        headers=owner,
    ).status_code == 200
    assert client.post(
        "/api/owner/ad/competitors",
        json={"competitor_place_url": competitor_url, "memo": "테스트 경쟁매장"},
        headers=owner,
    ).status_code == 200

    merchant_id = client.get("/api/crm/me", headers=owner).json()["merchant_id"]
    targets = client.get(
        f"/api/admin/ad/analysis-targets?merchant_id={merchant_id}", headers=admin
    )
    assert targets.status_code == 200
    assert {own_url, competitor_url}.issubset({row["place_url"] for row in targets.json()["targets"]})

    for place_url, blog, visitor, rank in (
        (own_url, 120, 240, 3),
        (competitor_url, 90, 180, 7),
    ):
        payload = {
            "merchant_id": merchant_id,
            "place_url": place_url,
            "date": today.isoformat(),
            "blog_review_count": blog,
            "visitor_review_count": visitor,
            "place_rank": rank,
            "search_keyword": "강남 미용실",
        }
        metric = client.post("/api/admin/ad/metrics", json=payload, headers=admin)
        assert metric.status_code == 200 and metric.json()["updated"] is False
        payload["blog_review_count"] += 1
        upsert = client.post("/api/admin/ad/metrics", json=payload, headers=admin)
        assert upsert.status_code == 200 and upsert.json()["updated"] is True

    summary = client.get("/api/owner/ad/analysis/summary?range=month", headers=owner)
    assert summary.status_code == 200
    data = summary.json()
    assert data["analysis_keyword"] == "강남 미용실"
    assert data["data_status"]["needs_admin_action"] is False
    assert data["comparison"]["my_latest_rank"] == 3
    assert data["comparison"]["comp_latest_rank"] == 7

    # Designers can read the common service menu but cannot alter store-wide prices.
    services = client.get("/api/crm/services", headers=designer)
    assert services.status_code == 200
    denied = client.post(
        "/api/crm/services",
        json={"name": "권한 우회 시술", "price": 1000, "duration_min": 10},
        headers=designer,
    )
    assert denied.status_code == 403


def test_crm_navigation_is_limited_to_requested_features(client):
    js = client.get("/static/js/dashboard.js").text
    expected = ("dashboard", "customers", "staff", "services", "messages")
    for tab in expected:
        assert f"{{id:'{tab}'" in js
    crm_tabs = js[js.index("const tabs=[", js.index("async function loadCRM")):]
    crm_tabs = crm_tabs[:crm_tabs.index("];")]
    for removed in ("reservations", "analytics", "marketing"):
        assert f"{{id:'{removed}'" not in crm_tabs
