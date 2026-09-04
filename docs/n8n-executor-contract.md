# n8n executor contract

n8n is a replaceable execution adapter. The MCP Brain remains the controller.

## Input envelope

An n8n workflow accepts one bounded assignment selected by `orchestrate_task`:

```json
{
    "execution_id": "brain-e8e65e69",
    "idempotency_key": "job-hunt-2026-09-04",
    "step_id": "integration_execution",
    "worker_role": "workflow_executor",
    "instruction": "Execute approved integration steps and return evidence.",
    "depends_on": ["specialist_work"],
    "approval_granted": true,
    "knowledge_policy": "adaptive_model_choice",
    "model_route": {
        "strategy": "runtime_capability_match",
        "resolved_model": "provider/model-id"
    },
    "source_sensitivity": "internal",
    "context_refs": ["obsidian://Brain/project/example"]
}
```

The envelope contains references, not the entire vault. The executor retrieves
only explicitly authorized context.

## Output envelope

```json
{
    "execution_id": "brain-e8e65e69",
    "step_id": "integration_execution",
    "status": "completed",
    "summary": "Bounded description of the outcome",
    "evidence": [
        {
            "kind": "workflow_execution",
            "reference": "provider-owned execution identifier"
        }
    ],
    "memory_candidates": [],
    "errors": []
}
```

## Required rules

- n8n must not create additional assignments or change dependencies.
- Every result returns evidence or an explicit blocker.
- State-changing nodes require approval from the MCP plan or host.
- Secrets stay in n8n credentials and never enter workflow payloads or logs.
- The MCP critic reviews results before long-term memory is written.
- Retries use the same `execution_id`, `step_id` and `idempotency_key`.
- MCP selects the configured model route at execution time; n8n must not build
  or maintain a separate model ranking.
- Public and internal research requires citations. Private and secret sources
  must remain in the Obsidian boundary.

## Durability boundary

When the Vercel adapter is configured in production, Vercel Workflow owns
checkpointing, retry and resume. Each external network or database operation
belongs in a `use step` function; the `use workflow` function only walks the
dependency graph. n8n returns evidence for its bounded integration step and
does not decide what runs next.
