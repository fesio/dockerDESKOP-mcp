from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.audit import AuditLogger
from app.config import Settings


class N8nError(RuntimeError):
    pass


def _host_allowed(host: str | None, allowed: tuple[str, ...]) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    for rule in allowed:
        rule = rule.lower().strip().rstrip(".")
        if rule.startswith("*.") and (host == rule[2:] or host.endswith(rule[1:])):
            return True
        if host == rule:
            return True
    return False


def _validate_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise N8nError("n8n URL must use http or https")
    if not _host_allowed(parsed.hostname, allowed_hosts):
        raise N8nError(f"n8n host {parsed.hostname!r} is not in N8N_ALLOWED_HOSTS")
    return url.rstrip("/")


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


@dataclass(slots=True)
class N8nRestClient:
    settings: Settings
    audit: AuditLogger

    def _base(self) -> str:
        if not self.settings.n8n_base_url:
            raise N8nError("N8N_BASE_URL is not configured")
        return _validate_url(self.settings.n8n_base_url, self.settings.n8n_allowed_hosts)

    def _headers(self) -> dict[str, str]:
        if not self.settings.n8n_api_key:
            raise N8nError("N8N_API_KEY is not configured")
        if self.settings.n8n_api_auth_scheme == "bearer":
            return {"Authorization": f"Bearer {self.settings.n8n_api_key}"}
        return {"X-N8N-API-KEY": self.settings.n8n_api_key}

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        retries: int = 3,
    ) -> Any:
        base = self._base()
        url = f"{base}{path}"
        headers = {**self._headers(), "Accept": "application/json"}
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.settings.n8n_timeout_seconds,
                    verify=self.settings.n8n_verify_tls,
                    headers=headers,
                ) as client:
                    response = await client.request(method, url, params=params, json=json)
            except httpx.HTTPError as exc:
                if attempt + 1 >= retries:
                    self.audit.write("n8n.rest", "network_error", method=method, path=path)
                    raise N8nError(f"n8n network error: {exc.__class__.__name__}") from exc
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status_code in {429, 502, 503, 504} and attempt + 1 < retries:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.is_error:
                try:
                    body = response.json()
                except ValueError:
                    body = {"message": response.text[:500]}
                self.audit.write("n8n.rest", "error", method=method, path=path, status=response.status_code)
                raise N8nError(f"n8n API {response.status_code}: {body}")
            self.audit.write("n8n.rest", "ok", method=method, path=path, status=response.status_code)
            if response.status_code == 204 or not response.content:
                return {"ok": True}
            return response.json()
        raise N8nError("n8n request failed after retries")

    async def list_workflows(self, limit: int = 50, cursor: str = "") -> Any:
        params: dict[str, Any] = {"limit": max(1, min(limit, 250))}
        if cursor:
            params["cursor"] = cursor
        return await self.request("GET", "/api/v1/workflows", params=params)

    async def get_workflow(self, workflow_id: str) -> Any:
        return await self.request("GET", f"/api/v1/workflows/{workflow_id}")

    async def create_workflow(self, workflow: dict[str, Any]) -> Any:
        return await self.request("POST", "/api/v1/workflows", json=workflow)

    async def update_workflow(self, workflow_id: str, workflow: dict[str, Any]) -> Any:
        return await self.request("PUT", f"/api/v1/workflows/{workflow_id}", json=workflow)

    async def activate_workflow(self, workflow_id: str) -> Any:
        return await self.request("POST", f"/api/v1/workflows/{workflow_id}/activate")

    async def deactivate_workflow(self, workflow_id: str) -> Any:
        return await self.request("POST", f"/api/v1/workflows/{workflow_id}/deactivate")

    async def list_executions(self, workflow_id: str = "", limit: int = 50) -> Any:
        params: dict[str, Any] = {"limit": max(1, min(limit, 250))}
        if workflow_id:
            params["workflowId"] = workflow_id
        return await self.request("GET", "/api/v1/executions", params=params)

    def webhook_url(self, path: str, test: bool = False) -> str:
        if not path.strip("/"):
            raise N8nError("webhook path must not be empty")
        prefix = "webhook-test" if test else "webhook"
        return f"{self._base()}/{prefix}/{path.strip('/')}"


@dataclass(slots=True)
class N8nMcpBridge:
    settings: Settings
    audit: AuditLogger

    def _url(self) -> str:
        if not self.settings.n8n_mcp_url:
            raise N8nError("N8N_MCP_URL is not configured")
        return _validate_url(self.settings.n8n_mcp_url, self.settings.n8n_allowed_hosts)

    def _check_tool(self, tool_name: str) -> None:
        if tool_name not in self.settings.n8n_mcp_allowed_tools:
            raise N8nError(f"n8n MCP tool {tool_name!r} is not in N8N_MCP_ALLOWED_TOOLS")

    async def list_tools(self) -> list[dict[str, Any]]:
        url = self._url()
        headers = {"Authorization": f"Bearer {self.settings.n8n_mcp_token}"} if self.settings.n8n_mcp_token else {}
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=httpx2.Timeout(self.settings.n8n_timeout_seconds, read=300.0),
            verify=self.settings.n8n_verify_tls,
        ) as http_client:
            transport = streamable_http_client(url, http_client=http_client)
            async with Client(transport) as client:
                result = await client.list_tools()
        tools = []
        for tool in result.tools:
            if tool.name in self.settings.n8n_mcp_allowed_tools:
                dumped = tool.model_dump(mode="json", by_alias=True)
                tools.append({
                    "name": dumped.get("name"),
                    "description": dumped.get("description"),
                    "inputSchema": dumped.get("inputSchema", dumped.get("input_schema")),
                })
        self.audit.write("n8n.mcp.list_tools", "ok", count=len(tools))
        return tools

    async def call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        self._check_tool(tool_name)
        url = self._url()
        headers = {"Authorization": f"Bearer {self.settings.n8n_mcp_token}"} if self.settings.n8n_mcp_token else {}
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=httpx2.Timeout(self.settings.n8n_timeout_seconds, read=3600.0),
            verify=self.settings.n8n_verify_tls,
        ) as http_client:
            transport = streamable_http_client(url, http_client=http_client)
            async with Client(transport) as client:
                result = await client.call_tool(tool_name, arguments or {})
        self.audit.write("n8n.mcp.call", "ok", tool=tool_name)
        return _dump(result)

    async def prepare_build_context(
        self,
        description: str,
        technique: str = "",
        node_queries: list[str] | None = None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "description": description,
            "recommended_sequence": [
                "get_workflow_sdk_reference",
                "get_workflow_best_practices (when a technique is known)",
                "search_nodes",
                "get_node_types",
                "generate Workflow SDK code",
                "validate_workflow",
                "create_workflow_from_code or update_workflow",
                "test workflow",
                "publish_workflow only after validation",
            ],
        }
        context["sdk_reference"] = await self.call("get_workflow_sdk_reference", {"section": "all"})
        if technique:
            context["best_practices"] = await self.call("get_workflow_best_practices", {"technique": technique})
        if node_queries:
            context["node_search"] = await self.call("search_nodes", {"queries": node_queries, "usage": "workflow"})
        return context
