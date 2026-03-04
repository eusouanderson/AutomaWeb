from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(GROQ_API_KEY="test")
    assert settings.APP_NAME == "AutomaWeb"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./app.db"
    assert settings.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert settings.GROQ_TIMEOUT_SECONDS == 30
    assert settings.GROQ_MAX_RETRIES == 3
    assert settings.CACHE_TTL_SECONDS == 300
    assert settings.STATIC_DIR == "app/static"


def test_settings_custom_values() -> None:
    settings = Settings(
        APP_NAME="CustomApp",
        DATABASE_URL="postgresql://test",
        GROQ_API_KEY="custom_key",
        GROQ_MODEL="custom-model",
        GROQ_TIMEOUT_SECONDS=60,
        GROQ_MAX_RETRIES=5,
        CACHE_TTL_SECONDS=600,
        STATIC_DIR="custom/static"
    )
    assert settings.APP_NAME == "CustomApp"
    assert settings.DATABASE_URL == "postgresql://test"
    assert settings.GROQ_API_KEY == "custom_key"
    assert settings.GROQ_MODEL == "custom-model"
    assert settings.GROQ_TIMEOUT_SECONDS == 60
    assert settings.GROQ_MAX_RETRIES == 5
    assert settings.CACHE_TTL_SECONDS == 600
    assert settings.STATIC_DIR == "custom/static"
