# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.18-python3.13-trixie-slim AS base
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY app ./app

FROM base AS test
RUN uv sync --all-groups --no-install-project
COPY tests ./tests
RUN uv run ruff check app tests && uv run pytest -q

FROM base AS runtime
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && mkdir -p /workspace /data \
    && chown -R appuser:appgroup /workspace /data /home/appuser
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]
CMD ["python", "-m", "app"]

FROM runtime AS host-tools
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
