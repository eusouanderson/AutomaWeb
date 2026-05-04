from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import copilot_routes


class _AsyncClientCtx:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _service_mock() -> MagicMock:
    svc = MagicMock()
    svc.auth_manager = MagicMock()
    svc.auth_manager.auth_file_path = MagicMock()
    svc.auth_manager.auth_file_path.exists.return_value = True
    return svc


@pytest.mark.asyncio
async def test_start_oauth_flow_returns_200_when_already_authenticated() -> None:
    service = _service_mock()
    service.get_valid_token = AsyncMock(return_value="tok")

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        with pytest.raises(HTTPException) as exc:
            await copilot_routes.start_oauth_flow(copilot_routes.AuthorizationRequest())

    assert exc.value.status_code == 200
    assert exc.value.detail == "Already authenticated"


@pytest.mark.asyncio
async def test_start_oauth_flow_success_when_no_valid_token() -> None:
    service = _service_mock()
    service.get_valid_token = AsyncMock(side_effect=RuntimeError("no token"))
    service.auth_manager._request_device_code = AsyncMock(
        return_value=SimpleNamespace(
            verification_uri="https://github.com/login/device",
            user_code="ABCD-EFGH",
            device_code="dev-code",
            expires_in=900,
        )
    )

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service), patch(
        "httpx.AsyncClient",
        return_value=_AsyncClientCtx(MagicMock()),
    ):
        result = await copilot_routes.start_oauth_flow(copilot_routes.AuthorizationRequest())

    assert result.device_code == "dev-code"
    assert result.user_code == "ABCD-EFGH"


@pytest.mark.asyncio
async def test_start_oauth_flow_wraps_generic_error() -> None:
    service = _service_mock()
    service.get_valid_token = AsyncMock(side_effect=RuntimeError("no token"))
    service.auth_manager._request_device_code = AsyncMock(side_effect=Exception("boom"))

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service), patch(
        "httpx.AsyncClient",
        return_value=_AsyncClientCtx(MagicMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await copilot_routes.start_oauth_flow(copilot_routes.AuthorizationRequest())

    assert exc.value.status_code == 400
    assert "Authorization failed" in exc.value.detail


@pytest.mark.asyncio
async def test_check_token_success() -> None:
    service = _service_mock()
    service.get_valid_token = AsyncMock(return_value="token-ok")

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        result = await copilot_routes.check_token()

    assert result.ok is True
    assert result.authenticated is True


@pytest.mark.asyncio
async def test_check_token_failure() -> None:
    service = _service_mock()
    service.get_valid_token = AsyncMock(side_effect=Exception("bad token"))

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        result = await copilot_routes.check_token()

    assert result.ok is False
    assert "Token check failed" in result.message


@pytest.mark.asyncio
async def test_poll_device_code_success_saves_record() -> None:
    service = _service_mock()
    service.auth_manager._request_token_by_device_code = AsyncMock(
        return_value=SimpleNamespace(
            access_token="gho_token",
            token_type=None,
            refresh_token=None,
            expires_in=None,
            error=None,
        )
    )
    service.auth_manager._save_auth_record = AsyncMock()

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service), patch(
        "httpx.AsyncClient",
        return_value=_AsyncClientCtx(MagicMock()),
    ):
        result = await copilot_routes.poll_device_code(
            copilot_routes.DeviceCodePollRequest(device_code="dev-1")
        )

    assert result.authenticated is True
    service.auth_manager._save_auth_record.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,slow_down,msg",
    [
        ("authorization_pending", False, "Waiting for authorization"),
        ("slow_down", True, "Please wait a moment"),
        ("expired_token", False, "Device code expired"),
        ("something_else", False, "Authorization pending... (something_else)"),
    ],
)
async def test_poll_device_code_error_variants(error: str, slow_down: bool, msg: str) -> None:
    service = _service_mock()
    service.auth_manager._request_token_by_device_code = AsyncMock(
        return_value=SimpleNamespace(
            access_token=None,
            error=error,
            token_type=None,
            refresh_token=None,
            expires_in=None,
        )
    )

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service), patch(
        "httpx.AsyncClient",
        return_value=_AsyncClientCtx(MagicMock()),
    ):
        result = await copilot_routes.poll_device_code(
            copilot_routes.DeviceCodePollRequest(device_code="dev-2")
        )

    assert result.authenticated is False
    assert result.slow_down is slow_down
    assert msg in result.message


@pytest.mark.asyncio
async def test_poll_device_code_wraps_exception() -> None:
    service = _service_mock()
    service.auth_manager._request_token_by_device_code = AsyncMock(side_effect=Exception("network"))

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service), patch(
        "httpx.AsyncClient",
        return_value=_AsyncClientCtx(MagicMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await copilot_routes.poll_device_code(
                copilot_routes.DeviceCodePollRequest(device_code="dev-3")
            )

    assert exc.value.status_code == 400
    assert "Poll failed" in exc.value.detail


@pytest.mark.asyncio
async def test_list_models_success_and_error() -> None:
    service = _service_mock()

    model = SimpleNamespace(
        id="gpt-5-mini",
        name="GPT-5 Mini",
        family="gpt-5",
        capabilities=SimpleNamespace(model_dump=lambda: {"reasoning": True}),
        limits=SimpleNamespace(model_dump=lambda: {"context_tokens": 1000}),
    )
    service.fetch_models = AsyncMock(return_value=[model])

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        ok_result = await copilot_routes.list_models()
    assert ok_result.count == 1
    assert ok_result.models[0]["id"] == "gpt-5-mini"

    service.fetch_models = AsyncMock(side_effect=Exception("broken"))
    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        with pytest.raises(HTTPException) as exc:
            await copilot_routes.list_models()
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_generate_success_and_error() -> None:
    service = _service_mock()
    service.generate = AsyncMock(return_value="generated")

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        ok = await copilot_routes.generate(copilot_routes.GenerateRequest(prompt="hi"))
    assert ok.content == "generated"
    assert ok.model == "gpt-5-mini"

    service.generate = AsyncMock(side_effect=Exception("fail"))
    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        with pytest.raises(HTTPException) as exc:
            await copilot_routes.generate(copilot_routes.GenerateRequest(prompt="hi"))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_generate_robot_test_success_and_error() -> None:
    service = _service_mock()
    service.generate_robot_test = AsyncMock(return_value="*** Test Cases ***")

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        ok = await copilot_routes.generate_robot_test(
            copilot_routes.RobotTestRequest(prompt="login")
        )
    assert "*** Test Cases ***" in ok.test_code
    assert ok.model == "gpt-5-mini"

    service.generate_robot_test = AsyncMock(side_effect=Exception("nope"))
    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        with pytest.raises(HTTPException) as exc:
            await copilot_routes.generate_robot_test(
                copilot_routes.RobotTestRequest(prompt="login")
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_health_check_success_and_failure() -> None:
    service = _service_mock()
    service.check_connection = AsyncMock(return_value={"ok": True, "message": "up"})

    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        ok = await copilot_routes.health_check()
    assert ok.ok is True
    assert ok.authenticated is True
    assert ok.message == "up"

    service.check_connection = AsyncMock(side_effect=Exception("down"))
    with patch("app.api.copilot_routes.get_copilot_service", return_value=service):
        bad = await copilot_routes.health_check()
    assert bad.ok is False
    assert "Health check failed" in bad.message
