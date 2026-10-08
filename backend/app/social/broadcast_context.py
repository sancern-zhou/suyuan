"""Persist outbound broadcasts in a recipient-specific broadcast inbox.

Broadcasts intentionally live outside the user's normal social session.  This
keeps scheduled notifications out of the Agent context while retaining a
durable inbox that the Android App can query after a push/reminder arrives.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import shutil
from pathlib import Path
from typing import Any

from app.agent.session.models import Session
from app.agent.session.session_resolver import (
    append_session_transcript_for_mode,
    load_session_for_mode,
    replace_session_transcript_for_mode,
)
from app.utils.path_config import get_data_registry, resolve_agent_path


def resolve_broadcast_media_path(media_path: str | Path) -> Path:
    """Resolve a broadcast path to the user-facing report artifact.

    ReportPackage tools expose ``report.qmd`` as their source ``file_path``
    while rendered DOCX/PDF files live beside it.  Sending that source file
    makes App preview the Markdown source instead of the generated report.
    Only the canonical ReportPackage layout is upgraded; ordinary Markdown
    attachments remain untouched.
    """
    source = resolve_agent_path(media_path)
    if source.name.lower() == "report.qmd":
        for rendition_name in ("report.docx", "report.pdf"):
            rendition = source.with_name(rendition_name)
            if rendition.is_file():
                return rendition
    return source


def broadcast_session_id(social_user_id: str) -> str:
    """Return a stable, non-guessable session id for one social identity."""
    digest = hashlib.sha256(str(social_user_id).encode("utf-8")).hexdigest()[:32]
    return f"broadcast_session_{digest}"


async def load_broadcast_messages(social_user_id: str) -> list[dict[str, Any]]:
    """Load the broadcast inbox for one identity, newest message first."""
    session = await load_session_for_mode(
        broadcast_session_id(social_user_id), mode="social"
    )
    if session is None:
        return []
    messages = [
        item for item in session.conversation_history
        if isinstance(item, dict) and item.get("type") == "broadcast"
    ]
    return list(reversed(messages))


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
    attachment_root = get_data_registry() / "social" / "broadcast_attachments" / hashlib.sha256(
        message_id.encode("utf-8")
    ).hexdigest()[:32]
    attachments = []
    for media_path in media:
        source = resolve_broadcast_media_path(media_path)
        if not source.is_file():
            continue
        attachment_root.mkdir(parents=True, exist_ok=True)
        target = attachment_root / source.name
        shutil.copy2(source, target)
        attachments.append({
            "name": target.name or "attachment",
            "path": str(target),
            "type": "file",
        })

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
