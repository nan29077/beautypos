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


def test_legacy_owner_mobile_page_redirects_to_full_dashboard():
    legacy_mobile = read_static("mobile/mobile.html")

    assert "window.location.replace('/static/dashboard.html?view=mobile')" in legacy_mobile
