"""Unit tests for app/llm/copilot_models.py"""
from __future__ import annotations

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_http_client(json_data: dict = None, status_code: int = 200):
    http = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data or {}
    resp.status_code = status_code
    http.get = AsyncMock(return_value=resp)
    return http


def _make_client(http=None):
    from app.llm.copilot_models import CopilotModelsClient

    return CopilotModelsClient(http_client=http or _mock_http_client())


def _model_item(
    model_id: str = "gpt-5-mini",
    enabled: bool = True,
    policy_state: str = "enabled",
    supports: dict = None,
    limits: dict = None,
):
    return {
        "id": model_id,
        "name": f"{model_id}-name",
        "model_picker_enabled": enabled,
        "policy": {"state": policy_state},
        "supported_endpoints": ["chat"],
        "capabilities": {
            "family": "gpt-5",
            "limits": limits or {
                "max_context_window_tokens": 8192,
                "max_output_tokens": 4096,
                "max_prompt_tokens": 4096,
            },
            "supports": supports or {
                "streaming": True,
                "tool_calls": True,
                "vision": False,
                "structured_outputs": True,
            },
        },
    }


# ---------------------------------------------------------------------------
# _parse_model_item
# ---------------------------------------------------------------------------


def test_parse_model_item_basic():
    from app.llm.copilot_models import CopilotModelsClient, CopilotModelInfo

    client = _make_client()
    item = _model_item()
    result = client._parse_model_item(item)
    assert isinstance(result, CopilotModelInfo)
    assert result.id == "gpt-5-mini"
    assert result.limits.context_tokens == 8192
    assert result.capabilities.streaming is True
    assert result.capabilities.tool_calls is True
    assert result.capabilities.vision is False


def test_parse_model_item_reasoning_adaptive_thinking():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    item = _model_item(supports={"adaptive_thinking": True})
    result = client._parse_model_item(item)
    assert result.capabilities.reasoning is True


def test_parse_model_item_reasoning_effort_list():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    item = _model_item(supports={"reasoning_effort": ["low", "high"]})
    result = client._parse_model_item(item)
    assert result.capabilities.reasoning is True


def test_parse_model_item_reasoning_effort_empty_list():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    item = _model_item(supports={"reasoning_effort": []})
    result = client._parse_model_item(item)
    assert result.capabilities.reasoning is False


def test_parse_model_item_reasoning_max_thinking_budget():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    item = _model_item(supports={"max_thinking_budget": 1024})
    result = client._parse_model_item(item)
    assert result.capabilities.reasoning is True


def test_parse_model_item_reasoning_min_thinking_budget():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    item = _model_item(supports={"min_thinking_budget": 0})
    result = client._parse_model_item(item)
    assert result.capabilities.reasoning is True


def test_parse_model_item_defaults_for_missing_limits():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    # Build item without any limits keys
    item = _model_item()
    item["capabilities"]["limits"] = {}
    result = client._parse_model_item(item)
    assert result.limits.context_tokens == 4096
    assert result.limits.output_tokens == 2048
    assert result.limits.prompt_tokens == 2048


def test_parse_model_item_uses_id_as_name_fallback():
    from app.llm.copilot_models import CopilotModelsClient

    client = _make_client()
    item = _model_item()
    item.pop("name", None)
    result = client._parse_model_item(item)
    assert result.name == result.id


# ---------------------------------------------------------------------------
# _do_fetch_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_do_fetch_models_returns_enabled_models():
    data = {
        "data": [
            _model_item("gpt-5-mini", enabled=True, policy_state="enabled"),
            _model_item("gpt-5", enabled=True, policy_state="enabled"),
        ]
    }
    client = _make_client(_mock_http_client(json_data=data))
    models = await client._do_fetch_models("https://api.githubcopilot.com")
    assert len(models) == 2
    assert models[0].id == "gpt-5-mini"


@pytest.mark.asyncio
async def test_do_fetch_models_excludes_disabled_models():
    data = {
        "data": [
            _model_item("gpt-5-mini", enabled=True, policy_state="enabled"),
            _model_item("gpt-5", enabled=False, policy_state="enabled"),
            _model_item("gpt-4o", enabled=True, policy_state="disabled"),
        ]
    }
    client = _make_client(_mock_http_client(json_data=data))
    models = await client._do_fetch_models("https://api.githubcopilot.com")
    assert len(models) == 1
    assert models[0].id == "gpt-5-mini"


@pytest.mark.asyncio
async def test_do_fetch_models_raises_on_invalid_format():
    client = _make_client(_mock_http_client(json_data={"not_data": []}))
    with pytest.raises(ValueError, match="Invalid response format"):
        await client._do_fetch_models("https://api.githubcopilot.com")


@pytest.mark.asyncio
async def test_do_fetch_models_skips_unparseable_items(caplog):
    bad_item = {"id": None, "capabilities": {}}  # will fail _parse_model_item (missing id key)
    good_item = _model_item("gpt-5-mini", enabled=True, policy_state="enabled")
    data = {"data": [bad_item, good_item]}

    client = _make_client(_mock_http_client(json_data=data))
    models = await client._do_fetch_models("https://api.githubcopilot.com")
    # good_item should still be returned
    assert any(m.id == "gpt-5-mini" for m in models)


# ---------------------------------------------------------------------------
# fetch_models() — caching & inflight dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_models_caches_result():
    data = {"data": [_model_item()]}
    http = _mock_http_client(json_data=data)
    client = _make_client(http)

    r1 = await client.fetch_models("https://api.githubcopilot.com")
    r2 = await client.fetch_models("https://api.githubcopilot.com")

    assert r1 == r2
    # HTTP only called once
    assert http.get.await_count == 1


@pytest.mark.asyncio
async def test_fetch_models_force_refresh_bypasses_cache():
    data = {"data": [_model_item()]}
    http = _mock_http_client(json_data=data)
    client = _make_client(http)

    await client.fetch_models("https://api.githubcopilot.com")
    await client.fetch_models("https://api.githubcopilot.com", force_refresh=True)

    assert http.get.await_count == 2


@pytest.mark.asyncio
async def test_fetch_models_returns_cached_when_not_expired():
    from app.llm.copilot_models import CacheEntry, CopilotModelInfo, ModelLimits, ModelCapabilities

    client = _make_client()
    fake_model = CopilotModelInfo(
        id="cached-model",
        name="Cached",
        family="gpt",
        endpoints=[],
        limits=ModelLimits(context_tokens=4096, output_tokens=2048, prompt_tokens=2048),
        capabilities=ModelCapabilities(),
    )
    client._cache["https://api.githubcopilot.com"] = CacheEntry(
        value=[fake_model],
        expires_at=int(time.time() * 1000) + 999_999,
    )

    result = await client.fetch_models("https://api.githubcopilot.com")
    assert result[0].id == "cached-model"
    # No HTTP request made
    client.http_client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_models_expired_cache_refetches():
    from app.llm.copilot_models import CacheEntry, CopilotModelInfo, ModelLimits, ModelCapabilities

    data = {"data": [_model_item("new-model")]}
    http = _mock_http_client(json_data=data)
    client = _make_client(http)

    fake_model = CopilotModelInfo(
        id="old-model",
        name="Old",
        family="gpt",
        endpoints=[],
        limits=ModelLimits(context_tokens=4096, output_tokens=2048, prompt_tokens=2048),
        capabilities=ModelCapabilities(),
    )
    client._cache["https://api.githubcopilot.com"] = CacheEntry(
        value=[fake_model],
        expires_at=int(time.time() * 1000) - 1,  # already expired
    )

    result = await client.fetch_models("https://api.githubcopilot.com")
    assert result[0].id == "new-model"


@pytest.mark.asyncio
async def test_fetch_models_exception_propagates():
    http = MagicMock()
    http.get = AsyncMock(side_effect=Exception("network failure"))
    client = _make_client(http)

    with pytest.raises(Exception, match="network failure"):
        await client.fetch_models("https://api.githubcopilot.com")

    # inflight should be cleaned up
    assert "https://api.githubcopilot.com" not in client._inflight


@pytest.mark.asyncio
async def test_fetch_models_returns_inflight_future_when_already_in_progress():
    """Hits the _inflight branch (lines 113-116) by pre-populating _inflight."""
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()

    from app.llm.copilot_models import CopilotModelInfo, ModelLimits, ModelCapabilities
    fake_model = CopilotModelInfo(
        id="inflight-model",
        name="Inflight",
        family="gpt",
        endpoints=[],
        limits=ModelLimits(context_tokens=4096, output_tokens=2048, prompt_tokens=2048),
        capabilities=ModelCapabilities(),
    )

    client = _make_client()
    url = "https://api.githubcopilot.com"
    client._inflight[url] = fut

    # Resolve the future concurrently
    async def resolve():
        await asyncio.sleep(0)
        fut.set_result([fake_model])

    result, _ = await asyncio.gather(client.fetch_models(url), resolve())
    assert result[0].id == "inflight-model"
    # No HTTP request made
    client.http_client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_models_deduplicates_inflight_requests():
    """Two concurrent fetch calls for same URL should only hit API once."""
    data = {"data": [_model_item()]}
    http = _mock_http_client(json_data=data)
    client = _make_client(http)

    results = await asyncio.gather(
        client.fetch_models("https://api.githubcopilot.com"),
        client.fetch_models("https://api.githubcopilot.com"),
    )

    assert results[0] == results[1]
    # Only one real HTTP call
    assert http.get.await_count == 1
