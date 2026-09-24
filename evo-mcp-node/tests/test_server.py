import pytest
from mcp import Client
from starlette.testclient import TestClient

from app.server import app, mcp


@pytest.mark.asyncio
async def test_server_status_tool_reports_runtime():
    async with Client(mcp) as client:
        result = await client.call_tool("server_status", {})
    payload = result.structured_content
    assert payload["name"] == "evo-mcp-node"
    assert payload["version"] == "0.1.0"
    assert payload["transport"] == "streamable-http"


@pytest.mark.asyncio
async def test_echo_tool():
    async with Client(mcp) as client:
        result = await client.call_tool("echo", {"text": "docker-ok"})
    assert result.structured_content["result"] == "docker-ok"


def test_health_and_ready_routes():
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
