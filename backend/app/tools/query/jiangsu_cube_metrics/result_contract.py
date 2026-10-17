"""Runtime checks for the sparse Jiangsu Agent result contract."""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.utils.path_config import resolve_agent_path


CONTRACT_PATH = resolve_agent_path(
    "projects/jiangsu-ops/data-ops/semantic/result_contract.yaml"
)


def load_contract() -> Dict[str, Any]:
    with Path(CONTRACT_PATH).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def validate_result(profile: str, payload: Dict[str, Any]) -> List[str]:
    """Return contract violations without mutating a live query response."""
    profile_spec = (load_contract().get("profiles") or {}).get(profile)
    if not profile_spec:
        return [f"unknown profile: {profile}"]
    errors: List[str] = []
    for field in profile_spec.get("required", []):
        if field not in payload:
            errors.append(f"missing required field: {field}")
    semantic = payload.get("semantic_context") or {}
    if profile == "metric_query":
        for field in ("dataset", "grain", "applicability", "data_as_of"):
            if field not in semantic:
                errors.append(f"semantic_context missing: {field}")
        if not semantic.get("metric_definitions"):
            errors.append("semantic_context missing: metric_definitions")
    elif profile == "metric_definition":
        for field in ("metric_definitions", "grain", "applicability"):
            if field not in semantic:
                errors.append(f"semantic_context missing: {field}")
    elif profile == "evidence_sql":
        if semantic.get("query_role") not in {"field_evidence", "schema_introspection"}:
            errors.append("semantic_context.query_role must identify SQL evidence")
        if semantic.get("official_metric_calculation") is not False:
            errors.append("official_metric_calculation must be false")
    elif profile == "analysis":
        evidence_ids = {
            item.get("id") for item in (payload.get("evidence") or [])
            if isinstance(item, dict)
        }
        for finding in payload.get("findings") or []:
            supported = finding.get("supported_by", []) if isinstance(finding, dict) else []
            if not set(supported).issubset(evidence_ids):
                errors.append("finding supported_by references missing evidence")
    return errors
