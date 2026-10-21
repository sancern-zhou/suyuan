"""Domain-neutral result lineage for Agent workflow nodes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional


def build_node_lineage(
    *,
    task_id: str,
    dependency_task_ids: Iterable[str] = (),
    result: Any = None,
) -> Dict[str, Any]:
    """Build a stable manifest linking a node to inputs, evidence and artifacts."""
    envelope = _result_envelope(result)
    evidence = _normalize_refs(envelope.get("evidence"), task_id=task_id, kind="evidence")
    artifacts = _normalize_refs(envelope.get("artifacts"), task_id=task_id, kind="artifact")
    return {
        "task_id": task_id,
        "inputs": [
            {"ref_id": str(dependency), "kind": "node_result", "source_task_id": str(dependency)}
            for dependency in dependency_task_ids
        ],
        "output": {"ref_id": f"{task_id}:result", "kind": "node_result", "source_task_id": task_id},
        "evidence": evidence,
        "artifacts": artifacts,
        "status": "complete" if envelope else "partial",
    }


def validate_node_lineage(
    manifest: Mapping[str, Any],
    *,
    expected_task_id: Optional[str] = None,
    expected_dependencies: Iterable[str] = (),
    require_envelope: bool = False,
) -> List[Dict[str, str]]:
    """Return machine-readable lineage violations for a node result."""
    violations: List[Dict[str, str]] = []
    task_id = str(manifest.get("task_id") or "")
    if expected_task_id and task_id != expected_task_id:
        violations.append({"path": "$.task_id", "expected": expected_task_id, "got": task_id})
    output = manifest.get("output")
    if not isinstance(output, Mapping) or output.get("source_task_id") != task_id:
        violations.append({"path": "$.output.source_task_id", "expected": task_id, "got": str((output or {}).get("source_task_id") if isinstance(output, Mapping) else None)})
    input_refs = {
        str(item.get("source_task_id"))
        for item in manifest.get("inputs") or []
        if isinstance(item, Mapping)
    }
    missing_dependencies = sorted(set(str(item) for item in expected_dependencies) - input_refs)
    for dependency in missing_dependencies:
        violations.append({"path": "$.inputs", "expected": dependency, "got": "missing"})
    if require_envelope and manifest.get("status") != "complete":
        violations.append({"path": "$.status", "expected": "complete", "got": str(manifest.get("status"))})
    return violations


def _result_envelope(result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    data = result.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("result_envelope"), Mapping):
        return data["result_envelope"]
    if isinstance(result.get("result_envelope"), Mapping):
        return result["result_envelope"]
    # Coordinator adapters may already return the shared envelope directly.
    if {"status", "outputs", "evidence", "artifacts"}.issubset(result):
        return result
    return {}


def _normalize_refs(items: Any, *, task_id: str, kind: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items or []):
        value = deepcopy(dict(item)) if isinstance(item, Mapping) else {"value": item}
        ref_id = str(value.get("ref_id") or value.get("evidence_id") or value.get("artifact_id") or value.get("id") or f"{task_id}:{kind}:{index + 1}")
        value.update({
            "ref_id": ref_id,
            "kind": value.get("kind") or kind,
            "source_task_id": value.get("source_task_id") or task_id,
        })
        normalized.append(value)
    return normalized
