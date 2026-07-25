"""
Authentication routes: register, login, OAuth stubs, test-login, /me
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.auth.jwt_handler import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
)
from app.auth.dependencies import get_current_user
from app.schemas.schemas import RegisterRequest, LoginRequest, TokenResponse
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

settings = get_settings()


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
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    role_val = req.role
    if role_val not in [r.value for r in UserRole]:
        role_val = "owner"

    # 디자이너는 직접 회원가입할 수 없고, 소속 미용실 원장님이 등록한다.
    if role_val == UserRole.DESIGNER.value:
        raise HTTPException(
            status_code=403,
            detail="디자이너는 직접 가입할 수 없습니다. 소속 미용실 원장님에게 계정 등록을 요청하세요.",
        )

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        role=UserRole(role_val),
    )
    db.add(user)
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
        "landlord": "landlord@test.com",
    }
    email = role_email_map.get(role)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid role. Use: admin/sales/owner/designer/landlord")
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
