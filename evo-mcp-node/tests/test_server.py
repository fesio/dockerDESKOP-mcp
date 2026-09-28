import pytest
from mcp import Client
from starlette.testclient import TestClient

from app.server import app, mcp


@pytest.mark.asyncio
async def test_server_status_reports_integrations():
    async with Client(mcp) as client:
        result = await client.call_tool("server_status", {})
    payload = result.structured_content
    assert payload["name"] == "evo-mcp-node"
    assert payload["version"] == "0.3.0"
    assert payload["transport"] == "streamable-http"
    assert payload["programmer_profile"] in {"read", "standard", "autonomous"}


@pytest.mark.asyncio
async def test_prompt_is_available():
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    assert "n8n_workflow_builder" in {prompt.name for prompt in prompts.prompts}


@pytest.mark.asyncio
async def test_required_evo_tools_are_discoverable():
    async with Client(mcp) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
    assert {"brain_collect_sources", "task_start", "n8n_export_workflow"} <= tools


def test_health_and_ready_routes():
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
