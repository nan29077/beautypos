"""
Authentication routes: register, login, OAuth stubs, test-login, /me
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.settlement import MerchantSalesAssignment
from app.auth.jwt_handler import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from app.auth.dependencies import get_current_user
from app.schemas.schemas import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from app.services import plan_service
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

settings = get_settings()

# 자가 회원가입은 원장(OWNER)만 허용. 영업관리자는 최고관리자가 직접 생성한다.
_ALLOWED_REGISTER_ROLES = {"owner"}


def _user_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "name": u.name,
        "role": u.role.value if isinstance(u.role, UserRole) else u.role,
        "is_active": u.is_active,
    }


def _issue_tokens(user: User) -> dict:
    access = create_access_token({"sub": str(user.id), "role": user.role.value if isinstance(user.role, UserRole) else user.role})
    refresh = create_refresh_token({"sub": str(user.id)})
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": _user_dict(user),
    }


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    role_str = req.role.lower()
    if role_str not in _ALLOWED_REGISTER_ROLES:
        raise HTTPException(
            status_code=400,
            detail="공개 회원가입은 원장님 계정만 가능합니다. 관리자·영업관리자 계정은 최고관리자가 추가합니다.",
        )

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    role = UserRole(role_str)

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        phone=req.phone,
        role=role,
        referral_code=None,
    )
    db.add(user)
    db.flush()  # user.id 확보

    # OWNER 가입: shop_name 있으면 Merchant 자동 생성
    if role == UserRole.OWNER and req.shop_name:
        merchant = Merchant(
            name=req.shop_name,
            owner_user_id=user.id,
            business_no=req.business_number,
            address=req.address,
            phone=req.phone,
        )
        db.add(merchant)
        db.flush()  # merchant.id 확보

        # 신규 가맹점은 베이직 플랜으로 시작
        plan_service.ensure_default_plan(db, merchant.id)

        # 추천 코드로 영업관리자 자동 연결
        if req.sales_referral_code:
            sales_user = db.query(User).filter(
                User.referral_code == req.sales_referral_code,
                User.role == UserRole.SALES,
                User.is_active == True,  # noqa: E712
            ).first()
            if sales_user:
                assignment = MerchantSalesAssignment(
                    merchant_id=merchant.id,
                    sales_manager_user_id=sales_user.id,
                )
                db.add(assignment)

    db.commit()
    db.refresh(user)
    return _issue_tokens(user)


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return _issue_tokens(user)


@router.post("/refresh")
def refresh_access_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """refresh_token 으로 새 access_token 발급.

    access_token 만료마다 강제 로그아웃되지 않도록 프론트가 401 시 호출한다.
    """
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    access = create_access_token({
        "sub": str(user.id),
        "role": user.role.value if isinstance(user.role, UserRole) else user.role,
    })
    return {"access_token": access, "token_type": "bearer"}


@router.post("/test-login")
def test_login(role: str = Query(...), db: Session = Depends(get_db)):
    """Dev-mode only: quick login with test accounts."""
    if not settings.DEV_MODE:
        raise HTTPException(status_code=403, detail="Test login disabled in production")

    role_email_map = {
        "admin": "admin@test.com",
        "sales": "sales@test.com",
        "owner": "owner@test.com",
        "designer": "designer@test.com",
    }
    email = role_email_map.get(role)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid role. Use: admin/sales/owner/designer")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Test account not found. Run seed first.")
    return _issue_tokens(user)


# ─── OAuth stubs ─────────────────────────────────────────────

@router.get("/oauth/{provider}/start")
def oauth_start(provider: str):
    """Redirect URL for OAuth. Returns the URL the frontend should navigate to."""
    base = settings.OAUTH_REDIRECT_BASE
    if provider == "kakao":
        client_id = settings.KAKAO_CLIENT_ID
        if not client_id:
            return {"url": "#", "message": "Kakao OAuth not configured"}
        return {"url": f"https://kauth.kakao.com/oauth/authorize?client_id={client_id}&redirect_uri={base}/api/auth/oauth/kakao/callback&response_type=code"}
    elif provider == "naver":
        client_id = settings.NAVER_CLIENT_ID
        if not client_id:
            return {"url": "#", "message": "Naver OAuth not configured"}
        return {"url": f"https://nid.naver.com/oauth2.0/authorize?client_id={client_id}&redirect_uri={base}/api/auth/oauth/naver/callback&response_type=code"}
    elif provider == "google":
        client_id = settings.GOOGLE_CLIENT_ID
        if not client_id:
            return {"url": "#", "message": "Google OAuth not configured"}
        return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={base}/api/auth/oauth/google/callback&response_type=code&scope=email%20profile"}
    else:
        raise HTTPException(status_code=400, detail="Unknown provider")


@router.get("/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str = "", db: Session = Depends(get_db)):
    """OAuth callback handler (stub — requires real OAuth keys to work)."""
    # In a real implementation, exchange code for token, get user info, create/login user
    return {
        "message": f"OAuth callback for {provider} received. Code: {code[:10]}...",
        "note": "Implement token exchange with provider SDK in production."
    }


@router.get("/me", summary="Get current user info")
def get_me(current_user: User = Depends(get_current_user)):
    return _user_dict(current_user)
