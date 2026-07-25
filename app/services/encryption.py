"""
Simple symmetric encryption for PG secrets (Fernet-based).
"""
import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    # Derive a valid Fernet key from the config ENCRYPTION_KEY
    raw = settings.ENCRYPTION_KEY.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_value(plain: str) -> str:
    f = _get_fernet()
    return f.encrypt(plain.encode()).decode()


def decrypt_value(cipher: str) -> str:
    f = _get_fernet()
    return f.decrypt(cipher.encode()).decode()


def mask_value(plain: str, visible: int = 4) -> str:
    """Show only last `visible` chars."""
    if len(plain) <= visible:
        return "****"
    return "*" * (len(plain) - visible) + plain[-visible:]
