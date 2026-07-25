from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # Database
    DB_HOST: str = "db"
    DB_PORT: int = 3306
    DB_USER: str = "adpay"
    DB_PASSWORD: str = "adpay_secret_2024"
    DB_NAME: str = "adpay"

    # JWT
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Encryption
    ENCRYPTION_KEY: str = "c2VjcmV0LWVuY3J5cHRpb24ta2V5LWZvci1hZHBheQ=="

    # OAuth
    KAKAO_CLIENT_ID: str = ""
    KAKAO_CLIENT_SECRET: str = ""
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_BASE: str = "http://localhost:8000"

    # App
    APP_ENV: str = "development"
    DEV_MODE: bool = True

    # Allow override for local dev (SQLite)
    DATABASE_URL_OVERRIDE: str = ""

    # ONGI (위아오너) — 내통장 결제 연동
    # pay.ongi.site는 해시 라우터를 사용 — 결제창 URL은 https://pay.ongi.site/#/qr/{qr_token}?... 형태
    ONGI_PAY_BASE_URL: str = "https://pay.ongi.site"
    ONGI_QR_TOKEN: str = ""  # 가맹점별 ONGI QR 토큰 (위아오너에서 발급)
    ONGI_CALLBACK_URL: str = ""  # 결제 완료 콜백 URL (https 절대주소). 미설정 시 자체 도메인 자동 사용
    ONGI_PUBLIC_BASE_URL: str = ""  # 콜백 자동 생성용 자체 공개 도메인 (예: https://adpay.example.com)

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
