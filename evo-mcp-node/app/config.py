from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int(value: str | None, default: int) -> int:
    return int(value) if value else default


def _float(value: str | None, default: float) -> float:
    return float(value) if value else default


DEFAULT_N8N_MCP_TOOLS = (
    "search_workflows",
    "get_workflow_details",
    "execute_workflow",
    "test_workflow",
    "get_workflow_execution",
    "search_workflow_executions",
    "get_workflow_history",
    "get_workflow_version",
    "get_workflow_versions_diff",
    "restore_workflow_version",
    "publish_workflow",
    "unpublish_workflow",
    "prepare_workflow_pin_data",
    "get_workflow_sdk_reference",
    "get_workflow_best_practices",
    "search_nodes",
    "get_node_types",
    "explore_node_resources",
    "validate_workflow",
    "validate_node_config",
    "create_workflow_from_code",
    "update_workflow",
    "search_projects",
    "search_folders",
    "list_credentials",
    "list_workflow_tags",
)


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

    programmer_profile: str
    programmer_workspace: str
    programmer_max_file_bytes: int
    programmer_command_timeout: int
    programmer_allowed_commands: tuple[str, ...]
    programmer_approval_secret: str
    programmer_allow_docker: bool
    audit_log_path: str

    n8n_base_url: str
    n8n_api_key: str
    n8n_api_auth_scheme: str
    n8n_mcp_url: str
    n8n_mcp_token: str
    n8n_allowed_hosts: tuple[str, ...]
    n8n_timeout_seconds: float
    n8n_verify_tls: bool
    n8n_mcp_allowed_tools: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Settings:
        require_auth = _as_bool(os.getenv("MCP_REQUIRE_AUTH"), False)
        api_key = os.getenv("MCP_API_KEY", "").strip()
        if require_auth and len(api_key) < 32:
            raise RuntimeError("MCP_API_KEY must contain at least 32 characters when auth is enabled")

        profile = os.getenv("PROGRAMMER_PROFILE", "standard").strip().lower()
        if profile not in {"read", "standard", "autonomous"}:
            raise RuntimeError("PROGRAMMER_PROFILE must be read, standard, or autonomous")

        api_auth_scheme = os.getenv("N8N_API_AUTH_SCHEME", "api-key").strip().lower()
        if api_auth_scheme not in {"api-key", "bearer"}:
            raise RuntimeError("N8N_API_AUTH_SCHEME must be api-key or bearer")

        return cls(
            bind_host=os.getenv("MCP_BIND_HOST", "0.0.0.0"),
            port=_int(os.getenv("MCP_PORT"), 8000),
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
            programmer_profile=profile,
            programmer_workspace=os.getenv("PROGRAMMER_WORKSPACE", "/workspace"),
            programmer_max_file_bytes=_int(os.getenv("PROGRAMMER_MAX_FILE_BYTES"), 2_000_000),
            programmer_command_timeout=_int(os.getenv("PROGRAMMER_COMMAND_TIMEOUT"), 120),
            programmer_allowed_commands=_csv(
                os.getenv("PROGRAMMER_ALLOWED_COMMANDS"),
                ("git", "python", "python3", "pytest", "ruff", "uv", "node", "npm", "pnpm", "docker"),
            ),
            programmer_approval_secret=os.getenv("PROGRAMMER_APPROVAL_SECRET", ""),
            programmer_allow_docker=_as_bool(os.getenv("PROGRAMMER_ALLOW_DOCKER"), False),
            audit_log_path=os.getenv("AUDIT_LOG_PATH", "/data/audit.jsonl"),
            n8n_base_url=os.getenv("N8N_BASE_URL", "").rstrip("/"),
            n8n_api_key=os.getenv("N8N_API_KEY", "").strip(),
            n8n_api_auth_scheme=api_auth_scheme,
            n8n_mcp_url=os.getenv("N8N_MCP_URL", "").strip(),
            n8n_mcp_token=os.getenv("N8N_MCP_TOKEN", "").strip(),
            n8n_allowed_hosts=_csv(os.getenv("N8N_ALLOWED_HOSTS"), ("localhost", "127.0.0.1", "n8n")),
            n8n_timeout_seconds=_float(os.getenv("N8N_TIMEOUT_SECONDS"), 30.0),
            n8n_verify_tls=_as_bool(os.getenv("N8N_VERIFY_TLS"), True),
            n8n_mcp_allowed_tools=_csv(os.getenv("N8N_MCP_ALLOWED_TOOLS"), DEFAULT_N8N_MCP_TOOLS),
        )
