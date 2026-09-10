from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "demo"
    APP_NAME: str = "PharmaFlow AI"

    # If unset, fall back to a local SQLite file so the app always runs offline.
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'pharmaflow_dev.db').as_posix()}"

    JWT_SECRET: str = "dev-insecure-change-me-0000000000000000"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720

    # Registry signing keys are stored here (gitignored). One Ed25519 key per license.
    KEYS_DIR: str = str(BASE_DIR / "app" / "keys")
    UPLOADS_DIR: str = str(BASE_DIR / "uploads")

    # Business rules (configurable — never hardcode regulatory numbers into logic)
    EXPIRY_ALERT_DAYS: int = 60
    QTY_TOLERANCE_PCT: float = 2.0
    QTY_TOLERANCE_MIN_UNITS: int = 2
    RETAILER_RETURN_WINDOW_DAYS: int = 30
    MANUFACTURER_DISPOSAL_WINDOW_DAYS: int = 30
    REENTRY_TARGET_SECONDS: float = 5.0

    # Optional external integrations (all mocked by default)
    MAPBOX_TOKEN: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMS_PROVIDER_URL: str = ""

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


_SQLITE_DEFAULT = f"sqlite:///{(BASE_DIR / 'pharmaflow_dev.db').as_posix()}"


def _normalize_db_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return _SQLITE_DEFAULT
    # Accept the raw strings Postgres hosts (Supabase, Neon, Heroku, ...) hand out and
    # bind them to the installed driver (psycopg v3).
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.DATABASE_URL = _normalize_db_url(s.DATABASE_URL)
    Path(s.KEYS_DIR).mkdir(parents=True, exist_ok=True)
    Path(s.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
