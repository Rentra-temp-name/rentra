from functools import lru_cache
from typing import Optional
from PIL import ImageColor
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.
    
    Fails on startup if any required environment variable is missing or empty.
    Secrets are masked in string representations to prevent accidental leakage.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "apps/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(
        ...,
        min_length=1,
        description="Postgres connection string through pooler for rentra_api role",
    )
    SUPABASE_URL: str = Field(
        ...,
        min_length=1,
        description="Supabase project URL",
    )
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ...,
        min_length=1,
        description="Supabase service role key (Storage/Auth admin only, never DB queries)",
    )
    FRONTEND_ORIGIN: str = Field(
        ...,
        min_length=1,
        description="Allowed frontend origin for CORS",
    )
    TEST_DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Local test database URL (pointing at local Postgres, used by tests only)",
    )
    READ_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1)
    READ_RATE_LIMIT_ANONYMOUS: int = Field(default=60, ge=1)
    READ_RATE_LIMIT_USER: int = Field(default=120, ge=1)
    WRITE_RATE_LIMIT_USER: int = Field(default=20, ge=1)
    PHOTO_BAR_COLOR: str = "black"
    LISTINGS_PAGE_MAX: int = Field(default=50, ge=1, le=50)
    MAP_RESPONSE_CAP: int = Field(default=500, ge=1)
    MAP_CLUSTER_ZOOM: float = Field(default=10.0, ge=0, le=22)
    TRUSTED_PROXY_CIDRS: str = ""
    LOG_LEVEL: str = "INFO"
    ENV: str = "development"
    SERVICE_VERSION: str = "0.1.0"
    SENTRY_DSN: Optional[str] = None
    METRICS_TOKEN: Optional[str] = None

    @field_validator(
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "FRONTEND_ORIGIN",
    )
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Environment variable must not be empty")
        return v.strip()

    @field_validator("PHOTO_BAR_COLOR")
    @classmethod
    def validate_photo_bar_color(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("PHOTO_BAR_COLOR must not be empty")
        value = value.strip()
        try:
            ImageColor.getrgb(value)
        except ValueError as exc:
            raise ValueError("PHOTO_BAR_COLOR must be a valid Pillow color") from exc
        return value

    def __repr__(self) -> str:
        return (
            f"Settings("
            f"DATABASE_URL='***', "
            f"SUPABASE_URL={self.SUPABASE_URL!r}, "
            f"SUPABASE_SERVICE_ROLE_KEY='***', "
            f"FRONTEND_ORIGIN={self.FRONTEND_ORIGIN!r}, "
            f"TEST_DATABASE_URL={'***' if self.TEST_DATABASE_URL else None!r}"
            f")"
        )

    def __str__(self) -> str:
        return self.__repr__()


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance, reading from environment."""
    return Settings()
