import pytest

from app.llm.groq_client import SimpleCache


def test_cache_set_and_get() -> None:
    cache = SimpleCache(ttl_seconds=10)
    cache.set("key1", "value1")
    
    assert cache.get("key1") == "value1"


def test_cache_miss() -> None:
    cache = SimpleCache(ttl_seconds=10)
    assert cache.get("nonexistent") is None


def test_cache_expiration() -> None:
    import time
    
    cache = SimpleCache(ttl_seconds=1)
    cache.set("key1", "value1")
    
    assert cache.get("key1") == "value1"
    
    time.sleep(1.1)
    
    assert cache.get("key1") is None


def test_groq_client_initialization() -> None:
    from unittest.mock import patch
    from app.llm.groq_client import GroqClient
    
    with patch.dict("os.environ", {"GROQ_API_KEY": "test_key"}):
        from app.core.config import Settings
        settings = Settings(GROQ_API_KEY="test_key")
        
        with patch("app.llm.groq_client.settings", settings):
            client = GroqClient()
            assert client._client is not None


def test_groq_client_no_api_key() -> None:
    from unittest.mock import patch
    from app.llm.groq_client import GroqClient
    
    with patch.dict("os.environ", {}, clear=True):
        from app.core.config import Settings
        settings = Settings(GROQ_API_KEY="")
        
        with patch("app.llm.groq_client.settings", settings):
            with pytest.raises(ValueError, match="GROQ_API_KEY is not configured"):
                GroqClient()


def test_groq_client_generate_with_cache() -> None:
    from unittest.mock import MagicMock, patch
    from app.llm.groq_client import GroqClient
    
    with patch.dict("os.environ", {"GROQ_API_KEY": "test_key"}):
        from app.core.config import Settings
        settings = Settings(GROQ_API_KEY="test_key")
        
        with patch("app.llm.groq_client.settings", settings):
            client = GroqClient()
            
            # Mock Groq response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Generated test code"
            
            client._client.chat.completions.create = MagicMock(return_value=mock_response)
            
            # First call
            result1 = client.generate_robot_test("test prompt")
            assert result1 == "Generated test code"
            
            # Second call should use cache
            result2 = client.generate_robot_test("test prompt")
            assert result2 == "Generated test code"
            
            # Should only call API once due to cache
            assert client._client.chat.completions.create.call_count == 1


def test_groq_client_initialization_insecure_skip_verify() -> None:
    from unittest.mock import MagicMock, patch
    from app.llm.groq_client import GroqClient

    with patch.dict("os.environ", {"GROQ_API_KEY": "test_key"}):
        from app.core.config import Settings

        settings = Settings(
            GROQ_API_KEY="test_key",
            GROQ_INSECURE_SKIP_VERIFY=True,
            GROQ_CA_BUNDLE=None,
        )

        with patch("app.llm.groq_client.settings", settings):
            with patch("app.llm.groq_client.httpx.Client") as mock_http_client:
                with patch("app.llm.groq_client.Groq", return_value=MagicMock()):
                    GroqClient()

                assert mock_http_client.call_args.kwargs["verify"] is False


def test_groq_client_initialization_with_ca_bundle() -> None:
    from unittest.mock import MagicMock, patch
    from app.llm.groq_client import GroqClient

    with patch.dict("os.environ", {"GROQ_API_KEY": "test_key"}):
        from app.core.config import Settings

        settings = Settings(
            GROQ_API_KEY="test_key",
            GROQ_INSECURE_SKIP_VERIFY=False,
            GROQ_CA_BUNDLE="/etc/ssl/custom-ca.pem",
        )

        with patch("app.llm.groq_client.settings", settings):
            with patch("app.llm.groq_client.httpx.Client") as mock_http_client:
                with patch("app.llm.groq_client.Groq", return_value=MagicMock()):
                    GroqClient()

                assert mock_http_client.call_args.kwargs["verify"] == "/etc/ssl/custom-ca.pem"


def test_groq_client_generate_with_page_structure_in_system_prompt() -> None:
    from unittest.mock import MagicMock, patch
    from app.llm.groq_client import GroqClient

    with patch.dict("os.environ", {"GROQ_API_KEY": "test_key"}):
        from app.core.config import Settings

        settings = Settings(GROQ_API_KEY="test_key")

        with patch("app.llm.groq_client.settings", settings):
            client = GroqClient()

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Generated test code"
            client._client.chat.completions.create = MagicMock(return_value=mock_response)

            structure = {"buttons": [{"text": "Entrar"}]}
            result = client.generate_robot_test("test prompt", page_structure=structure)

            assert result == "Generated test code"
            call_args = client._client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            assert "Here is the page structure in JSON format" in messages[0]["content"]
            assert '"buttons"' in messages[0]["content"]


# ---------------------------------------------------------------------------
# regenerate_robot_step  (lines 143-165)
# ---------------------------------------------------------------------------


def _make_groq_client():
    """Helper: return a GroqClient with mocked Groq internals."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()
    return client


def test_groq_client_generate_with_context_in_user_message():
    """Line 122: when context is provided the user message is prefixed with it."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Generated test code"
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client.generate_robot_test("my prompt", context="some context")

    assert result == "Generated test code"
    messages = client._client.chat.completions.create.call_args.kwargs["messages"]
    assert "What (o quê):" in messages[1]["content"]
    assert "Why (por que):" in messages[1]["content"]
    assert "Where (onde):" in messages[1]["content"]
    assert "How (como):" in messages[1]["content"]
    assert "some context" in messages[1]["content"]
    assert "my prompt" in messages[1]["content"]


def test_regenerate_robot_step_returns_first_line():
    """Returns the first non-empty line of the model response."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "    Click    css=#real-btn\nsome extra line"
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client.regenerate_robot_step(
        original_prompt="Login test",
        failing_step="    Click    css=#ghost",
        error_message="Element not found",
    )

    assert result == "Click    css=#real-btn"
    call_args = client._client.chat.completions.create.call_args.kwargs
    messages = call_args["messages"]
    assert messages[0]["role"] == "system"
    assert "UMA linha" in messages[0]["content"]
    assert "Login test" in messages[1]["content"]
    assert "css=#ghost" in messages[1]["content"]
    assert "Element not found" in messages[1]["content"]


def test_regenerate_robot_step_with_context():
    """Context is included in the user message."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "    Fill Text    css=#user    admin"
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client.regenerate_robot_step(
        original_prompt="Fill form",
        failing_step="    Fill Text    css=#username",
        error_message="strict mode violation",
        context="Page is a login form",
    )

    assert result == "Fill Text    css=#user    admin"
    messages = client._client.chat.completions.create.call_args.kwargs["messages"]
    assert "Page is a login form" in messages[1]["content"]


def test_regenerate_robot_step_without_context_uses_na():
    """When context is None the user message contains 'N/A'."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "    Click    css=#btn"
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    client.regenerate_robot_step(
        original_prompt="Click test",
        failing_step="    Click    //a",
        error_message="generic xpath",
        context=None,
    )

    messages = client._client.chat.completions.create.call_args.kwargs["messages"]
    assert "N/A" in messages[1]["content"]


def test_regenerate_robot_step_returns_empty_string_when_content_empty():
    """Returns '' when the model returns empty/whitespace content."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "   "  # whitespace only → strip → ""
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client.regenerate_robot_step(
        original_prompt="test",
        failing_step="    Click    css=#x",
        error_message="err",
    )

    assert result == ""


def test_regenerate_robot_step_returns_empty_string_when_content_is_none():
    """Returns '' when message.content is None."""
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = None
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client.regenerate_robot_step(
        original_prompt="test",
        failing_step="    Click    css=#x",
        error_message="err",
    )

    assert result == ""


def test_check_api_health_live_success():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "ok"
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client.check_api_health()

    assert result["ok"] is True
    assert result["source"] == "live"
    assert result["error"] is None


def test_check_api_health_uses_fallback_cache_on_failure():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key", LLM_HEALTH_FALLBACK_WINDOW_SECONDS=300)
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "ok"
    client._client.chat.completions.create = MagicMock(return_value=mock_response)
    first = client.check_api_health()
    assert first["ok"] is True

    client._client.chat.completions.create = MagicMock(side_effect=RuntimeError("network down"))
    second = client.check_api_health()

    assert second["ok"] is True
    assert second["source"] == "fallback_cache"
    assert "network down" in str(second["error"])


def test_check_api_health_returns_not_ok_when_live_fails_without_recent_success():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key", LLM_HEALTH_FALLBACK_WINDOW_SECONDS=300)
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    client._client.chat.completions.create = MagicMock(side_effect=RuntimeError("health down"))

    result = client.check_api_health()

    assert result["ok"] is False
    assert result["source"] == "live"
    assert result["last_success_epoch"] is None
    assert "health down" in str(result["error"])


def test_generate_robot_test_retries_once_with_compact_payload_on_413():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    class _PayloadTooLargeError(Exception):
        status_code = 413

    settings_obj = Settings(
        GROQ_API_KEY="test_key",
        LLM_MAX_PROMPT_CHARS=2000,
        LLM_MAX_CONTEXT_CHARS=3000,
        LLM_MAX_PAGE_STRUCTURE_CHARS=6000,
    )
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "*** Test Cases ***\nExample\n    Log    ok"
    client._client.chat.completions.create = MagicMock(side_effect=[_PayloadTooLargeError(), mock_response])

    long_context = "ctx-" * 4000
    long_prompt = "prompt-" * 2000
    result = client.generate_robot_test(
        long_prompt,
        context=long_context,
        page_structure={"items": ["x" * 4000 for _ in range(10)]},
    )

    assert "*** Test Cases ***" in result
    assert client._client.chat.completions.create.call_count == 2

    first_messages = client._client.chat.completions.create.call_args_list[0].kwargs["messages"]
    second_messages = client._client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert len(second_messages[1]["content"]) < len(first_messages[1]["content"])
    assert "Where (onde):" in second_messages[1]["content"]
    assert "Contexto reduzido automaticamente" in second_messages[1]["content"]


def test_generate_robot_test_raises_payload_too_large_after_compact_fallback():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient, PayloadTooLargeError

    class _PayloadTooLargeError(Exception):
        status_code = 413

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    client._client.chat.completions.create = MagicMock(side_effect=[_PayloadTooLargeError(), _PayloadTooLargeError()])

    with pytest.raises(PayloadTooLargeError, match="payload exceeds provider limits"):
        client.generate_robot_test(
            "Prompt",
            context="Contexto" * 3000,
            page_structure={"items": ["x" * 5000 for _ in range(10)]},
        )


def test_generate_robot_test_reraises_non_413_error_from_compact_fallback():
    from unittest.mock import patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    class _PayloadTooLargeError(Exception):
        status_code = 413

    class _CompactFallbackError(Exception):
        pass

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    # Bypass tenacity retry wrapper to assert the direct branch behavior.
    with patch.object(
        client,
        "_chat_completion",
        side_effect=[_PayloadTooLargeError("413"), _CompactFallbackError("boom")],
    ):
        with pytest.raises(_CompactFallbackError, match="boom"):
            GroqClient.generate_robot_test.__wrapped__(
                client,
                "Prompt",
                context="ctx",
                page_structure={"k": "v"},
            )


# --- Cobertura extra: exceção inesperada em generate_robot_test ---
def test_generate_robot_test_raises_unexpected_exception():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    class _SomeOtherError(Exception):
        pass

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    client._client.chat.completions.create = MagicMock(side_effect=_SomeOtherError("fail!"))

    import tenacity
    with pytest.raises(tenacity.RetryError) as excinfo:
        client.generate_robot_test("Prompt", context="ctx")
    # A causa original deve ser _SomeOtherError
    assert isinstance(excinfo.value.last_attempt.exception(), _SomeOtherError)


# --- Cobertura extra: _chat_completion retorna None ou vazio ---
def test__chat_completion_returns_empty_string_on_none():
    from unittest.mock import MagicMock, patch
    from app.core.config import Settings
    from app.llm.groq_client import GroqClient

    settings_obj = Settings(GROQ_API_KEY="test_key")
    with patch("app.llm.groq_client.settings", settings_obj):
        client = GroqClient()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    client._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = client._chat_completion([{"role": "user", "content": "hi"}])
    assert result == ""

    mock_response.choices[0].message.content = ""
    result2 = client._chat_completion([{"role": "user", "content": "hi"}])
    assert result2 == ""


# --- Cobertura extra: _is_payload_too_large com response.status_code ---
def test__is_payload_too_large_with_response_status_code():
    from app.llm.groq_client import GroqClient
    client = GroqClient()

    class DummyResponse:
        status_code = 413

    class DummyExc(Exception):
        response = DummyResponse()

    exc = DummyExc()
    assert client._is_payload_too_large(exc) is True

    class DummyResponse2:
        status_code = 400

    class DummyExc2(Exception):
        response = DummyResponse2()

    exc2 = DummyExc2()
    assert client._is_payload_too_large(exc2) is False


# ---------------------------------------------------------------------------
# _build_wwwh_prompt – line 136: extra param appended when non-empty
# ---------------------------------------------------------------------------

def test_build_wwwh_prompt_includes_extra_when_provided() -> None:
    """Line 136: when a non-empty `extra` is passed its content appears in the output."""
    from app.llm.groq_client import GroqClient

    client = GroqClient()
    result = client._build_wwwh_prompt(
        what="what text",
        why="why text",
        where="where text",
        how="how text",
        extra="extra note",
    )
    assert "extra note" in result
    assert result.count("\n\n") == 4  # 4 separators → 5 parts


def test_build_wwwh_prompt_excludes_extra_when_none() -> None:
    """extra=None (default) → only 4 parts, no trailing separator."""
    from app.llm.groq_client import GroqClient

    client = GroqClient()
    result = client._build_wwwh_prompt(
        what="w", why="y", where="o", how="h"
    )
    assert result.count("\n\n") == 3  # 3 separators → 4 parts


def test_build_wwwh_prompt_excludes_extra_when_whitespace_only() -> None:
    """extra='   ' is treated as absent (branch: extra.strip() is falsy)."""
    from app.llm.groq_client import GroqClient

    client = GroqClient()
    result = client._build_wwwh_prompt(
        what="w", why="y", where="o", how="h", extra="   "
    )
    assert result.count("\n\n") == 3

