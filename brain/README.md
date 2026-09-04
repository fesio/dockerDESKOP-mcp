# Fesiomatyzacja Brain Orchestrator

The Brain is a separate Noodle Seed MCP entrypoint. It does not replace the
existing Docker Hub MCP implementation in `src/`.

## Control model

The MCP server is the control plane. It classifies work, builds a dependency
graph, assigns logical worker roles, requires evidence, invokes an independent
critic and prepares approved memory records.

n8n is an optional executor. It is selected only for external integrations,
webhooks or schedules. It never owns task routing, model selection or the final
completion gate.

The MCP plan selects Vercel Workflow as the preferred durability layer for
production execution. A configured adapter persists step results, retries
transient failures at most three times and resumes from the first incomplete
dependency. The MCP plan exposes a stable `idempotency_key`; n8n must reuse it
for every state-changing adapter call.

## Knowledge layers

| Layer           | Responsibility                                           |
| --------------- | -------------------------------------------------------- |
| Obsidian        | Editable source of truth and long-term project memory    |
| LanceDB bridge  | Semantic retrieval over approved Obsidian notes          |
| Google Drive    | Durable synchronization of approved non-secret documents |
| Model host      | Executes the task route selected by MCP at runtime       |
| MCP Brain       | Planning, routing, policy and completion gates           |
| Vercel Workflow | Durable checkpoints, bounded retries and resume          |
| n8n             | Optional integration and scheduling executor             |

## Default routing policy

`orchestrate_task` defaults to `knowledge_policy=adaptive_model_choice`,
`source_sensitivity=internal` and `durable_execution=true`.

- MCP resolves the best currently configured route from task domain, priority,
  risk and required capabilities. It records the resolved model identifier and
  one contract-compatible fallback.
- No periodic ranking is created, queried or stored.
- Fresh research requires claim-to-source citations, confidence and unresolved
  gaps regardless of the selected model.
- Private and secret material remains within the local Obsidian boundary.

## MCP surface

- `get_brain_context` — returns the authoritative architecture and boundaries.
- `orchestrate_task` — creates an ordered, dependency-aware execution plan.
- `prepare_code_project` — creates a production implementation contract.
- `design_workflow` — creates an orchestration and reliability contract.
- `list_programming_catalog` — returns the operational priority catalog.
- `audit_programming_coverage` — detects missing language profiles.
- `prepare_memory_record` — produces safe Markdown for the Obsidian bridge.
- `brain://architecture` — model-readable architecture resource.
- `execute_with_brain` — prompt for the full plan, execute, critic and memory loop.

## Local evidence

Run the public Noodle commands from the repository root:

```bash
noodle validate --json
noodle test --json
```

The MCP surface and routing policy run locally and are covered by the commands
above. Live execution still requires real endpoints and authentication for the
Vercel Workflow adapter, Obsidian bridge, Drive, selected model host and n8n
executor. Keep all credentials outside the source tree.
