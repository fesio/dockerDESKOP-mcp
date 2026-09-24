# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.18-python3.13-trixie-slim AS base
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY app ./app

FROM base AS test
RUN uv sync --all-groups --no-install-project
COPY tests ./tests
RUN uv run ruff check app tests && uv run pytest -q

FROM python:3.13-slim-trixie AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MCP_BIND_HOST=0.0.0.0 \
    MCP_PORT=8000
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser
COPY --from=base --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=base --chown=appuser:appgroup /app/app /app/app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]
CMD ["python", "-m", "app"]
