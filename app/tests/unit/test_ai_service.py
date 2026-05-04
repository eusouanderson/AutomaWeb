"""Unit tests for app/services/ai_service.py"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(
    token_return="tok-abc",
    models_return=None,
    generate_return="generated text",
):
    """Return a CopilotService with all dependencies mocked."""
    from app.services.ai_service import CopilotService

    service = CopilotService.__new__(CopilotService)
    service.base_url = "https://api.githubcopilot.com"
    service._logger = MagicMock()

    # auth_manager
    service.auth_manager = MagicMock()
    service.auth_manager.get_valid_access_token = AsyncMock(return_value=token_return)

    # models_client
    service.models_client = MagicMock()
    service.models_client.fetch_models = AsyncMock(return_value=models_return or [])

    # provider
    service.provider = MagicMock()
    service.provider.run_model = AsyncMock(return_value=generate_return)

    # http_client
    service.http_client = MagicMock()

    return service


# ---------------------------------------------------------------------------
# get_valid_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_valid_token_delegates_to_auth_manager():
    service = _make_service(token_return="my-token")
    result = await service.get_valid_token()
    assert result == "my-token"
    service.auth_manager.get_valid_access_token.assert_awaited_once()


# ---------------------------------------------------------------------------
# fetch_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_models_delegates_to_models_client():
    from app.llm.copilot_models import CopilotModelInfo

    fake_models = [MagicMock(spec=CopilotModelInfo)]
    service = _make_service(models_return=fake_models)
    result = await service.fetch_models()
    assert result == fake_models
    service.models_client.fetch_models.assert_awaited_once_with(
        service.base_url, force_refresh=False
    )


@pytest.mark.asyncio
async def test_fetch_models_force_refresh():
    service = _make_service()
    await service.fetch_models(force_refresh=True)
    service.models_client.fetch_models.assert_awaited_once_with(
        service.base_url, force_refresh=True
    )


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_uses_provided_model():
    service = _make_service(generate_return="output")
    result = await service.generate(prompt="hello", model="gpt-4o")
    assert result == "output"
    service.provider.run_model.assert_awaited_once_with(
        "gpt-4o",
        [{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=None,
    )


@pytest.mark.asyncio
async def test_generate_falls_back_to_env_model(monkeypatch):
    monkeypatch.setenv("COPILOT_MODEL", "env-model")
    service = _make_service()
    await service.generate(prompt="hi")
    call_args = service.provider.run_model.call_args
    assert call_args[0][0] == "env-model"


@pytest.mark.asyncio
async def test_generate_falls_back_to_default_when_no_env(monkeypatch):
    from app.core.config import settings

    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    service = _make_service()
    await service.generate(prompt="hi")
    call_args = service.provider.run_model.call_args
    assert call_args[0][0] == settings.COPILOT_MODEL


@pytest.mark.asyncio
async def test_generate_includes_system_prompt():
    service = _make_service()
    await service.generate(prompt="q", system_prompt="You are helpful.")
    messages = service.provider.run_model.call_args[0][1]
    assert messages[0] == {"role": "system", "content": "You are helpful."}
    assert messages[1] == {"role": "user", "content": "q"}


@pytest.mark.asyncio
async def test_generate_without_system_prompt():
    service = _make_service()
    await service.generate(prompt="q")
    messages = service.provider.run_model.call_args[0][1]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


@pytest.mark.asyncio
async def test_generate_passes_temperature_and_max_tokens():
    service = _make_service()
    await service.generate(prompt="q", temperature=0.7, max_tokens=512)
    _, kwargs = service.provider.run_model.call_args
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_tokens"] == 512


# ---------------------------------------------------------------------------
# generate_robot_test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_robot_test_basic():
    service = _make_service(generate_return="*** Test Cases ***")
    result = await service.generate_robot_test(prompt="Test login")
    assert result == "*** Test Cases ***"
    assert service.provider.run_model.await_count == 1


@pytest.mark.asyncio
async def test_generate_robot_test_appends_context():
    service = _make_service()
    await service.generate_robot_test(prompt="Test X", context="extra ctx")
    messages = service.provider.run_model.call_args[0][1]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "extra ctx" in user_msg["content"]
    assert "Contexto:" in user_msg["content"]


@pytest.mark.asyncio
async def test_generate_robot_test_without_context():
    service = _make_service()
    await service.generate_robot_test(prompt="Test X")
    messages = service.provider.run_model.call_args[0][1]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert user_msg["content"] == "Test X"


@pytest.mark.asyncio
async def test_generate_robot_test_with_page_structure():
    service = _make_service()
    page_structure = {"title": "Login", "elements": [{"type": "input"}]}
    await service.generate_robot_test(prompt="Test", page_structure=page_structure)
    system_messages = service.provider.run_model.call_args[0][1]
    sys_msg = next(m for m in system_messages if m["role"] == "system")
    assert "Login" in sys_msg["content"]
    assert "Estrutura da página" in sys_msg["content"]


@pytest.mark.asyncio
async def test_generate_robot_test_without_page_structure():
    service = _make_service()
    await service.generate_robot_test(prompt="Test")
    messages = service.provider.run_model.call_args[0][1]
    sys_msg = next((m for m in messages if m["role"] == "system"), None)
    assert sys_msg is not None
    assert "Estrutura da página" not in sys_msg["content"]


@pytest.mark.asyncio
async def test_generate_robot_test_keeps_execution_contract_with_custom_system_prompt():
    service = _make_service()
    await service.generate_robot_test(
        prompt="Test",
        system_prompt="Use linguagem objetiva e foco em fluxo feliz.",
    )
    messages = service.provider.run_model.call_args[0][1]
    sys_msg = next(m for m in messages if m["role"] == "system")
    assert "New Browser -> New Context -> Set Browser Timeout 30s -> New Page" in sys_msg["content"]
    assert "Use linguagem objetiva e foco em fluxo feliz." in sys_msg["content"]


@pytest.mark.asyncio
async def test_generate_robot_test_uses_zero_temperature():
    service = _make_service()
    await service.generate_robot_test(prompt="Test")
    _, kwargs = service.provider.run_model.call_args
    assert kwargs["temperature"] == 0.0


# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_connection_success():
    service = _make_service(token_return="valid-token")
    result = await service.check_connection()
    assert result["ok"] is True
    assert result["has_token"] is True
    assert "message" in result


@pytest.mark.asyncio
async def test_check_connection_failure():
    service = _make_service()
    service.auth_manager.get_valid_access_token = AsyncMock(
        side_effect=Exception("auth failed")
    )
    result = await service.check_connection()
    assert result["ok"] is False
    assert "auth failed" in result["error"]
    assert "message" in result


# ---------------------------------------------------------------------------
# get_copilot_service (singleton)
# ---------------------------------------------------------------------------


def test_get_copilot_service_returns_instance():
    import app.services.ai_service as ai_mod

    ai_mod._copilot_service = None  # reset
    svc = ai_mod.get_copilot_service()
    from app.services.ai_service import CopilotService
    assert isinstance(svc, CopilotService)
    # Second call returns same instance
    assert ai_mod.get_copilot_service() is svc
    ai_mod._copilot_service = None  # cleanup


def test_get_copilot_service_uses_enterprise_env(monkeypatch):
    import app.services.ai_service as ai_mod

    ai_mod._copilot_service = None
    monkeypatch.setenv("COPILOT_ENTERPRISE_URL", "https://enterprise.example.com")
    svc = ai_mod.get_copilot_service()
    assert svc.auth_manager.enterprise_url == "https://enterprise.example.com"
    ai_mod._copilot_service = None  # cleanup


# ---------------------------------------------------------------------------
# initialize_copilot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_copilot_resets_singleton():
    import app.services.ai_service as ai_mod
    from app.services.ai_service import CopilotService

    old = MagicMock()
    ai_mod._copilot_service = old

    svc = await ai_mod.initialize_copilot(base_url="https://custom.api.com")
    assert isinstance(svc, CopilotService)
    assert ai_mod._copilot_service is svc
    assert svc.base_url == "https://custom.api.com"
    ai_mod._copilot_service = None  # cleanup


@pytest.mark.asyncio
async def test_initialize_copilot_defaults():
    import app.services.ai_service as ai_mod
    from app.services.ai_service import CopilotService, DEFAULT_BASE_URL

    ai_mod._copilot_service = None
    svc = await ai_mod.initialize_copilot()
    assert isinstance(svc, CopilotService)
    assert svc.base_url == DEFAULT_BASE_URL
    ai_mod._copilot_service = None  # cleanup
