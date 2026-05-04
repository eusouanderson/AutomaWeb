"""Unit tests for app/llm/copilot_adapter.py"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(service=None):
    """Return a CopilotServiceAdapter with a mocked _service."""
    from app.llm.copilot_adapter import CopilotServiceAdapter

    adapter = CopilotServiceAdapter.__new__(CopilotServiceAdapter)
    adapter._last_health_ok_at = None
    adapter._last_health_error = None
    adapter._service = service or MagicMock()
    return adapter


# ---------------------------------------------------------------------------
# __init__ — lines 24-28
# ---------------------------------------------------------------------------


def test_init_creates_adapter_with_service():
    from app.llm.copilot_adapter import CopilotServiceAdapter
    from app.services.ai_service import CopilotService

    with patch("app.services.ai_service.get_copilot_service") as mock_get:
        mock_svc = MagicMock(spec=CopilotService)
        mock_get.return_value = mock_svc
        adapter = CopilotServiceAdapter()

    assert adapter._service is mock_svc
    assert adapter._last_health_ok_at is None
    assert adapter._last_health_error is None


# ---------------------------------------------------------------------------
# check_api_health — ok branch
# ---------------------------------------------------------------------------


def test_check_api_health_ok():
    import asyncio

    svc = MagicMock()
    svc.check_connection = AsyncMock(return_value={"ok": True})
    adapter = _make_adapter(svc)

    with patch("asyncio.run", side_effect=lambda coro: asyncio.get_event_loop().run_until_complete(coro)):
        result = adapter.check_api_health()

    assert result["ok"] is True
    assert result["source"] == "live"
    assert result["error"] is None
    assert adapter._last_health_error is None
    assert adapter._last_health_ok_at is not None


def test_check_api_health_not_ok():
    import asyncio

    svc = MagicMock()
    svc.check_connection = AsyncMock(return_value={"ok": False, "error": "no token"})
    adapter = _make_adapter(svc)
    adapter._last_health_ok_at = 1_700_000_000.0

    with patch("asyncio.run", side_effect=lambda coro: asyncio.get_event_loop().run_until_complete(coro)):
        result = adapter.check_api_health()

    assert result["ok"] is False
    assert result["error"] == "no token"
    assert result["last_success_epoch"] == 1_700_000_000
    assert adapter._last_health_error == "no token"


def test_check_api_health_not_ok_no_previous_success():
    import asyncio

    svc = MagicMock()
    svc.check_connection = AsyncMock(return_value={"ok": False})
    adapter = _make_adapter(svc)

    with patch("asyncio.run", side_effect=lambda coro: asyncio.get_event_loop().run_until_complete(coro)):
        result = adapter.check_api_health()

    assert result["last_success_epoch"] is None


def test_check_api_health_exception():
    adapter = _make_adapter()

    with patch("asyncio.run", side_effect=RuntimeError("no event loop")):
        result = adapter.check_api_health()

    assert result["ok"] is False
    assert "RuntimeError" in result["error"]
    assert result["last_success_epoch"] is None


def test_check_api_health_exception_with_previous_success():
    adapter = _make_adapter()
    adapter._last_health_ok_at = 1_700_000_000.0

    with patch("asyncio.run", side_effect=Exception("timeout")):
        result = adapter.check_api_health()

    assert result["ok"] is False
    assert result["last_success_epoch"] == 1_700_000_000


# ---------------------------------------------------------------------------
# generate_robot_test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_robot_test_returns_content():
    svc = MagicMock()
    svc.generate_robot_test = AsyncMock(return_value="*** Test Cases ***\nTest Login\n")
    adapter = _make_adapter(svc)

    result = await adapter.generate_robot_test("Login test", context_text="ctx", page_structure={"k": "v"})
    assert result == "*** Test Cases ***\nTest Login\n"
    svc.generate_robot_test.assert_awaited_once_with(
        prompt="Login test",
        context="ctx",
        page_structure={"k": "v"},
    )


@pytest.mark.asyncio
async def test_generate_robot_test_uses_default_prompt_when_empty():
    svc = MagicMock()
    svc.generate_robot_test = AsyncMock(return_value="*** Test Cases ***")
    adapter = _make_adapter(svc)

    await adapter.generate_robot_test("")
    call_kwargs = svc.generate_robot_test.call_args[1]
    assert "conforme solicitação" in call_kwargs["prompt"]


@pytest.mark.asyncio
async def test_generate_robot_test_forwards_optional_generation_params():
    svc = MagicMock()
    svc.generate_robot_test = AsyncMock(return_value="*** Test Cases ***\nSmoke\n")
    adapter = _make_adapter(svc)

    result = await adapter.generate_robot_test(
        "Prompt base",
        context_text="ctx",
        page_structure={"dom": "snapshot"},
        model="gpt-5",
        system_prompt="system instructions",
        temperature=0.4,
        max_tokens=2048,
    )

    assert result == "*** Test Cases ***\nSmoke\n"
    svc.generate_robot_test.assert_awaited_once_with(
        prompt="Prompt base",
        context="ctx",
        page_structure={"dom": "snapshot"},
        model="gpt-5",
        system_prompt="system instructions",
        temperature=0.4,
        max_tokens=2048,
    )


@pytest.mark.asyncio
async def test_generate_robot_test_raises_on_empty_response():
    svc = MagicMock()
    svc.generate_robot_test = AsyncMock(return_value="")
    adapter = _make_adapter(svc)

    with pytest.raises(Exception):
        await adapter.generate_robot_test("Test")


@pytest.mark.asyncio
async def test_generate_robot_test_raises_payload_too_large_on_413():
    from app.llm.copilot_adapter import PayloadTooLargeError

    svc = MagicMock()
    svc.generate_robot_test = AsyncMock(side_effect=Exception("413 payload too large"))
    adapter = _make_adapter(svc)

    with pytest.raises(PayloadTooLargeError):
        await adapter.generate_robot_test("Test")


@pytest.mark.asyncio
async def test_generate_robot_test_reraises_other_exceptions():
    svc = MagicMock()
    svc.generate_robot_test = AsyncMock(side_effect=RuntimeError("network failure"))
    adapter = _make_adapter(svc)

    with pytest.raises(RuntimeError, match="network failure"):
        await adapter.generate_robot_test("Test")


# ---------------------------------------------------------------------------
# regenerate_robot_step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_robot_step_returns_first_line():
    svc = MagicMock()
    svc.generate = AsyncMock(return_value="    Click    css=#submit\nextra line")
    adapter = _make_adapter(svc)

    result = await adapter.regenerate_robot_step(
        original_prompt="Login test",
        failing_step="    Click    css=#btn",
        error_message="strict mode violation",
    )
    assert result == "    Click    css=#submit"


@pytest.mark.asyncio
async def test_regenerate_robot_step_passes_correct_args():
    svc = MagicMock()
    svc.generate = AsyncMock(return_value="Fixed step")
    adapter = _make_adapter(svc)

    await adapter.regenerate_robot_step(
        original_prompt="Test login flow",
        failing_step="Click    button",
        error_message="element not found",
        context="some context",
    )

    call_kwargs = svc.generate.call_args[1]
    assert call_kwargs["temperature"] == 0.0
    assert call_kwargs["max_tokens"] == 256
    assert "system_prompt" in call_kwargs


@pytest.mark.asyncio
async def test_regenerate_robot_step_returns_original_on_error():
    svc = MagicMock()
    svc.generate = AsyncMock(side_effect=Exception("LLM down"))
    adapter = _make_adapter(svc)

    result = await adapter.regenerate_robot_step(
        original_prompt="p",
        failing_step="    Fill Text    css=#user    admin",
        error_message="error",
    )
    assert result == "    Fill Text    css=#user    admin"


@pytest.mark.asyncio
async def test_regenerate_robot_step_returns_empty_string_when_content_empty():
    svc = MagicMock()
    svc.generate = AsyncMock(return_value="")
    adapter = _make_adapter(svc)

    result = await adapter.regenerate_robot_step("p", "step", "err")
    assert result == ""
