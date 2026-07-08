"""Persist lightweight context for non-silent social heartbeat runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import structlog

from app.agent.session.models import Session
from app.agent.session.session_resolver import (
    append_session_transcript_for_mode,
    load_session_for_mode,
)

logger = structlog.get_logger(__name__)

MAX_SUMMARY_CHARS = 800
MAX_TASKS = 5


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _task_label(task: Dict[str, Any]) -> str:
    name = str(task.get("name") or "定时任务").strip()
    mode = str(task.get("manual_mode") or task.get("mode") or "").strip()
    return f"{name} [{mode}]" if mode else name


def build_heartbeat_context_message(
    *,
    user_id: str,
    response: Dict[str, Any],
    heartbeat_session_id: str,
    tasks: Iterable[Dict[str, Any]] = (),
    recorded_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a compact transcript row that makes non-silent heartbeats follow-up aware."""
    executed_at = str(response.get("executed_at") or recorded_at or datetime.now().isoformat())
    task_list = [task for task in tasks if isinstance(task, dict)][:MAX_TASKS]
    task_names = [_task_label(task) for task in task_list]
    summary = _truncate_text(response.get("summary"), MAX_SUMMARY_CHARS)
    event_id = f"heartbeat_context:{heartbeat_session_id}"

    task_text = "、".join(task_names) if task_names else "未命名定时任务"
    content = (
        "[定时任务事件] 刚刚有一条非静默定时任务执行结果，已向用户发出通知。"
        f"\n任务：{task_text}"
        f"\n执行时间：{executed_at}"
        f"\n心跳会话：{heartbeat_session_id}"
        f"\n摘要：{summary}"
        "\n如用户追问详情，应优先基于该事件回答；需要完整过程时，可按心跳会话或任务名检索历史运行记录。"
    )

    return {
        "id": event_id,
        "type": "scheduled_task_event",
        "role": "user",
        "content": content,
        "timestamp": recorded_at or executed_at,
        "data": {
            "kind": "scheduled_task_event",
            "silent": False,
            "should_notify": True,
            "user_id": user_id,
            "heartbeat_session_id": heartbeat_session_id,
            "tasks": task_names,
            "summary_preview": summary,
            "executed_at": executed_at,
        },
    }


async def persist_heartbeat_context_event(
    *,
    session_mapper: Any,
    user_id: str,
    response: Dict[str, Any],
    heartbeat_session_id: str,
    tasks: Iterable[Dict[str, Any]] = (),
) -> bool:
    """Append a lightweight non-silent heartbeat event to the user's main social session.

    Silent heartbeats intentionally stay out of the main transcript. Non-silent
    heartbeats are persisted as a compact event so later user turns can recover
    continuity without loading the full scheduled-task run.
    """
    if not response.get("should_notify"):
        return False
    if not user_id or not heartbeat_session_id:
        return False

    main_session_id = await session_mapper.get_or_create_session(user_id, mode="social")
    session = await load_session_for_mode(main_session_id, mode="social")
    if not session:
        session = Session(
            session_id=main_session_id,
            query="社交定时任务上下文",
        )

    message = build_heartbeat_context_message(
        user_id=user_id,
        response=response,
        heartbeat_session_id=heartbeat_session_id,
        tasks=tasks,
    )
    existing_ids = {
        item.get("id")
        for item in session.conversation_history
        if isinstance(item, dict)
    }
    if message["id"] not in existing_ids:
        session.conversation_history.append(message)

    events = [
        item
        for item in session.metadata.get("scheduled_task_events", [])
        if isinstance(item, dict)
    ]
    if not any(item.get("id") == message["id"] for item in events):
        events.append({
            "id": message["id"],
            **message["data"],
        })
    session.metadata["scheduled_task_events"] = events[-20:]
    session.metadata["last_scheduled_task_event"] = {
        "id": message["id"],
        **message["data"],
    }

    saved = await append_session_transcript_for_mode(session, mode="social")
    if saved:
        logger.info(
            "heartbeat_context_event_persisted",
            user_id=user_id,
            main_session_id=main_session_id,
            heartbeat_session_id=heartbeat_session_id,
        )
    else:
        logger.warning(
            "heartbeat_context_event_persist_failed",
            user_id=user_id,
            main_session_id=main_session_id,
            heartbeat_session_id=heartbeat_session_id,
        )
    return bool(saved)
