from __future__ import annotations

import logging
import secrets
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability import metrics

logger = logging.getLogger("evo_mcp.http")


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, *, enabled: bool, api_key: str) -> None:
        self.app = app
        self.enabled = enabled
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        protected = scope.get("path", "").startswith(("/mcp", "/metrics"))
        if scope["type"] == "http" and protected and self.enabled:
            auth = Headers(scope=scope).get("authorization", "")
            expected = f"Bearer {self.api_key}"
            if not secrets.compare_digest(auth, expected):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        request_id = Headers(scope=scope).get("x-request-id") or uuid.uuid4().hex
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers.append("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_seconds = time.perf_counter() - started
            elapsed_ms = round(elapsed_seconds * 1000, 2)
            metrics.observe(str(scope.get("method", "UNKNOWN")), status_code, elapsed_seconds)
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "elapsed_ms": elapsed_ms,
                },
            )
