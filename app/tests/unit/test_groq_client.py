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
    assert "Contexto:\nsome context" in messages[1]["content"]
    assert "Prompt:\nmy prompt" in messages[1]["content"]


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
