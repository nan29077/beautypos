"""ADPAY FastAPI application."""
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.admin_routes import landing_stats
from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.crm_routes import router as crm_router
from app.api.designer_routes import router as designer_router
from app.api.owner_routes import router as owner_router
from app.api.sales_routes import router as sales_router
from app.api.terminal_routes import router as terminal_router
from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.merchant import Merchant
from app.models.receipt_review import ReceiptReview, ReceiptReviewConfig
from app.models.system_config import (
    AD_BLOG_ENABLED,
    AD_ORDER_MGMT_ENABLED,
    AD_PLACE_TRAFFIC_ENABLED,
    SystemConfig,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.init_db import init_db
    from app.services import rank_scheduler

    init_db()
    # 매일 오후 2시(KST) 플레이스 순위 자동 수집
    rank_scheduler.start(_app)
    try:
        yield
    finally:
        await rank_scheduler.stop(_app)


app = FastAPI(
    title="ADPAY",
    description="오프라인 PG, 직원별 매출, 광고 분석 및 주문 관리 플랫폼",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(terminal_router)
app.include_router(owner_router)
app.include_router(sales_router)
app.include_router(designer_router)
app.include_router(crm_router)

app.get("/api/stats/landing", tags=["public"])(landing_stats)


@app.get("/api/public/review/{token}")
def get_review_page_data(token: str, db: Session = Depends(get_db)):
    """Return the merchant information needed by the public review page."""
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.token == token,
        ReceiptReviewConfig.is_active == True,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="유효하지 않은 링크입니다")
    merchant = db.query(Merchant).filter(Merchant.id == config.merchant_id).first()
    return {
        "merchant_name": merchant.name if merchant else "매장",
        "welcome_message": config.welcome_message,
        "place_url": config.place_url,
        "category": merchant.category if merchant else None,
        "display_category": merchant.display_category if merchant else None,
    }


@app.post("/api/public/review/{token}/submit")
def submit_receipt_review(
    token: str,
    customer_name: Optional[str] = Form(None),
    customer_phone: Optional[str] = Form(None),
    receipt_image_url: Optional[str] = Form(None),
    memo: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a receipt review submitted from the public QR/NFC page."""
    config = db.query(ReceiptReviewConfig).filter(
        ReceiptReviewConfig.token == token,
        ReceiptReviewConfig.is_active == True,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="유효하지 않은 링크입니다")

    review = ReceiptReview(
        merchant_id=config.merchant_id,
        config_id=config.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        receipt_image_url=receipt_image_url,
        memo=memo,
        status="pending",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return {
        "ok": True,
        "review_id": review.id,
        "place_url": config.place_url,
        "message": "영수증이 제출되었습니다. 감사합니다.",
    }


static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/static/landing/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "adpay"}


@app.get("/api/feature-flags")
def get_feature_flags(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Return authenticated advertising feature flags."""
    master_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == AD_ORDER_MGMT_ENABLED).first()
    blog_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == AD_BLOG_ENABLED).first()
    place_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == AD_PLACE_TRAFFIC_ENABLED).first()
    return {
        "ad_order_mgmt_enabled": master_cfg.is_enabled if master_cfg else False,
        "ad_blog_enabled": blog_cfg.is_enabled if blog_cfg else False,
        "ad_place_traffic_enabled": place_cfg.is_enabled if place_cfg else False,
    }


@app.get("/favicon.ico")
def favicon():
    from fastapi.responses import FileResponse, Response

    favicon_path = os.path.join(static_dir, "favicon.ico")
    if os.path.isfile(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    return Response(status_code=204)
