"""
SystemConfig — 시스템 전역 설정 (Feature Flags 등)
관리자가 ON/OFF 할 수 있는 기능 스위치를 저장합니다.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.database import Base


class SystemConfig(Base):
    """키-값 기반 시스템 설정 테이블"""
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(String(500), nullable=True)
    is_enabled = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── 기본 설정 키 정의 ─────────────────────────────────────
AD_ORDER_MGMT_ENABLED = "ad_order_mgmt_enabled"       # 광고 주문 관리 마스터 스위치 ON/OFF
AD_BLOG_ENABLED = "ad_blog_enabled"                    # 블로그 배포 광고 ON/OFF
AD_PLACE_TRAFFIC_ENABLED = "ad_place_traffic_enabled"  # 플레이스 유입 광고 ON/OFF

# ─── 영업수수료 표시 여부 (역할별) ──────────────────────────
# 최고관리자가 ON/OFF. 각 계정은 자기 하위 단계의 영업수수료를 ON일 때만 조회.
# 최고관리자(ADMIN)는 항상 전체 조회 가능.
COMMISSION_VISIBLE_TO_SALES = "commission_visible_to_sales"        # 딜러(영업)에게 표시
COMMISSION_VISIBLE_TO_OWNER = "commission_visible_to_owner"        # 사장님에게 표시
COMMISSION_VISIBLE_TO_DESIGNER = "commission_visible_to_designer"  # 디자이너에게 표시
