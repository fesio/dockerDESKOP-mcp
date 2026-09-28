# Evo MCP creates or updates n8n

1. Call `n8n_validate_workflow_json` with `workflow-to-manage.json`.
2. For a new workflow call `n8n_import_workflow` without `workflow_id`.
3. Before an update call `n8n_get_workflow`, retain its `versionId`, then call
   `n8n_import_workflow` with both `workflow_id` and `expected_version_id`.
4. Run it with `n8n_execute_workflow` (or its webhook), poll `n8n_get_execution_status`, and inspect
   the redacted `n8n_get_execution_logs` result.
5. Save a portable backup with `n8n_export_workflow`; credential IDs and instance metadata are removed.

The native n8n MCP builder remains preferred when a workflow must be generated from natural language.
REST JSON import exists for deterministic, reviewed workflows and refuses stale updates.
