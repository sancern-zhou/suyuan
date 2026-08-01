"""Persist outbound broadcasts in each recipient's main social conversation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.agent.session.models import Session
from app.agent.session.session_resolver import (
    append_session_transcript_for_mode,
    load_session_for_mode,
)


async def persist_broadcast_context(
    *,
    session_mapper: Any,
    social_user_id: str,
    message: str,
    media: list[str],
    metadata: dict[str, Any],
) -> bool:
    """Append one idempotent assistant broadcast with message attachments."""
    session_id = await session_mapper.get_or_create_session(
        social_user_id,
        mode="social",
    )
    session = await load_session_for_mode(session_id, mode="social")
    if session is None:
        session = Session(session_id=session_id, query="社交广播上下文")

    message_id = (
        f"broadcast:{metadata['task_id']}:{metadata['event_id']}:{social_user_id}"
    )
    attachments = [
        {
            "name": Path(media_path).name or "attachment",
            "path": media_path,
            "type": "file",
        }
        for media_path in media
    ]

    if not any(
        item.get("id") == message_id
        for item in session.conversation_history
        if isinstance(item, dict)
    ):
        session.conversation_history.append({
            "id": message_id,
            "type": "broadcast",
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().astimezone().isoformat(),
            "data": {**metadata, "attachments": attachments},
        })

    return bool(
        await append_session_transcript_for_mode(session, mode="social")
    )
