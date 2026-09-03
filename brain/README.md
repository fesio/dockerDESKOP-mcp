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

## Knowledge layers

| Layer | Responsibility |
| --- | --- |
| Obsidian | Editable source of truth and long-term project memory |
| LanceDB bridge | Semantic retrieval over approved Obsidian notes |
| Google Drive | Durable synchronization of non-secret documents |
| NotebookLM | Source-grounded research over a curated Drive subset |
| MCP Brain | Planning, routing, policy and completion gates |
| n8n | Optional integration and scheduling executor |

## MCP surface

- `get_brain_context` — returns the authoritative architecture and boundaries.
- `orchestrate_task` — creates an ordered, dependency-aware execution plan.
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

The current build is intentionally local-only. Connecting a live Obsidian
bridge, Drive, NotebookLM or n8n executor requires their real endpoint and
authentication configuration. Credentials must be managed outside the source
tree.

