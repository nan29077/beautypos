"""Owner (원장님) API package.

Combines the modularized owner sub-routers into a single `router` with the
same prefix/tags as the original monolithic app/api/owner_routes.py:
    - dashboard_routes: transactions, calendar, settlement breakdown/list, dashboard stats
    - staff_routes: staff & designer account management
    - ad_owner_routes: place/competitor analysis, ad orders, ad executions
    - review_routes: receipt review management
    - misc_routes: payout requests, merchant info, affiliate malls
"""
from fastapi import APIRouter

from app.api.owner.dashboard_routes import router as dashboard_router
from app.api.owner.staff_routes import router as staff_router
from app.api.owner.ad_owner_routes import router as ad_router
from app.api.owner.review_routes import router as review_router
from app.api.owner.misc_routes import router as misc_router

router = APIRouter(prefix="/api/owner", tags=["owner"])
router.include_router(dashboard_router)
router.include_router(staff_router)
router.include_router(ad_router)
router.include_router(review_router)
router.include_router(misc_router)
