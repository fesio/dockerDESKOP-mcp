from __future__ import annotations

from typing import Any


class WorkflowValidationError(ValueError):
    pass


def validate_workflow_json(workflow: dict[str, Any]) -> dict[str, Any]:
    required = {"name", "nodes", "connections"}
    missing = sorted(required - workflow.keys())
    if missing:
        raise WorkflowValidationError(f"workflow missing required fields: {', '.join(missing)}")
    if not isinstance(workflow["name"], str) or not workflow["name"].strip():
        raise WorkflowValidationError("workflow name must be a non-empty string")
    if not isinstance(workflow["nodes"], list):
        raise WorkflowValidationError("workflow nodes must be a list")
    if not isinstance(workflow["connections"], dict):
        raise WorkflowValidationError("workflow connections must be an object")
    names: set[str] = set()
    for index, node in enumerate(workflow["nodes"]):
        if not isinstance(node, dict):
            raise WorkflowValidationError(f"node {index} must be an object")
        for key in ("name", "type", "position", "parameters"):
            if key not in node:
                raise WorkflowValidationError(f"node {index} missing {key}")
        if node["name"] in names:
            raise WorkflowValidationError(f"duplicate node name: {node['name']}")
        names.add(node["name"])
    sanitized = {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow.get("settings", {"executionOrder": "v1"}),
    }
    if "staticData" in workflow:
        sanitized["staticData"] = workflow["staticData"]
    return sanitized
