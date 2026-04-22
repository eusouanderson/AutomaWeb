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
    LLM_HEALTH_FALLBACK_WINDOW_SECONDS: int = 300
    LLM_MAX_PROMPT_CHARS: int = 6000
    LLM_MAX_CONTEXT_CHARS: int = 12000
    LLM_MAX_PAGE_STRUCTURE_CHARS: int = 24000
    LLM_DOM_CHUNKING_ENABLED: bool = True
    LLM_DOM_CHUNK_TARGET_CHARS: int = 12000
    LLM_DOM_CHUNK_MAX_PARTS: int = 8

    # Chunked generation settings
    GROQ_CHUNK_TOKEN_BUDGET: int = 100000
    LLM_MAX_CHUNKS_PER_REQUEST: int = 10
    LLM_MAX_CONCURRENT_CHUNKS: int = 3
    LLM_CHUNK_RESERVE_CHARS: int = 500

    # DOM preprocessing settings
    DOM_MAX_TEXT_PER_ELEMENT: int = 200
    DOM_CACHE_MAX_ENTRIES: int = 100

    CACHE_TTL_SECONDS: int = 300
    SCAN_CACHE_TTL_SECONDS: int = 3600
    STATIC_DIR: str = "app/static"
    AI_VALIDATION_ENABLED: bool = True
    AI_DEBUG: bool = False
    AI_DEBUG_LOG_PATH: str = "logs/ai_debug.log"
    AI_LIVE_CHECK_ENABLED: bool = False
    AI_LIVE_CHECK_TIMEOUT_SECONDS: int = 15


settings = Settings()
