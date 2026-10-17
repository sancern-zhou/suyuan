"""Sparse result contract checks for Xuchang metric queries."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.utils.path_config import resolve_agent_path

CONTRACT_PATH = resolve_agent_path("projects/xuchang/data-ops/semantic/result_contract.yaml")


def _contract() -> dict[str, Any]:
    try:
        return yaml.safe_load(Path(CONTRACT_PATH).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def validate_result(profile: str, payload: Dict[str, Any]) -> List[str]:
    spec = (_contract().get("profiles") or {}).get(profile)
    if not spec:
        return [f"unknown profile: {profile}"]
    errors = [f"missing required field: {field}" for field in spec.get("required", []) if field not in payload]
    semantic = payload.get("semantic_context") or {}
    if profile == "metric_query":
        for field in ("dataset", "grain", "applicability", "data_as_of", "metric_definitions"):
            if field not in semantic:
                errors.append(f"semantic_context missing: {field}")
    elif profile == "metric_definition":
        for field in ("dataset", "grain", "applicability", "metric_definitions"):
            if field not in semantic:
                errors.append(f"semantic_context missing: {field}")
    return errors
