"""Canonical session transcript persistence helpers.

The UI/display transcript is the source of truth for session restore. Runtime
LLM memory is a lossy projection and must not overwrite it.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.agent.session.models import Session


class ConversationPersistenceService:
    """Apply display transcript and artifact metadata to a Session."""

    @staticmethod
    def _message_key(message: Dict[str, Any]) -> tuple[Any, ...]:
        explicit_id = message.get("id") or message.get("message_id")
        if explicit_id:
            return ("id", explicit_id)
        data_key = json.dumps(
            message.get("data"),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return (
            "content",
            message.get("type"),
            message.get("role"),
            message.get("content"),
            message.get("timestamp"),
            message.get("tool_use_id"),
            data_key,
        )

    def _append_missing_messages(
        self,
        existing_history: List[Dict[str, Any]],
        display_history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged = [dict(message) for message in existing_history]
        seen = {self._message_key(message) for message in merged}

        for message in display_history:
            key = self._message_key(message)
            if key in seen:
                continue
            merged.append(dict(message))
            seen.add(key)

        return merged

    def apply_complete(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        collected_data_ids: List[str],
        collected_visuals: List[Dict[str, Any]],
        office_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        session.conversation_history = list(display_history)
        self.apply_metadata(
            session,
            collected_data_ids=collected_data_ids,
            collected_visuals=collected_visuals,
            office_documents=office_documents,
        )

    def append_complete(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        collected_data_ids: List[str],
        collected_visuals: List[Dict[str, Any]],
        office_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        session.conversation_history = self._append_missing_messages(
            session.conversation_history,
            display_history,
        )
        self.append_metadata(
            session,
            collected_data_ids=collected_data_ids,
            collected_visuals=collected_visuals,
            office_documents=office_documents,
        )

    def apply_terminal(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        terminal_message: Dict[str, Any],
        collected_data_ids: List[str],
        collected_visuals: List[Dict[str, Any]],
        office_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        session.conversation_history = list(display_history) + [dict(terminal_message)]
        self.apply_metadata(
            session,
            collected_data_ids=collected_data_ids,
            collected_visuals=collected_visuals,
            office_documents=office_documents,
        )

    def append_terminal(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        terminal_message: Dict[str, Any],
        collected_data_ids: List[str],
        collected_visuals: List[Dict[str, Any]],
        office_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        session.conversation_history = self._append_missing_messages(
            session.conversation_history,
            list(display_history) + [dict(terminal_message)],
        )
        self.append_metadata(
            session,
            collected_data_ids=collected_data_ids,
            collected_visuals=collected_visuals,
            office_documents=office_documents,
        )

    def apply_metadata(
        self,
        session: Session,
        *,
        collected_data_ids: List[str],
        collected_visuals: List[Dict[str, Any]],
        office_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        session.data_ids = list(dict.fromkeys(collected_data_ids))
        session.visual_ids = [
            visual.get("id")
            for visual in collected_visuals
            if isinstance(visual, dict) and visual.get("id")
        ]
        if office_documents is not None:
            session.office_documents = list(office_documents)
        if collected_visuals:
            session.metadata["visualizations"] = list(collected_visuals)
            session.metadata["visuals_count"] = len(collected_visuals)

    def append_metadata(
        self,
        session: Session,
        *,
        collected_data_ids: List[str],
        collected_visuals: List[Dict[str, Any]],
        office_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        session.data_ids = list(dict.fromkeys([*session.data_ids, *collected_data_ids]))

        existing_visuals = []
        if isinstance(session.metadata, dict):
            existing_visuals = [
                visual
                for visual in session.metadata.get("visualizations", [])
                if isinstance(visual, dict)
            ]
        visuals_by_id: Dict[str, Dict[str, Any]] = {}
        anonymous_visuals: List[Dict[str, Any]] = []
        for visual in [*existing_visuals, *collected_visuals]:
            if not isinstance(visual, dict):
                continue
            visual_id = visual.get("id")
            if visual_id:
                visuals_by_id[visual_id] = visual
            else:
                anonymous_visuals.append(visual)

        merged_visuals = [*visuals_by_id.values(), *anonymous_visuals]
        session.visual_ids = [
            visual.get("id")
            for visual in merged_visuals
            if isinstance(visual, dict) and visual.get("id")
        ]
        if merged_visuals:
            session.metadata["visualizations"] = merged_visuals
            session.metadata["visuals_count"] = len(merged_visuals)

        if office_documents is not None:
            session.office_documents = list(office_documents)
