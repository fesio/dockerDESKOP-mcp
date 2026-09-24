from dataclasses import replace

import pytest

from app.config import DEFAULT_N8N_MCP_TOOLS, Settings


def test_auth_requires_long_key(monkeypatch):
    monkeypatch.setenv("MCP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("MCP_API_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        Settings.from_env()


def test_programmer_profile_validation(monkeypatch):
    monkeypatch.setenv("PROGRAMMER_PROFILE", "root")
    with pytest.raises(RuntimeError, match="PROGRAMMER_PROFILE"):
        Settings.from_env()


def test_current_n8n_native_tools_are_allowlisted(monkeypatch):
    monkeypatch.delenv("N8N_MCP_ALLOWED_TOOLS", raising=False)
    settings = Settings.from_env()
    expected = {
        "get_workflow_details",
        "test_workflow",
        "get_workflow_execution",
        "search_workflow_executions",
        "get_workflow_versions_diff",
        "prepare_workflow_pin_data",
        "get_workflow_sdk_reference",
        "validate_workflow",
        "create_workflow_from_code",
        "update_workflow",
    }
    assert expected.issubset(set(settings.n8n_mcp_allowed_tools))
    assert "get_workflow" not in DEFAULT_N8N_MCP_TOOLS


def test_n8n_auth_scheme_validation(monkeypatch):
    monkeypatch.setenv("N8N_API_AUTH_SCHEME", "cookie")
    with pytest.raises(RuntimeError, match="api-key or bearer"):
        Settings.from_env()
