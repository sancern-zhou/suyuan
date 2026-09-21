"""Typed handoff contracts for parent/child agent workflows."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional

WORKFLOW_PROTOCOL_VERSION = "workflow.v1"

EXPERT_ANALYSIS_RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["status", "findings", "evidence", "uncertainties", "data_gaps"],
    "properties": {
        "status": {"type": "string", "enum": ["completed", "completed_with_gaps", "needs_more_evidence", "failed"]},
        "scope": {"type": "object"},
        "findings": {"type": "array", "items": {"type": "object"}},
        "evidence": {"type": "array", "items": {"type": "object"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "artifacts": {"type": "array", "items": {"type": "object"}},
    },
    "additionalProperties": True,
}


def build_expert_analysis_task(*, question: str, decision_context: str = "", scope: Optional[Mapping[str, Any]] = None,
                               required_evidence: Optional[Iterable[str]] = None, deliverables: Optional[Iterable[str]] = None,
                               task_id: Optional[str] = None, parent_task_id: Optional[str] = None) -> Dict[str, Any]:
    task: Dict[str, Any] = {
        "protocol_version": WORKFLOW_PROTOCOL_VERSION,
        "task_type": "expert_analysis",
        "question": question,
        "decision_context": decision_context,
        "scope": deepcopy(dict(scope or {})),
        "required_evidence": list(required_evidence or []),
        "deliverables": list(deliverables or ["findings", "evidence", "uncertainties", "data_gaps"]),
        "result_schema": deepcopy(EXPERT_ANALYSIS_RESULT_SCHEMA),
    }
    if task_id:
        task["task_id"] = task_id
    if parent_task_id:
        task["parent_task_id"] = parent_task_id
    return task


def extract_structured_result(text: str) -> Optional[Any]:
    if not isinstance(text, str) or not text.strip():
        return None
    candidates: List[str] = [m.group(1).strip() for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)]
    candidates.append(text.strip())
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
                return value
            except json.JSONDecodeError:
                continue
    return None


def validate_result_schema(value: Any, schema: Mapping[str, Any]) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []

    def visit(node: Any, spec: Mapping[str, Any], path: str) -> None:
        expected_type = spec.get("type")
        if expected_type and not _matches_type(node, expected_type):
            violations.append({"path": path, "expected": str(expected_type), "got": _value_type(node)})
            return
        if "enum" in spec and node not in spec["enum"]:
            violations.append({"path": path, "expected": f"one of {spec['enum']}", "got": repr(node)})
        if isinstance(node, Mapping):
            for name in spec.get("required", []):
                if name not in node:
                    violations.append({"path": f"{path}.{name}", "expected": "required", "got": "missing"})
            for name, child_spec in spec.get("properties", {}).items():
                if name in node and isinstance(child_spec, Mapping):
                    visit(node[name], child_spec, f"{path}.{name}")
        elif isinstance(node, list) and isinstance(spec.get("items"), Mapping):
            for index, item in enumerate(node):
                visit(item, spec["items"], f"{path}[{index}]")

    visit(value, schema, "$")
    return violations


def _matches_type(value: Any, expected: Any) -> bool:
    expected_types = expected if isinstance(expected, list) else [expected]
    return any(
        (kind == "object" and isinstance(value, Mapping)) or
        (kind == "array" and isinstance(value, list)) or
        (kind == "string" and isinstance(value, str)) or
        (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or
        (kind == "integer" and isinstance(value, int) and not isinstance(value, bool)) or
        (kind == "boolean" and isinstance(value, bool)) or
        (kind == "null" and value is None)
        for kind in expected_types
    )


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__
