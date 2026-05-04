"""Unit tests for app/llm/copilot_provider.py"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(post_return=None):
    """Return a CopilotProvider with a mocked http_client."""
    from app.llm.copilot_provider import CopilotProvider

    provider = CopilotProvider(base_url="https://api.githubcopilot.com")
    mock_http = MagicMock()

    if post_return is None:
        # Default: valid chat completions response
        post_return = _mock_response(
            {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
        )

    mock_http.post = AsyncMock(return_value=post_return)
    provider.http_client = mock_http
    return provider


def _mock_response(json_data: dict, status_code: int = 200):
    """Build a mock httpx-like response."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    resp.status_code = status_code
    resp.is_success = status_code < 400
    resp.text = str(json_data)
    return resp


# ---------------------------------------------------------------------------
# _extract_responses_text
# ---------------------------------------------------------------------------


def test_extract_responses_text_uses_output_text():
    from app.llm.copilot_provider import CopilotProvider

    p = CopilotProvider()
    result = p._extract_responses_text({"output_text": "  hello world  "})
    assert result == "hello world"


def test_extract_responses_text_skips_empty_output_text():
    from app.llm.copilot_provider import CopilotProvider

    p = CopilotProvider()
    result = p._extract_responses_text({"output_text": "   "})
    assert result is None


def test_extract_responses_text_from_output_array():
    from app.llm.copilot_provider import CopilotProvider

    p = CopilotProvider()
    data = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "line1"},
                    {"type": "text", "text": "line2"},
                ]
            }
        ]
    }
    result = p._extract_responses_text(data)
    assert result == "line1\nline2"


def test_extract_responses_text_skips_non_text_parts():
    from app.llm.copilot_provider import CopilotProvider

    p = CopilotProvider()
    data = {
        "output": [
            {"content": [{"type": "image", "text": "img"}]}
        ]
    }
    result = p._extract_responses_text(data)
    assert result is None


def test_extract_responses_text_returns_none_when_empty():
    from app.llm.copilot_provider import CopilotProvider

    p = CopilotProvider()
    assert p._extract_responses_text({}) is None


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_returns_content():
    provider = _make_provider(
        _mock_response(
            {"choices": [{"message": {"role": "assistant", "content": "result text"}}]}
        )
    )
    result = await provider.chat("gpt-5-mini", [{"role": "user", "content": "hi"}])
    assert result == "result text"


@pytest.mark.asyncio
async def test_chat_raises_on_empty_content():
    provider = _make_provider(
        _mock_response(
            {"choices": [{"message": {"role": "assistant", "content": "   "}}]}
        )
    )
    with pytest.raises(ValueError, match="Empty response"):
        await provider.chat("gpt-5-mini", [{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_raises_on_missing_choices():
    provider = _make_provider(_mock_response({"choices": []}))
    with pytest.raises(ValueError, match="Invalid response"):
        await provider.chat("gpt-5-mini", [])


@pytest.mark.asyncio
async def test_chat_posts_to_correct_url():
    provider = _make_provider()
    await provider.chat("gpt-5-mini", [{"role": "user", "content": "q"}], temperature=0.5, max_tokens=100)
    provider.http_client.post.assert_awaited_once()
    call_args = provider.http_client.post.call_args
    assert "/chat/completions" in call_args[0][0]
    body = call_args[1]["json"]
    assert body["model"] == "gpt-5-mini"
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 100


@pytest.mark.asyncio
async def test_chat_raises_on_invalid_response_format():
    provider = _make_provider(_mock_response({"unexpected": "data"}))
    with pytest.raises(ValueError, match="Invalid response"):
        await provider.chat("gpt-5-mini", [])


@pytest.mark.asyncio
async def test_chat_logs_error_and_raises_on_non_success_status():
    """Covers line 148 — error log when response.is_success is False."""
    import httpx

    resp = MagicMock()
    resp.json.return_value = {}
    resp.status_code = 500
    resp.is_success = False
    resp.text = "Internal Server Error"
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500 error", request=MagicMock(), response=MagicMock()
        )
    )

    provider = _make_provider(resp)
    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat("gpt-5-mini", [{"role": "user", "content": "hi"}])

    resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# responses()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_responses_returns_output_text():
    provider = _make_provider(
        _mock_response({"output_text": "generated code"})
    )
    result = await provider.responses("gpt-5", [{"role": "user", "content": "go"}])
    assert result == "generated code"


@pytest.mark.asyncio
async def test_responses_returns_from_output_array():
    provider = _make_provider(
        _mock_response(
            {
                "output": [
                    {"content": [{"type": "output_text", "text": "from array"}]}
                ]
            }
        )
    )
    result = await provider.responses("gpt-5", [])
    assert result == "from array"


@pytest.mark.asyncio
async def test_responses_raises_on_empty_output():
    provider = _make_provider(_mock_response({}))
    with pytest.raises(ValueError, match="Empty response"):
        await provider.responses("gpt-5", [])


@pytest.mark.asyncio
async def test_responses_posts_to_correct_url():
    provider = _make_provider(_mock_response({"output_text": "ok"}))
    await provider.responses("gpt-5", [{"role": "user", "content": "q"}], temperature=0.0, max_tokens=512)
    call_args = provider.http_client.post.call_args
    assert "/responses" in call_args[0][0]
    body = call_args[1]["json"]
    assert body["model"] == "gpt-5"
    assert body["temperature"] == 0.0
    assert body["max_output_tokens"] == 512
    assert body["input"] == [{"role": "user", "content": "q"}]


@pytest.mark.asyncio
async def test_responses_retries_with_legacy_payload_on_400():
    import httpx

    req = httpx.Request("POST", "https://api.githubcopilot.com/responses")

    bad_response = _mock_response({"error": "bad payload"}, status_code=400)
    bad_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "400 bad request",
            request=req,
            response=httpx.Response(400, request=req, text="bad payload"),
        )
    )

    ok_response = _mock_response({"output_text": "legacy ok"})

    provider = _make_provider()
    provider.http_client.post = AsyncMock(side_effect=[bad_response, ok_response])

    result = await provider.responses("gpt-5.4", [{"role": "user", "content": "go"}], temperature=0.0, max_tokens=256)

    assert result == "legacy ok"
    assert provider.http_client.post.await_count == 2

    first_payload = provider.http_client.post.await_args_list[0].kwargs["json"]
    second_payload = provider.http_client.post.await_args_list[1].kwargs["json"]
    assert "input" in first_payload
    assert first_payload["max_output_tokens"] == 256
    assert "messages" in second_payload
    assert second_payload["max_tokens"] == 256


@pytest.mark.asyncio
async def test_responses_raises_and_logs_on_invalid_format():
    provider = _make_provider(_mock_response({"output_text": "   "}))
    with pytest.raises(ValueError, match="Invalid response from responses API"):
        await provider.responses("gpt-5", [])


# ---------------------------------------------------------------------------
# run_model() — endpoint routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_model_uses_chat_for_gpt5_mini():
    provider = _make_provider(
        _mock_response(
            {"choices": [{"message": {"role": "assistant", "content": "mini result"}}]}
        )
    )
    result = await provider.run_model("gpt-5-mini", [{"role": "user", "content": "hi"}])
    assert result == "mini result"
    # Verify /chat/completions was called
    call_url = provider.http_client.post.call_args[0][0]
    assert "/chat/completions" in call_url


@pytest.mark.asyncio
async def test_run_model_uses_responses_for_gpt5():
    provider = _make_provider(_mock_response({"output_text": "advanced result"}))
    result = await provider.run_model("gpt-5", [{"role": "user", "content": "hi"}])
    assert result == "advanced result"
    call_url = provider.http_client.post.call_args[0][0]
    assert "/responses" in call_url


@pytest.mark.asyncio
async def test_run_model_uses_responses_for_gpt5_other():
    """Any gpt-5 model that isn't gpt-5-mini should use responses API."""
    provider = _make_provider(_mock_response({"output_text": "pro result"}))
    result = await provider.run_model("gpt-5-pro", [])
    assert result == "pro result"
    call_url = provider.http_client.post.call_args[0][0]
    assert "/responses" in call_url


@pytest.mark.asyncio
async def test_run_model_uses_chat_for_non_gpt5_model():
    provider = _make_provider(
        _mock_response(
            {"choices": [{"message": {"role": "assistant", "content": "gpt4 result"}}]}
        )
    )
    result = await provider.run_model("gpt-4o", [])
    assert result == "gpt4 result"
    call_url = provider.http_client.post.call_args[0][0]
    assert "/chat/completions" in call_url


@pytest.mark.asyncio
async def test_run_model_passes_temperature_and_max_tokens():
    provider = _make_provider(
        _mock_response(
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )
    )
    await provider.run_model("gpt-5-mini", [], temperature=0.7, max_tokens=256)
    body = provider.http_client.post.call_args[1]["json"]
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 256
