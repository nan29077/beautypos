from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DB_HOST: str = "db"
    DB_PORT: int = 3306
    DB_USER: str = "adpay"
    DB_PASSWORD: str = "adpay_secret_2024"
    DB_NAME: str = "adpay"

    # JWT
    JWT_SECRET_KEY: str = "development-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Encryption
    ENCRYPTION_KEY: str = "c2VjcmV0LWVuY3J5cHRpb24ta2V5LWZvci1hZHBheQ=="

    # 단말기 API 키 지문(HMAC) 전용 키.
    # 비워두면 하위 호환을 위해 JWT_SECRET_KEY 를 쓰지만, 운영에서는 따로 두어야
    # JWT 서명 키가 유출돼도 단말기 지문을 역산할 수 없다. (terminal_fingerprint_key 참조)
    TERMINAL_FINGERPRINT_KEY: str = ""

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
    DEV_MODE: bool = False
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Allow override for local dev (SQLite)
    DATABASE_URL_OVERRIDE: str = ""

    # 플레이스 순위 자동 수집 스케줄러 (한국 시간 기준)
    # 광고 자동 집행(14시)보다 먼저 돌아야 그날의 기준선이 남는다.
    RANK_SCHEDULER_ENABLED: bool = True
    RANK_SCHEDULER_HOUR: int = 12
    RANK_SCHEDULER_MINUTE: int = 0

    # 광고 자동 집행 스케줄러. 집행 시각은 관리자 화면(리워드팝 연동 설정)에서 정한다.
    AD_DISPATCH_SCHEDULER_ENABLED: bool = True

    # 리워드팝 드라이런 강제 스위치.
    # 미설정(None)이면 관리자 화면에 저장된 값을 따르고, true/false 를 주면 그 값이 우선한다.
    REWARDPOP_DRY_RUN: Optional[bool] = None

    # 온기 결제 동기화 스케줄러. 폴링 주기는 관리자 화면(온기 연동 설정)에서 정한다.
    ONGI_SYNC_ENABLED: bool = True

    # 로그인 실패 제한 — 같은 계정/IP 로 N 회 연속 실패하면 일정 시간 잠근다.
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 300

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def terminal_fingerprint_key(self) -> str:
        """단말기 지문 HMAC 키. 미설정이면 JWT_SECRET_KEY 로 하위 호환한다."""
        return self.TERMINAL_FINGERPRINT_KEY.strip() or self.JWT_SECRET_KEY

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.APP_ENV.lower() in {"production", "prod"}:
            if self.DEV_MODE:
                raise ValueError("DEV_MODE must be false in production")
            if self.JWT_SECRET_KEY in {"change-me", "development-only-change-me"} or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be a unique value of at least 32 characters in production")
            if self.ENCRYPTION_KEY == "c2VjcmV0LWVuY3J5cHRpb24ta2V5LWZvci1hZHBheQ==":
                raise ValueError("ENCRYPTION_KEY must be replaced in production")
            insecure_db_passwords = {"", "adpay_secret_2024", "adpay", "password"}
            if not self.DATABASE_URL_OVERRIDE and self.DB_PASSWORD in insecure_db_passwords:
                raise ValueError("DB_PASSWORD must be replaced with a unique value in production")
            if "adpay_secret_2024" in self.DATABASE_URL:
                raise ValueError("Default DB password must not be used in production")
            if self.TERMINAL_FINGERPRINT_KEY.strip() and len(self.TERMINAL_FINGERPRINT_KEY.strip()) < 32:
                raise ValueError("TERMINAL_FINGERPRINT_KEY must be at least 32 characters in production")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
        return self

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
