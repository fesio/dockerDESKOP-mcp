from dataclasses import replace

import httpx
import pytest

from app.audit import AuditLogger
from app.config import Settings
from app.n8n_client import N8nError, N8nMcpBridge, N8nRestClient, _validate_url
from app.n8n_workflows import N8nConflictError, WorkflowService
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


@pytest.mark.asyncio
async def test_export_removes_instance_and_credential_metadata(tmp_path):
    workflow = {
        "id": "wf-1",
        "createdAt": "today",
        "updatedAt": "today",
        "versionId": "v1",
        "name": "Export",
        "nodes": [{"name": "HTTP", "type": "n8n-nodes-base.httpRequest", "position": [0, 0],
                   "parameters": {}, "credentials": {"httpHeaderAuth": {"id": "secret", "name": "Prod"}}}],
        "connections": {},
        "settings": {},
        "pinData": {"x": "private"},
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=workflow))
    settings = make_settings(tmp_path)
    client = N8nRestClient(settings, AuditLogger(settings.audit_log_path), transport=transport)
    exported = await WorkflowService(client).export_workflow("wf-1", include_pin_data=False)
    assert "id" not in exported
    assert "createdAt" not in exported
    assert "pinData" not in exported
    assert exported["nodes"][0]["credentials"] == {
        "httpHeaderAuth": {"name": "${N8N_CREDENTIAL_HTTPHEADERAUTH}"}
    }


@pytest.mark.asyncio
async def test_import_requires_matching_version_for_update(tmp_path):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"id": "wf-1", "versionId": "newer"})
    )
    settings = make_settings(tmp_path)
    service = WorkflowService(
        N8nRestClient(settings, AuditLogger(settings.audit_log_path), transport=transport)
    )
    workflow = {"name": "Demo", "nodes": [], "connections": {}, "settings": {}}
    with pytest.raises(N8nConflictError, match="version"):
        await service.import_workflow(workflow, workflow_id="wf-1", expected_version_id="older")
