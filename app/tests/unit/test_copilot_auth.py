"""Tests for Copilot authentication module - Unit tests only.

These tests ONLY test pure business logic without:
- Real OAuth calls
- Real HTTP requests
- User input/browser interaction
- Async operations that require external services
"""

import pytest
from app.llm.copilot_auth import (
    normalize_domain,
    resolve_oauth_domain,
    resolve_oauth_endpoints,
    is_token_expired,
    CopilotAuthManager,
)


class TestTokenExpiration:
    """Test token expiration helper function."""

    def test_is_token_expired_returns_true_for_expired(self):
        """Test token expiration check for expired token."""
        # Token that expired 1 hour ago (in milliseconds)
        expired_time = 1000000000  # Very old timestamp in milliseconds
        result = is_token_expired(expired_time)
        assert result is True

    def test_is_token_expired_returns_false_for_valid(self):
        """Test token expiration check for valid token."""
        # Token that expires far in the future (in milliseconds)
        # Use current time + 1 day in milliseconds
        import time
        valid_time = int((time.time() + 86400) * 1000)  # 1 day in future
        result = is_token_expired(valid_time)
        assert result is False


class TestOAuthDomainResolution:
    """Test OAuth domain resolution functions."""

    def test_normalize_domain_with_http(self):
        """Test domain normalization removes http prefix."""
        result = normalize_domain("http://github.com")
        assert result == "github.com"

    def test_normalize_domain_with_https(self):
        """Test domain normalization removes https prefix."""
        result = normalize_domain("https://github.com")
        assert result == "github.com"

    def test_normalize_domain_already_clean(self):
        """Test domain normalization with clean domain."""
        result = normalize_domain("github.com")
        assert result == "github.com"

    def test_resolve_oauth_domain_default(self):
        """Test OAuth domain resolution returns valid domain."""
        domain = resolve_oauth_domain()
        assert domain is not None
        assert isinstance(domain, str)
        assert len(domain) > 0

    def test_resolve_oauth_endpoints_returns_dict(self):
        """Test OAuth endpoints are returned as dict."""
        endpoints = resolve_oauth_endpoints()
        assert isinstance(endpoints, dict)
        assert "device_authorization_url" in endpoints or "token_url" in endpoints


class TestCopilotAuthManager:
    """Tests for CopilotAuthManager initialization only - NO network/async calls."""

    def test_auth_manager_initialization(self, tmp_path):
        """Test that auth manager can be initialized."""
        auth_path = tmp_path / ".copilot" / "auth.json"
        tmp_path.joinpath(".copilot").mkdir()
        manager = CopilotAuthManager(auth_file_path=str(auth_path))
        
        # Manager should be initialized
        assert manager is not None
        assert str(manager.auth_file_path) == str(auth_path)

    def test_auth_manager_has_client_id(self, tmp_path):
        """Test that auth manager has client ID."""
        auth_path = tmp_path / ".copilot" / "auth.json"
        tmp_path.joinpath(".copilot").mkdir()
        manager = CopilotAuthManager(auth_file_path=str(auth_path))
        
        # Should have a client ID (either default or provided)
        assert manager.client_id is not None
        assert isinstance(manager.client_id, str)
        assert len(manager.client_id) > 0

    def test_auth_manager_custom_client_id(self, tmp_path):
        """Test that auth manager accepts custom client ID."""
        auth_path = tmp_path / ".copilot" / "auth.json"
        tmp_path.joinpath(".copilot").mkdir()
        custom_id = "my_custom_client_id"
        manager = CopilotAuthManager(
            auth_file_path=str(auth_path),
            client_id=custom_id
        )
        
        # Should use custom client ID
        assert manager.client_id == custom_id
