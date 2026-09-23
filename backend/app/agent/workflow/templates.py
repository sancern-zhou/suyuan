"""Reusable workflow definitions for common Agent orchestration shapes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any


def build_report_analysis_workflow(
    *,
    workflow_id: str,
    source_tasks: Iterable[Mapping[str, Any]],
    synthesis_task: Mapping[str, Any],
    delivery_tasks: Iterable[Mapping[str, Any]] | None = None,
    version: str = "report_analysis_v1",
) -> dict[str, Any]:
    """Build a standard report DAG without embedding domain-specific fields.

    Source tasks run in parallel. The synthesis task consumes every source
    result and returns a report-ready brief. The parent report Agent remains
    the single writer and closes the report package after this DAG completes.
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
        if source.get("target_mode") not in {"query", "expert"} or not source.get("goal"):
            raise ValueError("source task requires target_mode query/expert and goal")
        source.setdefault("require_lineage", True)

    synthesis = deepcopy(dict(synthesis_task))
    synthesis_id = str(synthesis.get("task_id") or "synthesis").strip()
    if synthesis.get("target_mode") != "expert" or not synthesis.get("goal"):
        raise ValueError("synthesis task requires target_mode expert and goal")
    synthesis["task_id"] = synthesis_id
    declared_dependencies = list(synthesis.get("dependencies") or [])
    if declared_dependencies and set(declared_dependencies) != set(source_ids):
        raise ValueError("synthesis dependencies must include every source task")
    synthesis["dependencies"] = source_ids
    synthesis.setdefault("require_lineage", True)

    if list(delivery_tasks or []):
        raise ValueError(
            "report delivery tasks are not supported; the parent report Agent owns final delivery"
        )

    all_ids = source_ids + [synthesis_id]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("workflow task_id values must be unique")

    return {
        "workflow_id": workflow_id,
        "version": version,
        "nodes": sources + [synthesis],
    }


def build_report_analysis_manifest(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return the compact, report-ready synthesis receipt for the parent Agent."""
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
    synthesis_status = str(envelope.get("status") or "").strip()
    data_gaps = list(envelope.get("data_gaps") or [])
    missing = []
    if not synthesis_id:
        missing.append("synthesis_node")
    elif (lineages.get(synthesis_id) or {}).get("status") != "complete":
        missing.append("synthesis_lineage")
    if synthesis_status != "completed":
        missing.append(f"synthesis_status:{synthesis_status or 'missing'}")
    if data_gaps:
        missing.append("synthesis_data_gaps")
    return {
        "schema_version": "report_analysis.v1",
        "status": "completed" if not missing else "completed_with_gaps",
        "synthesis_task_id": synthesis_id,
        "synthesis_status": synthesis_status or None,
        "synthesis_outputs": envelope.get("outputs") or {},
        "evidence": evidence,
        "artifacts": artifacts,
        "data_gaps": data_gaps,
        "missing": missing,
    }


def build_report_delivery_manifest(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for callers migrating to analysis-only DAGs."""
    return build_report_analysis_manifest(snapshot)
