"""Assistant stream buffering and visibility rules."""

from __future__ import annotations

from app.agent.markup_sanitizer import DSMLStreamFilter, strip_dsml_tool_call_markup


class AssistantStreamBuffer:
    """Tracks raw assistant text and prevents tool-planning text leaks."""

    def __init__(self) -> None:
        self.raw_text = ""
        self.visible_text = ""
        self._last_visible_snapshot = ""
        self.suppress_after_tool_use = False
        self._markup_filter = DSMLStreamFilter()

    def note_tool_use(self) -> None:
        self.suppress_after_tool_use = True

    def append(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.raw_text += chunk
        if self.suppress_after_tool_use:
            return ""
        return self._append_visible(self._markup_filter.append(chunk))

    def flush(self) -> str:
        if self.suppress_after_tool_use:
            return ""
        return self._append_visible(self._markup_filter.flush())

    def _append_visible(self, text: str) -> str:
        if not text:
            return ""
        self.visible_text += text
        if self.visible_text == self._last_visible_snapshot:
            return ""
        self._last_visible_snapshot = self.visible_text
        return text

    def final_text(self, fallback: str = "") -> str:
        return strip_dsml_tool_call_markup(fallback or self.raw_text)[0]
