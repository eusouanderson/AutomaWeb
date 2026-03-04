"""Additional test for groq_client.py line 64 coverage"""


def test_groq_client_with_context() -> None:
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
            mock_response.choices[0].message.content = "Test with context"
            
            client._client.chat.completions.create = MagicMock(return_value=mock_response)
            
            # Call with context to cover line 64
            result = client.generate_robot_test("test prompt", context="some context")
            assert result == "Test with context"
            assert client._client.chat.completions.create.call_count == 1
            
            # Verify the context was used in the call
            call_args = client._client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_message = messages[1]["content"]
            assert "Contexto" in user_message
            assert "some context" in user_message
            assert "test prompt" in user_message
