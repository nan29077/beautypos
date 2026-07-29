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
    RANK_SCHEDULER_ENABLED: bool = True
    RANK_SCHEDULER_HOUR: int = 14
    RANK_SCHEDULER_MINUTE: int = 0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.APP_ENV.lower() in {"production", "prod"}:
            if self.DEV_MODE:
                raise ValueError("DEV_MODE must be false in production")
            if self.JWT_SECRET_KEY in {"change-me", "development-only-change-me"} or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be a unique value of at least 32 characters in production")
            if self.ENCRYPTION_KEY == "c2VjcmV0LWVuY3J5cHRpb24ta2V5LWZvci1hZHBheQ==":
                raise ValueError("ENCRYPTION_KEY must be replaced in production")
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
