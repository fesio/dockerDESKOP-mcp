from dataclasses import replace

import pytest

from app.audit import AuditLogger
from app.config import Settings
from app.n8n_client import N8nError, N8nMcpBridge, N8nRestClient, _validate_url
from app.workflow_validation import WorkflowValidationError, validate_workflow_json


def make_settings(tmp_path):
    return replace(
        Settings.from_env(),
        audit_log_path=str(tmp_path / "audit.jsonl"),
        n8n_base_url="http://n8n:5678",
        n8n_api_key="test-key",
        n8n_mcp_url="http://n8n:5678/mcp-server/http",
        n8n_mcp_token="test-token",
    )


def test_n8n_host_allowlist_blocks_ssrf():
    with pytest.raises(N8nError, match="not in N8N_ALLOWED_HOSTS"):
        _validate_url("https://evil.example/api", ("n8n", "localhost"))


def test_rest_webhook_helper(tmp_path):
    settings = make_settings(tmp_path)
    client = N8nRestClient(settings, AuditLogger(settings.audit_log_path))
    assert client.webhook_url("my-hook") == "http://n8n:5678/webhook/my-hook"
    assert client.webhook_url("my-hook", test=True) == "http://n8n:5678/webhook-test/my-hook"


def test_native_bridge_rejects_non_allowlisted_tool(tmp_path):
    settings = make_settings(tmp_path)
    bridge = N8nMcpBridge(settings, AuditLogger(settings.audit_log_path))
    with pytest.raises(N8nError, match="not in N8N_MCP_ALLOWED_TOOLS"):
        bridge._check_tool("delete_everything")


def test_workflow_json_validation_and_sanitization():
    workflow = {
        "name": "Demo",
        "nodes": [
            {
                "name": "Manual",
                "type": "n8n-nodes-base.manualTrigger",
                "position": [0, 0],
                "parameters": {},
            }
        ],
        "connections": {},
        "settings": {},
        "ignored": "not sent",
    }
    clean = validate_workflow_json(workflow)
    assert clean["name"] == "Demo"
    assert "ignored" not in clean


def test_workflow_json_rejects_duplicate_node_names():
    node = {
        "name": "Same",
        "type": "n8n-nodes-base.noOp",
        "position": [0, 0],
        "parameters": {},
    }
    with pytest.raises(WorkflowValidationError):
        validate_workflow_json({"name": "Bad", "nodes": [node, node], "connections": {}})
