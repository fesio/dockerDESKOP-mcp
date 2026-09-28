from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.n8n_client import N8nRestClient
from app.workflow_validation import validate_workflow_json


class N8nConflictError(RuntimeError):
    pass


INSTANCE_FIELDS = {
    "id",
    "createdAt",
    "updatedAt",
    "versionId",
    "activeVersionId",
    "shared",
    "homeProject",
}


def _export_safe(workflow: dict[str, Any], include_pin_data: bool) -> dict[str, Any]:
    value = deepcopy(workflow)
    for key in INSTANCE_FIELDS:
        value.pop(key, None)
    if not include_pin_data:
        value.pop("pinData", None)
    for node in value.get("nodes", []):
        credentials = node.get("credentials")
        if not isinstance(credentials, dict):
            continue
        node["credentials"] = {
            kind: {"name": "${N8N_CREDENTIAL_" + kind.upper() + "}"} for kind in credentials
        }
    return validate_workflow_json(value)


def _redact_execution(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"authorization", "apikey", "api_key", "token", "credentials"}:
                output[key] = "[REDACTED]"
            else:
                output[key] = _redact_execution(item)
        return output
    if isinstance(value, list):
        return [_redact_execution(item) for item in value[:500]]
    if isinstance(value, str):
        return value[:20_000]
    return value


@dataclass(slots=True)
class WorkflowService:
    client: N8nRestClient

    async def export_workflow(
        self, workflow_id: str, *, include_pin_data: bool = False
    ) -> dict[str, Any]:
        workflow = await self.client.get_workflow(workflow_id)
        return _export_safe(workflow, include_pin_data)

    async def import_workflow(
        self,
        workflow: dict[str, Any],
        *,
        workflow_id: str = "",
        expected_version_id: str = "",
    ) -> Any:
        clean = validate_workflow_json(workflow)
        if not workflow_id:
            return await self.client.create_workflow(clean)
        current = await self.client.get_workflow(workflow_id)
        if not expected_version_id:
            raise N8nConflictError("expected_version_id is required when updating a workflow")
        if current.get("versionId") != expected_version_id:
            raise N8nConflictError("workflow version changed; export and review the latest version")
        return await self.client.update_workflow(workflow_id, clean)

    async def execution_status(self, execution_id: str) -> dict[str, Any]:
        execution = await self.client.get_execution(execution_id, include_data=False)
        return {
            key: execution.get(key)
            for key in ("id", "workflowId", "status", "startedAt", "stoppedAt", "finished")
        }

    async def execution_logs(self, execution_id: str) -> Any:
        return _redact_execution(await self.client.get_execution(execution_id, include_data=True))
