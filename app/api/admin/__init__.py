"""Admin API routes package — accessible only by ADMIN role.

Covers: merchants CRUD, PG config, transactions, payout requests,
        ad orders management, metrics, fee policies, sales assignments, landing stats.

원본 단일 파일 app/api/admin_routes.py 를 도메인별 서브 라우터로 분리했다:
- merchant_routes.py — 가맹점 CRUD, 단말기, 사용자 관리, 제휴중개몰
- pg_routes.py — PG config, pg-providers, PG 테스트
- settlement_routes.py — 정산/수수료 관련 (payout 제외)
- ad_routes.py — 광고 주문/지표/단가/플랜/집행 관련
- payout_routes.py — 페이아웃(출금) 요청 관련
- misc_routes.py — 대시보드 통계, AI 설정 등
"""
from fastapi import APIRouter

from app.api.admin import (
    merchant_routes, pg_routes, settlement_routes, ad_routes, payout_routes, misc_routes,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(merchant_routes.router)
router.include_router(pg_routes.router)
router.include_router(settlement_routes.router)
router.include_router(ad_routes.router)
router.include_router(payout_routes.router)
router.include_router(misc_routes.router)
