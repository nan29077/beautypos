"""Admin routes — 가맹점 CRUD, 단말기(terminals), 사용자 관리(users), 제휴중개몰(affiliate-malls)."""
import secrets
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.terminal import TerminalDevice
from app.models.transaction import Transaction, TransactionStatus
from app.models.settlement import MerchantSalesAssignment
from app.models.affiliate_mall import AffiliateMall
from app.auth.dependencies import require_admin
from app.auth.jwt_handler import hash_password
from app.schemas.schemas import (
    MerchantCreate, MerchantUpdate, TerminalCreate, TerminalUpdate,
)
from app.services import plan_service, terminal_auth

router = APIRouter()


# ─── Merchants ───────────────────────────────────────────────

@router.get("/merchants")
def list_merchants(db: Session = Depends(get_db), _=Depends(require_admin)):
    merchants = db.query(Merchant).all()
    results = []
    for m in merchants:
        results.append({
            "id": m.id, "name": m.name, "owner_user_id": m.owner_user_id,
            "business_no": m.business_no, "address": m.address,
            "phone": m.phone, "is_active": m.is_active,
            "created_at": str(m.created_at),
        })
    return results


@router.post("/merchants")
def create_merchant(req: MerchantCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    owner = db.query(User).filter(User.id == req.owner_user_id).first()
    if not owner:
        raise HTTPException(status_code=400, detail="소유자 계정을 찾을 수 없습니다")
    # 원장 화면은 owner_user_id 로 가맹점을 1개만 찾으므로, 잘못된 역할·중복 소유를 등록 시점에 막는다.
    if owner.role != UserRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail=f"사장님 역할의 계정만 가맹점 소유자가 될 수 있습니다. (현재: {owner.role.value})",
        )
    existing = db.query(Merchant).filter(Merchant.owner_user_id == req.owner_user_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"이 계정은 이미 '{existing.name}' 가맹점을 소유하고 있습니다",
        )
    m = Merchant(
        name=req.name, owner_user_id=req.owner_user_id,
        business_no=req.business_no, address=req.address, phone=req.phone,
    )
    db.add(m)
    db.flush()
    plan_service.ensure_default_plan(db, m.id)  # 신규 가맹점은 베이직 플랜으로 시작
    db.commit()
    db.refresh(m)
    return {"id": m.id, "name": m.name}


@router.put("/merchants/{mid}")
def update_merchant(mid: int, req: MerchantUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    m = db.query(Merchant).filter(Merchant.id == mid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Merchant not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return {"ok": True}


@router.get("/merchants/{mid}")
def get_merchant(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    m = db.query(Merchant).filter(Merchant.id == mid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return {
        "id": m.id, "name": m.name, "owner_user_id": m.owner_user_id,
        "business_no": m.business_no, "address": m.address,
        "phone": m.phone, "is_active": m.is_active,
    }


# ─── Terminals ───────────────────────────────────────────────

def _terminal_stats(db: Session, terminal_ids: list) -> dict:
    """단말기별 (승인 거래 건수, 마지막 거래 시각). 취소 거래는 세지 않는다.

    단말기마다 두 번씩 조회하면 N+1 이 되므로 한 번에 group by 로 가져온다.
    """
    if not terminal_ids:
        return {}
    rows = db.query(
        Transaction.terminal_id,
        func.count(Transaction.id),
        func.max(Transaction.created_at),
    ).filter(
        Transaction.terminal_id.in_(terminal_ids),
        Transaction.status == TransactionStatus.APPROVED,
    ).group_by(Transaction.terminal_id).all()
    return {r[0]: {"count": int(r[1] or 0), "last_at": r[2]} for r in rows}


def _terminal_payload(t: TerminalDevice, merchant_name: Optional[str], stats: dict) -> dict:
    """단말기 응답 한 건. API 키는 해시로만 보관되므로 절대 담지 않는다."""
    stat = stats.get(t.id) or {}
    return {
        "id": t.id,
        "merchant_id": t.merchant_id,
        "merchant_name": merchant_name or f"가맹점#{t.merchant_id}",
        "terminal_serial": t.terminal_serial,
        "memo": t.memo,
        "is_active": t.is_active,
        "transaction_count": int(stat.get("count", 0)),
        "last_transaction_at": str(stat["last_at"]) if stat.get("last_at") else None,
        "created_at": str(t.created_at),
    }


def _require_merchant(db: Session, merchant_id: int) -> Merchant:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="가맹점을 찾을 수 없습니다")
    return merchant


def _assert_serial_free(db: Session, serial: str, exclude_id: Optional[int] = None) -> None:
    q = db.query(TerminalDevice).filter(TerminalDevice.terminal_serial == serial)
    if exclude_id is not None:
        q = q.filter(TerminalDevice.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail="이미 등록된 단말기 일련번호입니다")


@router.get("/terminals")
def list_terminals(
    merchant_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """단말기 목록. API 키는 해시로만 보관되므로 절대 반환하지 않는다."""
    q = db.query(TerminalDevice)
    if merchant_id:
        q = q.filter(TerminalDevice.merchant_id == merchant_id)
    terminals = q.order_by(TerminalDevice.id).all()
    merchant_names = {m.id: m.name for m in db.query(Merchant).all()}
    stats = _terminal_stats(db, [t.id for t in terminals])
    return [
        _terminal_payload(t, merchant_names.get(t.merchant_id), stats)
        for t in terminals
    ]


@router.get("/terminals/{tid}")
def get_terminal(tid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """단말기 한 건 상세."""
    t = db.query(TerminalDevice).filter(TerminalDevice.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="단말기를 찾을 수 없습니다")
    merchant = db.query(Merchant).filter(Merchant.id == t.merchant_id).first()
    return _terminal_payload(t, merchant.name if merchant else None,
                             _terminal_stats(db, [t.id]))


@router.post("/terminals", status_code=201)
def create_terminal(
    req: TerminalCreate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """단말기를 등록한다.

    api_key 를 비워 보내면 서버가 만들어 준다. 평문 키는 저장하지 않으므로
    **이 응답에서 한 번만** 보여준다. 잃어버리면 rotate-key 로 다시 발급해야 한다.
    """
    _require_merchant(db, req.merchant_id)
    serial = req.terminal_serial.strip()
    if not serial:
        raise HTTPException(status_code=400, detail="단말기 일련번호를 입력해주세요")
    _assert_serial_free(db, serial)

    api_key = (req.api_key or "").strip() or terminal_auth.generate_api_key()
    terminal = TerminalDevice(
        merchant_id=req.merchant_id,
        terminal_serial=serial,
        memo=(req.memo or "").strip() or None,
        is_active=req.is_active,
        api_key_hash="",
    )
    terminal_auth.apply_api_key(terminal, api_key)
    db.add(terminal)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 등록된 단말기 일련번호입니다")
    db.refresh(terminal)

    merchant = db.query(Merchant).filter(Merchant.id == terminal.merchant_id).first()
    return {
        **_terminal_payload(terminal, merchant.name if merchant else None, {}),
        "api_key": api_key,
        "api_key_notice": "이 키는 지금 한 번만 표시됩니다. 단말기에 등록한 뒤 안전하게 보관하세요.",
    }


@router.put("/terminals/{tid}")
def update_terminal(
    tid: int,
    req: TerminalUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """단말기 정보 수정 (소속 가맹점 · 일련번호 · 메모 · 사용 여부)."""
    t = db.query(TerminalDevice).filter(TerminalDevice.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="단말기를 찾을 수 없습니다")

    changes = req.model_dump(exclude_unset=True)
    if "merchant_id" in changes and changes["merchant_id"] is not None:
        _require_merchant(db, changes["merchant_id"])
        t.merchant_id = changes["merchant_id"]
    if "terminal_serial" in changes and changes["terminal_serial"] is not None:
        serial = changes["terminal_serial"].strip()
        if not serial:
            raise HTTPException(status_code=400, detail="단말기 일련번호를 입력해주세요")
        _assert_serial_free(db, serial, exclude_id=t.id)
        t.terminal_serial = serial
    if "memo" in changes:
        t.memo = (changes["memo"] or "").strip() or None
    if "is_active" in changes and changes["is_active"] is not None:
        t.is_active = changes["is_active"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 등록된 단말기 일련번호입니다")
    db.refresh(t)
    merchant = db.query(Merchant).filter(Merchant.id == t.merchant_id).first()
    return _terminal_payload(t, merchant.name if merchant else None,
                             _terminal_stats(db, [t.id]))


@router.post("/terminals/{tid}/rotate-key")
def rotate_terminal_key(tid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """단말기 API 키를 새로 발급한다. 기존 키는 즉시 못 쓰게 된다."""
    t = db.query(TerminalDevice).filter(TerminalDevice.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="단말기를 찾을 수 없습니다")
    api_key = terminal_auth.generate_api_key()
    terminal_auth.apply_api_key(t, api_key)
    db.commit()
    return {
        "ok": True,
        "id": t.id,
        "terminal_serial": t.terminal_serial,
        "api_key": api_key,
        "api_key_notice": "이 키는 지금 한 번만 표시됩니다. 이전 키는 더 이상 동작하지 않습니다.",
    }


@router.delete("/terminals/{tid}")
def delete_terminal(tid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """단말기 삭제.

    거래 기록이 남아 있으면 지우지 않는다 — 지우면 그 거래들의 단말기 추적이 끊긴다.
    대신 사용 중지(is_active=false)로 바꿔 더 이상 결제를 받지 않게 한다.
    """
    t = db.query(TerminalDevice).filter(TerminalDevice.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="단말기를 찾을 수 없습니다")

    txn_count = db.query(func.count(Transaction.id)).filter(
        Transaction.terminal_id == t.id
    ).scalar() or 0
    if txn_count:
        if t.is_active:
            t.is_active = False
            db.commit()
        return {
            "ok": True,
            "deleted": False,
            "deactivated": True,
            "transaction_count": int(txn_count),
            "detail": "거래 기록이 있어 삭제 대신 사용 중지 처리했습니다",
        }

    db.delete(t)
    db.commit()
    return {"ok": True, "deleted": True, "deactivated": False}


# ─── Users Management ───────────────────────────────────────

@router.get("/users")
def list_all_users(
    role: Optional[str] = None,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """전체 사용자 목록 (역할별 필터 가능)"""
    q = db.query(User)
    if role:
        try:
            role_enum = UserRole(role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 역할입니다: {role}")
        q = q.filter(User.role == role_enum)
    users = q.order_by(User.created_at.desc()).all()

    results = []
    for u in users:
        # 소유 가맹점 이름 조회
        merchant = db.query(Merchant).filter(Merchant.owner_user_id == u.id).first()
        # 영업관리자인 경우 담당 가맹점 수
        assigned_count = 0
        if u.role == UserRole.SALES:
            assigned_count = db.query(MerchantSalesAssignment).filter(
                MerchantSalesAssignment.sales_manager_user_id == u.id,
                MerchantSalesAssignment.is_active == True,
            ).count()
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role.value,
            "phone": u.phone,
            "is_active": u.is_active,
            "created_at": str(u.created_at),
            "merchant_name": merchant.name if merchant else None,
            "assigned_merchant_count": assigned_count,
            "referral_code": u.referral_code if u.role == UserRole.SALES else None,
        })
    return results


class _CreateSalesRequest(BaseModel):
    name: str
    email: str
    password: str


@router.post("/users/create-sales")
def create_sales_user(
    req_body: _CreateSalesRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """최고관리자가 영업관리자 계정을 직접 생성한다. 고유 추천 코드가 자동 발급된다."""
    name, email, password = req_body.name, req_body.email, req_body.password
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    referral_code = f"SALES-{secrets.token_hex(4).upper()}"
    while db.query(User).filter(User.referral_code == referral_code).first():
        referral_code = f"SALES-{secrets.token_hex(4).upper()}"

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=UserRole.SALES,
        referral_code=referral_code,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": "sales",
        "referral_code": user.referral_code,
    }


@router.put("/users/{uid}/role")
def update_user_role(uid: int, role: str = Query(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    """사용자 역할 변경"""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    valid_roles = [r.value for r in UserRole]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 역할입니다. 사용 가능: {valid_roles}")
    user.role = UserRole(role)
    db.commit()
    return {"ok": True, "role": role}


@router.put("/users/{uid}/toggle-active")
def toggle_user_active(uid: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """사용자 활성/비활성 토글"""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="자기 자신의 상태는 변경할 수 없습니다.")
    user.is_active = not user.is_active
    db.commit()
    return {"ok": True, "is_active": user.is_active}


@router.delete("/users/{uid}")
def delete_user(uid: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """사용자 완전 삭제 (복구 불가)"""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다.")
    try:
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="삭제 실패: 해당 사용자에게 연결된 거래·정산 등의 데이터가 있습니다. 먼저 관련 데이터를 정리해주세요."
        )
    return {"ok": True, "message": "사용자가 삭제되었습니다."}


# ═══════════════════════════════════════════════════════════
# AFFILIATE MALLS (제휴중개몰)
# ═══════════════════════════════════════════════════════════

@router.get("/affiliate-malls")
def list_affiliate_malls(db: Session = Depends(get_db), _=Depends(require_admin)):
    """제휴중개몰 목록"""
    malls = db.query(AffiliateMall).order_by(AffiliateMall.sort_order, AffiliateMall.id).all()
    return [{
        "id": m.id, "name": m.name, "logo_url": m.logo_url,
        "website_url": m.website_url, "description": m.description,
        "category": m.category, "commission_rate": m.commission_rate,
        "is_active": m.is_active, "sort_order": m.sort_order,
        "created_at": str(m.created_at),
    } for m in malls]


@router.post("/affiliate-malls")
def create_affiliate_mall(
    name: str = Query(...),
    logo_url: Optional[str] = Query(None),
    website_url: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    commission_rate: Optional[str] = Query(None),
    sort_order: int = Query(0),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """제휴중개몰 등록"""
    mall = AffiliateMall(
        name=name, logo_url=logo_url, website_url=website_url,
        description=description, category=category,
        commission_rate=commission_rate, sort_order=sort_order,
    )
    db.add(mall)
    db.commit()
    db.refresh(mall)
    return {"id": mall.id, "name": mall.name, "message": "제휴중개몰이 등록되었습니다."}


@router.put("/affiliate-malls/{mall_id}")
def update_affiliate_mall(
    mall_id: int,
    name: Optional[str] = Query(None),
    logo_url: Optional[str] = Query(None),
    website_url: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    commission_rate: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    sort_order: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """제휴중개몰 수정"""
    mall = db.query(AffiliateMall).filter(AffiliateMall.id == mall_id).first()
    if not mall:
        raise HTTPException(404, "중개몰을 찾을 수 없습니다.")
    if name is not None: mall.name = name
    if logo_url is not None: mall.logo_url = logo_url
    if website_url is not None: mall.website_url = website_url
    if description is not None: mall.description = description
    if category is not None: mall.category = category
    if commission_rate is not None: mall.commission_rate = commission_rate
    if is_active is not None: mall.is_active = is_active
    if sort_order is not None: mall.sort_order = sort_order
    db.commit()
    return {"id": mall.id, "message": "제휴중개몰이 수정되었습니다."}


@router.delete("/affiliate-malls/{mall_id}")
def delete_affiliate_mall(
    mall_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """제휴중개몰 삭제"""
    mall = db.query(AffiliateMall).filter(AffiliateMall.id == mall_id).first()
    if not mall:
        raise HTTPException(404, "중개몰을 찾을 수 없습니다.")
    db.delete(mall)
    db.commit()
    return {"message": "제휴중개몰이 삭제되었습니다."}
