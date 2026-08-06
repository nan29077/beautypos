"""미용실 CRM (고객관리프로그램) API 패키지.

원장(OWNER): 본인 미용실 전체 데이터.
디자이너(DESIGNER): 본인 소속 미용실 데이터 (기본은 본인 고객/실적 위주, scope=all 로 전체 조회 가능).
관리자(ADMIN): 지원용.

모든 데이터는 merchant_id 로 격리된다.

서브 라우터 구성:
- customer_routes  : 고객 CRUD, 타임라인, 방문 기록, 시술 메뉴, 예약
- analytics_routes  : 대시보드 통계, 분석, 디자이너별 실적
- campaign_routes   : 포인트, 재방문/생일 타겟, 쿠폰, 메시지 발송
"""
from fastapi import APIRouter

from app.api.crm.customer_routes import router as customer_router
from app.api.crm.analytics_routes import router as analytics_router
from app.api.crm.campaign_routes import router as campaign_router

router = APIRouter(prefix="/api/crm", tags=["crm"])
router.include_router(customer_router)
router.include_router(analytics_router)
router.include_router(campaign_router)

__all__ = ["router"]
