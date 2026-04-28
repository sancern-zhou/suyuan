"""Assistant stream buffering and visibility rules."""

from __future__ import annotations


class AssistantStreamBuffer:
    """Tracks raw assistant text and prevents tool-planning text leaks."""

    def __init__(self) -> None:
        self.raw_text = ""
        self.visible_text = ""
        self._last_visible_snapshot = ""
        self.suppress_after_tool_use = False

    def note_tool_use(self) -> None:
        self.suppress_after_tool_use = True

    def append(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.raw_text += chunk
        if self.suppress_after_tool_use:
            return ""
        self.visible_text += chunk
        if self.visible_text == self._last_visible_snapshot:
            return ""
        self._last_visible_snapshot = self.visible_text
        return chunk

    def final_text(self, fallback: str = "") -> str:
        return fallback or self.visible_text or self.raw_text
