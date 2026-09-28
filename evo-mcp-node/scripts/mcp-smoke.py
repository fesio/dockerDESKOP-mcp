from __future__ import annotations

import asyncio
import os
import sys

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main() -> int:
    url = os.getenv("EVO_MCP_URL", "http://127.0.0.1:8000/mcp")
    token = os.environ["MCP_API_KEY"]
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=httpx2.Timeout(30, read=30)
    ) as http_client, Client(streamable_http_client(url, http_client=http_client)) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
    profile = os.getenv("MCP_TOOL_PROFILE", "all")
    expected = {
        "apps": {"brain_collect_sources", "task_start", "programmer_tree"},
        "n8n": {"n8n_export_workflow", "n8n_list_workflows", "n8n_validate_workflow_json"},
        "all": {"brain_collect_sources", "task_start", "n8n_export_workflow"},
    }[profile]
    missing = sorted(expected - tools)
    if missing:
        print(f"missing tools: {', '.join(missing)}", file=sys.stderr)
        return 1
    forbidden_prefix = "n8n_" if profile == "apps" else None
    if forbidden_prefix and any(name.startswith(forbidden_prefix) for name in tools):
        print("apps profile leaked n8n tools", file=sys.stderr)
        return 1
    if profile == "n8n" and any(
        name.startswith(("programmer_", "brain_", "task_")) for name in tools
    ):
        print("n8n profile leaked apps tools", file=sys.stderr)
        return 1
    print(f"authenticated MCP {profile} discovery passed ({len(tools)} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
