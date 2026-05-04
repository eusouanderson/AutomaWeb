"""Unit tests for app/llm/copilot_http.py"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_auth_manager(token: str = "tok-123"):
    mgr = MagicMock()
    mgr.get_valid_access_token = AsyncMock(return_value=token)
    return mgr


def _mock_response(status_code: int = 200, text: str = "ok"):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.request = MagicMock()
    return resp


def _make_client(auth_manager=None, http_client=None, max_retries=2, retry_delay_ms=0):
    from app.llm.copilot_http import CopilotHTTPClient

    return CopilotHTTPClient(
        auth_manager=auth_manager or _mock_auth_manager(),
        max_retries=max_retries,
        retry_delay_ms=retry_delay_ms,
        http_client=http_client,
    )


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def test_is_network_error_true_for_os_error():
    from app.llm.copilot_http import is_network_error

    assert is_network_error(OSError("connection reset")) is True


def test_is_network_error_true_for_httpx_network_error():
    from app.llm.copilot_http import is_network_error

    assert is_network_error(httpx.ConnectError("fail")) is True


def test_is_network_error_false_for_value_error():
    from app.llm.copilot_http import is_network_error

    assert is_network_error(ValueError("nope")) is False


@pytest.mark.asyncio
async def test_delay_ms_sleeps_correct_duration():
    from app.llm.copilot_http import delay_ms

    with patch("app.llm.copilot_http.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await delay_ms(500)
        mock_sleep.assert_awaited_once_with(0.5)


def test_should_retry_status_true():
    from app.llm.copilot_http import should_retry_status

    assert should_retry_status(503, [500, 503]) is True


def test_should_retry_status_false():
    from app.llm.copilot_http import should_retry_status

    assert should_retry_status(200, [500, 503]) is False


def test_can_retry_body_true_for_dict():
    from app.llm.copilot_http import can_retry_body

    assert can_retry_body({"key": "val"}) is True


def test_can_retry_body_false_for_byte_stream():
    from app.llm.copilot_http import can_retry_body

    assert can_retry_body(httpx.ByteStream(b"data")) is False


def test_can_retry_body_true_for_none():
    from app.llm.copilot_http import can_retry_body

    assert can_retry_body(None) is True


# ---------------------------------------------------------------------------
# _get_http_client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_http_client_returns_injected_client():
    fake = MagicMock(spec=httpx.AsyncClient)
    client = _make_client(http_client=fake)
    result = await client._get_http_client()
    assert result is fake


@pytest.mark.asyncio
async def test_get_http_client_creates_new_when_none():
    client = _make_client()
    result = await client._get_http_client()
    assert isinstance(result, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# _add_auth_headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_auth_headers_injects_bearer_token():
    client = _make_client(auth_manager=_mock_auth_manager("my-token"))
    headers = {}
    result = await client._add_auth_headers(headers)
    assert result["Authorization"] == "Bearer my-token"
    assert "User-Agent" in result
    assert "Openai-Intent" in result


# ---------------------------------------------------------------------------
# request() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_returns_response_on_success():
    resp = _mock_response(200)
    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(return_value=resp)

    client = _make_client(http_client=mock_inner)
    result = await client.request("GET", "https://example.com/api")
    assert result is resp


# ---------------------------------------------------------------------------
# request() — 401 handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_retries_on_401_and_succeeds():
    first = _mock_response(401)
    second = _mock_response(200)

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(side_effect=[first, second])

    client = _make_client(http_client=mock_inner)
    result = await client.request("GET", "https://api.example.com/v1")
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_request_raises_on_401_after_refresh_still_401():
    first = _mock_response(401)
    second = _mock_response(401, text="still unauthorized")

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(side_effect=[first, second])

    client = _make_client(http_client=mock_inner)
    with pytest.raises(httpx.HTTPStatusError, match="Still unauthorized"):
        await client.request("GET", "https://api.example.com/v1")


@pytest.mark.asyncio
async def test_request_raises_when_token_refresh_itself_fails():
    first = _mock_response(401)

    auth_mgr = _mock_auth_manager()
    # First call (initial) succeeds, second call (refresh) raises
    auth_mgr.get_valid_access_token = AsyncMock(
        side_effect=[
            "old-token",  # headers for first request
            "old-token",  # headers before the request
            Exception("refresh failed"),
        ]
    )

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(return_value=first)

    client = _make_client(auth_manager=auth_mgr, http_client=mock_inner)
    with pytest.raises(httpx.HTTPStatusError, match="authentication failed"):
        await client.request("GET", "https://api.example.com/v1")


# ---------------------------------------------------------------------------
# request() — retryable status codes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_retries_on_503():
    fail = _mock_response(503)
    ok = _mock_response(200)

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(side_effect=[fail, ok])

    client = _make_client(http_client=mock_inner, max_retries=1, retry_delay_ms=0)
    result = await client.request("POST", "https://api.example.com/v1", json={"a": 1})
    assert result.status_code == 200
    assert mock_inner.request.await_count == 2


@pytest.mark.asyncio
async def test_request_returns_after_max_retries_exceeded():
    fail = _mock_response(503)

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(return_value=fail)

    client = _make_client(http_client=mock_inner, max_retries=1, retry_delay_ms=0)
    result = await client.request("POST", "https://api.example.com/v1", json={})
    # max_retries=1: first attempt + 1 retry = 2 calls, then returns the response
    assert result.status_code == 503
    assert mock_inner.request.await_count == 2


# ---------------------------------------------------------------------------
# request() — network error retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_retries_on_network_error():
    ok = _mock_response(200)

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(
        side_effect=[httpx.ConnectError("timeout"), ok]
    )

    client = _make_client(http_client=mock_inner, max_retries=1, retry_delay_ms=0)
    result = await client.request("GET", "https://api.example.com/v1")
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_request_retries_on_timeout_exception():
    ok = _mock_response(200)

    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(
        side_effect=[httpx.ReadTimeout("read timeout"), ok]
    )

    client = _make_client(http_client=mock_inner, max_retries=1, retry_delay_ms=0)
    result = await client.request("GET", "https://api.example.com/v1")
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_request_raises_network_error_after_max_retries():
    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(side_effect=httpx.ConnectError("no route"))

    client = _make_client(http_client=mock_inner, max_retries=1, retry_delay_ms=0)
    with pytest.raises(httpx.ConnectError):
        await client.request("GET", "https://api.example.com/v1")


# ---------------------------------------------------------------------------
# get() / post() convenience wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_calls_request_with_get_method():
    ok = _mock_response(200)
    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(return_value=ok)

    client = _make_client(http_client=mock_inner)
    await client.get("https://api.example.com/models")
    call = mock_inner.request.call_args
    assert call[0][0] == "GET"


@pytest.mark.asyncio
async def test_post_calls_request_with_post_method():
    ok = _mock_response(200)
    mock_inner = MagicMock(spec=httpx.AsyncClient)
    mock_inner.request = AsyncMock(return_value=ok)

    client = _make_client(http_client=mock_inner)
    await client.post("https://api.example.com/chat", json={"msg": "hi"})
    call = mock_inner.request.call_args
    assert call[0][0] == "POST"
