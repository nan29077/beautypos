"""
PG Provider interface + mock implementations.
"""
import abc
import random
from datetime import datetime
from typing import Dict, Any


class PGProviderBase(abc.ABC):
    """Abstract PG provider interface."""

    @abc.abstractmethod
    def test_connection(self, mid: str, secret: str) -> Dict[str, Any]:
        """Test PG connection. Returns {"success": bool, "message": str}"""
        ...

    @abc.abstractmethod
    def process_payment(self, mid: str, secret: str, amount: float, **kwargs) -> Dict[str, Any]:
        ...


class SeedPaymentsMock(PGProviderBase):
    def test_connection(self, mid: str, secret: str) -> Dict[str, Any]:
        ok = random.random() > 0.2  # 80% success
        return {
            "success": ok,
            "message": "씨드페이먼츠 연동 성공" if ok else "씨드페이먼츠 인증 실패 (mock)",
            "tested_at": datetime.utcnow().isoformat(),
        }

    def process_payment(self, mid, secret, amount, **kw):
        return {"success": True, "approval_code": f"SEED-{random.randint(100000,999999)}"}


class KiwoomPayMock(PGProviderBase):
    def test_connection(self, mid: str, secret: str) -> Dict[str, Any]:
        ok = random.random() > 0.2
        return {
            "success": ok,
            "message": "키움페이 연동 성공" if ok else "키움페이 인증 실패 (mock)",
            "tested_at": datetime.utcnow().isoformat(),
        }

    def process_payment(self, mid, secret, amount, **kw):
        return {"success": True, "approval_code": f"KIWOOM-{random.randint(100000,999999)}"}


class TossMock(PGProviderBase):
    def test_connection(self, mid: str, secret: str) -> Dict[str, Any]:
        ok = random.random() > 0.2
        return {
            "success": ok,
            "message": "토스 연동 성공" if ok else "토스 인증 실패 (mock)",
            "tested_at": datetime.utcnow().isoformat(),
        }

    def process_payment(self, mid, secret, amount, **kw):
        return {"success": True, "approval_code": f"TOSS-{random.randint(100000,999999)}"}


# Provider registry
PG_PROVIDERS: Dict[str, PGProviderBase] = {
    "seedpayments": SeedPaymentsMock(),
    "kiwoompay": KiwoomPayMock(),
    "toss": TossMock(),
}


def get_pg_provider(code: str) -> PGProviderBase:
    provider = PG_PROVIDERS.get(code)
    if not provider:
        raise ValueError(f"Unknown PG provider: {code}")
    return provider
