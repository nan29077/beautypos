"""매장별 리워드팝 광고 집행 설정.

리워드팝 POST /ads 호출 시 필요한 광고 타입별 파라미터를 매장별로 저장한다.
- place_traffic: missionCategory=VISIT, missionAction 선택, keywordMode 선택
- blog_review: 추후 리워드팝 명세 확인 후 추가
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship

from app.database import Base

# missionCategory 허용값
MISSION_CATEGORIES = [
    ("VISIT", "방문하기"),
    ("SAVE", "저장하기"),
]
MISSION_CATEGORY_CODES = [c for c, _ in MISSION_CATEGORIES]

# missionAction 허용값 (카테고리별로 다름)
MISSION_ACTIONS = {
    "VISIT": [
        ("WRITE_REVIEW", "방문자 리뷰"),
        ("FIND_PATH", "길찾기"),
        ("SPOT_CHECK", "명소확인"),
        ("RANDOM_MISSION", "랜덤 미션"),
        ("BUSINESS_HOURS", "영업시간"),
        ("INTRODUCTION", "소개"),
        ("WALK_COUNT", "도보수"),
        ("BUS_STATION", "정류장"),
    ],
    "SAVE": [
        ("PLACE_SAVE", "플레이스 저장"),
    ],
}
MISSION_ACTION_CODES = [code for actions in MISSION_ACTIONS.values() for code, _ in actions]

# keywordMode 허용값
KEYWORD_MODES = [
    ("MANUAL", "직접 입력"),
    ("AUTO", "자동 추출"),
]
KEYWORD_MODE_CODES = [c for c, _ in KEYWORD_MODES]

# AUTO 모드 키워드 수 허용값
AUTO_COUNT_OPTIONS = [10, 30, 50]

# 블로그 포스트 유형 허용값
BLOG_POST_TYPES = ["INFO", "REVIEW", "FREE"]

# 블로그 placeUrl 입력 안내 문구
BLOG_PLACE_URL_GUIDE = (
    "네이버 지도 앱 또는 모바일 웹에서 업체 검색 후 업체 상세 페이지 URL을 복사하세요. "
    "예시: https://m.place.naver.com/restaurant/1750900108/home — "
    "PC 네이버 지도 URL(map.naver.com)은 사용 불가하며, "
    "반드시 m.place.naver.com으로 시작하는 모바일 URL을 입력해야 합니다. "
    "네이버 앱에서는 업체명 우측 공유 버튼을 눌러 링크를 복사하세요."
)


class MerchantAdConfig(Base):
    """매장별 광고 타입별 리워드팝 집행 설정.

    광고 집행 시 리워드팝 POST /ads 에 보낼 파라미터 (missionCategory, missionAction,
    keywordMode 등)를 매장·광고타입 조합마다 저장한다.
    설정이 없는 광고 타입은 SKIP_NO_CONFIG 로 건너뛴다.
    """
    __tablename__ = "merchant_ad_configs"
    __table_args__ = (
        UniqueConstraint("merchant_id", "ad_type", name="uq_merchant_ad_config"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    ad_type = Column(String(30), nullable=False)          # place_traffic, blog_review 등
    mission_category = Column(String(20), nullable=True)  # VISIT, SAVE
    mission_action = Column(String(30), nullable=True)    # WRITE_REVIEW, FIND_PATH 등
    keyword_mode = Column(String(10), nullable=False, default="MANUAL")  # MANUAL, AUTO
    auto_count = Column(Integer, nullable=True)           # AUTO 모드 키워드 수 (10/30/50)

    # 블로그 전용 필드 (blog_review 자동 월별 접수용 — POST /ads/cloblog)
    blog_place_url = Column(String(500), nullable=True)    # 네이버 모바일 플레이스 URL (m.place.naver.com)
    blog_place_name = Column(String(100), nullable=True)   # 업체명
    blog_main_keyword = Column(String(100), nullable=True) # 필수 키워드 1개
    blog_work_keywords = Column(Text, nullable=True)       # 작업 키워드 1~5개 (JSON 배열)
    blog_tags = Column(Text, nullable=True)                # 해시태그 5개 이상 (JSON 배열)
    blog_post_type = Column(String(10), nullable=True)     # INFO / REVIEW / FREE
    blog_store_address = Column(String(200), nullable=True) # 매장 주소
    blog_store_phone = Column(String(30), nullable=True)   # 대표번호
    blog_extra_link = Column(String(500), nullable=True)   # 추가 링크

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
