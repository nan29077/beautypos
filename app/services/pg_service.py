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


class OngiProvider(PGProviderBase):
    """ONGI (위아오너) — 내통장 결제. 실제 결제는 ongi_service의 결제창 리다이렉트 + 콜백 흐름으로 진행."""

    def test_connection(self, mid: str, secret: str) -> Dict[str, Any]:
        from app.config import get_settings
        settings = get_settings()
        configured = bool(settings.ONGI_QR_TOKEN)
        return {
            "success": configured,
            "message": "ONGI 연동 준비 완료" if configured else "ONGI_QR_TOKEN이 설정되지 않았습니다",
            "tested_at": datetime.utcnow().isoformat(),
        }

    def process_payment(self, mid, secret, amount, **kw):
        # ONGI는 결제창 리다이렉트 방식 — 동기 process_payment는 지원하지 않음
        return {
            "success": False,
            "message": "ONGI는 결제창 리다이렉트 방식입니다. /api/public/rent-qr/{token}/ongi/initiate 를 사용하세요.",
        }


# Provider registry
PG_PROVIDERS: Dict[str, PGProviderBase] = {
    "seedpayments": SeedPaymentsMock(),
    "kiwoompay": KiwoomPayMock(),
    "toss": TossMock(),
    "ongi": OngiProvider(),
}


def get_pg_provider(code: str) -> PGProviderBase:
    provider = PG_PROVIDERS.get(code)
    if not provider:
        raise ValueError(f"Unknown PG provider: {code}")
    return provider
