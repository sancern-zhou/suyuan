"""节点成果缓存：同一 workflow 重提时复用已完成节点，只重跑受影响的节点。

参照 zai-org/ZCode dynamic-workflow 的 imported-cache 思想：
- 缓存键 = (workflow_id, task_id, goal 哈希 + target_mode)——goal 变了即视为受影响节点
- 复用要求依赖闭包全部命中：上游结果可得，下游才能跳过
- 上游变化时下游自动失效（goal 哈希级联），无需显式传播

fail-soft：缓存缺失/损坏一律按未命中处理，绝不阻断执行。
"""

from __future__ import annotations

import hashlib
import json
import structlog
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

CACHE_DIRNAME = "workflow_cache"
# 单节点结果缓存上限：超过则跳过缓存（大体积产物走 registry 文件，不进缓存）
MAX_RESULT_BYTES = 512 * 1024


def _cache_root() -> Path:
    return Path(get_data_registry()) / CACHE_DIRNAME


def goal_hash(goal: str, target_mode: str) -> str:
    normalized = " ".join(str(goal or "").split())
    digest = hashlib.sha256(f"{target_mode}|{normalized}".encode("utf-8")).hexdigest()
    return digest[:16]


def _node_path(workflow_id: str, task_id: str) -> Path:
    safe_wf = "".join(ch for ch in str(workflow_id) if ch.isalnum() or ch in "-_.") or "wf"
    safe_task = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in "-_.") or "task"
    return _cache_root() / safe_wf / f"{safe_task}.json"


def store_node_result(
    workflow_id: str,
    task_id: str,
    goal: str,
    target_mode: str,
    result: Mapping[str, Any],
) -> bool:
    """成功节点结果落盘；过大或写入失败返回 False（不阻断）。"""
    try:
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        if len(serialized.encode("utf-8")) > MAX_RESULT_BYTES:
            logger.info("workflow_cache_result_too_large", task_id=task_id, size=len(serialized))
            return False
        path = _node_path(workflow_id, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "goal_hash": goal_hash(goal, target_mode),
            "target_mode": target_mode,
            "stored_at": Path(path).stat().st_mtime if path.exists() else None,
            "result": result,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001 — 缓存写入失败不影响执行
        logger.warning("workflow_cache_store_failed", task_id=task_id, error=str(exc))
        return False


def load_node_result(
    workflow_id: str,
    task_id: str,
    goal: str,
    target_mode: str,
) -> Optional[Dict[str, Any]]:
    """读取缓存结果；goal 不一致/缺失/损坏返回 None。"""
    path = _node_path(workflow_id, task_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("workflow_cache_load_failed", task_id=task_id, error=str(exc))
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("goal_hash") != goal_hash(goal, target_mode):
        logger.info("workflow_cache_goal_changed", workflow_id=workflow_id, task_id=task_id)
        return None
    result = payload.get("result")
    return result if isinstance(result, dict) else None


def select_reusable_nodes(
    workflow_id: str,
    nodes: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """按依赖闭包选择可复用节点：节点命中且全部上游也命中才算可复用。

    多轮迭代直至不动点（节点数即轮数上限，规模小无性能顾虑）。
    """
    node_list: List[Mapping[str, Any]] = [dict(node) for node in nodes]
    reusable: Dict[str, Dict[str, Any]] = {}
    changed = True
    while changed:
        changed = False
        for node in node_list:
            task_id = str(node.get("task_id") or "")
            if not task_id or task_id in reusable:
                continue
            dependencies = [
                str(dep) for dep in (node.get("dependencies") or []) if str(dep)
            ]
            if any(dep not in reusable for dep in dependencies):
                continue
            cached = load_node_result(
                workflow_id,
                task_id,
                str(node.get("goal") or ""),
                str(node.get("target_mode") or ""),
            )
            if cached is not None:
                reusable[task_id] = cached
                changed = True
    return reusable
