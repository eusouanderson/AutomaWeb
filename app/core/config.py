from __future__ import annotations

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "AutomaWeb"
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TIMEOUT_SECONDS: int = 30
    GROQ_MAX_RETRIES: int = 3
    GROQ_CA_BUNDLE: str | None = None
    GROQ_INSECURE_SKIP_VERIFY: bool = False
    CACHE_TTL_SECONDS: int = 300
    SCAN_CACHE_TTL_SECONDS: int = 3600
    STATIC_DIR: str = "app/static"
    AI_VALIDATION_ENABLED: bool = True
    AI_DEBUG: bool = False
    AI_DEBUG_LOG_PATH: str = "logs/ai_debug.log"
    # When True, opens the real page to count locator matches (adds latency).
    # Set to False in CI or when page access is unavailable.
    AI_LIVE_CHECK_ENABLED: bool = False
    AI_LIVE_CHECK_TIMEOUT_SECONDS: int = 15


settings = Settings()
