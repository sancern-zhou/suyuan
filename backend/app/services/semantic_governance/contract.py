# -*- coding: utf-8 -*-
"""运行时结果契约校验，profile 规则声明在契约 YAML 里。

规则全部来自契约文件（projects/<project>/data-ops/semantic/result_contract.yaml），
共享层不做任何 per-profile 硬编码——粤苏两分支曾因各自硬编码 profile 规则而
漂移（2026-10-31 上移共享时改为声明式）。契约文件可声明：

  profiles.<name>.required:                   payload 顶层必返字段
  profiles.<name>.semantic_context_required:  semantic_context 必含键
  profiles.<name>.semantic_context_equals:    semantic_context 键值相等断言

加载 fail-open：契约缺失/损坏返回 None → 跳过校验（仅告警）。配置文件问题
不得把已成功的查询变成失败；与 catalog_store 的 fail-closed 形成正确不对称。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog
import yaml

logger = structlog.get_logger()


@lru_cache(maxsize=8)
def _load_cached(path_str: str, mtime_ns: int, log_event: str) -> Optional[Dict[str, Any]]:
    path = Path(path_str)
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(log_event, path=str(path), error=str(exc))
        return None


def load_contract(path: Union[str, Path], *,
                  log_event: str = "result_contract_unavailable") -> Optional[Dict[str, Any]]:
    """加载契约；fail-open（缺失/损坏 → None，调用方跳过校验）。"""
    resolved = Path(path)
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        logger.warning(log_event, path=str(resolved), error="contract file missing")
        return None
    return _load_cached(str(resolved), mtime, log_event)


def validate_result(contract: Optional[Dict[str, Any]], profile: str,
                    payload: Dict[str, Any]) -> List[str]:
    """返回契约违例列表，不改动在线查询响应。"""
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
        for key in profile_spec.get("semantic_context_required") or []:
            if key not in semantic:
                errors.append(f"{profile}: semantic_context missing '{key}'")
        for key, expected in (profile_spec.get("semantic_context_equals") or {}).items():
            if semantic.get(key) != expected:
                errors.append(
                    f"{profile}: semantic_context['{key}'] must be {expected!r}")
    return errors
