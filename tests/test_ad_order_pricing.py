"""광고 단가 설정과 주문 예산 계산 회귀 테스트."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "ad-pricing.db"
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


def _pricing_payload():
    return {
        "blog_unit_price": 45000,
        "place_traffic_unit_price": 700,
        "shorts_distribution_unit_price": 18000,
        "shorts_duration_prices": {
            "15s": 12000,
            "30s": 17000,
            "60s": 27000,
            "90s": 39000,
        },
    }


def test_admin_can_set_pricing_and_owner_can_read_it(client):
    enabled = client.put(
        "/api/admin/ad-feature-flags"
        "?ad_order_mgmt_enabled=true"
        "&ad_blog_enabled=true"
        "&ad_place_traffic_enabled=true"
        "&ad_shorts_enabled=true",
        json={},
        headers=_auth(client, "admin"),
    )
    assert enabled.status_code == 200

    saved = client.put(
        "/api/admin/ad-pricing",
        json=_pricing_payload(),
        headers=_auth(client, "admin"),
    )
    assert saved.status_code == 200
    assert saved.json()["blog_unit_price"] == 45000

    owner_view = client.get(
        "/api/owner/ad/pricing",
        headers=_auth(client, "owner"),
    )
    assert owner_view.status_code == 200
    assert owner_view.json() == _pricing_payload()


def test_blog_order_saves_quantity_and_server_calculated_budget(client):
    response = client.post(
        "/api/owner/ad/blog-orders",
        json={
            "campaign_name": "여름 헤어 캠페인",
            "main_keywords": ["강남 미용실"],
            "order_count": 10,
            "unit_price": 1,
        },
        headers=_auth(client, "owner"),
    )
    assert response.status_code == 200
    assert response.json()["estimate"] == {
        "order_count": 10,
        "unit_price": 45000,
        "total_cost": 450000,
    }

    orders = client.get(
        "/api/owner/ad/orders",
        headers=_auth(client, "owner"),
    ).json()
    detail = next(row["blog_detail"] for row in orders if row["type"] == "blog")
    assert detail["order_count"] == 10
    assert float(detail["unit_price"]) == 45000
    assert float(detail["est_total_cost"]) == 450000


def test_place_order_saves_quantity_and_server_calculated_budget(client):
    response = client.post(
        "/api/owner/ad/place-traffic-orders",
        json={
            "place_name_or_id": "애드페이 강남점",
            "search_keywords": ["강남 미용실"],
            "order_count": 100,
            "unit_price": 1,
        },
        headers=_auth(client, "owner"),
    )
    assert response.status_code == 200
    assert response.json()["estimate"] == {
        "order_count": 100,
        "unit_price": 700,
        "total_cost": 70000,
    }


def test_shorts_options_use_admin_pricing(client):
    options = client.get(
        "/api/owner/ad/shorts-options",
        headers=_auth(client, "owner"),
    )
    assert options.status_code == 200
    body = options.json()
    assert body["distribution_unit_price"] == 18000
    assert {
        row["code"]: row["unit_price"] for row in body["duration_tiers"]
    } == _pricing_payload()["shorts_duration_prices"]
