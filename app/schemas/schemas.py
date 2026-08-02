"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict
from datetime import datetime, date, timezone, timedelta
from enum import Enum


# ─── Auth ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str
    phone: Optional[str] = None
    role: str = "OWNER"                    # OWNER / SALES 가능 (ADMIN 불가)
    sales_referral_code: Optional[str] = None  # OWNER 가입 시 SALES 추천 코드
    shop_name: Optional[str] = None        # OWNER 가입 시 가맹점명
    business_number: Optional[str] = None  # OWNER 가입 시 사업자번호
    address: Optional[str] = None          # OWNER 가입 시 주소


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Merchant ────────────────────────────────────────────────

class MerchantCreate(BaseModel):
    name: str
    owner_user_id: int
    business_no: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


class MerchantUpdate(BaseModel):
    name: Optional[str] = None
    business_no: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


# ─── PG Config ───────────────────────────────────────────────

class PGConfigCreate(BaseModel):
    provider_id: int
    mid: str
    secret: str


# ─── Staff ───────────────────────────────────────────────────

class StaffCreate(BaseModel):
    name: str
    staff_code: str
    user_id: Optional[int] = None
    share_rate: Optional[float] = None  # 디자이너 분배율 (0~1). 미지정 시 기본 0.5


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    share_rate: Optional[float] = None  # 디자이너 분배율 (0~1)

class DesignerCreate(BaseModel):
    """원장이 디자이너 계정을 직접 등록할 때 사용.
    User(role=designer) 생성 + Staff 로 미용실 귀속."""
    name: str
    email: str
    password: str = Field(min_length=6)
    staff_code: str
    phone: Optional[str] = None
    share_rate: Optional[float] = None  # 디자이너 분배율 (0~1)


class DesignerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    share_rate: Optional[float] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # 비밀번호 재설정 (선택)



# ─── Terminal Transaction ────────────────────────────────────

class TerminalTransactionCreate(BaseModel):
    merchant_id: int
    terminal_id: Optional[str] = None  # terminal_serial
    amount: float = Field(..., gt=0, description="결제 금액 (0보다 커야 함)")
    installment_months: int = Field(0, ge=0, le=60, description="할부 개월수 (0~60)")
    staff_code: Optional[str] = None
    card_brand: Optional[str] = None
    approval_code: Optional[str] = None
    approved_at: Optional[datetime] = None

    @field_validator("approved_at")
    @classmethod
    def validate_approved_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        """승인 시각이 현재 시각 기준 ±24시간 이내인지 검증한다."""
        if v is None:
            return v
        now = datetime.now(timezone.utc)
        dt = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        diff = abs((dt - now).total_seconds())
        if diff > 86400:
            raise ValueError("approved_at은 현재 시각 기준 ±24시간 이내여야 합니다")
        return v


class TransactionCancelRequest(BaseModel):
    cancel_reason: Optional[str] = Field(None, max_length=255, description="취소 사유")


# ─── Payout ──────────────────────────────────────────────────

class PayoutRequestCreate(BaseModel):
    amount: float = Field(gt=0, description="출금 요청 금액 (원)")
    bank_info: Optional[str] = None
    memo: Optional[str] = None


# ─── Ad Orders ───────────────────────────────────────────────

class AdBlogOrderCreate(BaseModel):
    campaign_name: str = Field(min_length=2, max_length=300)
    address: Optional[str] = None
    contact: Optional[str] = None
    links: List[str] = Field(default_factory=list, max_length=10)
    main_keywords: List[str] = Field(default_factory=list, min_length=1, max_length=5)
    hashtags: List[str] = Field(default_factory=list, max_length=5)
    description: Optional[str] = None
    extra_image_link: Optional[str] = None
    order_count: int = Field(default=1, ge=1, le=10000)
class AdPlaceTrafficOrderCreate(BaseModel):
    place_name_or_id: str = Field(min_length=2, max_length=300)
    search_keywords: List[str] = Field(default_factory=list, min_length=1, max_length=3)
    order_count: int = Field(default=1, ge=1, le=10000)


class AdPricingUpdate(BaseModel):
    blog_unit_price: int = Field(ge=0, le=100000000)
    place_traffic_unit_price: int = Field(ge=0, le=100000000)
    shorts_distribution_unit_price: int = Field(ge=0, le=100000000)
    shorts_duration_prices: Dict[str, int] = Field(default_factory=dict)


class AdShortsOrderCreate(BaseModel):
    """쇼츠(숏폼) 제작·배포 주문 요청.

    예상 집행 비용은 클라이언트 값을 신뢰하지 않고 서버에서 다시 계산한다.
    """
    # 1) 브랜드 · 캠페인 기본 정보
    campaign_name: str = Field(min_length=2, max_length=300)
    brand_name: Optional[str] = Field(default=None, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=50)
    website_url: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None

    # 2) 캠페인 설정
    campaign_type: str = Field(min_length=2, max_length=40)
    distribution_count: int = Field(default=0, ge=0, le=1000)
    video_production_count: int = Field(default=0, ge=0, le=1000)
    video_duration_tier: Optional[str] = Field(default=None, max_length=10)
    platform_counts: Dict[str, int] = Field(default_factory=dict)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_keywords: List[str] = Field(default_factory=list, max_length=10)
    reference_links: List[str] = Field(default_factory=list, max_length=10)
    uploaded_video_url: Optional[str] = None

    # 3) 영상 제작 브리프
    brief_product_name: Optional[str] = Field(default=None, max_length=300)
    brief_product_detail: Optional[str] = None
    brief_categories: Dict[str, str] = Field(default_factory=dict)
    brief_tone: Optional[str] = Field(default=None, max_length=100)
    brief_style: Optional[str] = Field(default=None, max_length=100)
    brief_target_audience: Optional[str] = None
    brief_key_messages: Optional[str] = None
    brief_avoid: Optional[str] = None
    brief_hashtags: List[str] = Field(default_factory=list, max_length=10)

    # 4) 크리에이터 자격 요건
    creator_min_followers: Optional[str] = Field(default=None, max_length=20)
    creator_gender: Optional[str] = Field(default=None, max_length=20)
    creator_age_group: Optional[str] = Field(default=None, max_length=20)
    creator_requirements: Optional[str] = None

    # 4) 브랜드 세이프티
    brand_forbidden_words: Optional[str] = None
    brand_no_competitor: bool = False
    brand_no_adult: bool = False
    brand_no_violence: bool = False
    brand_no_political: bool = False

    # 4) 성과 추적
    track_utm: bool = False
    track_promo_code: bool = False
    kpi_goals: List[str] = Field(default_factory=list, max_length=10)


class AdOrderStatusUpdate(BaseModel):
    status: str  # reviewing / running / done / rejected
    admin_memo: Optional[str] = None


# ─── Ad Metrics ──────────────────────────────────────────────

class AdMetricCreate(BaseModel):
    merchant_id: int
    place_url: str
    date: date
    blog_review_count: int = 0
    visitor_review_count: int = 0
    place_rank: Optional[int] = None
    search_keyword: Optional[str] = Field(default=None, max_length=200)
    source: str = "manual"


# ─── Ad Place Profile ───────────────────────────────────────

class AdPlaceProfileCreate(BaseModel):
    place_url: Optional[str] = None
    place_id: Optional[str] = None
    nickname: Optional[str] = None
    analysis_keyword: Optional[str] = Field(default=None, max_length=200)


class AdCompetitorCreate(BaseModel):
    competitor_place_url: str = Field(min_length=5, max_length=500)
    memo: Optional[str] = Field(default=None, max_length=200)


# ─── Fee Policy ──────────────────────────────────────────────

class FeePolicyUpdate(BaseModel):
    pg_fee_rate: float = 0.03  # 3.0% (VAT 별도, 실제 적용 3.3%, 하위 호환)


class GlobalFeeSettingsUpdate(BaseModel):
    merchant_fee_rate: float  # 미용실 부과 총 수수료율
    pg_fee_rate: float        # PG사 실비용
    sales_commission_rate: float  # 전역 기본 영업 커미션율


class MerchantFeeOverrideUpdate(BaseModel):
    merchant_fee_rate: Optional[float] = None  # None 이면 전역값 사용
    pg_fee_rate: Optional[float] = None        # None 이면 전역값 사용


class SalesCommissionOverrideUpdate(BaseModel):
    commission_rate: Optional[float] = None  # None 이면 전역값 사용


class SalesAssignmentCreate(BaseModel):
    merchant_id: int
    sales_manager_user_id: int
    commission_rate: float = 0.01
    memo: Optional[str] = None


class SalesAssignmentUpdate(BaseModel):
    commission_rate: Optional[float] = None
    memo: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Commission Visibility (Admin) ───────────────────────────

class CommissionVisibilityUpdate(BaseModel):
    sales: Optional[bool] = None
    owner: Optional[bool] = None
    designer: Optional[bool] = None


# ─── Staff Share Rate (Admin) ────────────────────────────────

class StaffShareRateUpdate(BaseModel):
    share_rate: float  # 0~1


# ─── Merchant Info Update (Owner) ────────────────────────────

class MerchantInfoUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    category_custom: Optional[str] = None
    place_url: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


# ─── Receipt Review ──────────────────────────────────────────

class ReceiptReviewConfigUpdate(BaseModel):
    place_url: Optional[str] = None
    welcome_message: Optional[str] = None
    is_active: Optional[bool] = None


# ─── AI 설정 (Admin) ─────────────────────────────────────────

class AISettingsUpdate(BaseModel):
    api_key: str


# ─── 플랜 관리 (Admin) ───────────────────────────────────────

class PlanUpdate(BaseModel):
    """플랜 수수료율/광고 목표 건수 수정. 일별 값은 월 목표에서 자동 산정한다."""
    merchant_fee_rate: Optional[float] = Field(default=None, ge=0, le=100)  # 부가세 별도 퍼센트 값
    blog_review_daily: Optional[int] = Field(default=None, ge=0)
    blog_review_monthly: Optional[int] = Field(default=None, ge=0)
    receipt_review_daily: Optional[int] = Field(default=None, ge=0)
    receipt_review_monthly: Optional[int] = Field(default=None, ge=0)
    place_traffic_daily: Optional[int] = Field(default=None, ge=0)
    place_traffic_monthly: Optional[int] = Field(default=None, ge=0)
    place_save_daily: Optional[int] = Field(default=None, ge=0)
    place_save_monthly: Optional[int] = Field(default=None, ge=0)
    shorts_daily: Optional[int] = Field(default=None, ge=0)
    shorts_monthly: Optional[int] = Field(default=None, ge=0)


class MerchantPlanAssign(BaseModel):
    plan_id: int


class AdExecutionCreate(BaseModel):
    merchant_id: int
    ad_type: str                       # blog_review | receipt_review | place_traffic | place_save | shorts
    executed_count: int = Field(ge=0)
    execution_date: Optional[date] = None  # 미지정 시 오늘
    note: Optional[str] = None
