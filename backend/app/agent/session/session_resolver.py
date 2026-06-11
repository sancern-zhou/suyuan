"""Resolve session storage by runtime mode.

Most agent surfaces use the database-backed manager. Social mode is different:
its user/session mapping and transcript are local operational state, so it must
use the file-backed manager as the source of truth.
"""

from __future__ import annotations

import inspect
from typing import Any, Optional

from .models import Session
from .session_manager import SessionManager
from .session_manager import get_session_manager as get_file_session_manager


def _is_social_mode(mode: Optional[str]) -> bool:
    return mode == "social"


def get_session_manager_for_mode(mode: Optional[str] = None) -> Any:
    """Return the canonical session manager for a runtime mode."""
    if _is_social_mode(mode):
        return get_file_session_manager()

    from . import get_session_manager

    return get_session_manager()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def load_session_for_mode(
    session_id: str,
    *,
    mode: Optional[str] = None,
    include_messages: bool = True,
) -> Optional[Session]:
    manager = get_session_manager_for_mode(mode)
    if isinstance(manager, SessionManager):
        return await _maybe_await(manager.load_session(session_id))
    return await _maybe_await(
        manager.load_session(session_id, include_messages=include_messages)
    )


async def load_session_for_llm_mode(
    session_id: str,
    *,
    mode: Optional[str] = None,
) -> Optional[Session]:
    manager = get_session_manager_for_mode(mode)
    if isinstance(manager, SessionManager):
        return await _maybe_await(manager.load_session(session_id))
    if hasattr(manager, "load_session_for_llm"):
        return await _maybe_await(manager.load_session_for_llm(session_id))
    return await _maybe_await(manager.load_session(session_id, include_messages=True))


async def save_session_metadata_for_mode(
    session: Session,
    *,
    mode: Optional[str] = None,
    update_timestamp: bool = True,
) -> bool:
    manager = get_session_manager_for_mode(mode)
    if hasattr(manager, "save_session_metadata"):
        return bool(
            await _maybe_await(
                manager.save_session_metadata(
                    session,
                    update_timestamp=update_timestamp,
                )
            )
        )
    return bool(
        await _maybe_await(
            manager.save_session(session, update_timestamp=update_timestamp)
        )
    )


async def save_llm_compact_state_for_mode(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    source_until_sequence: int,
    mode: Optional[str] = None,
    token_estimate: Optional[int] = None,
    reason: Optional[str] = None,
) -> bool:
    manager = get_session_manager_for_mode(mode)
    if not hasattr(manager, "save_llm_compact_state"):
        return False
    return bool(
        await _maybe_await(
            manager.save_llm_compact_state(
                session_id,
                messages,
                source_until_sequence=source_until_sequence,
                token_estimate=token_estimate,
                reason=reason,
            )
        )
    )


async def append_session_transcript_for_mode(
    session: Session,
    *,
    mode: Optional[str] = None,
    update_timestamp: bool = True,
) -> bool:
    manager = get_session_manager_for_mode(mode)
    if hasattr(manager, "append_session_transcript"):
        return bool(
            await _maybe_await(
                manager.append_session_transcript(
                    session,
                    update_timestamp=update_timestamp,
                )
            )
        )
    return bool(
        await _maybe_await(
            manager.save_session(session, update_timestamp=update_timestamp)
        )
    )


async def replace_session_transcript_for_mode(
    session: Session,
    *,
    mode: Optional[str] = None,
    update_timestamp: bool = True,
) -> bool:
    manager = get_session_manager_for_mode(mode)
    if hasattr(manager, "replace_session_transcript"):
        return bool(
            await _maybe_await(
                manager.replace_session_transcript(
                    session,
                    update_timestamp=update_timestamp,
                )
            )
        )
    return bool(
        await _maybe_await(
            manager.save_session(session, update_timestamp=update_timestamp)
        )
    )
