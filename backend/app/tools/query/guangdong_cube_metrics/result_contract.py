"""Runtime checks for the sparse Guangdong Agent result contract."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import yaml

from app.utils.path_config import resolve_agent_path

logger = structlog.get_logger()


CONTRACT_PATH = resolve_agent_path(
    "projects/guangdong/data-ops/semantic/result_contract.yaml"
)


@lru_cache(maxsize=1)
def load_contract() -> Optional[Dict[str, Any]]:
    """契约缺失/损坏时 fail-open（返回 None → 跳过校验），与 registry 的容错语义
    一致：配置文件问题不得把已成功的查询变成失败。仅记录告警日志。
    进程内缓存（改契约后需重启生效）。"""
    try:
        with Path(CONTRACT_PATH).open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("guangdong_result_contract_unavailable", error=str(exc))
        return None


def validate_result(profile: str, payload: Dict[str, Any]) -> List[str]:
    """Return contract violations without mutating a live query response."""
    contract = load_contract()
    if contract is None:
        return []
    profile_spec = (contract.get("profiles") or {}).get(profile)
    if not profile_spec:
        return [f"unknown profile: {profile}"]
    errors: List[str] = []
    for field in profile_spec.get("required", []):
        if field not in payload:
            errors.append(f"{profile}: missing required field '{field}'")
    semantic = payload.get("semantic_context")
    if isinstance(semantic, dict):
        if profile == "metric_definition":
            for key in ("metric_definitions", "grain", "applicability"):
                if key not in semantic:
                    errors.append(f"metric_definition: semantic_context missing '{key}'")
        elif profile == "metric_query":
            for key in ("dataset", "grain", "applicability", "data_as_of", "metric_definitions"):
                if key not in semantic:
                    errors.append(f"metric_query: semantic_context missing '{key}'")
        elif profile == "schema_introspection":
            if semantic.get("query_role") != "schema_introspection":
                errors.append("schema_introspection: query_role must be 'schema_introspection'")
    return errors
