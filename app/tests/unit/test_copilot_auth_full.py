"""Extended unit tests for app/llm/copilot_auth.py — covers uncovered lines."""
from __future__ import annotations

import json
import time
import pytest
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx

from app.llm.copilot_auth import (
    CopilotAuthManager,
    CopilotAuthRecord,
    OAuthDeviceCodeResponse,
    OAuthTokenResponse,
    get_static_copilot_token,
    is_token_expired,
    resolve_oauth_endpoints,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path, token=None, enterprise_url=None):
    auth_file = tmp_path / ".copilot" / "auth.json"
    mgr = CopilotAuthManager(
        auth_file_path=str(auth_file),
        enterprise_url=enterprise_url,
    )
    mgr._http_client = MagicMock(spec=httpx.AsyncClient)
    return mgr


def _valid_record(extra_secs: int = 3600) -> CopilotAuthRecord:
    return CopilotAuthRecord(
        access_token="acc-token",
        refresh_token="ref-token",
        expires_at=int((time.time() + extra_secs) * 1000),
    )


def _expired_record() -> CopilotAuthRecord:
    return CopilotAuthRecord(
        access_token="old-acc",
        refresh_token="old-ref",
        expires_at=int((time.time() - 3600) * 1000),
    )


# ---------------------------------------------------------------------------
# get_static_copilot_token
# ---------------------------------------------------------------------------


def test_get_static_copilot_token_returns_env_value(monkeypatch):
    monkeypatch.setenv("COPILOT_TOKEN", "static-tok")
    assert get_static_copilot_token() == "static-tok"


def test_get_static_copilot_token_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    assert get_static_copilot_token() is None


def test_get_static_copilot_token_returns_none_for_empty_string(monkeypatch):
    monkeypatch.setenv("COPILOT_TOKEN", "   ")
    assert get_static_copilot_token() is None


# ---------------------------------------------------------------------------
# resolve_oauth_endpoints — enterprise branch (line 78)
# ---------------------------------------------------------------------------


def test_resolve_oauth_endpoints_enterprise():
    endpoints = resolve_oauth_endpoints("https://github.mycompany.com")
    assert "github.mycompany.com" in endpoints["device_code_url"]
    assert "github.mycompany.com" in endpoints["token_url"]


# ---------------------------------------------------------------------------
# _get_http_client — line 140-144
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_http_client_returns_injected():
    fake = MagicMock(spec=httpx.AsyncClient)
    mgr = CopilotAuthManager.__new__(CopilotAuthManager)
    mgr._http_client = fake
    result = await mgr._get_http_client()
    assert result is fake


@pytest.mark.asyncio
async def test_get_http_client_creates_new_when_none(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr._http_client = None
    result = await mgr._get_http_client()
    assert isinstance(result, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# _load_auth_record — lines 148-164
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_auth_record_returns_cache_if_set(tmp_path):
    mgr = _make_manager(tmp_path)
    record = _valid_record()
    mgr._cache = record
    result = await mgr._load_auth_record()
    assert result is record


@pytest.mark.asyncio
async def test_load_auth_record_returns_none_when_file_missing(tmp_path):
    mgr = _make_manager(tmp_path)
    result = await mgr._load_auth_record()
    assert result is None


@pytest.mark.asyncio
async def test_load_auth_record_parses_valid_file(tmp_path):
    mgr = _make_manager(tmp_path)
    record = _valid_record()
    mgr.auth_file_path.parent.mkdir(parents=True, exist_ok=True)
    mgr.auth_file_path.write_text(json.dumps(record.model_dump()))
    result = await mgr._load_auth_record()
    assert result is not None
    assert result.access_token == "acc-token"
    assert mgr._cache is result


@pytest.mark.asyncio
async def test_load_auth_record_returns_none_on_invalid_json(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.auth_file_path.parent.mkdir(parents=True, exist_ok=True)
    mgr.auth_file_path.write_text("not json{{{")
    result = await mgr._load_auth_record()
    assert result is None


@pytest.mark.asyncio
async def test_load_auth_record_returns_none_on_missing_field(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.auth_file_path.parent.mkdir(parents=True, exist_ok=True)
    mgr.auth_file_path.write_text(json.dumps({"foo": "bar"}))
    result = await mgr._load_auth_record()
    assert result is None


# ---------------------------------------------------------------------------
# _save_auth_record — lines 168-176
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_auth_record_writes_file(tmp_path):
    mgr = _make_manager(tmp_path)
    record = _valid_record()
    await mgr._save_auth_record(record)
    assert mgr.auth_file_path.exists()
    data = json.loads(mgr.auth_file_path.read_text())
    assert data["access_token"] == "acc-token"
    assert mgr._cache is record


# ---------------------------------------------------------------------------
# _request_device_code — lines 182-192
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_device_code_parses_response(tmp_path):
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "device_code": "dev-code",
        "user_code": "USER-CODE",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_device_code(mock_client)
    assert result.device_code == "dev-code"
    assert result.user_code == "USER-CODE"


# ---------------------------------------------------------------------------
# _request_token_by_device_code — lines 198-209
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_token_by_device_code(tmp_path):
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "access_token": "new-access",
        "token_type": "bearer",
        "expires_in": 3600,
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_token_by_device_code("dev-code-123", mock_client)
    assert result.access_token == "new-access"


# ---------------------------------------------------------------------------
# _request_token_by_refresh_token — lines 215-226
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_token_by_refresh_token(tmp_path):
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "access_token": "refreshed-token",
        "token_type": "bearer",
        "expires_in": 3600,
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_token_by_refresh_token("ref-tok", mock_client)
    assert result.access_token == "refreshed-token"


# ---------------------------------------------------------------------------
# authorize_device_code_flow — lines 245-297
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_device_code_flow_success(tmp_path):
    mgr = _make_manager(tmp_path)

    device_resp = OAuthDeviceCodeResponse(
        device_code="dc",
        user_code="AB12-CD34",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=1,
    )
    token_resp = OAuthTokenResponse(
        access_token="flow-token",
        refresh_token="flow-refresh",
        expires_in=3600,
        token_type="bearer",
    )

    mgr._request_device_code = AsyncMock(return_value=device_resp)
    mgr._request_token_by_device_code = AsyncMock(return_value=token_resp)
    mgr._save_auth_record = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        record = await mgr.authorize_device_code_flow()

    assert record.access_token == "flow-token"
    mgr._save_auth_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorize_device_code_flow_authorization_pending(tmp_path):
    mgr = _make_manager(tmp_path)

    device_resp = OAuthDeviceCodeResponse(
        device_code="dc",
        user_code="AB12",
        verification_uri="https://github.com/login/device",
        expires_in=5,
        interval=1,
    )
    # First response is pending, second is success
    pending = OAuthTokenResponse(error="authorization_pending")
    success = OAuthTokenResponse(
        access_token="tok", refresh_token="ref", expires_in=3600, token_type="bearer"
    )

    mgr._request_device_code = AsyncMock(return_value=device_resp)
    mgr._request_token_by_device_code = AsyncMock(side_effect=[pending, success])
    mgr._save_auth_record = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        record = await mgr.authorize_device_code_flow()

    assert record.access_token == "tok"


@pytest.mark.asyncio
async def test_authorize_device_code_flow_slow_down(tmp_path):
    mgr = _make_manager(tmp_path)

    device_resp = OAuthDeviceCodeResponse(
        device_code="dc",
        user_code="AB12",
        verification_uri="https://github.com/login/device",
        expires_in=5,
        interval=1,
    )
    slow = OAuthTokenResponse(error="slow_down")
    success = OAuthTokenResponse(
        access_token="tok2", refresh_token="ref2", expires_in=3600, token_type="bearer"
    )

    mgr._request_device_code = AsyncMock(return_value=device_resp)
    mgr._request_token_by_device_code = AsyncMock(side_effect=[slow, success])
    mgr._save_auth_record = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        record = await mgr.authorize_device_code_flow()

    assert record.access_token == "tok2"


@pytest.mark.asyncio
async def test_authorize_device_code_flow_oauth_error(tmp_path):
    mgr = _make_manager(tmp_path)

    device_resp = OAuthDeviceCodeResponse(
        device_code="dc",
        user_code="AB12",
        verification_uri="https://github.com/login/device",
        expires_in=10,
        interval=1,
    )
    error_resp = OAuthTokenResponse(error="access_denied")

    mgr._request_device_code = AsyncMock(return_value=device_resp)
    mgr._request_token_by_device_code = AsyncMock(return_value=error_resp)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ValueError, match="OAuth error"):
            await mgr.authorize_device_code_flow()


@pytest.mark.asyncio
async def test_authorize_device_code_flow_timeout(tmp_path):
    """Covers TimeoutError when device code expires before user authorizes."""
    mgr = _make_manager(tmp_path)

    device_resp = OAuthDeviceCodeResponse(
        device_code="dc",
        user_code="AB12",
        verification_uri="https://github.com/login/device",
        expires_in=0,  # immediately expired
        interval=1,
    )

    mgr._request_device_code = AsyncMock(return_value=device_resp)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(TimeoutError):
            await mgr.authorize_device_code_flow()


# ---------------------------------------------------------------------------
# get_valid_access_token — lines 314-368
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_valid_access_token_returns_static_token(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_TOKEN", "env-static")
    mgr = _make_manager(tmp_path)
    result = await mgr.get_valid_access_token()
    assert result == "env-static"


@pytest.mark.asyncio
async def test_get_valid_access_token_returns_valid_cached(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=_valid_record())
    mgr._exchange_for_copilot_token = AsyncMock(return_value="copilot-api-token")
    result = await mgr.get_valid_access_token()
    assert result == "copilot-api-token"
    mgr._exchange_for_copilot_token.assert_awaited_once_with("acc-token", ANY)


@pytest.mark.asyncio
async def test_get_valid_access_token_raises_when_no_record(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="authentication required"):
        await mgr.get_valid_access_token()


@pytest.mark.asyncio
async def test_get_valid_access_token_returns_optimistically_when_expired_no_refresh(tmp_path, monkeypatch):
    """Classic gho_ tokens: if locally expired but no refresh_token, return token and extend expiry."""
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    expired = CopilotAuthRecord(
        access_token="gho_old_classic",
        refresh_token=None,
        expires_at=int((time.time() - 3600) * 1000),
    )
    mgr._load_auth_record = AsyncMock(return_value=expired)
    mgr._save_auth_record = AsyncMock()
    mgr._exchange_for_copilot_token = AsyncMock(return_value="copilot-classic-token")
    result = await mgr.get_valid_access_token()
    assert result == "copilot-classic-token"
    # Exchange was called with the classic token
    mgr._exchange_for_copilot_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_valid_access_token_refreshes_expired_token(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=_expired_record())

    new_token_resp = OAuthTokenResponse(
        access_token="refreshed",
        refresh_token="new-ref",
        expires_in=3600,
        token_type="bearer",
    )
    mgr._request_token_by_refresh_token = AsyncMock(return_value=new_token_resp)
    mgr._save_auth_record = AsyncMock()
    mgr._exchange_for_copilot_token = AsyncMock(return_value="copilot-refreshed")

    result = await mgr.get_valid_access_token()
    assert result == "copilot-refreshed"
    mgr._save_auth_record.assert_awaited_once()
    mgr._exchange_for_copilot_token.assert_awaited_once_with("refreshed", ANY)


@pytest.mark.asyncio
async def test_get_valid_access_token_raises_on_empty_refresh_response(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=_expired_record())

    empty_resp = OAuthTokenResponse(access_token=None)
    mgr._request_token_by_refresh_token = AsyncMock(return_value=empty_resp)

    with pytest.raises(RuntimeError, match="refresh failed"):
        await mgr.get_valid_access_token()


@pytest.mark.asyncio
async def test_get_valid_access_token_raises_on_refresh_exception(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=_expired_record())
    mgr._request_token_by_refresh_token = AsyncMock(side_effect=Exception("network"))

    with pytest.raises(RuntimeError, match="refresh failed"):
        await mgr.get_valid_access_token()


@pytest.mark.asyncio
async def test_get_valid_access_token_uses_old_refresh_when_new_is_none(tmp_path, monkeypatch):
    """Covers line 375: refresh_token fallback to record.refresh_token."""
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=_expired_record())

    # New token response has no refresh_token → should use old one
    new_resp = OAuthTokenResponse(
        access_token="new-tok",
        refresh_token=None,
        expires_in=3600,
        token_type="bearer",
    )
    mgr._request_token_by_refresh_token = AsyncMock(return_value=new_resp)
    mgr._save_auth_record = AsyncMock()
    mgr._exchange_for_copilot_token = AsyncMock(return_value="copilot-new-tok")

    result = await mgr.get_valid_access_token()
    assert result == "copilot-new-tok"
    saved: CopilotAuthRecord = mgr._save_auth_record.call_args[0][0]
    assert saved.refresh_token == "old-ref"  # kept old refresh token


# ---------------------------------------------------------------------------
# get_auth_record — delegates to _load_auth_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_auth_record_returns_record(tmp_path):
    mgr = _make_manager(tmp_path)
    record = _valid_record()
    mgr._load_auth_record = AsyncMock(return_value=record)
    result = await mgr.get_auth_record()
    assert result is record


@pytest.mark.asyncio
async def test_get_auth_record_returns_none_when_not_found(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr._load_auth_record = AsyncMock(return_value=None)
    result = await mgr.get_auth_record()
    assert result is None


# ---------------------------------------------------------------------------
# GitHub JSON response format tests
# Real GitHub API returns camelCase keys — verify they are parsed correctly.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_auth_record_handles_camelcase_keys(tmp_path):
    """GitHub classic tokens (gho_) are saved with camelCase by old code versions."""
    mgr = _make_manager(tmp_path)
    mgr.auth_file_path.parent.mkdir(parents=True, exist_ok=True)
    # Write in the camelCase format that was saved by older code
    mgr.auth_file_path.write_text(json.dumps({
        "accessToken": "gho_AbCdEfGhIj1234567890",
        "expiresAt": int((time.time() + 86400 * 28) * 1000),
        "tokenType": "bearer",
    }))
    result = await mgr._load_auth_record()
    assert result is not None
    assert result.access_token == "gho_AbCdEfGhIj1234567890"
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_load_auth_record_handles_mixed_keys(tmp_path):
    """Some fields camelCase, some snake_case — all should be normalized."""
    mgr = _make_manager(tmp_path)
    mgr.auth_file_path.parent.mkdir(parents=True, exist_ok=True)
    mgr.auth_file_path.write_text(json.dumps({
        "accessToken": "gho_MixedFormat",
        "refresh_token": "ref-tok",          # already snake_case
        "expiresAt": int((time.time() + 3600) * 1000),
        "tokenType": "bearer",
    }))
    result = await mgr._load_auth_record()
    assert result is not None
    assert result.access_token == "gho_MixedFormat"
    assert result.refresh_token == "ref-tok"


@pytest.mark.asyncio
async def test_request_token_by_device_code_no_expires_in(tmp_path):
    """GitHub classic tokens (gho_) don't include expires_in.
    poll_device_code should store them with a 28-day expiry."""
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    # GitHub response for classic token — no expires_in
    mock_resp.json.return_value = {
        "access_token": "gho_ClassicToken",
        "token_type": "bearer",
        # no expires_in, no refresh_token
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_token_by_device_code("dc-123", mock_client)
    assert result.access_token == "gho_ClassicToken"
    assert result.expires_in is None
    assert result.refresh_token is None


@pytest.mark.asyncio
async def test_get_valid_access_token_extends_expiry_for_classic_token(tmp_path, monkeypatch):
    """When token has no refresh_token and is 'expired' locally,
    it should be returned anyway and the expiry extended to 28 days."""
    monkeypatch.delenv("COPILOT_TOKEN", raising=False)
    mgr = _make_manager(tmp_path)

    # Simulate a classic gho_ token that our local expiry wrongly thinks is expired
    expired_classic = CopilotAuthRecord(
        access_token="gho_ClassicNoRefresh",
        refresh_token=None,
        expires_at=int((time.time() - 1) * 1000),  # 1ms in the past
    )
    mgr._load_auth_record = AsyncMock(return_value=expired_classic)
    mgr._save_auth_record = AsyncMock()
    mgr._exchange_for_copilot_token = AsyncMock(return_value="gho_ClassicNoRefresh")

    token = await mgr.get_valid_access_token()
    assert token == "gho_ClassicNoRefresh"

    # Expiry should be extended to ~28 days
    saved: CopilotAuthRecord = mgr._save_auth_record.call_args[0][0]
    days_remaining = (saved.expires_at / 1000 - time.time()) / 86400
    assert days_remaining > 27


@pytest.mark.asyncio
async def test_request_token_by_device_code_authorization_pending(tmp_path):
    """GitHub returns authorization_pending while user hasn't clicked authorize yet."""
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "error": "authorization_pending",
        "error_description": "The authorization request is still pending.",
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_token_by_device_code("dc-123", mock_client)
    assert result.access_token is None
    assert result.error == "authorization_pending"


@pytest.mark.asyncio
async def test_request_token_by_device_code_slow_down(tmp_path):
    """GitHub returns slow_down when polling too fast (<5s interval)."""
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "error": "slow_down",
        "error_description": "Please slow down.",
        "interval": 10,
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_token_by_device_code("dc-123", mock_client)
    assert result.access_token is None
    assert result.error == "slow_down"


@pytest.mark.asyncio
async def test_request_token_by_device_code_expired_token(tmp_path):
    """GitHub returns expired_token when device_code TTL runs out."""
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "error": "expired_token",
        "error_description": "The device code has expired.",
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_token_by_device_code("dc-123", mock_client)
    assert result.access_token is None
    assert result.error == "expired_token"


@pytest.mark.asyncio
async def test_request_device_code_response_shape(tmp_path):
    """Verify the device code response contains all fields frontend needs."""
    mgr = _make_manager(tmp_path)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "device_code": "3584d83530557fdd1f46af8289938c8ef79f9dc5",
        "user_code": "WDJB-MJHT",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    result = await mgr._request_device_code(mock_client)
    assert result.device_code == "3584d83530557fdd1f46af8289938c8ef79f9dc5"
    assert result.user_code == "WDJB-MJHT"
    assert result.verification_uri == "https://github.com/login/device"
    assert result.expires_in == 900
    assert result.interval == 5


@pytest.mark.asyncio
async def test_save_auth_record_writes_snake_case_json(tmp_path):
    """Auth record must always be saved as snake_case (not camelCase)."""
    mgr = _make_manager(tmp_path)
    record = CopilotAuthRecord(
        access_token="gho_TestToken",
        refresh_token=None,
        expires_at=int((time.time() + 86400 * 28) * 1000),
    )
    await mgr._save_auth_record(record)

    raw = json.loads(mgr.auth_file_path.read_text())
    # Must have snake_case keys
    assert "access_token" in raw
    assert "expires_at" in raw
    assert "token_type" in raw
    # Must NOT have camelCase keys
    assert "accessToken" not in raw
    assert "expiresAt" not in raw
    assert "tokenType" not in raw

