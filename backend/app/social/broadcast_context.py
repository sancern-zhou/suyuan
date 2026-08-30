"""Persist outbound broadcasts in a recipient-specific broadcast inbox.

Broadcasts intentionally live outside the user's normal social session.  This
keeps scheduled notifications out of the Agent context while retaining a
durable inbox that the Android App can query after a push/reminder arrives.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any

from app.agent.session.models import Session
from app.agent.session.session_resolver import (
    append_session_transcript_for_mode,
    load_session_for_mode,
    replace_session_transcript_for_mode,
)


def broadcast_session_id(social_user_id: str) -> str:
    """Return a stable, non-guessable session id for one social identity."""
    digest = hashlib.sha256(str(social_user_id).encode("utf-8")).hexdigest()[:32]
    return f"broadcast_session_{digest}"


async def load_broadcast_messages(
    social_user_id: str,
    *,
    limit: int | None = None,
    before_message_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load broadcasts newest first, optionally paging towards older messages."""
    session = await load_session_for_mode(
        broadcast_session_id(social_user_id), mode="social"
    )
    if session is None:
        return []
    messages = [
        item for item in session.conversation_history
        if isinstance(item, dict) and item.get("type") == "broadcast"
    ]
    messages = list(reversed(messages))
    if before_message_id:
        cursor_index = next(
            (
                index
                for index, item in enumerate(messages)
                if str(item.get("id") or "") == before_message_id
            ),
            None,
        )
        if cursor_index is None:
            return []
        messages = messages[cursor_index + 1 :]
    if limit is not None:
        return messages[:limit]
    return messages


async def delete_broadcast_message(social_user_id: str, message_id: str) -> bool:
    """Delete one broadcast from the dedicated inbox."""
    session = await load_session_for_mode(
        broadcast_session_id(social_user_id), mode="social"
    )
    if session is None:
        return False
    original_count = len(session.conversation_history)
    session.conversation_history = [
        item
        for item in session.conversation_history
        if not (
            isinstance(item, dict)
            and item.get("type") == "broadcast"
            and str(item.get("id") or "") == message_id
        )
    ]
    if len(session.conversation_history) == original_count:
        return False
    return bool(await replace_session_transcript_for_mode(session, mode="social"))


async def mark_broadcast_read(social_user_id: str, message_id: str | None = None) -> bool:
    """Mark one message (or all messages when id is omitted) as read."""
    session = await load_session_for_mode(
        broadcast_session_id(social_user_id), mode="social"
    )
    if session is None:
        return False
    changed = False
    for item in session.conversation_history:
        if not isinstance(item, dict) or item.get("type") != "broadcast":
            continue
        if message_id and item.get("id") != message_id:
            continue
        data = item.setdefault("data", {})
        if not isinstance(data, dict):
            data = {}
            item["data"] = data
        if item.get("read") is not True or data.get("read") is not True:
            item["read"] = True
            data["read"] = True
            data["read_at"] = datetime.now().astimezone().isoformat()
            changed = True
    if not changed:
        return False
    return bool(await replace_session_transcript_for_mode(session, mode="social"))


async def persist_broadcast_context(
    *,
    session_mapper: Any,
    social_user_id: str,
    message: str,
    media: list[str],
    metadata: dict[str, Any],
) -> bool:
    """Append one idempotent assistant broadcast with message attachments."""
    # Keep the mapper argument for service compatibility, but never use the
    # user's normal chat mapping for broadcasts.
    del session_mapper
    session_id = broadcast_session_id(social_user_id)
    session = await load_session_for_mode(session_id, mode="social")
    if session is None:
        session = Session(
            session_id=session_id,
            query="广播消息",
            metadata={"kind": "broadcast_inbox", "social_user_id": social_user_id},
        )

    task_id = str(metadata.get("task_id") or "manual")
    event_id = str(metadata.get("event_id") or hashlib.sha256(message.encode("utf-8")).hexdigest()[:16])
    message_id = f"broadcast:{task_id}:{event_id}:{social_user_id}"
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
            "read": False,
            "data": {**metadata, "attachments": attachments, "read": False},
        })

    return bool(
        await append_session_transcript_for_mode(session, mode="social")
    )
