from __future__ import annotations

from typing import Any

import httpx

from app.knowledge.models import SourceRecord


class NotionSource:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.notion.com",
        version: str = "2026-03-11",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.transport = transport

    async def search(self, query: str, limit: int = 10) -> list[SourceRecord]:
        if not self.token or not query.strip():
            return []
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            headers=headers, timeout=20, transport=self.transport
        ) as client:
            response = await client.post(
                f"{self.base_url}/v1/search",
                json={"query": query, "page_size": max(1, min(limit, 100))},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        output: list[SourceRecord] = []
        for page in payload.get("results", []):
            page_id = page.get("id", "")
            url = page.get("url") or f"notion://{page_id}"
            title = _title(page) or "Untitled Notion page"
            output.append(SourceRecord.from_text("notion", url, title, title, {"page_id": page_id}))
        return output


def _title(page: dict[str, Any]) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(part.get("plain_text", "") for part in prop.get("title", []))
    return ""
