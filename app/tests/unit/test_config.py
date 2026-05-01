from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(COPILOT_MODEL="gpt-5-mini")
    assert settings.APP_NAME == "AutomaWeb"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./app.db"
    assert settings.COPILOT_MODEL == "gpt-5-mini"
    assert settings.COPILOT_BASE_URL == "https://api.githubcopilot.com"
    assert settings.CACHE_TTL_SECONDS == 300
    assert settings.STATIC_DIR == "app/static"


def test_settings_custom_values() -> None:
    settings = Settings(
        APP_NAME="CustomApp",
        DATABASE_URL="postgresql://test",
        COPILOT_MODEL="gpt-5",
        COPILOT_BASE_URL="https://custom.copilot.api",
        CACHE_TTL_SECONDS=600,
        STATIC_DIR="custom/static",
    )
    assert settings.APP_NAME == "CustomApp"
    assert settings.DATABASE_URL == "postgresql://test"
    assert settings.COPILOT_MODEL == "gpt-5"
    assert settings.COPILOT_BASE_URL == "https://custom.copilot.api"
    assert settings.LLM_HEALTH_FALLBACK_WINDOW_SECONDS == 300
    assert settings.CACHE_TTL_SECONDS == 600
    assert settings.STATIC_DIR == "custom/static"
