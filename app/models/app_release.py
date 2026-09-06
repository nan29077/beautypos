"""AppRelease — 안드로이드 앱 배포본(APK) 메타데이터.

관리자가 새 APK를 업로드할 때마다 1행. 앱은 실행 시 최신 활성 버전의
version_code 를 자신의 BuildConfig.VERSION_CODE 와 비교해 업데이트를 판단한다.

APK 파일 자체는 DB 가 아니라 서버 디스크(uploads/apk/)에 저장하고,
여기에는 파일명·크기·버전·변경사항만 둔다. 다운로드는 전용 라우트가
FileResponse 로 서빙한다.

서명 주의
    업로드하는 APK 는 반드시 릴리스 keystore 로 서명돼야 한다. 서명이 다르면
    (예: 디버그 키) 기존 설치본이 업데이트를 거부한다. 이는 운영 규칙이며
    서버가 강제하지는 않는다.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, ForeignKey
)

from app.database import Base


class AppRelease(Base):
    __tablename__ = "app_releases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_code = Column(Integer, nullable=False, unique=True, index=True)  # 앱 비교 기준(정수 증가)
    version_name = Column(String(50), nullable=False)                        # 표시용 (예: 1.1.0)
    apk_filename = Column(String(255), nullable=False)                       # uploads/apk/ 내 저장 파일명
    file_size = Column(Integer, nullable=False, default=0)                   # 바이트
    notes = Column(Text, nullable=True)                                      # 변경사항(사용자 안내 문구)
    is_mandatory = Column(Boolean, nullable=False, default=False)            # 강제 업데이트 여부
    is_active = Column(Boolean, nullable=False, default=True)                # 배포 노출 스위치(롤백 대비)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
