"""하위 호환 shim.

실제 CRM 라우터 구현은 app/api/crm/ 패키지(customer_routes.py, analytics_routes.py,
campaign_routes.py, _helpers.py)로 이동되었다. app/main.py 를 비롯해 기존에
`from app.api.crm_routes import router` 로 임포트하던 코드가 그대로 동작하도록
router 심볼만 재노출한다.
"""
from app.api.crm import router  # noqa: F401
