from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_static(relative_path: str) -> str:
    return (PROJECT_ROOT / "static" / relative_path).read_text(encoding="utf-8")


def test_dashboard_contains_role_specific_mobile_shell():
    dashboard = read_static("dashboard.html")
    script = read_static("js/dashboard.js")

    assert 'id="roleMobileHeader"' in dashboard
    assert 'id="mobileBottomNav"' in dashboard
    assert 'id="mobileMenuSheet"' in dashboard
    assert "['owner', 'designer'].includes(currentUser.role)" in script
    assert "currentUser.role === 'owner'" in script
    assert "'designer-settlement'" in script


def test_mobile_styles_include_touch_and_safe_area_support():
    dashboard = read_static("dashboard.html")
    styles = read_static("css/style.css")

    assert "viewport-fit=cover" in dashboard
    assert "body.role-mobile-ui" in styles
    assert "env(safe-area-inset-bottom)" in styles
    assert "min-height: 44px" in styles
    assert ".mobile-card-table" in styles


def test_admin_and_sales_get_a_mobile_layer_of_their_own():
    """최고관리자·영업관리자는 사이드바 구조를 유지한 채 내용만 모바일 최적화한다."""
    script = read_static("js/dashboard.js")
    styles = read_static("css/style.css")

    assert "['admin', 'sales'].includes(currentUser.role)" in script
    assert "classList.toggle('admin-mobile-ui', isAdminMobile())" in script
    # 표 카드 전환은 두 역할군 모두에 적용된다.
    assert "if (!container || (!isRoleMobile() && !isAdminMobile())) return;" in script

    assert "body.admin-mobile-ui .mobile-card-table" in styles
    assert "body.admin-mobile-ui .modal-content" in styles
    assert "body.sidebar-open { overflow: hidden; }" in styles


def test_sidebar_breakpoint_matches_the_hamburger_breakpoint():
    """768px 에서 사이드바와 햄버거가 동시에 사라지는 사각지대가 없어야 한다."""
    dashboard = read_static("dashboard.html")
    styles = read_static("css/style.css")

    # 햄버거는 부트스트랩 d-md-none (>= 768px 에서 숨김)
    assert "d-md-none mobile-header desktop-role-mobile-header" in dashboard
    # 따라서 사이드바를 화면 밖으로 미는 미디어쿼리도 767.98px 이어야 한다.
    assert "@media (max-width: 768px)" not in styles
    assert ".sidebar { transform: translateX(-100%); }" in styles


def test_modal_tables_are_also_converted_to_cards():
    """모달은 #pageContent 밖이라 별도 감시가 없으면 표가 그대로 남는다."""
    script = read_static("js/dashboard.js")

    assert "document.addEventListener('shown.bs.modal'" in script
    assert "document.addEventListener('hidden.bs.modal'" in script
    assert "mobileModalObserver" in script


def test_owner_settlement_and_payout_pages_are_reachable_on_mobile():
    script = read_static("js/dashboard.js")

    assert "'owner-settlements': ['정산 내역'" in script
    assert "'owner-payouts': ['출금 요청'" in script
    assert "case 'owner-settlements':" in script
    assert "case 'owner-payouts':" in script
    assert "'owner-settlements', 'owner-payouts'" in script


def test_dashboard_does_not_shadow_the_shared_api_helpers():
    """api.js 의 apiPost/apiDelete 를 덮으면 401 자동 로그아웃이 사라진다."""
    script = read_static("js/dashboard.js")

    assert "async function apiPost(url, data)" not in script
    assert "async function apiDelete(url)" not in script


def test_legacy_owner_mobile_page_redirects_to_full_dashboard():
    legacy_mobile = read_static("mobile/mobile.html")

    assert "window.location.replace('/static/dashboard.html?view=mobile')" in legacy_mobile
