from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables and an optional .env file."""

    database_url: str = "sqlite:///./dain.db"
    institutional_email_domain: str = "du.ac.bd"
    app_env: str = "development"
    debug: bool = True
    
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    smtp_use_ssl: bool = False
    verification_token_ttl_minutes: int = 60
    session_token_ttl_minutes: int = 1440
    expose_verification_token_in_response: bool = True
    media_root: str = "uploads"
    max_upload_size_bytes: int = 5_242_880
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
