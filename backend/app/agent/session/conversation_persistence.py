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
    def _is_persistent_message(message: Dict[str, Any]) -> bool:
        # Thought events are runtime/debug progress. They may be streamed to the
        # UI, but keeping them in restored transcripts causes the model to treat
        # prior intermediate text as conversational history.
        return message.get("type") != "thought"

    def _persistent_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            dict(message)
            for message in messages
            if self._is_persistent_message(message)
        ]

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
        merged = self._persistent_messages(existing_history)
        seen = {self._message_key(message) for message in merged}

        for message in self._persistent_messages(display_history):
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
        drawio_board: Optional[Dict[str, Any]] = None,
    ) -> None:
        session.conversation_history = self._persistent_messages(display_history)
        self.apply_metadata(
            session,
            drawio_board=drawio_board,
        )

    def append_complete(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        drawio_board: Optional[Dict[str, Any]] = None,
    ) -> None:
        session.conversation_history = self._append_missing_messages(
            session.conversation_history,
            display_history,
        )
        self.append_metadata(
            session,
            drawio_board=drawio_board,
        )

    def apply_terminal(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        terminal_message: Dict[str, Any],
        drawio_board: Optional[Dict[str, Any]] = None,
    ) -> None:
        session.conversation_history = self._persistent_messages(
            list(display_history) + [dict(terminal_message)]
        )
        self.apply_metadata(
            session,
            drawio_board=drawio_board,
        )

    def append_terminal(
        self,
        session: Session,
        *,
        display_history: List[Dict[str, Any]],
        terminal_message: Dict[str, Any],
        drawio_board: Optional[Dict[str, Any]] = None,
    ) -> None:
        session.conversation_history = self._append_missing_messages(
            session.conversation_history,
            list(display_history) + [dict(terminal_message)],
        )
        self.append_metadata(
            session,
            drawio_board=drawio_board,
        )

    @staticmethod
    def normalize_drawio_board(board_context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(board_context, dict):
            return None

        board_id = (
            board_context.get("board_id")
            or board_context.get("active_board_id")
            or board_context.get("activeBoardId")
            or board_context.get("artifact_id")
            or board_context.get("id")
        )
        current_version_id = (
            board_context.get("current_version_id")
            or board_context.get("currentVersionId")
            or board_context.get("version_id")
        )
        selected_cells = board_context.get("selected_cells") or board_context.get("selectedCells") or []
        if not isinstance(selected_cells, list):
            selected_cells = []
        if board_id and current_version_id and board_context.get("revision") is not None:
            return {
                "artifact_kind": "drawio_board",
                "board_id": board_id,
                "active_board_id": board_id,
                "title": board_context.get("title") or board_context.get("name") or "Draw.io Board",
                "current_version_id": current_version_id,
                "revision": int(board_context.get("revision") or 0),
                "selected_cells": selected_cells,
                "updated_at": board_context.get("updated_at") or board_context.get("updatedAt"),
            }

        current_xml = (
            board_context.get("current_xml")
            or board_context.get("currentXml")
            or board_context.get("xml")
            or board_context.get("drawio_xml")
        )
        if not current_xml:
            return None

        return {
            "artifact_kind": "drawio_board",
            "board_id": board_id,
            "active_board_id": board_id,
            "title": board_context.get("title") or board_context.get("name") or "Draw.io Board",
            "current_xml": current_xml,
            "selected_cells": selected_cells,
            "version": board_context.get("version"),
            "dirty": bool(board_context.get("dirty", False)),
            "updated_at": board_context.get("updated_at") or board_context.get("updatedAt"),
        }

    def apply_metadata(
        self,
        session: Session,
        *,
        drawio_board: Optional[Dict[str, Any]] = None,
    ) -> None:
        normalized_board = self.normalize_drawio_board(drawio_board)
        if normalized_board:
            session.metadata["drawio_board"] = normalized_board

    def append_metadata(
        self,
        session: Session,
        *,
        drawio_board: Optional[Dict[str, Any]] = None,
    ) -> None:
        normalized_board = self.normalize_drawio_board(drawio_board)
        if normalized_board:
            session.metadata["drawio_board"] = normalized_board
