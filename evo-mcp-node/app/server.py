from __future__ import annotations

import platform
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from app import __version__
from app.audit import AuditLogger
from app.config import Settings
from app.knowledge.notebooklm import NotebookBundle
from app.knowledge.notion import NotionSource
from app.knowledge.obsidian import ObsidianSource
from app.knowledge.service import KnowledgeService
from app.logging_setup import configure_logging
from app.middleware import BearerAuthMiddleware, RequestLogMiddleware
from app.n8n_client import N8nMcpBridge, N8nRestClient
from app.n8n_workflows import WorkflowService
from app.observability import metrics
from app.programmer import ProgrammerWorkspace
from app.tasks import TaskRunner, TaskStore
from app.telemetry import telemetry_enabled, wrap_asgi
from app.workflow_validation import validate_workflow_json

settings = Settings.from_env()
configure_logging(settings.log_level)
audit = AuditLogger(settings.audit_log_path)
programmer = ProgrammerWorkspace(settings=settings, audit=audit)
n8n_rest = N8nRestClient(settings=settings, audit=audit)
n8n_mcp = N8nMcpBridge(settings=settings, audit=audit)
n8n_workflows = WorkflowService(n8n_rest)
notion_source = (
    NotionSource(
        settings.notion_token,
        base_url=settings.notion_base_url,
        version=settings.notion_version,
    )
    if settings.notion_token
    else None
)
knowledge = KnowledgeService(ObsidianSource(settings.brain_vault_path), notion_source)
notebooklm = NotebookBundle(settings.notebooklm_bundle_path, settings.notebooklm_import_path)
task_owner = sha256(settings.api_key.encode()).hexdigest() if settings.require_auth else "local"
task_store = TaskStore(settings.task_db_path, settings.task_artifact_dir)
task_store.recover_interrupted()


def _programmer_task(method: str):
    def run(arguments: dict[str, Any], cancelled, log):
        if cancelled():
            return {"cancelled": True}
        log(f"starting {method}")
        result = getattr(programmer, method)(**arguments)
        log(f"finished {method} with return code {result.get('returncode')}")
        return result

    return run


task_runner = TaskRunner(
    task_store,
    {
        "programmer.test": _programmer_task("test"),
        "programmer.lint": _programmer_task("lint"),
        "programmer.format_check": _programmer_task("format_check"),
        "programmer.typecheck": _programmer_task("typecheck"),
        "docker.build": _programmer_task("docker_build"),
        "docker.compose_up": _programmer_task("compose_up"),
    },
    workers=settings.task_workers,
)


class ProfiledMCPServer(MCPServer):
    """MCP server that can expose an app-only or n8n-only tool surface."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._evo_tool_profiles: dict[str, str] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        register = super().tool(*args, **kwargs)

        def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
            registered = register(function)
            name = kwargs.get("name") or function.__name__
            if name in {"server_status", "echo"}:
                profile = "shared"
            else:
                profile = "n8n" if name.startswith("n8n_") else "apps"
            self._evo_tool_profiles[name] = profile
            return registered

        return decorator

    def apply_tool_profile(self, profile: str) -> None:
        if profile == "all":
            return
        for name, registered_profile in tuple(self._evo_tool_profiles.items()):
            if registered_profile not in {"shared", profile}:
                self.remove_tool(name)


mcp = ProfiledMCPServer(
    "evo-mcp-node",
    title="Evo MCP Node",
    description="Local-first programmer MCP with native n8n workflow automation.",
    version=__version__,
    instructions=(
        "Operate only inside the configured /workspace. Prefer read/validate/test before writes. "
        "For n8n workflow creation, use the native n8n MCP builder path: reference -> best practices -> "
        "node search -> validate -> create/update -> test -> publish."
    ),
)


def _structured(result: Any) -> Any:
    if not isinstance(result, dict):
        return None
    return result.get("structuredContent", result.get("structured_content"))


def _require_standard() -> None:
    programmer._require("standard")


def _n8n_tool_policy(tool_name: str) -> None:
    destructive = {"archive_workflow", "delete_workflow", "delete_execution"}
    if tool_name in destructive or tool_name.startswith(("delete_", "archive_")):
        raise ValueError(f"destructive n8n MCP tool {tool_name!r} is blocked by Evo MCP")
    mutating = {
        "execute_workflow",
        "test_workflow",
        "create_workflow_from_code",
        "update_workflow",
        "publish_workflow",
        "unpublish_workflow",
        "restore_workflow_version",
        "explore_node_resources",
    }
    if tool_name in mutating:
        _require_standard()


@mcp.tool()
def server_status() -> dict[str, Any]:
    """Return non-sensitive runtime and integration status."""
    return {
        "name": "evo-mcp-node",
        "version": __version__,
        "transport": "streamable-http",
        "tool_profile": settings.tool_profile,
        "python": platform.python_version(),
        "auth_required": settings.require_auth,
        "programmer_profile": settings.programmer_profile,
        "workspace": settings.programmer_workspace,
        "docker_enabled": settings.programmer_allow_docker,
        "n8n_rest_configured": bool(settings.n8n_base_url and settings.n8n_api_key),
        "n8n_native_mcp_configured": bool(settings.n8n_mcp_url and settings.n8n_mcp_token),
        "opentelemetry_enabled": telemetry_enabled(),
        "utc": datetime.now(UTC).isoformat(),
    }


@mcp.tool()
def echo(text: str) -> str:
    """Return supplied text for connectivity tests."""
    return text


@mcp.tool()
def programmer_tree(path: str = ".", max_depth: int = 3, max_entries: int = 250) -> list[dict[str, object]]:
    """List files under the sandboxed workspace."""
    return programmer.tree(path, max_depth=max(1, min(max_depth, 8)), max_entries=max(1, min(max_entries, 1000)))


@mcp.tool()
def programmer_read_file(path: str, max_chars: int = 120_000) -> str:
    """Read a UTF-8 text file from the sandboxed workspace."""
    return programmer.read(path, max_chars=max(1, min(max_chars, 500_000)))


@mcp.tool()
def programmer_search(query: str, path: str = ".", max_results: int = 50) -> list[dict[str, object]]:
    """Search text recursively within the sandboxed workspace."""
    return programmer.search(query, path, max_results=max(1, min(max_results, 200)))


@mcp.tool()
def programmer_write_file(path: str, content: str, overwrite: bool = True) -> dict[str, object]:
    """Write a file inside /workspace. Requires standard or autonomous profile."""
    return programmer.write(path, content, overwrite=overwrite)


@mcp.tool()
def programmer_delete(path: str, approval: str) -> dict[str, object]:
    """Delete a workspace path. Requires autonomous profile and local approval secret."""
    return programmer.delete(path, approval)


@mcp.tool()
def programmer_run(argv: list[str], cwd: str = ".") -> dict[str, object]:
    """Run an allow-listed command without a shell inside the workspace."""
    return programmer.run(argv, cwd)


@mcp.tool()
def programmer_git_status() -> dict[str, object]:
    """Return git status for the workspace repository."""
    return programmer.git_status()


@mcp.tool()
def programmer_git_diff(staged: bool = False) -> dict[str, object]:
    """Return current git diff."""
    return programmer.git_diff(staged=staged)


@mcp.tool()
def programmer_git_branch(name: str) -> dict[str, object]:
    """Create and switch to a new git branch."""
    return programmer.git_branch(name)


@mcp.tool()
def programmer_git_commit(message: str, paths: list[str]) -> dict[str, object]:
    """Commit explicitly listed paths. Blanket git add is intentionally disabled."""
    return programmer.git_commit(message, paths)


@mcp.tool()
def programmer_git_push(branch: str, approval: str) -> dict[str, object]:
    """Push a branch. Requires autonomous profile and local approval secret."""
    return programmer.git_push(branch, approval)


@mcp.tool()
def programmer_test(cwd: str = ".") -> dict[str, object]:
    """Run the workspace test suite through a fixed command."""
    return programmer.test(cwd)


@mcp.tool()
def programmer_lint(cwd: str = ".") -> dict[str, object]:
    """Run Ruff lint through a fixed command."""
    return programmer.lint(cwd)


@mcp.tool()
def programmer_typecheck(cwd: str = ".") -> dict[str, object]:
    """Run Pyright through a fixed command."""
    return programmer.typecheck(cwd)


@mcp.tool()
def programmer_docker_status(cwd: str = ".") -> dict[str, object]:
    """Show Compose status when host Docker access is explicitly enabled."""
    return programmer.docker_status(cwd)


@mcp.tool()
def programmer_docker_logs(service: str, lines: int = 200, cwd: str = ".") -> dict[str, object]:
    """Read bounded Compose logs for one service."""
    return programmer.docker_logs(service, lines, cwd)


@mcp.tool()
def task_start(
    operation: str, arguments: dict[str, Any] | None, idempotency_key: str
) -> dict[str, Any]:
    """Start one registered long-running operation and return immediately."""
    return task_runner.start(task_owner, operation, arguments or {}, idempotency_key).public()


@mcp.tool()
def task_status(task_id: str) -> dict[str, Any]:
    """Get an owner-isolated durable task status."""
    return task_store.get(task_owner, task_id).public()


@mcp.tool()
def task_logs(task_id: str) -> list[dict[str, Any]]:
    """Get bounded logs for an owner-isolated task."""
    return task_store.logs(task_owner, task_id)


@mcp.tool()
def task_result(task_id: str) -> Any:
    """Get the JSON result for a completed owner-isolated task."""
    return task_store.result(task_owner, task_id)


@mcp.tool()
def task_cancel(task_id: str) -> dict[str, Any]:
    """Cooperatively request cancellation of a running task."""
    return task_store.request_cancel(task_owner, task_id).public()


@mcp.tool()
def task_list(limit: int = 50) -> list[dict[str, Any]]:
    """List recent durable tasks for the authenticated owner."""
    return [task.public() for task in task_store.list(task_owner, limit)]


@mcp.tool()
async def brain_collect_sources(
    question: str, sensitivity: str = "private", require_fresh: bool = False
) -> dict[str, Any]:
    """Collect cited Obsidian and optionally Notion evidence before answering."""
    return (await knowledge.collect(
        question, sensitivity=sensitivity, require_fresh=require_fresh
    )).to_dict()


@mcp.tool()
async def brain_answer_context(
    question: str, sensitivity: str = "private", require_fresh: bool = False
) -> dict[str, Any]:
    """Return the evidence gate and source excerpts; answer only when ready_to_answer is true."""
    pack = await knowledge.collect(
        question, sensitivity=sensitivity, require_fresh=require_fresh
    )
    result = pack.to_dict()
    result["instruction"] = (
        "Answer only from these sources and cite every material claim. "
        "If ready_to_answer is false, ask for sources instead of guessing."
    )
    return result


@mcp.tool()
async def brain_prepare_notebook(
    question: str, sensitivity: str = "private", require_fresh: bool = False
) -> dict[str, str]:
    """Prepare a local source bundle for manual use with personal NotebookLM."""
    pack = await knowledge.collect(
        question, sensitivity=sensitivity, require_fresh=require_fresh
    )
    return notebooklm.prepare(str(uuid4()), question, pack.sources, sensitivity=sensitivity)


@mcp.tool()
def brain_resume_notebook(filename: str) -> dict[str, Any]:
    """Import a manually exported NotebookLM answer from the configured safe folder."""
    return notebooklm.resume(filename).to_dict()


@mcp.tool()
async def n8n_list_workflows(limit: int = 50, cursor: str = "") -> Any:
    """List n8n workflows through the public REST API."""
    return await n8n_rest.list_workflows(limit, cursor)


@mcp.tool()
async def n8n_get_workflow(workflow_id: str) -> Any:
    """Fetch a workflow through the public REST API."""
    return await n8n_rest.get_workflow(workflow_id)


@mcp.tool()
def n8n_validate_workflow_json(workflow: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize portable n8n workflow JSON without changing n8n state."""
    return validate_workflow_json(workflow)


@mcp.tool()
async def n8n_create_workflow_json(workflow: dict[str, Any]) -> Any:
    """Create a workflow through REST after local shape validation. Native MCP builder is preferred."""
    _require_standard()
    return await n8n_rest.create_workflow(validate_workflow_json(workflow))


@mcp.tool()
async def n8n_update_workflow_json(workflow_id: str, workflow: dict[str, Any]) -> Any:
    """Update a workflow through REST after validation. Native MCP update_workflow is preferred."""
    _require_standard()
    return await n8n_rest.update_workflow(workflow_id, validate_workflow_json(workflow))


@mcp.tool()
async def n8n_activate_workflow_rest(workflow_id: str) -> Any:
    """Activate a workflow using REST fallback."""
    _require_standard()
    return await n8n_rest.activate_workflow(workflow_id)


@mcp.tool()
async def n8n_deactivate_workflow_rest(workflow_id: str) -> Any:
    """Deactivate a workflow using REST fallback."""
    _require_standard()
    return await n8n_rest.deactivate_workflow(workflow_id)


@mcp.tool()
async def n8n_list_executions_rest(workflow_id: str = "", limit: int = 50) -> Any:
    """List workflow executions through REST."""
    return await n8n_rest.list_executions(workflow_id, limit)


@mcp.tool()
async def n8n_export_workflow(workflow_id: str, include_pin_data: bool = False) -> Any:
    """Export portable workflow JSON with instance metadata and credential IDs removed."""
    return await n8n_workflows.export_workflow(workflow_id, include_pin_data=include_pin_data)


@mcp.tool()
async def n8n_import_workflow(
    workflow: dict[str, Any], workflow_id: str = "", expected_version_id: str = ""
) -> Any:
    """Create or version-safely update a validated n8n workflow from JSON."""
    _require_standard()
    return await n8n_workflows.import_workflow(
        workflow, workflow_id=workflow_id, expected_version_id=expected_version_id
    )


@mcp.tool()
async def n8n_get_execution_status(execution_id: str) -> dict[str, Any]:
    """Return the bounded status summary of one n8n execution."""
    return await n8n_workflows.execution_status(execution_id)


@mcp.tool()
async def n8n_get_execution_logs(execution_id: str) -> Any:
    """Return redacted and bounded n8n execution data/logs."""
    return await n8n_workflows.execution_logs(execution_id)


@mcp.tool()
def n8n_webhook_url(path: str, test: bool = False) -> str:
    """Build a production or test n8n webhook URL from N8N_BASE_URL."""
    return n8n_rest.webhook_url(path, test=test)


@mcp.tool()
async def n8n_native_tools() -> list[dict[str, Any]]:
    """List allow-listed tools exposed by n8n's instance-level MCP server."""
    return await n8n_mcp.list_tools()


@mcp.tool()
async def n8n_native_call(tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call an allow-listed native n8n MCP tool. Mutating calls require standard profile."""
    _n8n_tool_policy(tool_name)
    return await n8n_mcp.call(tool_name, arguments or {})


@mcp.tool()
async def n8n_prepare_workflow_build(
    description: str,
    technique: str = "",
    node_queries: list[str] | None = None,
) -> dict[str, Any]:
    """Collect current n8n Workflow SDK reference, best practices and node candidates for an AI builder."""
    return await n8n_mcp.prepare_build_context(description, technique, node_queries)


@mcp.tool()
async def n8n_validate_workflow_code(code: str) -> Any:
    """Validate n8n Workflow SDK TypeScript/JavaScript before creation or update."""
    return await n8n_mcp.call("validate_workflow", {"code": code})


@mcp.tool()
async def n8n_create_workflow_from_code(
    code: str,
    name: str = "",
    description: str = "",
    project_id: str = "",
    folder_id: str = "",
    skills_used: list[str] | None = None,
) -> dict[str, Any]:
    """Validate Workflow SDK code, then create it through n8n's native MCP builder."""
    _require_standard()
    validation = await n8n_mcp.call("validate_workflow", {"code": code})
    structured = _structured(validation)
    if isinstance(structured, dict) and structured.get("valid") is False:
        return {"created": False, "validation": validation}
    arguments: dict[str, Any] = {"code": code}
    if name:
        arguments["name"] = name
    if description:
        arguments["description"] = description
    if project_id:
        arguments["projectId"] = project_id
    if folder_id:
        arguments["folderId"] = folder_id
    if skills_used:
        arguments["skillsUsed"] = skills_used
    created = await n8n_mcp.call("create_workflow_from_code", arguments)
    return {"created": True, "validation": validation, "result": created}


@mcp.tool()
async def n8n_update_workflow_native(
    workflow_id: str,
    operations: list[dict[str, Any]],
    skills_used: list[str] | None = None,
) -> Any:
    """Apply an atomic ordered batch of native n8n workflow update operations."""
    _require_standard()
    args: dict[str, Any] = {"workflowId": workflow_id, "operations": operations}
    if skills_used:
        args["skillsUsed"] = skills_used
    return await n8n_mcp.call("update_workflow", args)


@mcp.tool()
async def n8n_test_workflow(
    workflow_id: str,
    pin_data: dict[str, list[Any]],
    trigger_node_name: str = "",
    timeout: int = 300,
) -> Any:
    """Run an n8n workflow test using pin data so external services can be bypassed."""
    _require_standard()
    args: dict[str, Any] = {
        "workflowId": workflow_id,
        "pinData": pin_data,
        "timeout": max(1, min(timeout, 3600)),
    }
    if trigger_node_name:
        args["triggerNodeName"] = trigger_node_name
    return await n8n_mcp.call("test_workflow", args)


@mcp.tool()
async def n8n_execute_workflow(
    workflow_id: str,
    execution_mode: str,
    trigger_node_name: str = "",
    inputs: dict[str, Any] | None = None,
) -> Any:
    """Start an n8n workflow through native MCP and return its execution ID."""
    _require_standard()
    if execution_mode not in {"manual", "production"}:
        raise ValueError("execution_mode must be manual or production")
    args: dict[str, Any] = {"workflowId": workflow_id, "executionMode": execution_mode}
    if trigger_node_name:
        args["triggerNodeName"] = trigger_node_name
    if inputs is not None:
        args["inputs"] = inputs
    return await n8n_mcp.call("execute_workflow", args)


@mcp.tool()
async def n8n_get_workflow_details(workflow_id: str, detail_level: str = "execution") -> Any:
    """Fetch current workflow details through n8n native MCP."""
    if detail_level not in {"full", "execution"}:
        raise ValueError("detail_level must be full or execution")
    return await n8n_mcp.call(
        "get_workflow_details",
        {"workflowId": workflow_id, "detailLevel": detail_level},
    )


@mcp.tool()
async def n8n_prepare_workflow_pin_data(workflow_id: str) -> Any:
    """Ask n8n to prepare schemas for realistic pin data used by test_workflow."""
    return await n8n_mcp.call("prepare_workflow_pin_data", {"workflowId": workflow_id})


@mcp.tool()
async def n8n_search_workflow_executions(
    workflow_id: str = "",
    status: list[str] | None = None,
    started_after: str = "",
    started_before: str = "",
    limit: int = 20,
    cursor: str = "",
) -> Any:
    """Search n8n execution metadata with status/time filters and cursor pagination."""
    args: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    if workflow_id:
        args["workflowId"] = workflow_id
    if status:
        args["status"] = status
    if started_after:
        args["startedAfter"] = started_after
    if started_before:
        args["startedBefore"] = started_before
    if cursor:
        args["cursor"] = cursor
    return await n8n_mcp.call("search_workflow_executions", args)


@mcp.tool()
async def n8n_get_workflow_history(workflow_id: str, limit: int = 50, offset: int = 0) -> Any:
    """List saved workflow versions before making or restoring changes."""
    return await n8n_mcp.call(
        "get_workflow_history",
        {"workflowId": workflow_id, "limit": max(1, min(limit, 50)), "offset": max(0, offset)},
    )


@mcp.tool()
async def n8n_get_workflow_version(workflow_id: str, version_id: str) -> Any:
    """Read one saved workflow version with sanitized credential references."""
    return await n8n_mcp.call(
        "get_workflow_version", {"workflowId": workflow_id, "versionId": version_id}
    )


@mcp.tool()
async def n8n_validate_node_config(nodes: list[dict[str, Any]]) -> Any:
    """Validate 1-50 node parameter objects before assembling/updating a workflow."""
    if not 1 <= len(nodes) <= 50:
        raise ValueError("nodes must contain between 1 and 50 entries")
    return await n8n_mcp.call("validate_node_config", {"nodes": nodes})


@mcp.tool()
async def n8n_restore_workflow_version(workflow_id: str, version_id: str) -> Any:
    """Restore a saved version as the current draft. Requires standard programmer profile."""
    _require_standard()
    return await n8n_mcp.call(
        "restore_workflow_version", {"workflowId": workflow_id, "versionId": version_id}
    )


@mcp.tool()
async def n8n_get_workflow_versions_diff(
    workflow_id: str,
    from_version_id: str,
    to_version_id: str,
) -> Any:
    """Compare two workflow versions before publishing an update."""
    return await n8n_mcp.call(
        "get_workflow_versions_diff",
        {
            "workflowId": workflow_id,
            "fromVersionId": from_version_id,
            "toVersionId": to_version_id,
        },
    )


@mcp.tool()
async def n8n_get_workflow_execution(
    workflow_id: str,
    execution_id: str,
    include_data: bool = False,
    node_names: list[str] | None = None,
    truncate_data: int = 0,
) -> Any:
    """Fetch execution status/data from n8n's native MCP server."""
    args: dict[str, Any] = {
        "workflowId": workflow_id,
        "executionId": execution_id,
        "includeData": include_data,
    }
    if node_names:
        args["nodeNames"] = node_names
    if truncate_data > 0:
        args["truncateData"] = truncate_data
    return await n8n_mcp.call("get_workflow_execution", args)


@mcp.tool()
async def n8n_publish_workflow(workflow_id: str, version_id: str = "") -> Any:
    """Publish the validated draft version for production execution."""
    _require_standard()
    args: dict[str, Any] = {"workflowId": workflow_id}
    if version_id:
        args["versionId"] = version_id
    return await n8n_mcp.call("publish_workflow", args)


@mcp.tool()
async def n8n_unpublish_workflow(workflow_id: str) -> Any:
    """Unpublish a workflow so production triggers stop."""
    _require_standard()
    return await n8n_mcp.call("unpublish_workflow", {"workflowId": workflow_id})


@mcp.prompt()
def n8n_workflow_builder(description: str) -> str:
    """Create a disciplined prompt for building an n8n workflow from natural language."""
    return (
        "Build an n8n workflow for this requirement: " + description + "\n\n"
        "Use the native n8n MCP sequence exactly: "
        "get_workflow_sdk_reference -> get_workflow_best_practices when relevant -> "
        "search_nodes/get_node_types -> generate Workflow SDK code -> validate_workflow -> "
        "create_workflow_from_code or update_workflow -> prepare_workflow_pin_data -> "
        "test_workflow -> inspect execution/version diff -> publish only after validation. "
        "Do not invent node types or credential IDs. Never delete or archive workflows automatically."
    )


@mcp.resource("evo://about")
def about() -> str:
    return (
        "Evo MCP Node 0.3: source-first personal brain, durable tasks, sandboxed programmer tools, "
        "Docker/Git gates, and safe native/REST n8n workflow automation."
    )


@mcp.resource("evo://n8n/build-sequence")
def n8n_build_sequence() -> str:
    return (
        "1 get_workflow_sdk_reference; 2 get_workflow_best_practices; 3 search_nodes; "
        "4 get_node_types; 5 generate SDK code; 6 validate_workflow; 7 create/update; "
        "8 prepare_workflow_pin_data + test_workflow; 9 publish_workflow."
    )


mcp.apply_tool_profile(settings.tool_profile)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "evo-mcp-node", "version": __version__})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ready": True,
            "workspace": settings.programmer_workspace,
            "n8nRestConfigured": bool(settings.n8n_base_url and settings.n8n_api_key),
            "n8nMcpConfigured": bool(settings.n8n_mcp_url and settings.n8n_mcp_token),
            "notionConfigured": bool(settings.notion_token),
            "brainVault": settings.brain_vault_path,
            "taskStore": "ready",
        }
    )


@mcp.custom_route("/metrics", methods=["GET"])
async def prometheus_metrics(_: Request) -> PlainTextResponse:
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


if settings.trust_proxy:
    transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
else:
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(settings.allowed_hosts),
        allowed_origins=list(settings.allowed_origins),
    )

base_app = mcp.streamable_http_app(host=settings.bind_host, transport_security=transport_security)
app = wrap_asgi(
    RequestLogMiddleware(
        BearerAuthMiddleware(base_app, enabled=settings.require_auth, api_key=settings.api_key)
    ),
    "evo-mcp-node",
)
