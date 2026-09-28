# Evo MCP Node 0.3 Design

## Purpose

Evo MCP Node 0.3 completes the local-first programmer server on the
`evo-mcp-local-cloud` branch. It adds narrowly scoped developer operations,
enforced approval gates for destructive actions, durable long-running jobs,
current n8n workflow administration, a source-grounded Brain, stronger
observability, examples, tests, and a production-ready Cloud Run path.

The local Docker Desktop deployment is the trusted developer runtime. The
public deployment is a read-oriented integration endpoint and must not gain
host filesystem or Docker socket access.

## Constraints and Compatibility

- Keep `mcp==2.2.0` and Streamable HTTP.
- MCP Python SDK 2.2.0 does not implement the current SEP-2663 Tasks extension.
  Evo therefore exposes an explicit, durable job API through ordinary MCP tools.
  The API uses task-compatible states and isolates ownership so a later native
  Tasks adapter can replace the transport without changing operation workers.
- Do not downgrade to the legacy in-core Tasks implementation from MCP 1.x.
- Prefer n8n's instance-level MCP server for workflow building, validation,
  execution, version history, and publishing. Use the public REST API for
  workflow JSON CRUD, exports, and execution lookup fallback.
- Never persist API keys, approval secrets, workflow credentials, or execution
  payloads in Git.
- Do not merge into `main` as part of this work.

## Architecture

The server remains a single ASGI application, but feature code is split into
focused modules:

1. `programmer.py` owns jailed workspace and Git operations.
2. `command_policy.py` classifies command invocations before execution.
3. `approvals.py` verifies scoped, expiring approval tokens for destructive
   actions.
4. `tasks.py` owns the durable job store, state machine, worker execution,
   cancellation, bounded logs, and retention.
5. `n8n_client.py` owns authenticated REST and native MCP clients.
6. `n8n_workflows.py` owns import/export sanitization and orchestration.
7. `observability.py` owns operation spans, counters, and redaction helpers.
8. `server.py` contains only MCP-facing wrappers, resources, prompts, and HTTP
   routes.
9. `knowledge/` owns source normalization, Obsidian and Notion adapters, web
   evidence ingestion, and personal NotebookLM handoff bundles.
10. The existing `brain/server.ts` Noodle Seed entrypoint remains the policy and
    orchestration surface used by AI clients. Evo provides the local data-plane
    tools that perform retrieval, synchronization, source preparation, and
    evidence-pack validation.

SQLite under `/data/evo-tasks.sqlite3` stores task metadata and bounded logs.
Task results that exceed the configured inline limit are written beneath
`/data/tasks/<task-id>/` and referenced by the task record. The task store is
shared only by the single Cloud Run instance configured by the deployment
scripts. A future multi-instance deployment must replace this store with a
shared database before raising `max-instances` above one.

## Programmer Profile

### Read operations

The `read` profile exposes workspace tree, file read, text search, Git status,
Git diff, Git log, and current branch. Every filesystem candidate is resolved
before stat or read. Symlinks whose target leaves the workspace are rejected.

### Standard operations

The `standard` profile adds file creation/update, patch application, branch
creation, explicit-path commits, tests, lint, formatting, type checking, Docker
build, Compose validation/up, container status, health checks, and bounded log
reads.

Dedicated tools select commands from configuration rather than accepting an
arbitrary executable and arguments. The existing generic runner remains for
compatibility but rejects:

- shell interpreters and shell execution flags;
- inline code flags such as `python -c`, `node -e`, and equivalent forms;
- destructive Git operations including push, clean, reset, checkout restore,
  branch deletion, and forced operations;
- destructive Docker operations including rm, rmi, system prune, volume prune,
  and Compose down with volume removal;
- path arguments that resolve outside the workspace.

Output, runtime, and concurrency are bounded. Processes run without a shell and
receive a minimal environment.

### Destructive operations and approvals

Destructive tools require the `autonomous` profile and a valid approval token.
The token is an HMAC signed payload containing action, normalized target,
expiration, and nonce. A token authorizes one exact operation and is consumed
after successful verification. Plain comparison with a reusable global secret
is removed.

The following operations require approval:

- deleting or moving over workspace files;
- Git push, reset, clean, force, branch deletion, and tag deletion;
- Docker container/image/volume deletion or Compose teardown with volumes;
- n8n workflow unpublish, archive/delete if later enabled, version restore, and
  update of an existing workflow without a matching expected version.

Evo never exposes n8n workflow deletion or archival through the generic bridge.

## Long-running Evo Tasks

Long operations are represented by task records with these states:
`working`, `input_required`, `completed`, `failed`, and `cancelled`.

MCP tools:

- `task_start(operation, arguments, idempotency_key)` starts an allow-listed
  operation and returns a task ID.
- `task_status(task_id)` returns state, timestamps, progress, and a sanitized
  error summary.
- `task_logs(task_id, cursor, limit)` returns bounded incremental structured
  logs.
- `task_result(task_id)` returns or references the completed result.
- `task_cancel(task_id)` requests cooperative cancellation.
- `task_list(state, limit, cursor)` lists tasks owned by the authenticated
  caller.

Initial asynchronous operations are test, lint, typecheck, Docker build, Docker
Compose up, n8n workflow execution-and-wait, workflow import, and workflow
export. Direct synchronous tools remain available for fast operations.

Ownership is derived from the authenticated token identity. Local unauthenticated
mode receives one process-local owner identity. A caller cannot enumerate,
cancel, read logs from, or retrieve another owner's task. Idempotency keys are
scoped to owner plus operation.

At startup, unfinished tasks are marked failed with a restart explanation;
arbitrary commands are never silently resumed. Retention and log limits are
configurable. Cleanup removes expired task artifacts without following symlinks.

## Source-grounded Brain

### Control flow

Supported AI clients connect to the Brain MCP entrypoint rather than directly
to individual knowledge services. For every request that can benefit from
external or remembered knowledge, the Brain performs this gate:

1. classify sensitivity, topic, freshness requirement, and acceptable sources;
2. retrieve matching local Obsidian notes;
3. retrieve matching Notion pages shared with the configured integration;
4. when fresh evidence is required, collect approved web and document sources
   and create a NotebookLM-compatible source bundle;
5. normalize all findings into one evidence pack;
6. reject the answer stage when required citations, freshness, or source
   coverage are missing;
7. pass the evidence pack to the selected local or hosted model;
8. run the existing independent critic gate;
9. optionally write the approved result back to Obsidian and synchronize a
   non-secret collaboration copy to Notion.

The response model never receives connector credentials. Retrieved content is
untrusted data and cannot alter system policy, tool permissions, or approval
requirements.

### Source of truth and synchronization

Obsidian Markdown under `brain/obsidian-vault/Brain` remains the canonical,
local, inspectable source of truth. The implementation adds the shared
`brain/imports`, `brain/raw`, and `brain/wiki` directories plus
`brain/_index.md`, while preserving the existing vault paths and valid YAML
frontmatter.

Notion is a collaboration and capture layer. The adapter uses the official
Notion API version `2026-03-11`, reads only pages explicitly shared with the
integration, paginates searches, and stores the Notion page ID, URL, and last
edited timestamp as provenance. Synchronization is explicit and
conflict-aware: identical content hashes are skipped, newer remote edits are
imported as review candidates, and Evo never overwrites both sides in one run.

The user has personal NotebookLM, which has no supported server API. Evo does
not use reverse-engineered endpoints, copy Google session cookies, or make
NotebookLM a hidden availability dependency. Instead, `brain_prepare_notebook`
creates a timestamped directory containing deduplicated Markdown/PDF/TXT source
files, `sources.json`, a URL list, content hashes, and the research question.
The local helper opens `https://notebooklm.google.com/` and the source directory
for the signed-in user. When a compatible visible-browser automation host is
available, it may perform the upload as an explicit interactive action, but
that capability is not promised by the MCP server and must not be used in
headless or public hosting.

If a request merely needs sourced facts, the Brain answers from the normalized
Obsidian, Notion, and fresh web evidence pack without waiting for NotebookLM.
If the caller explicitly requires a NotebookLM synthesis, the Evo task enters
`input_required` and returns the prepared bundle plus a short continuation
instruction. The user can paste or export the NotebookLM note into
`brain/imports/notebooklm/`; resuming the task imports it with provenance and
runs the normal citation and critic gates. The server never claims that
NotebookLM was queried until such an imported result exists.

### Evidence pack

All adapters produce the same source record:

- stable source ID and connector type;
- title, canonical URI, author/publisher when available;
- created, updated, retrieved, and indexed timestamps;
- content hash, sensitivity, and freshness status;
- relevant excerpt or summary;
- claims supported by the source;
- connector-specific provenance without credentials.

`brain_collect_sources` returns a bounded evidence pack containing records,
claim-to-source citations, conflicts, confidence, missing information, and a
`ready_to_answer` decision. `brain_answer_context` returns model-ready context
only when the gate passes. `brain_prepare_notebook` creates the personal
NotebookLM handoff bundle, and `brain_resume_notebook` imports the user's
grounded result. A caller may explicitly request `local_only`, which disables
Notion, web retrieval, and NotebookLM handoff and keeps private or secret inputs
within the Obsidian boundary.

The Brain Noodle contract is updated so `ground_sources` depends on all enabled
adapters, `specialist_work` requires a passing evidence pack when fresh sources
are requested, and `critic_review` verifies that each material factual claim is
linked to at least one source.

### Client access

The repository includes copy-safe configuration examples and instruction files
for Gemini CLI on Windows, Codex/ChatGPT-compatible MCP clients, VS Code with
GitHub Copilot MCP support, OpenCode, Google Antigravity, and generic Streamable
HTTP MCP clients. Every client points to the same local or hosted Brain MCP
endpoint and receives the same rule: call the source collection gate before
answering factual, research, project-history, or current-information questions.

Configuration examples reference environment-variable placeholders and never
embed bearer tokens. Where a client cannot enforce mandatory tool use, the
documented workflow uses the single `brain_answer_context` entry tool so that
retrieval and the readiness decision happen server-side before context is
returned.

## n8n Integration

### Authentication and transport

- REST uses `X-N8N-API-KEY` by default and optionally bearer authentication.
- Native n8n MCP uses a separate bearer token.
- Both URLs pass scheme and hostname allow-list validation.
- Redirects may not leave the validated origin.
- Retries apply only to safe requests and explicitly idempotent writes.
- Audit and application logs redact headers, credentials, workflow credential
  bindings, and execution payloads by default.

Secrets come from environment variables locally and Secret Manager on Cloud
Run. `.env.example` documents names but contains no usable secret.

### Workflow tools

Evo exposes:

- list and get workflows;
- local JSON schema/shape validation plus native n8n validation;
- create and update from workflow JSON;
- native Workflow SDK create and atomic update;
- activate/deactivate and publish/unpublish with policy gates;
- execute/test and retrieve execution status, details, and sanitized logs;
- list/search executions with pagination and filters;
- export one workflow as sanitized JSON to the workspace or as a returned
  object;
- import one workflow JSON from the workspace or an argument, validate it, and
  create or update it;
- version history, diff, and gated restore.

Export strips instance identifiers, timestamps, shared metadata, credential
objects, and optional pin data. Credential references are represented as
placeholders unless explicitly retained by an approved local export. Import
rejects credential material and unknown top-level secret-bearing fields.

Update accepts `expected_version_id`. A mismatch fails without writing. Before
an update, Evo fetches and records a sanitized backup in the task artifact
directory. Rollback remains an explicit approved operation.

### Examples

`examples/n8n-calls-evo-mcp.workflow.json` is an importable workflow using the
n8n MCP Client Tool to call Evo's `server_status` and `echo` tools. It contains
credential placeholders only.

`examples/evo-manages-n8n.md` shows how an MCP client calls Evo to validate,
create, update, execute, poll, and export an n8n workflow. A companion fixture
contains the workflow JSON used by automated tests.

## Observability

- Every HTTP request receives an `X-Request-ID`.
- Every tool call receives an operation ID; tasks also carry a task ID.
- JSON logs contain timestamps, operation, duration, outcome, and safe target
  metadata.
- Audit records are append-only JSON lines and omit secrets and raw workflow or
  execution payloads.
- OpenTelemetry spans cover HTTP requests, programmer operations, n8n requests,
  knowledge adapter requests, and task lifecycle transitions when OTLP
  configuration is present.
- `/health` reports process liveness only.
- `/ready` checks task-store availability and configuration validity without
  disclosing secrets.
- `/metrics` exposes bounded Prometheus text metrics for request counts,
  operation outcomes, durations, task states, and n8n request outcomes. It is
  loopback-only by default and requires bearer authentication in public mode.

## Error Handling

Public errors use stable error codes and sanitized messages. Internal exception
details go only to local structured logs. Network failures distinguish timeout,
TLS, refused connection, authentication, authorization, rate limiting, invalid
workflow input, version conflict, and upstream server failure.

Cancellation is cooperative. A task that cannot terminate its subprocess within
the grace period is marked failed and the process tree is terminated. Partial
n8n writes return the last confirmed workflow version and backup reference.

## Testing

Unit tests cover path and symlink escapes, command classification, approval
scope/expiry/replay, task state transitions and owner isolation, retention,
redaction, workflow sanitization, version conflicts, URL/redirect SSRF checks,
each REST request shape, source normalization, freshness decisions, content
hash deduplication, local-only routing, Notion pagination/conflicts,
NotebookLM bundle safety and continuation handling, and evidence-pack readiness.

Integration tests use mocked n8n REST and MCP transports to exercise list/get,
create/update, validation, execution polling/log retrieval, and import/export.
Mocked Notion and web-retrieval transports exercise source collection, refresh,
failure isolation, and citation provenance. NotebookLM tests use local bundle
fixtures only and never contact Google. Server tests perform a real in-memory
MCP client handshake and tool discovery. Noodle validation and tests cover the
Brain dependency graph and prevent specialist execution before the source gate
passes.

Docker CI performs Ruff, pytest, production image build, Compose configuration,
runtime `/health`, authenticated `/mcp` initialization/tool listing, and n8n
container health. CI never needs live n8n or cloud credentials.

## Deployment

Docker Desktop remains bound to `127.0.0.1`. Docker socket access is an explicit
overlay and is never enabled in the default Compose file.

Cloud Run is the public hosting target because the container and long-running
task model do not fit Vercel's ephemeral function runtime. Cloud Run uses one
instance, bearer authentication, Secret Manager, read-only programmer profile,
no workspace host mount, and no Docker socket. The deployment script and GitHub
OIDC workflow verify `/health` and perform an authenticated MCP discovery/tool
listing request against `/mcp`.

Workload Identity Federation trust is restricted to the repository's protected
`production` environment subject, not merely to any branch in the repository.

If no Google identity is available in the execution environment, delivery stops
after validating the deployment artifacts and reports only the required user
authorization command and project selection. No Vercel deployment is attempted.

## Acceptance Criteria

- All requested programmer capabilities are available through dedicated tools.
- Generic command execution cannot bypass destructive-action approval gates.
- Workspace reads and searches cannot escape through symlinks.
- Long operations expose durable, owner-isolated status, logs, cancellation,
  and results through Evo task tools.
- n8n workflow JSON can be safely listed, read, validated, created, updated,
  executed, inspected, imported, and exported using mocked integration tests.
- Both requested n8n examples are present and documented.
- Obsidian, Notion, and fresh approved sources are normalized into one evidence
  pack before source-dependent answers.
- Personal NotebookLM receives a safe local source bundle and explicit
  human-in-the-loop continuation; no unofficial API or stored browser cookie is
  used.
- Private and secret requests remain inside the local Obsidian boundary.
- Client examples for Gemini CLI, Codex/ChatGPT-compatible MCP clients, VS Code
  with GitHub Copilot, OpenCode, Antigravity, and generic MCP clients all target
  the same Brain MCP policy surface.
- Logs, audit records, metrics, and traces contain correlation identifiers and
  no configured secrets.
- Local and CI verification covers `/health` and `/mcp`.
- Cloud Run deployment is attempted only with an authenticated Google identity;
  otherwise the single missing authorization step is reported.
- No merge to `main` occurs.
