import pytest

from app.config import Settings


def test_auth_requires_long_key(monkeypatch):
    monkeypatch.setenv("MCP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("MCP_API_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        Settings.from_env()


def test_local_defaults_are_private(monkeypatch):
    for key in ("MCP_REQUIRE_AUTH", "MCP_API_KEY", "MCP_TRUST_PROXY", "MCP_ALLOWED_HOSTS"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env()
    assert settings.require_auth is False
    assert settings.trust_proxy is False
    assert "localhost:*" in settings.allowed_hosts
