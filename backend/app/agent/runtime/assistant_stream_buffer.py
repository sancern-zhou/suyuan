"""Assistant stream buffering and visibility rules."""

from __future__ import annotations

import json


OPEN_JSON_FENCE = "```json"
FENCE = "```"
QUERY_DASHBOARD_METADATA_MARKER = "query_dashboard_metadata"


class AssistantStreamBuffer:
    """Tracks raw assistant text and prevents tool-planning text leaks."""

    def __init__(self, suppress_marked_dashboard_metadata: bool = False) -> None:
        self.raw_text = ""
        self.visible_text = ""
        self._last_visible_snapshot = ""
        self.suppress_after_tool_use = False
        self.suppress_marked_dashboard_metadata = suppress_marked_dashboard_metadata
        self._scan_buffer = ""
        self._held_json_fence = ""

    def note_tool_use(self) -> None:
        self.suppress_after_tool_use = True

    def append(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.raw_text += chunk
        if self.suppress_after_tool_use:
            return ""
        visible_chunk = (
            self._filter_marked_dashboard_metadata(chunk)
            if self.suppress_marked_dashboard_metadata
            else chunk
        )
        return self._append_visible(visible_chunk)

    def flush(self) -> str:
        """Emit any held text that was only buffered to detect a marked JSON block."""
        if self.suppress_after_tool_use or not self.suppress_marked_dashboard_metadata:
            return ""
        visible = ""
        if self._held_json_fence:
            visible += self._held_json_fence
            self._held_json_fence = ""
        if self._scan_buffer:
            visible += self._scan_buffer
            self._scan_buffer = ""
        return self._append_visible(visible)

    def _append_visible(self, text: str) -> str:
        if not text:
            return ""
        self.visible_text += text
        if self.visible_text == self._last_visible_snapshot:
            return ""
        self._last_visible_snapshot = self.visible_text
        return text

    def final_text(self, fallback: str = "") -> str:
        return fallback or self.visible_text or self.raw_text

    def _filter_marked_dashboard_metadata(self, chunk: str) -> str:
        self._scan_buffer += chunk
        output_parts: list[str] = []

        while self._scan_buffer or self._held_json_fence:
            if self._held_json_fence:
                if self._scan_buffer:
                    self._held_json_fence += self._scan_buffer
                    self._scan_buffer = ""
                closing_index = self._held_json_fence.find(FENCE, len(OPEN_JSON_FENCE))
                if closing_index < 0:
                    break

                block_end = closing_index + len(FENCE)
                block = self._held_json_fence[:block_end]
                remainder = self._held_json_fence[block_end:]
                if not self._is_marked_dashboard_metadata_block(block):
                    output_parts.append(block)
                self._held_json_fence = ""
                self._scan_buffer = remainder
                continue

            opening_index = self._scan_buffer.find(OPEN_JSON_FENCE)
            if opening_index < 0:
                hold_chars = len(OPEN_JSON_FENCE) - 1
                if len(self._scan_buffer) <= hold_chars:
                    break
                emit_until = len(self._scan_buffer) - hold_chars
                output_parts.append(self._scan_buffer[:emit_until])
                self._scan_buffer = self._scan_buffer[emit_until:]
                break

            if opening_index > 0:
                output_parts.append(self._scan_buffer[:opening_index])
            self._held_json_fence = self._scan_buffer[opening_index:]
            self._scan_buffer = ""

        return "".join(output_parts)

    def _is_marked_dashboard_metadata_block(self, block: str) -> bool:
        if not block.startswith(OPEN_JSON_FENCE) or not block.endswith(FENCE):
            return False
        raw_json = block[len(OPEN_JSON_FENCE):-len(FENCE)].strip()
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return False
        return (
            isinstance(payload, dict)
            and payload.get(QUERY_DASHBOARD_METADATA_MARKER) is True
        )
