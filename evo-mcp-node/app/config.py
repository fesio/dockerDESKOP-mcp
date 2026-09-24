from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    bind_host: str
    port: int
    log_level: str
    require_auth: bool
    api_key: str
    trust_proxy: bool
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Settings:
        require_auth = _as_bool(os.getenv("MCP_REQUIRE_AUTH"), False)
        api_key = os.getenv("MCP_API_KEY", "").strip()
        if require_auth and len(api_key) < 32:
            raise RuntimeError("MCP_API_KEY must contain at least 32 characters when auth is enabled")
        return cls(
            bind_host=os.getenv("MCP_BIND_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            require_auth=require_auth,
            api_key=api_key,
            trust_proxy=_as_bool(os.getenv("MCP_TRUST_PROXY"), False),
            allowed_hosts=_csv(
                os.getenv("MCP_ALLOWED_HOSTS"),
                ("127.0.0.1:*", "localhost:*", "[::1]:*"),
            ),
            allowed_origins=_csv(
                os.getenv("MCP_ALLOWED_ORIGINS"),
                ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"),
            ),
        )
