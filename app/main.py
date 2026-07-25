"""
ADPAY — Main FastAPI Application
"""
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
import logging
import os

from app.api.auth_routes import router as auth_router
from app.api.admin_routes import router as admin_router
from app.api.terminal_routes import router as terminal_router
from app.api.owner_routes import router as owner_router
from app.api.sales_routes import router as sales_router
from app.api.designer_routes import router as designer_router
from app.api.landlord_routes import router as landlord_router
from app.api.crm_routes import router as crm_router
from app.database import get_db
from app.models.receipt_review import ReceiptReviewConfig, ReceiptReview
from app.models.merchant import Merchant
from app.models.landlord import Tenant, RentPayment, RentPaymentStatus, RentPaymentMethod, PROPERTY_TYPE_KR
from app.models.system_config import SystemConfig, AD_ORDER_MGMT_ENABLED, AD_BLOG_ENABLED, AD_PLACE_TRAFFIC_ENABLED
from app.auth.dependencies import get_current_user

# Also expose landing stats publicly
from app.api.admin_routes import landing_stats

app = FastAPI(
    title="ADPAY",
    description="오프라인 PG + 직원별 매출 + 광고/분석/주문 관리 플랫폼",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(terminal_router)
app.include_router(owner_router)
app.include_router(sales_router)
app.include_router(designer_router)
app.include_router(landlord_router)
app.include_router(crm_router)

# Public stats endpoint (no auth)
app.get("/api/stats/landing", tags=["public"])(landing_stats)


@app.on_event("startup")
def _run_init_db():
    from app.init_db import init_db
    init_db()


# ─── Public Receipt Review API (no auth required) ──────────

@app.get("/api/public/review/{token}")
def get_review_page_data(token: str, db: Session = Depends(get_db)):
    """QR/NFC 스캔 시 매장 정보 조회 (인증 불필요)"""
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
    """고객이 영수증 리뷰를 제출 (인증 불필요)"""
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
        "message": "영수증이 제출되었습니다. 감사합니다!",
    }


# Mount static files (HTML/CSS/JS)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/")
def root():
    """Redirect to landing page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/landing/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "adpay"}


@app.get("/api/feature-flags")
def get_feature_flags(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """인증된 사용자가 광고 기능 ON/OFF 상태를 조회"""
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
    """Serve favicon from static directory."""
    from fastapi.responses import FileResponse
    favicon_path = os.path.join(static_dir, "favicon.ico")
    if os.path.isfile(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    from fastapi.responses import Response
    return Response(status_code=204)


# ─── Public Rent QR Payment API (no auth) ────────────────

@app.get("/api/public/rent-qr/{token}")
def get_rent_qr_data(token: str, db: Session = Depends(get_db)):
    """QR코드 스캔 시 임차인 정보 조회 (JSON)"""
    tenant = db.query(Tenant).filter(Tenant.qr_token == token, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="유효하지 않은 QR코드입니다")
    from app.models.landlord import LandlordProfile
    from app.models.user import User as UserModel
    landlord = db.query(UserModel).filter(UserModel.id == tenant.landlord_user_id).first()
    profile = db.query(LandlordProfile).filter(LandlordProfile.user_id == tenant.landlord_user_id).first()
    return {
        "tenant_name": tenant.name,
        "property_name": tenant.property_name,
        "unit_number": tenant.unit_number,
        "property_type_kr": PROPERTY_TYPE_KR.get(tenant.property_type.value, "기타"),
        "monthly_rent": tenant.monthly_rent,
        "rent_due_day": tenant.rent_due_day,
        "landlord_name": landlord.name if landlord else "-",
        "building_name": profile.building_name if profile else "-",
        "is_recurring": tenant.is_recurring,
    }


@app.get("/pay/{token}")
def rent_payment_page(token: str, db: Session = Depends(get_db)):
    """QR코드 스캔 시 결제 HTML 페이지"""
    from fastapi.responses import HTMLResponse
    tenant = db.query(Tenant).filter(Tenant.qr_token == token, Tenant.is_active == True).first()
    if not tenant:
        return HTMLResponse(content="""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>방긋페이</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Apple SD Gothic Neo',sans-serif;background:#f5f5f5;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}.error{text-align:center;color:#666}.error i{font-size:4rem;color:#ddd;margin-bottom:1rem;display:block}</style><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css"></head><body><div class="error"><i class="fas fa-exclamation-triangle"></i><h2>유효하지 않은 QR코드</h2><p style="margin-top:8px;color:#999">만료되었거나 잘못된 QR코드입니다.</p></div></body></html>""", status_code=404)

    from app.models.landlord import LandlordProfile
    from app.models.user import User as UserModel
    landlord = db.query(UserModel).filter(UserModel.id == tenant.landlord_user_id).first()
    profile = db.query(LandlordProfile).filter(LandlordProfile.user_id == tenant.landlord_user_id).first()
    building = profile.building_name if profile else ""
    landlord_name = landlord.name if landlord else "-"
    rent_formatted = f"{int(tenant.monthly_rent):,}"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
    <title>방긋페이 - 월세 결제</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css">
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;background:linear-gradient(180deg,#fff5eb 0%,#fff 40%);min-height:100vh;padding:0}}
        .pay-container{{max-width:440px;margin:0 auto;padding:20px 16px}}
        .pay-header{{text-align:center;padding:30px 0 20px}}
        .pay-header .brand{{font-size:1.4rem;font-weight:800;background:linear-gradient(135deg,#ff6b35,#ff9f1c);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
        .pay-header .sub{{color:#999;font-size:.78rem;margin-top:4px}}
        .pay-card{{background:#fff;border-radius:20px;box-shadow:0 4px 24px rgba(0,0,0,.06);padding:24px 20px;margin-bottom:16px}}
        .pay-card .title{{font-size:.78rem;color:#999;margin-bottom:12px;display:flex;align-items:center;gap:6px}}
        .info-row{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #f5f5f5}}
        .info-row:last-child{{border-bottom:none}}
        .info-row .label{{color:#888;font-size:.85rem}}
        .info-row .value{{font-weight:700;font-size:.9rem;color:#333}}
        .amount-display{{text-align:center;padding:20px 0}}
        .amount-display .won{{font-size:2.2rem;font-weight:800;color:#ff6b35}}
        .amount-display .won-label{{color:#999;font-size:.78rem;margin-bottom:4px}}
        .pay-btn{{width:100%;padding:16px;border:none;border-radius:14px;font-size:1.05rem;font-weight:700;color:#fff;cursor:pointer;transition:all .2s}}
        .pay-btn.primary{{background:linear-gradient(135deg,#ff6b35,#ff9f1c)}}
        .pay-btn.primary:active{{transform:scale(.97);opacity:.9}}
        .pay-btn:disabled{{opacity:.5;cursor:not-allowed}}
        .method-select{{display:flex;gap:8px;margin-bottom:16px}}
        .method-btn{{flex:1;padding:12px 4px;border:2px solid #eee;border-radius:12px;background:#fff;cursor:pointer;text-align:center;transition:all .2s;font-size:.78rem;color:#666}}
        .method-btn.active{{border-color:#ff6b35;background:rgba(255,107,53,.04);color:#ff6b35;font-weight:700}}
        .method-btn i{{display:block;font-size:1.2rem;margin-bottom:4px}}
        .status-badge{{display:inline-flex;align-items:center;gap:4px;padding:4px 12px;border-radius:50px;font-size:.72rem;font-weight:600}}
        .status-badge.recurring{{background:rgba(14,165,233,.08);color:#0ea5e9}}
        .status-badge.once{{background:rgba(139,92,246,.08);color:#8b5cf6}}
        .success-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:1000;align-items:center;justify-content:center;padding:20px}}
        .success-card{{background:#fff;border-radius:20px;padding:40px 30px;text-align:center;max-width:360px;width:100%}}
        .success-card i{{font-size:3.5rem;color:#22c55e;margin-bottom:16px}}
        .success-card h3{{margin-bottom:8px;color:#333}}
        .success-card p{{color:#888;font-size:.85rem}}
        .pg-notice{{background:rgba(14,165,233,.04);border:1px dashed rgba(14,165,233,.2);border-radius:12px;padding:12px;text-align:center;font-size:.75rem;color:#0ea5e9;margin-top:12px}}
        .footer{{text-align:center;padding:20px 0;font-size:.72rem;color:#ccc}}
    </style>
</head>
<body>
    <div class="pay-container">
        <div class="pay-header">
            <div class="brand"><i class="fas fa-smile" style="margin-right:4px"></i>방긋페이</div>
            <div class="sub">안전하고 간편한 월세 결제</div>
        </div>

        <div class="pay-card">
            <div class="title"><i class="fas fa-building"></i>임대물건 정보</div>
            <div class="info-row">
                <span class="label">임대물건</span>
                <span class="value">{tenant.property_name}</span>
            </div>
            <div class="info-row">
                <span class="label">호수</span>
                <span class="value">{tenant.unit_number}</span>
            </div>
            <div class="info-row">
                <span class="label">임차인</span>
                <span class="value">{tenant.name}</span>
            </div>
            <div class="info-row">
                <span class="label">임대인</span>
                <span class="value">{landlord_name}</span>
            </div>
            <div class="info-row">
                <span class="label">납부일</span>
                <span class="value">매월 {tenant.rent_due_day}일</span>
            </div>
        </div>

        <div class="pay-card">
            <div class="title"><i class="fas fa-won-sign"></i>결제 금액</div>
            <div class="amount-display">
                <div class="won-label">이번 달 월세</div>
                <div class="won">{rent_formatted}원</div>
            </div>
            <div style="text-align:center">
                {'<span class="status-badge recurring"><i class="fas fa-sync-alt"></i>정기결제</span>' if tenant.is_recurring else '<span class="status-badge once"><i class="fas fa-credit-card"></i>일반결제</span>'}
            </div>
        </div>

        <div class="pay-card" id="paymentMethodCard">
            <div class="title"><i class="fas fa-credit-card"></i>결제 수단</div>
            <div class="method-select">
                <div class="method-btn active" onclick="selectMethod(this,'card_once')">
                    <i class="fas fa-credit-card"></i>카드결제
                </div>
                <div class="method-btn" onclick="selectMethod(this,'card_recurring')">
                    <i class="fas fa-sync-alt"></i>정기결제
                </div>
                <div class="method-btn" onclick="selectMethod(this,'ongi_bank')">
                    <i class="fas fa-university"></i>내통장결제
                </div>
            </div>
            <div class="pg-notice" id="pgNotice">
                <i class="fas fa-shield-alt" style="margin-right:4px"></i>
                PG사 연동 후 실제 카드결제가 진행됩니다<br>
                <span style="color:#aaa">현재는 테스트 결제만 가능합니다</span>
            </div>
            <div class="pg-notice" id="ongiNotice" style="display:none;background:rgba(255,107,53,.04);border-color:rgba(255,107,53,.2);color:#ff6b35">
                <i class="fas fa-university" style="margin-right:4px"></i>
                ONGI 내통장 결제창으로 이동합니다<br>
                <span style="color:#aaa">결제 완료 후 자동으로 처리됩니다</span>
            </div>
        </div>

        <button class="pay-btn primary" id="payBtn" onclick="processPayment()">
            <i class="fas fa-lock" style="margin-right:6px"></i>{rent_formatted}원 결제하기
        </button>

        <div class="footer">
            <i class="fas fa-lock" style="margin-right:4px"></i>방긋페이 · 안전한 결제 시스템<br>
            결제 관련 문의는 임대인에게 연락해주세요
        </div>
    </div>

    <div class="success-overlay" id="successOverlay">
        <div class="success-card">
            <i class="fas fa-check-circle"></i>
            <h3>결제 완료!</h3>
            <p id="successMsg">월세 결제가 정상적으로 처리되었습니다.</p>
            <button class="pay-btn primary" style="margin-top:20px" onclick="document.getElementById('successOverlay').style.display='none'">확인</button>
        </div>
    </div>

    <script>
        let selectedMethod = '{'card_recurring' if tenant.is_recurring else 'card_once'}';
        function selectMethod(el, method) {{
            document.querySelectorAll('.method-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            selectedMethod = method;
            const isOngi = method === 'ongi_bank';
            document.getElementById('pgNotice').style.display = isOngi ? 'none' : 'block';
            document.getElementById('ongiNotice').style.display = isOngi ? 'block' : 'none';
        }}
        async function processPayment() {{
            const btn = document.getElementById('payBtn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin" style="margin-right:6px"></i>결제 처리중...';
            try {{
                if (selectedMethod === 'ongi_bank') {{
                    const fd = new FormData();
                    fd.append('payer_name', '{tenant.name}');
                    fd.append('payer_phone', '{tenant.phone or ""}');
                    const res = await fetch('/api/public/rent-qr/{token}/ongi/initiate', {{ method:'POST', body:fd }});
                    const data = await res.json();
                    if (data.ok && data.redirect_url) {{
                        window.location.href = data.redirect_url;
                        return;
                    }}
                    throw new Error(data.detail || 'ONGI 결제창을 열 수 없습니다');
                }}
                const fd = new FormData();
                fd.append('payment_method', selectedMethod);
                fd.append('card_brand', 'VISA');
                const res = await fetch('/api/public/rent-qr/{token}/pay', {{ method:'POST', body:fd }});
                const data = await res.json();
                if (data.ok) {{
                    document.getElementById('successMsg').textContent = data.message;
                    document.getElementById('successOverlay').style.display = 'flex';
                    btn.innerHTML = '<i class="fas fa-check" style="margin-right:6px"></i>결제 완료';
                    btn.style.background = '#22c55e';
                }} else {{
                    alert('결제 실패: ' + (data.detail || '오류 발생'));
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-lock" style="margin-right:6px"></i>{rent_formatted}원 결제하기';
                }}
            }} catch(e) {{
                alert('결제 오류: ' + e.message);
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-lock" style="margin-right:6px"></i>{rent_formatted}원 결제하기';
            }}
        }}
        // 정기결제 임차인이면 기본 선택
        {'document.querySelectorAll(".method-btn")[1].click();' if tenant.is_recurring else ''}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.post("/api/public/rent-qr/{token}/pay")
def pay_rent_via_qr(
    token: str,
    card_brand: Optional[str] = Form(None),
    payment_method: str = Form("card_once"),
    db: Session = Depends(get_db),
):
    """QR코드를 통한 월세 결제"""
    tenant = db.query(Tenant).filter(Tenant.qr_token == token, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="유효하지 않은 QR코드입니다")
    import random
    now = datetime.utcnow()
    payment = RentPayment(
        tenant_id=tenant.id,
        landlord_user_id=tenant.landlord_user_id,
        amount=tenant.monthly_rent,
        payment_method=RentPaymentMethod(payment_method),
        status=RentPaymentStatus.PAID,
        card_brand=card_brand or "VISA",
        approval_code=f"RENT-{random.randint(100000, 999999)}",
        payment_month=now.strftime("%Y-%m"),
        paid_at=now,
    )
    db.add(payment)
    db.commit()
    return {
        "ok": True,
        "message": f"{tenant.property_name} {tenant.unit_number} 월세 결제가 완료되었습니다.",
        "amount": tenant.monthly_rent,
    }


# ─── ONGI (위아오너) 내통장 결제 연동 ────────────────────────

_ongi_logger = logging.getLogger("ongi")


@app.post("/api/public/rent-qr/{token}/ongi/initiate")
def initiate_ongi_payment(
    token: str,
    request: Request,
    payer_name: Optional[str] = Form(None),
    payer_phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """ONGI 결제창으로 리다이렉트할 URL을 생성하고 PENDING RentPayment를 선기록."""
    from app.services.ongi_service import build_ongi_pay_url, resolve_callback_url
    from app.config import get_settings

    tenant = db.query(Tenant).filter(Tenant.qr_token == token, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="유효하지 않은 QR코드입니다")

    settings = get_settings()
    if not settings.ONGI_QR_TOKEN:
        raise HTTPException(status_code=503, detail="ONGI 연동이 설정되지 않았습니다 (ONGI_QR_TOKEN)")

    now = datetime.utcnow()
    payment = RentPayment(
        tenant_id=tenant.id,
        landlord_user_id=tenant.landlord_user_id,
        amount=tenant.monthly_rent,
        payment_method=RentPaymentMethod.ONGI_BANK,
        status=RentPaymentStatus.PENDING,
        payer_name=payer_name or tenant.name,
        payer_phone=payer_phone or tenant.phone,
        payment_month=now.strftime("%Y-%m"),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # 콜백 URL: 설정값 → 없으면 요청 호스트 기반 자동 생성
    callback_url = resolve_callback_url()
    if not callback_url:
        callback_url = str(request.url_for("ongi_callback"))

    pay_url = build_ongi_pay_url(
        amount=int(tenant.monthly_rent),
        name=payment.payer_name,
        phone=payment.payer_phone,
        order_code=f"RENT-{payment.id}",
        callback_url=callback_url,
        return_url=str(request.base_url).rstrip("/") + f"/pay/{token}",
    )
    return {"ok": True, "payment_id": payment.id, "redirect_url": pay_url}


@app.post("/api/public/ongi/callback", name="ongi_callback")
async def ongi_callback(request: Request, db: Session = Depends(get_db)):
    """ONGI 서버 → 가맹점 서버 결제 완료 통지 수신.

    payment_code 기준 멱등 처리. 가능한 한 빠르게 2xx 반환 (ONGI 타임아웃 15초).
    """
    from app.services.ongi_service import OngiCallbackPayload

    try:
        raw = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    try:
        payload = OngiCallbackPayload(**raw)
    except Exception as e:
        _ongi_logger.warning("ONGI callback parse failed: %s | raw=%s", e, raw)
        raise HTTPException(status_code=400, detail="invalid payload")

    # 멱등: 동일 payment_code가 이미 PAID로 기록되어 있으면 즉시 ok
    existing = db.query(RentPayment).filter(
        RentPayment.ongi_payment_code == payload.payment_code
    ).first()
    if existing and existing.status == RentPaymentStatus.PAID:
        return {"ok": True, "duplicate": True}

    # 완료가 아니면 PENDING 유지하고 종료
    if not payload.is_completed:
        _ongi_logger.info(
            "ONGI callback non-completed: code=%s state=%s result_cd=%s",
            payload.payment_code, payload.state, payload.result_cd,
        )
        return {"ok": True, "ignored": True, "reason": "not completed"}

    # order_code(RENT-{id})로 PENDING 레코드 매칭
    payment: Optional[RentPayment] = None
    if payload.order_code and payload.order_code.startswith("RENT-"):
        try:
            pid = int(payload.order_code.split("-", 1)[1])
            payment = db.query(RentPayment).filter(RentPayment.id == pid).first()
        except (ValueError, IndexError):
            payment = None

    if payment is None and existing is not None:
        payment = existing

    if payment is None:
        # 매칭 실패 — 로그만 남기고 2xx 반환 (재시도 폭주 방지)
        _ongi_logger.error(
            "ONGI callback: no matching payment. payment_code=%s order_code=%s",
            payload.payment_code, payload.order_code,
        )
        return {"ok": True, "matched": False}

    # 금액 검증 (선택적, 차이나면 로그만)
    if payload.pay_price is not None and abs(payload.pay_price - int(payment.amount)) > 0:
        _ongi_logger.warning(
            "ONGI amount mismatch: payment_id=%s expected=%s got=%s",
            payment.id, payment.amount, payload.pay_price,
        )

    payment.ongi_payment_code = payload.payment_code
    payment.ongi_auth_no = payload.auth_no
    payment.ongi_tr_no = payload.tr_no
    payment.status = RentPaymentStatus.PAID
    payment.approval_code = payload.auth_no or payment.approval_code
    payment.paid_at = datetime.utcnow()
    if payload.member_name:
        payment.payer_name = payload.member_name
    if payload.phone:
        payment.payer_phone = payload.phone
    db.commit()

    return {"ok": True, "payment_id": payment.id}
