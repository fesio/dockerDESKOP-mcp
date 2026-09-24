from __future__ import annotations

import platform
from datetime import UTC, datetime

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import __version__
from app.config import Settings
from app.logging_setup import configure_logging
from app.middleware import BearerAuthMiddleware, RequestLogMiddleware

settings = Settings.from_env()
configure_logging(settings.log_level)

mcp = MCPServer(
    "evo-mcp-node",
    title="Evo MCP Node",
    description="Private local-first MCP server for Docker Desktop and cloud hosting.",
    version=__version__,
    instructions="Use tools exposed by this node only for the authenticated owner of the server.",
)


@mcp.tool()
def server_status() -> dict[str, str | bool]:
    """Return non-sensitive runtime information about this MCP node."""
    return {
        "name": "evo-mcp-node",
        "version": __version__,
        "transport": "streamable-http",
        "python": platform.python_version(),
        "auth_required": settings.require_auth,
        "utc": datetime.now(UTC).isoformat(),
    }


@mcp.tool()
def echo(text: str) -> str:
    """Return the supplied text. Useful for connectivity checks."""
    return text


@mcp.resource("evo://about")
def about() -> str:
    """Describe this MCP node."""
    return "Evo MCP Node: local-first Docker Desktop server with cloud-ready Streamable HTTP."


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "evo-mcp-node", "version": __version__})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(_: Request) -> JSONResponse:
    return JSONResponse({"ready": True})


if settings.trust_proxy:
    transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
else:
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(settings.allowed_hosts),
        allowed_origins=list(settings.allowed_origins),
    )

base_app = mcp.streamable_http_app(
    host=settings.bind_host,
    transport_security=transport_security,
)
app = RequestLogMiddleware(
    BearerAuthMiddleware(base_app, enabled=settings.require_auth, api_key=settings.api_key)
)
