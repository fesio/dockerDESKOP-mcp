# n8n executor contract

n8n is a replaceable execution adapter. The MCP Brain remains the controller.

## Input envelope

An n8n workflow accepts one bounded assignment selected by `orchestrate_task`:

```json
{
  "execution_id": "brain-e8e65e69",
  "step_id": "integration_execution",
  "worker_role": "workflow_executor",
  "instruction": "Execute approved integration steps and return evidence.",
  "depends_on": ["specialist_work"],
  "approval_granted": true,
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
- Retries use the same `execution_id` and `step_id` for idempotency.

