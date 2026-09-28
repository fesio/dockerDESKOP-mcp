# Evo MCP Node 0.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a secure Evo MCP Node with durable long operations, complete n8n workflow tooling, a source-grounded Obsidian/Notion/personal-NotebookLM Brain, broad IDE/client support, and verified Docker/Cloud Run deployment artifacts.

**Architecture:** The Python MCP service is the local data plane for workspace, n8n, tasks, and knowledge retrieval; the existing Noodle Seed Brain remains the policy plane. Focused modules enforce paths, commands, approvals, source provenance, and task ownership. Local Docker runs the full standard profile while Cloud Run is authenticated and read-only.

**Tech Stack:** Python 3.13, MCP Python SDK 2.2.0, Starlette/Uvicorn, httpx, SQLite, OpenTelemetry, pytest, Ruff, TypeScript Noodle Seed, Docker Compose, GitHub Actions, Google Cloud Run.

**Spec:** `docs/superpowers/specs/2026-09-24-evo-mcp-node-0.3-design.md`

## Global Constraints

- Keep `mcp==2.2.0`; implement Evo task tools because SEP-2663 is not yet supported by the SDK.
- Never expose or persist API keys, approval secrets, browser cookies, or raw credential payloads.
- Obsidian is the local source of truth; Notion is an explicitly shared collaboration source.
- Personal NotebookLM uses a human-in-the-loop bundle, never an unofficial API.
- Public hosting uses `PROGRAMMER_PROFILE=read`, one Cloud Run instance, no Docker socket, and Bearer authentication.
- Do not merge to `main`.

## Review Focus

- Symlink and argument-based workspace escapes must fail before filesystem or subprocess access.
- Generic command execution must not bypass Git, Docker, shell, or inline-code approval policy.
- Approval tokens must be scoped, expiring, constant-time verified, and replay resistant.
- Task IDs, logs, results, and cancellation must remain isolated to the authenticated owner.
- Missing Notion or personal NotebookLM capabilities must produce explicit degraded/input-required states, never fabricated evidence.

---

### Task 1: Security policy and scoped approvals

**Files:**
- Create: `evo-mcp-node/app/command_policy.py`
- Create: `evo-mcp-node/app/approvals.py`
- Modify: `evo-mcp-node/app/config.py`
- Modify: `evo-mcp-node/app/programmer.py`
- Modify: `evo-mcp-node/app/server.py`
- Create: `evo-mcp-node/tests/test_approvals.py`
- Expand: `evo-mcp-node/tests/test_programmer.py`

**Interfaces:**
- Produces: `CommandPolicy.validate(argv: list[str], workspace: Path, docker_enabled: bool) -> None`.
- Produces: `ApprovalVerifier.verify(token: str, action: str, target: str) -> ApprovalClaims`.
- Produces: `create_approval_token(secret: str, action: str, target: str, ttl_seconds: int) -> str` for the local helper script only.
- Changes destructive tool arguments from reusable `approval` secret to scoped `approval_token`.

- [ ] **Step 1: Write failing command and path security tests**

```python
@pytest.mark.parametrize("argv", [
    ["git", "push", "origin", "main"],
    ["git", "clean", "-fdx"],
    ["python", "-c", "import shutil; shutil.rmtree('.')"],
    ["docker", "system", "prune", "-af"],
])
def test_generic_runner_rejects_destructive_bypasses(tmp_path, argv):
    ws = make_workspace(tmp_path, "standard")
    with pytest.raises(ProgrammerError, match="blocked"):
        ws.run(argv)

def test_search_rejects_symlink_outside_workspace(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)
    assert make_workspace(tmp_path, "read").search("secret") == []
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `uv run pytest tests/test_programmer.py -q`

- [ ] **Step 3: Implement semantic command policy and resolved-candidate checks**

```python
class CommandPolicy:
    def validate(self, argv: list[str], workspace: Path, docker_enabled: bool) -> None:
        command = Path(argv[0]).name.lower()
        if command in {"sh", "bash", "cmd", "powershell", "pwsh"}:
            raise ProgrammerError("shell execution is blocked")
        if command in {"python", "python3", "node"} and any(a in {"-c", "-e", "--eval"} for a in argv[1:]):
            raise ProgrammerError("inline code execution is blocked")
```

- [ ] **Step 4: Write failing approval expiry/scope/replay tests**

```python
def test_approval_is_single_use(tmp_path):
    verifier = ApprovalVerifier("x" * 32, tmp_path / "approvals.sqlite3")
    token = create_approval_token("x" * 32, "workspace.delete", "old.txt", 60)
    verifier.verify(token, "workspace.delete", "old.txt")
    with pytest.raises(ApprovalError, match="already used"):
        verifier.verify(token, "workspace.delete", "old.txt")
```

- [ ] **Step 5: Implement signed approval claims and local token helper**

Use canonical JSON, HMAC-SHA256, base64url encoding, `secrets.compare_digest`, Unix expiry, and a SQLite table keyed by nonce. Add `scripts/create-approval.ps1` that reads `PROGRAMMER_APPROVAL_SECRET` from a masked prompt and sends it only to a local Python helper through stdin.

- [ ] **Step 6: Run security tests and commit**

Run: `uv run pytest tests/test_programmer.py tests/test_approvals.py -q && uv run ruff check app tests`

Commit: `feat(evo): enforce scoped destructive approvals`

### Task 2: Dedicated developer tools and durable Evo tasks

**Files:**
- Create: `evo-mcp-node/app/tasks.py`
- Modify: `evo-mcp-node/app/programmer.py`
- Modify: `evo-mcp-node/app/server.py`
- Modify: `evo-mcp-node/app/config.py`
- Create: `evo-mcp-node/tests/test_tasks.py`
- Expand: `evo-mcp-node/tests/test_programmer.py`

**Interfaces:**
- Produces: `TaskStore.create/get/list/append_log/transition/request_cancel/result`.
- Produces: `TaskRunner.start(owner, operation, arguments, idempotency_key) -> dict`.
- Produces MCP tools `task_start`, `task_status`, `task_logs`, `task_result`, `task_cancel`, and `task_list`.
- Produces dedicated programmer methods `test`, `lint`, `format`, `typecheck`, `docker_build`, `compose_up`, `docker_status`, `docker_logs`.

- [ ] **Step 1: Write failing task lifecycle and owner-isolation tests**

```python
def test_task_is_owner_isolated(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3", tmp_path / "artifacts")
    task = store.create("owner-a", "test", {}, "key-1")
    assert store.get("owner-a", task.id).id == task.id
    with pytest.raises(TaskNotFound):
        store.get("owner-b", task.id)

def test_restart_marks_working_task_failed(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3", tmp_path / "artifacts")
    task = store.create("local", "lint", {}, "key")
    store.recover_interrupted()
    assert store.get("local", task.id).state == "failed"
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `uv run pytest tests/test_tasks.py -q`

- [ ] **Step 3: Implement SQLite state machine, bounded logs, artifacts, idempotency, and cooperative cancellation**

```python
TASK_STATES = {"working", "input_required", "completed", "failed", "cancelled"}
ALLOWED_TRANSITIONS = {
    "working": {"input_required", "completed", "failed", "cancelled"},
    "input_required": {"working", "cancelled", "failed"},
}
```

Use WAL mode, parameterized queries, per-owner lookups, a `ThreadPoolExecutor`, subprocess process-group termination, and configurable result/log/retention limits.

- [ ] **Step 4: Add dedicated developer wrappers and task operation registry**

The registry maps fixed names (`programmer.test`, `programmer.lint`, `programmer.typecheck`, `docker.build`, `docker.compose_up`) to dedicated Python callables. It never accepts an executable name from the model.

- [ ] **Step 5: Expose task and dedicated programmer MCP tools**

Owner identity is a digest of the authenticated bearer token; unauthenticated local mode uses `local`. Do not return the digest.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/test_tasks.py tests/test_programmer.py tests/test_server.py -q && uv run ruff check app tests`

Commit: `feat(evo): add durable long-running task tools`

### Task 3: Complete safe n8n workflow lifecycle

**Files:**
- Create: `evo-mcp-node/app/n8n_workflows.py`
- Modify: `evo-mcp-node/app/n8n_client.py`
- Modify: `evo-mcp-node/app/workflow_validation.py`
- Modify: `evo-mcp-node/app/server.py`
- Expand: `evo-mcp-node/tests/test_n8n.py`
- Create: `evo-mcp-node/tests/fixtures/n8n/sample-workflow.json`

**Interfaces:**
- Produces REST methods `get_execution`, `delete_execution` (blocked by default), and paginated workflow/execution helpers.
- Produces `WorkflowService.export_workflow`, `import_workflow`, `execution_status`, and `execution_logs`.
- Produces MCP tools `n8n_export_workflow`, `n8n_import_workflow`, `n8n_get_execution_status`, and `n8n_get_execution_logs`.

- [ ] **Step 1: Write failing mocked REST request-shape and sanitization tests**

```python
@pytest.mark.asyncio
async def test_export_removes_instance_and_credential_metadata(service):
    exported = await service.export_workflow("wf-1", include_pin_data=False)
    assert "id" not in exported
    assert "createdAt" not in exported
    assert "pinData" not in exported
    assert exported["nodes"][0]["credentials"] == {"httpHeaderAuth": {"name": "${N8N_CREDENTIAL}"}}
```

- [ ] **Step 2: Run n8n tests and confirm failure**

Run: `uv run pytest tests/test_n8n.py -q`

- [ ] **Step 3: Implement export/import, execution lookup/log sanitization, version conflict, and backups**

JSON imports pass local validation first. Existing workflows require `expected_version_id`; mismatch raises `N8nConflictError`. Backups use the task artifact directory and never include credential secrets.

- [ ] **Step 4: Add native MCP wrappers and destructive policy coverage**

Keep delete/archive blocked. Require an approval token for unpublish and restore. Validate `workflow_id`, `execution_id`, pagination, and log truncation.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_n8n.py tests/test_server.py -q && uv run ruff check app tests`

Commit: `feat(evo): complete n8n import export and executions`

### Task 4: Build the source-grounded Brain data plane

**Files:**
- Create: `evo-mcp-node/app/knowledge/__init__.py`
- Create: `evo-mcp-node/app/knowledge/models.py`
- Create: `evo-mcp-node/app/knowledge/obsidian.py`
- Create: `evo-mcp-node/app/knowledge/notion.py`
- Create: `evo-mcp-node/app/knowledge/notebooklm.py`
- Create: `evo-mcp-node/app/knowledge/service.py`
- Modify: `evo-mcp-node/app/config.py`
- Modify: `evo-mcp-node/app/server.py`
- Create: `evo-mcp-node/tests/test_knowledge.py`

**Interfaces:**
- Produces: `SourceRecord`, `EvidencePack`, and `KnowledgeService.collect`.
- Produces: `ObsidianSource.search(query, limit)`, `NotionSource.search(query, limit)`, and `NotebookBundle.prepare(question, sources)`.
- Produces MCP tools `brain_collect_sources`, `brain_answer_context`, `brain_prepare_notebook`, and `brain_resume_notebook`.

- [ ] **Step 1: Write failing provenance, freshness, local-only, and readiness tests**

```python
def test_private_query_is_local_only(service):
    pack = service.collect("private design", sensitivity="private", require_fresh=True)
    assert {source.connector for source in pack.sources} <= {"obsidian"}
    assert pack.policy == "local_only"

def test_evidence_pack_blocks_uncited_claims():
    pack = EvidencePack(question="q", sources=[], claims=[], conflicts=[])
    assert pack.ready_to_answer is False
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `uv run pytest tests/test_knowledge.py -q`

- [ ] **Step 3: Implement normalized records and Obsidian retrieval**

Resolve all Markdown candidates inside the configured vault, parse safe YAML frontmatter, score title/tag/body matches, calculate SHA-256, and return bounded excerpts with relative `obsidian://` URIs.

- [ ] **Step 4: Implement Notion official API retrieval**

Use Bearer auth plus `Notion-Version: 2026-03-11`, `/v1/search` pagination, page metadata, and block-child traversal. Only resources shared with the integration are visible. Retry 429/5xx with bounds and redact all headers.

- [ ] **Step 5: Implement personal NotebookLM bundles and continuation**

Write only under `/data/notebooklm/<task-id>/`; include `sources.json`, `question.md`, URL list, and deduplicated `.md` sources. Reject secret sensitivity. `resume` accepts a file only from `brain/imports/notebooklm`, records its hash/provenance, and never marks NotebookLM used before import.

- [ ] **Step 6: Expose Brain MCP tools and create the shared brain directories/index**

Create `brain/imports/.gitkeep`, `brain/imports/notebooklm/.gitkeep`, `brain/raw/.gitkeep`, `brain/wiki/.gitkeep`, and `brain/_index.md`. Ignore imported private content while keeping directory seeds.

- [ ] **Step 7: Run tests and commit**

Run: `uv run pytest tests/test_knowledge.py tests/test_server.py -q && uv run ruff check app tests`

Commit: `feat(brain): add grounded Obsidian Notion knowledge plane`

### Task 5: Update Brain orchestration policy and client support

**Files:**
- Modify: `brain/server.ts`
- Modify: `brain/README.md`
- Modify: `README.md`
- Create: `.mcp.json`
- Create: `.vscode/mcp.json`
- Create: `.gemini/settings.example.json`
- Create: `.agents/mcp_config.example.json`
- Create: `docs/clients/opencode.md`
- Create: `docs/clients/chatgpt-codex.md`
- Create: `docs/clients/brain-instructions.md`

**Interfaces:**
- Changes the Noodle plan so source-dependent specialist work depends on a passing evidence gate.
- Provides portable Streamable HTTP MCP configurations with `${env:EVO_MCP_API_KEY}`-style placeholders where supported.

- [ ] **Step 1: Add failing Noodle contract cases for source-gate dependencies and input-required NotebookLM**

Add examples that require `ground_sources` before `specialist_work`, preserve `local_only` for private/secret input, and emit `input_required` for explicit personal NotebookLM synthesis.

- [ ] **Step 2: Update `brain/server.ts` contracts and documentation**

Add knowledge executors `obsidian`, `notion`, `web_sources`, and `notebooklm_handoff`; add evidence readiness to the completion gate; remove the statement that NotebookLM is not required and replace it with the personal handoff policy.

- [ ] **Step 3: Add client configuration examples**

VS Code uses `.vscode/mcp.json` with top-level `servers`; portable Copilot uses `.mcp.json` with `mcpServers`; Gemini uses `.gemini/settings.json`; Antigravity uses `.agents/mcp_config.json`. Documentation covers ChatGPT/Codex and OpenCode without modifying global user configuration or embedding tokens.

- [ ] **Step 4: Validate in WSL2 and commit**

Run from WSL2: `noodle validate --json && noodle test --json`

Run: `npm run build && npm run format:check`

Commit: `feat(brain): enforce source-first MCP orchestration`

### Task 6: Observability, configuration, examples, and CI

**Files:**
- Create: `evo-mcp-node/app/observability.py`
- Modify: `evo-mcp-node/app/middleware.py`
- Modify: `evo-mcp-node/app/audit.py`
- Modify: `evo-mcp-node/app/telemetry.py`
- Modify: `evo-mcp-node/app/server.py`
- Modify: `evo-mcp-node/.env.example`
- Create: `evo-mcp-node/examples/n8n-calls-evo-mcp.workflow.json`
- Create: `evo-mcp-node/examples/evo-manages-n8n.md`
- Create: `evo-mcp-node/examples/workflow-to-manage.json`
- Modify: `evo-mcp-node/README.md`
- Modify: `.github/workflows/evo-mcp-node-ci.yml`
- Create: `evo-mcp-node/tests/test_observability.py`

**Interfaces:**
- Produces redaction helpers, operation spans/counters, `/metrics`, and richer `/ready`.
- Documents all environment variables and setup paths.

- [ ] **Step 1: Write failing redaction and metrics authorization tests**

```python
def test_redact_removes_nested_secrets():
    value = {"Authorization": "Bearer x", "node": {"credentials": {"id": "1"}}}
    assert "Bearer x" not in json.dumps(redact(value))
```

- [ ] **Step 2: Implement safe logs, audit metadata, counters, spans, readiness, and metrics**

Metrics contain no path, query, token, workflow payload, or source content labels. `/metrics` follows the same public-mode authentication policy as `/mcp`.

- [ ] **Step 3: Add both n8n examples and complete documentation/env examples**

The n8n-to-Evo example contains credential placeholders. The Evo-to-n8n guide demonstrates validate, create/update, execute, poll, logs, and export.

- [ ] **Step 4: Expand CI with authenticated MCP discovery**

Add a Python smoke client that connects to `http://127.0.0.1:8765/mcp`, supplies the CI bearer token, lists tools, and asserts `brain_collect_sources`, `task_start`, and `n8n_export_workflow` exist.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest -q && uv run ruff check app tests`

Commit: `test(evo): verify observability examples and MCP surface`

### Task 7: Docker and Cloud Run hardening

**Files:**
- Modify: `evo-mcp-node/Dockerfile`
- Modify: `evo-mcp-node/compose.yaml`
- Modify: `evo-mcp-node/compose.host-tools.yaml`
- Modify: `evo-mcp-node/scripts/setup.ps1`
- Modify: `evo-mcp-node/scripts/deploy-cloudrun.ps1`
- Modify: `evo-mcp-node/scripts/setup-gcp-wif.ps1`
- Modify: `.github/workflows/evo-mcp-cloudrun.yml`

**Interfaces:**
- Persists `/data` for tasks/audit/bundles locally.
- Restricts WIF to `environment:production`.
- Verifies `/health` and authenticated `/mcp` after deployment.

- [ ] **Step 1: Add Compose and script assertions to CI**

Check that default Compose has no Docker socket, the public profile is read-only, and no secret value appears in rendered configuration or logs.

- [ ] **Step 2: Harden WIF subject and runtime service account**

Map `attribute.environment=assertion.environment` and require repository plus `environment=='production'`. Use a dedicated runtime service account with only Secret Manager access rather than the Compute Engine default account.

- [ ] **Step 3: Add authenticated Cloud Run MCP verification**

The script reads the token from its existing secure source, uses the MCP SDK smoke client, and prints only endpoint URLs and pass/fail status.

- [ ] **Step 4: Build and run the complete local stack**

Run: `docker compose --profile n8n config`

Run: `docker build --target test -t evo-mcp-node:test .`

Run: `docker build --target runtime -t evo-mcp-node:local .`

Run: `docker compose up -d --build evo-mcp` followed by `/health` and authenticated `/mcp` discovery.

- [ ] **Step 5: Commit**

Commit: `chore(evo): harden Docker and Cloud Run deployment`

### Task 8: Whole-branch verification, GitHub update, and hosting attempt

**Files:**
- Verify all changed files.
- Update the existing `evo-mcp-local-cloud` remote branch only.

**Interfaces:**
- Produces final verification evidence and deployed endpoints if authorization exists.

- [ ] **Step 1: Run complete local verification**

Run: `uv run ruff check app tests`

Run: `uv run pytest -q`

Run: `docker compose --profile n8n config`

Run: `docker build --target test -t evo-mcp-node:test .`

Run: `docker build --target runtime -t evo-mcp-node:local .`

Run the live `/health`, `/ready`, `/metrics`, and authenticated `/mcp` smoke checks.

- [ ] **Step 2: Verify requirements against the spec and inspect the branch diff**

Run: `git diff --check origin/evo-mcp-local-cloud...HEAD`

Run: `git status --short --branch`

Confirm every acceptance criterion has either passing evidence or a precisely reported external authorization blocker.

- [ ] **Step 3: Push the feature branch without merging**

Push only `evo-mcp-local-cloud`. If GitHub CLI/remote authentication is unavailable, use the signed-in GitHub browser session only after verifying the exact repository and branch; otherwise report GitHub authentication as the blocker.

- [ ] **Step 4: Attempt Cloud Run deployment**

Use the existing authenticated `gcloud` identity and project when available. Do not deploy to Vercel because the stateful container/task architecture is incompatible. If no active Google identity or project exists, stop after validated deployment artifacts and report the single required `gcloud auth login`/project-selection step.

- [ ] **Step 5: Verify deployed endpoints**

Require HTTP 200 from `/health`; use a real MCP client with the bearer token to discover tools at `/mcp`. Record the public health and MCP URLs without revealing the token.

- [ ] **Step 6: Final commit if verification produced documentation-only corrections**

Commit: `docs(evo): record verified deployment workflow`
