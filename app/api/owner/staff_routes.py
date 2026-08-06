"""Owner staff / designer account management routes.

Split out of the original app/api/owner_routes.py.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.staff import Staff
from app.models.transaction import Transaction
from app.auth.jwt_handler import hash_password
from app.schemas.schemas import StaffCreate, StaffUpdate, DesignerCreate, DesignerUpdate

from app.api.owner._helpers import require_owner, _get_owner_merchant, _date_range

router = APIRouter()


# ─── Staff Management ───────────────────────────────────────

@router.get("/staff")
def list_staff(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    staff_list = db.query(Staff).filter(Staff.merchant_id == merchant.id).all()
    return [{
        "id": s.id, "name": s.name, "staff_code": s.staff_code,
        "user_id": s.user_id, "is_active": s.is_active,
        "share_rate": float(s.share_rate) if s.share_rate is not None else 0.5,
        "created_at": str(s.created_at),
    } for s in staff_list]


def _clamp_share_rate(value: float) -> float:
    """분배율을 0~1 범위로 제한."""
    return max(0.0, min(1.0, float(value)))


@router.post("/staff")
def create_staff(req: StaffCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    # Check unique staff_code within merchant
    existing = db.query(Staff).filter(
        Staff.merchant_id == merchant.id, Staff.staff_code == req.staff_code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Staff code already exists in this merchant")
    s = Staff(
        merchant_id=merchant.id, name=req.name,
        staff_code=req.staff_code, user_id=req.user_id,
        share_rate=_clamp_share_rate(req.share_rate) if req.share_rate is not None else 0.5,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "name": s.name, "staff_code": s.staff_code, "share_rate": float(s.share_rate)}


@router.put("/staff/{sid}")
def update_staff(sid: int, req: StaffUpdate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    merchant = _get_owner_merchant(user, db)
    s = db.query(Staff).filter(Staff.id == sid, Staff.merchant_id == merchant.id).first()
    if not s:
        raise HTTPException(status_code=404)
    for k, v in req.model_dump(exclude_unset=True).items():
        if k == "share_rate" and v is not None:
            v = _clamp_share_rate(v)
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


# ─── Designer Account Management (원장이 디자이너 계정 등록) ───
# 디자이너는 직접 회원가입할 수 없고, 원장이 계정을 만들어 미용실에 귀속시킨다.

@router.get("/designers")
def list_designers(db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """이 미용실에 귀속된 디자이너(로그인 계정 보유 Staff) 목록."""
    merchant = _get_owner_merchant(user, db)
    rows = db.query(Staff).filter(
        Staff.merchant_id == merchant.id, Staff.user_id.isnot(None)
    ).order_by(Staff.created_at.desc()).all()
    result = []
    for s in rows:
        u = db.query(User).filter(User.id == s.user_id).first()
        result.append({
            "staff_id": s.id,
            "user_id": s.user_id,
            "name": s.name,
            "staff_code": s.staff_code,
            "email": u.email if u else None,
            "phone": u.phone if u else None,
            "share_rate": float(s.share_rate) if s.share_rate is not None else 0.5,
            "is_active": s.is_active and (u.is_active if u else True),
            "created_at": str(s.created_at),
        })
    return result


@router.post("/designers")
def create_designer(req: DesignerCreate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """원장이 디자이너 계정을 직접 생성하고 본인 미용실에 귀속시킨다."""
    merchant = _get_owner_merchant(user, db)

    # 이메일 중복 체크
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")
    # 직원코드 중복 체크 (미용실 내)
    if db.query(Staff).filter(Staff.merchant_id == merchant.id, Staff.staff_code == req.staff_code).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 직원 코드입니다")

    # 1) 디자이너 로그인 계정 생성
    designer_user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        role=UserRole.DESIGNER,
        phone=req.phone,
    )
    db.add(designer_user)
    db.flush()

    # 2) Staff 로 미용실에 귀속
    staff = Staff(
        merchant_id=merchant.id,
        user_id=designer_user.id,
        name=req.name,
        staff_code=req.staff_code,
        share_rate=_clamp_share_rate(req.share_rate) if req.share_rate is not None else 0.5,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return {
        "staff_id": staff.id,
        "user_id": designer_user.id,
        "name": staff.name,
        "email": designer_user.email,
        "staff_code": staff.staff_code,
        "message": f"디자이너 '{req.name}' 계정이 등록되었습니다. ({merchant.name} 소속)",
    }


@router.put("/designers/{staff_id}")
def update_designer(staff_id: int, req: DesignerUpdate, db: Session = Depends(get_db), user: User = Depends(require_owner)):
    """디자이너 정보 수정 (이름/연락처/분배율/활성/비밀번호 재설정)."""
    merchant = _get_owner_merchant(user, db)
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.merchant_id == merchant.id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="디자이너를 찾을 수 없습니다")
    u = db.query(User).filter(User.id == staff.user_id).first()

    payload = req.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        staff.name = payload["name"]
        if u:
            u.name = payload["name"]
    if "phone" in payload and u:
        u.phone = payload["phone"]
    if "share_rate" in payload and payload["share_rate"] is not None:
        staff.share_rate = _clamp_share_rate(payload["share_rate"])
    if "is_active" in payload and payload["is_active"] is not None:
        staff.is_active = payload["is_active"]
        if u:
            u.is_active = payload["is_active"]
    if payload.get("password"):
        if u:
            u.password_hash = hash_password(payload["password"])
    db.commit()
    return {"ok": True}


# ─── Staff Sales ─────────────────────────────────────────────

@router.get("/staff/{sid}/sales")
def staff_sales(
    sid: int,
    range: str = Query("all", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    merchant = _get_owner_merchant(user, db)
    staff = db.query(Staff).filter(Staff.id == sid, Staff.merchant_id == merchant.id).first()
    if not staff:
        raise HTTPException(status_code=404)
    start, end = _date_range(range)
    txns = db.query(Transaction).filter(
        Transaction.merchant_id == merchant.id,
        Transaction.staff_id == sid,
        Transaction.created_at >= start,
        Transaction.created_at <= end,
    ).all()
    total = sum(float(t.amount) for t in txns)
    return {
        "staff_id": sid, "staff_name": staff.name,
        "range": range, "count": len(txns), "total_amount": total,
        "transactions": [{
            "id": t.id, "amount": float(t.amount),
            "approved_at": str(t.approved_at) if t.approved_at else None,
            "created_at": str(t.created_at),
        } for t in txns],
    }
