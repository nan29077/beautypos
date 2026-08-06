"""Admin routes — PG config, pg-providers, PG 연결 테스트."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.merchant import Merchant
from app.models.pg import PGProvider, MerchantPGConfig, PGConfigStatus
from app.auth.dependencies import require_admin
from app.services.encryption import encrypt_value, decrypt_value, mask_value
from app.services.pg_service import get_pg_provider
from app.schemas.schemas import PGConfigCreate

router = APIRouter()


# ─── PG Config ───────────────────────────────────────────────

@router.get("/merchants/{mid}/pg-configs")
def list_pg_configs(mid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    configs = db.query(MerchantPGConfig).filter(MerchantPGConfig.merchant_id == mid).all()
    results = []
    for c in configs:
        provider = db.query(PGProvider).filter(PGProvider.id == c.provider_id).first()
        results.append({
            "id": c.id,
            "provider_id": c.provider_id,
            "provider_code": provider.code if provider else None,
            "provider_name": provider.name if provider else None,
            "mid": c.mid,
            "secret_masked": mask_value(decrypt_value(c.secret_encrypted)),
            "status": c.status.value if c.status else None,
            "last_tested_at": str(c.last_tested_at) if c.last_tested_at else None,
        })
    return results


@router.post("/merchants/{mid}/pg-config")
def create_pg_config(mid: int, req: PGConfigCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    merchant = db.query(Merchant).filter(Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    provider = db.query(PGProvider).filter(PGProvider.id == req.provider_id).first()
    if not provider:
        raise HTTPException(status_code=400, detail="PG Provider not found")

    config = MerchantPGConfig(
        merchant_id=mid,
        provider_id=req.provider_id,
        mid=req.mid,
        secret_encrypted=encrypt_value(req.secret),
        status=PGConfigStatus.CONNECTED,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"id": config.id, "status": config.status.value}


@router.post("/merchants/{mid}/pg-test")
def test_pg_config(mid: int, config_id: int = Query(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    config = db.query(MerchantPGConfig).filter(
        MerchantPGConfig.id == config_id, MerchantPGConfig.merchant_id == mid
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="PG config not found")

    provider_row = db.query(PGProvider).filter(PGProvider.id == config.provider_id).first()
    if not provider_row:
        raise HTTPException(status_code=400, detail="Provider not found")

    pg = get_pg_provider(provider_row.code)
    secret = decrypt_value(config.secret_encrypted)
    result = pg.test_connection(config.mid, secret)

    config.last_tested_at = datetime.utcnow()
    if result["success"]:
        config.status = PGConfigStatus.TESTED
    db.commit()

    return result


# ─── PG Providers list ───────────────────────────────────────

@router.get("/pg-providers")
def list_pg_providers(db: Session = Depends(get_db), _=Depends(require_admin)):
    providers = db.query(PGProvider).all()
    return [{"id": p.id, "code": p.code, "name": p.name} for p in providers]
