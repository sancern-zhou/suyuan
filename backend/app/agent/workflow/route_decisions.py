"""委派路由决策审计（助手单入口方案 · 阶段 A）。

每次父模式对子模式的顶层委派（call_sub_agent / run_agent_workflow）落一行
``agent_route_decisions``，试运行期据此统计路由质量：边界拒收率、场景预填
命中、重裁链路。工作流节点（``_workflow_node`` 标记）与助手运行内部执行
（managed_delegation 作用域）不重复记录——只记顶层路由决定。

fail-soft：审计构建或写入失败只记日志，绝不阻塞委派本身。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Iterable, Optional, Set

import structlog
from sqlalchemy import text

logger = structlog.get_logger()

REASON_ASSISTANT_JUDGMENT = "assistant_judgment"
REASON_SCENE_PREFILL = "scene_prefill"
REASON_CONTINUITY = "continuity"
REASON_BOUNDARY_REFUSED = "boundary_refused"

REASON_CODES = frozenset(
    {
        REASON_ASSISTANT_JUDGMENT,
        REASON_SCENE_PREFILL,
        REASON_CONTINUITY,
        REASON_BOUNDARY_REFUSED,
    }
)

_INSERT_SQL = text(
    "INSERT INTO agent_route_decisions "
    "(id, session_id, user_identifier, parent_mode, target_modes, reason_code, "
    "reason_values, route_hint, created_at) "
    "VALUES (:id, :session_id, :user_identifier, :parent_mode, :target_modes, "
    ":reason_code, :reason_values, :route_hint, CURRENT_TIMESTAMP)"
)

# 持有任务引用，防止 fire-and-forget 任务被垃圾回收。
_pending_tasks: Set["asyncio.Task"] = set()


def build_decision_row(
    *,
    session_id: Optional[str],
    user_identifier: Optional[str] = None,
    parent_mode: Optional[str] = None,
    target_modes: Iterable[str],
    reason_code: str,
    reason_values: Optional[Dict[str, Any]] = None,
    route_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """组装一行决策记录；无目标模式或未知 reason_code 返回 None。"""
    modes = [str(mode).strip() for mode in target_modes if str(mode or "").strip()]
    if not modes or reason_code not in REASON_CODES:
        return None
    return {
        "id": uuid.uuid4().hex,
        "session_id": str(session_id)[:255] if session_id else None,
        "user_identifier": str(user_identifier)[:255] if user_identifier else None,
        "parent_mode": str(parent_mode)[:64] if parent_mode else None,
        "target_modes": modes,
        "reason_code": reason_code,
        "reason_values": dict(reason_values or {}),
        "route_hint": str(route_hint)[:255] if route_hint else None,
    }


async def _insert_row(row: Dict[str, Any]) -> None:
    from app.db.database import async_session

    params = {
        **row,
        "target_modes": json.dumps(row["target_modes"], ensure_ascii=False),
        "reason_values": json.dumps(row["reason_values"], ensure_ascii=False),
    }
    async with async_session() as session:
        await session.execute(_INSERT_SQL, params)
        await session.commit()


async def _insert_row_checked(row: Dict[str, Any]) -> None:
    try:
        await _insert_row(row)
    except Exception:  # noqa: BLE001 — 表未建/库不可用等一律 fail-soft
        logger.warning(
            "route_decision_write_failed",
            reason_code=row.get("reason_code"),
            exc_info=True,
        )


def record_route_decision(**kwargs: Any) -> None:
    """fire-and-forget 落库。无事件循环或写入失败都只记日志。"""
    try:
        row = build_decision_row(**kwargs)
    except Exception:  # noqa: BLE001
        logger.warning("route_decision_build_failed", exc_info=True)
        return
    if row is None:
        return
    try:
        task = asyncio.get_running_loop().create_task(_insert_row_checked(row))
    except RuntimeError:
        # 无运行中的事件循环（同步测试环境等）：放弃记录，不阻塞调用方。
        logger.debug("route_decision_no_event_loop", reason_code=row["reason_code"])
        return
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
