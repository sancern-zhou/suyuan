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
