"""
ONGI (위아오너) 결제 연동 서비스.

가이드: https://new.ongi.site/api

흐름:
1) 가맹점 서버가 ONGI 결제창 URL을 생성하여 사용자 웹뷰를 리다이렉트
   https://pay.ongi.site/#/qr/{qr_token}?checkout=pg&name=...&phone=...&amount=...&callback_url=...&order_code=...
2) 사용자가 결제 완료 → ONGI 서버가 callback_url로 HTTP POST(JSON) 전송
3) 가맹점 서버는 payment_code 기준 멱등 처리
"""
from typing import Optional
from urllib.parse import quote
from pydantic import BaseModel
from app.config import get_settings


def build_ongi_pay_url(
    amount: int,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    order_code: Optional[str] = None,
    callback_url: Optional[str] = None,
    return_url: Optional[str] = None,
    qr_token: Optional[str] = None,
) -> str:
    """ONGI 결제창 URL 생성.

    pay.ongi.site는 해시 라우터를 사용하므로 `#` 뒤에 경로와 쿼리를 붙임:
        {ONGI_PAY_BASE_URL}/#/qr/{qr_token}?checkout=pg&name=...&phone=...&amount=...
    """
    settings = get_settings()
    base = settings.ONGI_PAY_BASE_URL.rstrip("/")
    token = qr_token or settings.ONGI_QR_TOKEN
    if not token:
        raise ValueError("ONGI_QR_TOKEN이 설정되지 않았습니다.")

    params: list[str] = ["checkout=pg", f"amount={int(amount)}"]
    if name:
        params.append(f"name={quote(name, safe='')}")
    if phone:
        params.append(f"phone={quote(phone, safe='')}")
    if order_code:
        params.append(f"order_code={quote(order_code, safe='')}")
    if callback_url:
        params.append(f"callback_url={quote(callback_url, safe='')}")
    if return_url:
        params.append(f"return_url={quote(return_url, safe='')}")

    query = "&".join(params)
    return f"{base}/#/qr/{token}?{query}"


def resolve_callback_url(explicit_path: str = "/api/public/ongi/callback") -> Optional[str]:
    """설정된 ONGI_CALLBACK_URL을 우선 사용, 없으면 ONGI_PUBLIC_BASE_URL + 경로로 생성."""
    settings = get_settings()
    if settings.ONGI_CALLBACK_URL:
        return settings.ONGI_CALLBACK_URL
    if settings.ONGI_PUBLIC_BASE_URL:
        base = settings.ONGI_PUBLIC_BASE_URL.rstrip("/")
        return f"{base}{explicit_path}"
    return None


class OngiCallbackPayload(BaseModel):
    """ONGI 콜백 JSON 스키마.

    실제 필드는 결제 수단·주문 여부에 따라 일부 null일 수 있어 대부분 Optional.
    payment_code만 대외 식별자로 멱등 처리에 사용.
    """
    event: Optional[str] = None
    payment_code: str
    order_code: Optional[str] = None
    organization_pk: Optional[int] = None
    state: Optional[str] = None
    division: Optional[str] = None
    payment_amt: Optional[int] = None
    pay_price: Optional[int] = None
    discnt_price: Optional[int] = None
    payment_method: Optional[str] = None
    payment_type: Optional[str] = None
    auth_no: Optional[str] = None
    tr_no: Optional[str] = None
    tr_day: Optional[str] = None
    tr_time: Optional[str] = None
    result_cd: Optional[str] = None
    result_msg: Optional[str] = None
    member_name: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        extra = "allow"  # 알 수 없는 추가 필드 허용

    @property
    def is_completed(self) -> bool:
        if self.event and self.event != "payment.completed":
            return False
        if self.result_cd is not None and self.result_cd != "0":
            return False
        if self.state and self.state not in ("완료", "completed", "COMPLETED", "PAID"):
            return False
        return True
