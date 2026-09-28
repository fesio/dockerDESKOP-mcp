import json

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware import BearerAuthMiddleware
from app.observability import Metrics, redact


def test_redact_removes_nested_secrets():
    value = {
        "Authorization": "Bearer x",
        "node": {"credentials": {"id": "1"}},
        "api_key": "hidden",
    }
    rendered = json.dumps(redact(value))
    assert "Bearer x" not in rendered
    assert "hidden" not in rendered
    assert "[REDACTED]" in rendered


def test_metrics_have_no_sensitive_labels():
    metrics = Metrics()
    metrics.observe("GET", 200, 0.12)
    rendered = metrics.render()
    assert "evo_http_requests_total" in rendered
    assert "path=" not in rendered
    assert "query=" not in rendered


def test_metrics_route_uses_same_auth_gate_as_mcp():
    async def endpoint(_):
        return PlainTextResponse("ok")

    app = BearerAuthMiddleware(
        Starlette(routes=[Route("/metrics", endpoint)]), enabled=True, api_key="x" * 32
    )
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": f"Bearer {'x' * 32}"}).status_code == 200
