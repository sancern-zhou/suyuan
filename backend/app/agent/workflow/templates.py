"""Reusable workflow definitions for common Agent orchestration shapes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, Optional


def build_report_analysis_workflow(
    *,
    workflow_id: str,
    source_tasks: Iterable[Mapping[str, Any]],
    synthesis_task: Mapping[str, Any],
    delivery_tasks: Optional[Iterable[Mapping[str, Any]]] = None,
    version: str = "report_analysis_v1",
) -> Dict[str, Any]:
    """Build a standard report DAG without embedding domain-specific fields.

    Source tasks run in parallel.  The synthesis task consumes every source
    result.  Optional delivery tasks consume the synthesis result and run in
    parallel, which covers chart/report/artifact delivery without forcing one
    mode to own the whole workflow.
    """
    sources = [deepcopy(dict(task)) for task in source_tasks]
    if not sources:
        raise ValueError("report workflow requires at least one source task")
    source_ids = [str(task.get("task_id") or "").strip() for task in sources]
    if any(not task_id for task_id in source_ids):
        raise ValueError("source task_id is required")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source task_id values must be unique")
    for source in sources:
        source.setdefault("require_lineage", True)

    synthesis = deepcopy(dict(synthesis_task))
    synthesis_id = str(synthesis.get("task_id") or "synthesis").strip()
    if not synthesis.get("target_mode") or not synthesis.get("goal"):
        raise ValueError("synthesis task requires target_mode and goal")
    synthesis["task_id"] = synthesis_id
    synthesis["dependencies"] = list(synthesis.get("dependencies") or source_ids)
    synthesis.setdefault("require_lineage", True)

    deliveries = []
    for task in delivery_tasks or []:
        delivery = deepcopy(dict(task))
        task_id = str(delivery.get("task_id") or "").strip()
        if not task_id or not delivery.get("target_mode") or not delivery.get("goal"):
            raise ValueError("delivery task requires task_id, target_mode and goal")
        delivery["task_id"] = task_id
        delivery["dependencies"] = list(delivery.get("dependencies") or [synthesis_id])
        delivery.setdefault("require_lineage", True)
        deliveries.append(delivery)

    return {
        "workflow_id": workflow_id,
        "version": version,
        "nodes": sources + [synthesis] + deliveries,
    }


def build_report_delivery_manifest(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize report conclusions, evidence and delivery artifacts."""
    definition = snapshot.get("definition") if isinstance(snapshot, Mapping) else {}
    nodes = definition.get("nodes") if isinstance(definition, Mapping) else []
    node_by_id = {
        str(node.get("task_id")): node
        for node in nodes or []
        if isinstance(node, Mapping) and node.get("task_id")
    }
    lineages = snapshot.get("node_lineage") or {}
    results = snapshot.get("node_results") or {}
    def mode(node: Mapping[str, Any]) -> str:
        payload = node.get("payload") if isinstance(node.get("payload"), Mapping) else {}
        return str(node.get("target_mode") or payload.get("target_mode") or "").lower()

    synthesis_ids = [
        task_id for task_id, node in node_by_id.items()
        if node.get("dependencies") and mode(node) == "expert"
    ]
    synthesis_id = synthesis_ids[-1] if synthesis_ids else None
    delivery_ids = [
        task_id for task_id, node in node_by_id.items()
        if mode(node) in {"report", "chart", "report_generation"}
    ]
    evidence, artifacts = [], []
    for lineage in lineages.values():
        if not isinstance(lineage, Mapping):
            continue
        evidence.extend(item for item in lineage.get("evidence") or [] if isinstance(item, Mapping))
        artifacts.extend(item for item in lineage.get("artifacts") or [] if isinstance(item, Mapping))
    synthesis_result = results.get(synthesis_id) if synthesis_id else None
    envelope = {}
    if isinstance(synthesis_result, Mapping):
        data = synthesis_result.get("data")
        if isinstance(data, Mapping) and isinstance(data.get("result_envelope"), Mapping):
            envelope = data["result_envelope"]
    report_artifacts = [
        item for item in artifacts
        if item.get("source_task_id") in delivery_ids or item.get("kind") in {"file", "report", "report_package"}
    ]
    missing = []
    if not synthesis_id:
        missing.append("synthesis_node")
    elif (lineages.get(synthesis_id) or {}).get("status") != "complete":
        missing.append("synthesis_lineage")
    if not delivery_ids:
        missing.append("delivery_node")
    if not report_artifacts:
        missing.append("report_artifact")
    return {
        "schema_version": "report_delivery.v1",
        "status": "completed" if not missing else "completed_with_gaps",
        "synthesis_task_id": synthesis_id,
        "synthesis_outputs": envelope.get("outputs") or {},
        "evidence": evidence,
        "artifacts": artifacts,
        "delivery_task_ids": delivery_ids,
        "report_artifacts": report_artifacts,
        "missing": missing,
    }
