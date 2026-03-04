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
