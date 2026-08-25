"""
Seed data for ADPAY MVP.
Creates test accounts, merchant, staff, terminal, PG providers,
sample transactions, ad orders, and metrics.
"""
import json
import random
from datetime import datetime, timedelta, date
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.merchant import Merchant
from app.models.staff import Staff
from app.models.terminal import TerminalDevice
from app.services import terminal_auth
from app.models.pg import PGProvider, MerchantPGConfig, PGConfigStatus
from app.models.transaction import Transaction
from app.models.settlement import FeePolicy, MerchantSalesAssignment, PayoutRequest, PayoutStatus
from app.models.ad import (
    AdPlaceProfile, AdCompetitor, AdMetric,
    AdOrder, AdOrderType, AdOrderStatus,
    AdOrderBlogDetail, AdOrderPlaceTrafficDetail,
)
from app.models.crm import (CrmCustomer, CrmService, CrmVisit, CrmReservation, CrmPointLog,
                            CrmMessageTemplate, CrmCoupon, ReservationStatus, MessageChannel)
from app.models.plan import Plan, MerchantPlan

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
TEST_PASSWORD = "Test1234!"
TERMINAL_API_KEY = "term-api-key-001"


def run_seed(db: Session):
    # Check if already seeded
    if db.query(User).filter(User.email == "admin@test.com").first():
        print("   Seed data already exists, skipping.")
        return

    # ─── 1. Users ────────────────────────────────────────────
    pw_hash = pwd_context.hash(TEST_PASSWORD)

    admin = User(email="admin@test.com", password_hash=pw_hash, name="최고관리자", role=UserRole.ADMIN)
    sales = User(email="sales@test.com", password_hash=pw_hash, name="김영업", role=UserRole.SALES)
    owner = User(email="owner@test.com", password_hash=pw_hash, name="박원장", role=UserRole.OWNER)
    designer1 = User(email="designer@test.com", password_hash=pw_hash, name="홍길동", role=UserRole.DESIGNER)
    designer2 = User(email="designer2@test.com", password_hash=pw_hash, name="이디자", role=UserRole.DESIGNER)

    db.add_all([admin, sales, owner, designer1, designer2])
    db.flush()

    # ─── 2. Merchant ─────────────────────────────────────────
    merchant = Merchant(
        name="뷰티헤어살롱 강남점",
        owner_user_id=owner.id,
        business_no="123-45-67890",
        address="서울 강남구 테헤란로 123",
        phone="02-1234-5678",
    )
    db.add(merchant)
    db.flush()

    # ─── 3. Staff ────────────────────────────────────────────
    staff1 = Staff(merchant_id=merchant.id, user_id=designer1.id, name="홍길동", staff_code="1")
    staff2 = Staff(merchant_id=merchant.id, user_id=designer2.id, name="이디자", staff_code="2")
    db.add_all([staff1, staff2])
    db.flush()

    # ─── 4. Terminal ─────────────────────────────────────────
    terminal = TerminalDevice(
        merchant_id=merchant.id,
        terminal_serial="TERM001",
        api_key_hash=terminal_auth.hash_api_key(TERMINAL_API_KEY),
        api_key_fingerprint=terminal_auth.fingerprint(TERMINAL_API_KEY),
        memo="메인 카운터 단말기",
    )
    db.add(terminal)
    db.flush()

    # ─── 5. PG Providers ────────────────────────────────────
    pg1 = PGProvider(code="seedpayments", name="씨드페이먼츠")
    pg2 = PGProvider(code="kiwoompay", name="키움페이")
    pg3 = PGProvider(code="toss", name="토스")
    db.add_all([pg1, pg2, pg3])
    db.flush()

    # ─── 6. Merchant PG Config (sample) ─────────────────────
    from app.services.encryption import encrypt_value
    pg_config = MerchantPGConfig(
        merchant_id=merchant.id,
        provider_id=pg1.id,
        mid="MID-BEAUTY-001",
        secret_encrypted=encrypt_value("secret-key-12345"),
        status=PGConfigStatus.CONNECTED,
    )
    db.add(pg_config)

    # ─── 7. Fee Policy ──────────────────────────────────────
    # 저장값은 부가세 별도 3.0%, 실제 적용은 VAT 포함 3.3%.
    fee = FeePolicy(merchant_id=merchant.id, pg_fee_rate=0.03, vat_inclusive_rate=0.033)
    db.add(fee)

    # ─── 8. Sales Assignment ────────────────────────────────
    assign = MerchantSalesAssignment(
        merchant_id=merchant.id,
        sales_manager_user_id=sales.id,
        commission_rate=0.01,
    )
    db.add(assign)
    db.flush()

    # ─── 9. Sample Transactions (10건) ──────────────────────
    now = datetime.utcnow()
    card_brands = ["VISA", "MASTER", "삼성카드", "현대카드", "KB국민"]
    for i in range(10):
        days_ago = random.randint(0, 30)
        amount = random.choice([15000, 25000, 35000, 50000, 75000, 100000, 150000])
        # Assign some to staff, some to owner
        if i < 4:
            sid = staff1.id
            scode = "1"
        elif i < 7:
            sid = staff2.id
            scode = "2"
        else:
            sid = None
            scode = None

        txn = Transaction(
            merchant_id=merchant.id,
            terminal_id=terminal.id,
            staff_id=sid,
            owner_user_id=owner.id,
            amount=amount,
            installment_months=random.choice([0, 0, 0, 3, 6]),
            card_brand=random.choice(card_brands),
            approval_code=f"APR-{random.randint(100000, 999999)}",
            staff_code_input=scode,
            approved_at=now - timedelta(days=days_ago, hours=random.randint(0, 12)),
            created_at=now - timedelta(days=days_ago, hours=random.randint(0, 12)),
        )
        db.add(txn)

    # ─── 10. Ad Place Profile & Competitors ─────────────────
    profile = AdPlaceProfile(
        merchant_id=merchant.id,
        place_url="https://map.naver.com/v5/entry/place/12345",
        place_id="12345",
        nickname="뷰티헤어살롱 강남",
    )
    comp = AdCompetitor(
        merchant_id=merchant.id,
        competitor_place_url="https://map.naver.com/v5/entry/place/67890",
        memo="길 건너편 경쟁 미용실",
    )
    db.add_all([profile, comp])

    # ─── 11. Ad Metrics (sample) ────────────────────────────
    for i in range(7):
        d = date.today() - timedelta(days=i)
        m1 = AdMetric(
            merchant_id=merchant.id,
            place_url="https://map.naver.com/v5/entry/place/12345",
            date=d,
            blog_review_count=50 + random.randint(-5, 10),
            visitor_review_count=120 + random.randint(-10, 20),
            place_rank=random.randint(1, 10),
            source="manual",
            created_by=admin.id,
        )
        m2 = AdMetric(
            merchant_id=merchant.id,
            place_url="https://map.naver.com/v5/entry/place/67890",
            date=d,
            blog_review_count=40 + random.randint(-5, 10),
            visitor_review_count=100 + random.randint(-10, 20),
            place_rank=random.randint(1, 10),
            source="manual",
            created_by=admin.id,
        )
        db.add_all([m1, m2])

    # ─── 12. Ad Orders (2건) ────────────────────────────────
    order1 = AdOrder(
        merchant_id=merchant.id, type=AdOrderType.BLOG,
        status=AdOrderStatus.REVIEWING, created_by=owner.id,
    )
    db.add(order1)
    db.flush()

    blog_detail = AdOrderBlogDetail(
        order_id=order1.id,
        campaign_name="뷰티헤어살롱 강남점 블로그 리뷰",
        address="서울 강남구 테헤란로 123",
        contact="02-1234-5678",
        links_json=json.dumps(["https://map.naver.com/v5/entry/place/12345", "https://instagram.com/beauty_hair_gn"]),
        main_keywords_json=json.dumps(["강남미용실", "강남헤어살롱", "강남펌", "강남염색", "테헤란로미용실"]),
        hashtags_json=json.dumps(["#강남미용실", "#강남헤어살롱", "#강남펌추천"]),
        description="강남역 5분 거리 프리미엄 헤어살롱. 트렌디한 스타일링과 친절한 서비스.",
    )
    db.add(blog_detail)

    order2 = AdOrder(
        merchant_id=merchant.id, type=AdOrderType.PLACE_TRAFFIC,
        status=AdOrderStatus.REQUESTED, created_by=owner.id,
    )
    db.add(order2)
    db.flush()

    place_detail = AdOrderPlaceTrafficDetail(
        order_id=order2.id,
        place_name_or_id="뷰티헤어살롱 강남점",
        search_keywords_json=json.dumps(["강남미용실", "강남헤어", "테헤란로미용실"]),
    )
    db.add(place_detail)


    db.commit()

    # ─── 13. CRM 데모 데이터 ────────────────────────────────
    seed_crm_demo(db)

    print("   Created users: admin/sales/owner/designer x2")
    print(f"   Created merchant: {merchant.name}")
    print(f"   Created 2 staff, 1 terminal, 3 PG providers")
    print(f"   Created 10 sample transactions")
    print(f"   Created 2 ad orders + 7 days of metrics")
    print(f"   Terminal API Key: {TERMINAL_API_KEY}")


def seed_crm_demo(db: Session):
    """미용실 CRM 데모 데이터를 멱등하게 시드한다.

    데모 미용실(owner@test.com 소유)에 CRM 고객이 하나도 없을 때만 채운다.
    기존 운영 DB에서도 1회 안전하게 실행 가능 (다른 미용실은 건드리지 않음)."""
    owner = db.query(User).filter(User.email == "owner@test.com").first()
    if not owner:
        return
    merchant = db.query(Merchant).filter(Merchant.owner_user_id == owner.id).first()
    if not merchant:
        return
    if db.query(CrmCustomer).filter(CrmCustomer.merchant_id == merchant.id).first():
        return  # 이미 시드됨

    if not merchant.category:
        merchant.category = "hair_salon"

    now = datetime.utcnow()
    staff_list = db.query(Staff).filter(Staff.merchant_id == merchant.id).all()
    staff_ids = [s.id for s in staff_list] or [None]

    # ─ 시술 메뉴 (카테고리 포함) ─
    services = [
        ("컷", "커트", 25000, 40), ("남성컷", "커트", 20000, 30),
        ("일반염색", "염색", 70000, 90), ("뿌리염색", "염색", 50000, 70),
        ("디지털펌", "펌", 120000, 150), ("열펌", "펌", 100000, 130),
        ("두피클리닉", "클리닉", 50000, 60), ("드라이/스타일링", "스타일링", 30000, 40),
    ]
    service_objs = []
    for nm, cat, pr, dur in services:
        sv = CrmService(merchant_id=merchant.id, name=nm, category=cat, price=pr, duration_min=dur)
        db.add(sv)
        service_objs.append(sv)

    # ─ 고객 (상세 프로필) ─
    bmonth = now.month
    customers_data = [
        {"name": "김지영", "phone": "010-2345-6789", "gender": "female", "tags": "단골,염색", "memo": "컬러 밝게 선호", "allergy": "암모니아 염모제 알레르기 (패치테스트 필수)", "hair": "모발 가늘고 손상모, 클리닉 병행 권장", "pref_svc": "뿌리염색", "bday": (bmonth, 15)},
        {"name": "박서연", "phone": "010-9871-2345", "gender": "female", "tags": "단골,VIP", "memo": "예약 시 창가자리 선호", "allergy": "", "hair": "굵은 직모, 펌 잘 풀림", "pref_svc": "디지털펌", "bday": (bmonth, 22)},
        {"name": "이민재", "phone": "010-4423-1100", "gender": "male", "tags": "일반", "memo": "", "allergy": "", "hair": "", "pref_svc": "남성컷", "bday": (3, 3)},
        {"name": "정수빈", "phone": "010-5510-2233", "gender": "female", "tags": "일반", "memo": "주말 오후 선호", "allergy": "", "hair": "반곱슬", "pref_svc": "드라이/스타일링", "bday": (7, 9)},
        {"name": "최예린", "phone": "010-7702-8890", "gender": "female", "tags": "신규", "memo": "", "allergy": "", "hair": "", "pref_svc": "일반염색", "bday": (bmonth, 5)},
        {"name": "한도윤", "phone": "010-3398-4521", "gender": "male", "tags": "휴면", "memo": "재방문 유도 필요", "allergy": "", "hair": "", "pref_svc": "컷", "bday": (11, 28)},
        {"name": "윤하늘", "phone": "010-6611-7788", "gender": "female", "tags": "휴면", "memo": "", "allergy": "두피 예민", "hair": "염색 이력 많음", "pref_svc": "두피클리닉", "bday": (5, 17)},
        {"name": "장은우", "phone": "010-2244-3366", "gender": "female", "tags": "신규,친구추천", "memo": "친구 추천 방문", "allergy": "", "hair": "", "pref_svc": "컷", "bday": (bmonth, 27)},
    ]
    customer_objs = []
    for i, cd in enumerate(customers_data):
        sid = staff_ids[i % len(staff_ids)]
        try:
            bday = date(2026 - random.randint(22, 45), cd["bday"][0], cd["bday"][1])
        except Exception:
            bday = None
        c = CrmCustomer(
            merchant_id=merchant.id,
            name=cd["name"], phone=cd["phone"], gender=cd["gender"],
            tags=cd["tags"], memo=cd["memo"],
            allergy_memo=cd["allergy"] or None, hair_memo=cd["hair"] or None,
            birthday=bday,
            assigned_staff_id=sid, preferred_staff_id=sid, preferred_service=cd["pref_svc"],
            created_at=now - timedelta(days=random.randint(10, 220)),
        )
        db.add(c)
        customer_objs.append(c)
    db.flush()

    # ─ 방문/시술 이력 (다양한 요일·시간대) ─
    visit_plan = [12, 9, 6, 5, 2, 3, 2, 1]
    service_choices = [(s.name, float(s.price)) for s in service_objs]
    for c, vcount in zip(customer_objs, visit_plan):
        if "휴면" in (c.tags or ""):
            last_offset = random.randint(65, 130)
        elif "신규" in (c.tags or ""):
            last_offset = random.randint(0, 7)
        else:
            last_offset = random.randint(1, 20)
        for v in range(vcount):
            svc_name, svc_price = random.choice(service_choices)
            vdate = now - timedelta(days=last_offset + v * random.randint(20, 40))
            vdate = vdate.replace(hour=random.choice([10, 11, 13, 14, 15, 16, 17, 18, 19]),
                                  minute=random.choice([0, 30]))
            if vdate > now:
                vdate = now - timedelta(days=1)
            db.add(CrmVisit(
                merchant_id=merchant.id, customer_id=c.id, staff_id=c.assigned_staff_id,
                service_name=svc_name, amount=svc_price, visit_date=vdate, created_at=vdate,
            ))
        pts = vcount * 2000
        c.points = pts
        db.add(CrmPointLog(merchant_id=merchant.id, customer_id=c.id, delta=pts,
                           reason="누적 적립", balance_after=pts, created_at=now - timedelta(days=last_offset)))

    # ─ 예약 (오늘 + 향후) ─
    reservation_plan = [
        (customer_objs[0], 0, 11, "뿌리염색", 70, ReservationStatus.CONFIRMED),
        (customer_objs[1], 0, 14, "디지털펌", 150, ReservationStatus.BOOKED),
        (customer_objs[2], 0, 16, "컷", 40, ReservationStatus.CONFIRMED),
        (customer_objs[3], 1, 13, "두피클리닉", 60, ReservationStatus.BOOKED),
        (customer_objs[4], 2, 15, "일반염색", 90, ReservationStatus.BOOKED),
        (customer_objs[7], 3, 10, "컷", 40, ReservationStatus.BOOKED),
    ]
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for cust, day_offset, hour, svc, dur, status in reservation_plan:
        start = today0 + timedelta(days=day_offset, hours=hour)
        db.add(CrmReservation(
            merchant_id=merchant.id, customer_id=cust.id, customer_name=cust.name, phone=cust.phone,
            staff_id=cust.assigned_staff_id, service_name=svc, reserved_at=start,
            end_at=start + timedelta(minutes=dur), duration_min=dur, status=status,
        ))

    # ─ 메시지 템플릿 ─
    templates = [
        ("예약 리마인더", MessageChannel.SMS, "reminder", "[{매장명}] {고객명}님, 예약일이 다가왔습니다. 방문 부탁드립니다 :)"),
        ("생일 축하", MessageChannel.ALIMTALK, "birthday", "[{매장명}] {고객명}님, 생일 축하드립니다! 생일 기념 10% 할인 쿠폰을 드려요."),
        ("재방문 유도", MessageChannel.SMS, "dormant", "[{매장명}] {고객명}님, 오랜만이에요! 보유 포인트 {포인트}P로 더 알뜰하게 관리받으세요."),
        ("방문 감사", MessageChannel.SMS, "thanks", "[{매장명}] {고객명}님, 오늘 방문 감사합니다. 다음에도 예쁘게 관리해 드릴게요!"),
    ]
    for nm, ch, cat, body in templates:
        db.add(CrmMessageTemplate(merchant_id=merchant.id, name=nm, channel=ch, category=cat, body=body))

    # ─ 쿠폰 (VIP/휴면 대상 예시) ─
    db.add(CrmCoupon(merchant_id=merchant.id, customer_id=customer_objs[1].id, name="VIP 15% 할인",
                     discount_type="percent", value=15, expires_at=(now + timedelta(days=60)).date(), memo="VIP 감사 쿠폰"))
    db.add(CrmCoupon(merchant_id=merchant.id, customer_id=customer_objs[5].id, name="재방문 1만원 할인",
                     discount_type="amount", value=10000, expires_at=(now + timedelta(days=30)).date(), memo="휴면 고객 컴백"))

    db.commit()
    print(f"   Created CRM demo: {len(customer_objs)} customers, {len(service_objs)} services, visits, reservations, templates, coupons")


def seed_general_owner(db: Session):
    """일반 업종 테스트 원장 계정을 멱등하게 시드한다.

    owner_general@test.com — business_type='general', CRM 없음.
    기존 뷰티 업종 owner@test.com 과 구분해 일반 업종 테스트용으로 사용.
    """
    if db.query(User).filter(User.email == "owner_general@test.com").first():
        return  # 이미 시드됨

    pw_hash = pwd_context.hash(TEST_PASSWORD)

    owner_g = User(
        email="owner_general@test.com",
        password_hash=pw_hash,
        name="김일반",
        role=UserRole.OWNER,
        business_type="general",  # CRM 비활성화 — 일반 업종 테스트용
    )
    db.add(owner_g)
    db.flush()

    merchant_g = Merchant(
        name="일반상점 테스트점",
        owner_user_id=owner_g.id,
        business_no="987-65-43210",
        address="서울 마포구 홍대로 456",
        phone="02-9876-5432",
    )
    db.add(merchant_g)
    db.flush()

    from app.services import plan_service
    plan_service.ensure_default_plan(db, merchant_g.id)

    db.commit()
    print("   Created general owner: owner_general@test.com (일반상점 테스트점, CRM 없음)")


# ─── 플랜 시드 ──────────────────────────────────────────────

# (code, name, 수수료율%, 블로그 일/월, 영수증 일/월, 방문 일/월, 저장 일/월, 쇼츠 일/월)
# 광고 월 목표 건수는 모두 0 으로 둔다.
# 이 수치가 곧 매일 자동 집행되는 양이고 그대로 비용이 되므로, 최고관리자가
# [플랜 관리] 화면에서 직접 입력하기 전에는 아무것도 집행되지 않게 한다.
# 수수료율만 기본값을 준다.
DEFAULT_PLANS = [
    ("basic",    "베이직",   5.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("standard", "스탠다드", 5.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("premium",  "프리미엄", 4.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
]


def seed_plans(db: Session):
    """플랜 3종을 멱등하게 시드하고, 플랜이 없는 기존 가맹점에 베이직을 배정한다.

    이미 존재하는 플랜의 값은 덮어쓰지 않는다 (어드민이 수정한 값 보존).
    """
    created = 0
    for (code, name, fee, br_d, br_m, rr_d, rr_m, pt_d, pt_m, ps_d, ps_m, sh_d, sh_m) in DEFAULT_PLANS:
        if db.query(Plan).filter(Plan.code == code).first():
            continue
        db.add(Plan(
            code=code, name=name, merchant_fee_rate=fee,
            blog_review_daily=br_d, blog_review_monthly=br_m,
            receipt_review_daily=rr_d, receipt_review_monthly=rr_m,
            place_traffic_daily=pt_d, place_traffic_monthly=pt_m,
            place_save_daily=ps_d, place_save_monthly=ps_m,
            shorts_daily=sh_d, shorts_monthly=sh_m,
        ))
        created += 1
    db.flush()

    basic = db.query(Plan).filter(Plan.code == "basic").first()
    assigned = 0
    if basic:
        assigned_ids = {row[0] for row in db.query(MerchantPlan.merchant_id).distinct()}
        for merchant in db.query(Merchant).all():
            if merchant.id in assigned_ids:
                continue
            db.add(MerchantPlan(merchant_id=merchant.id, plan_id=basic.id))
            assigned += 1

    db.commit()
    if created or assigned:
        print(f"   Created {created} plans, assigned 베이직 to {assigned} merchants")
