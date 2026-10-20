"""Sanitize provider-native tool-call markup leaked into answer text."""

from __future__ import annotations

import re

_DSML_MARKER = "｜｜DSML｜｜"
_DSML_TAG_RE = re.compile(r"[<＜]\s*(/?)\s*｜｜DSML｜｜\s*([A-Za-z_]+)")

DSML_TOOL_CALL_BLOCKED_NOTICE = (
    "模型输出包含未执行的工具调用，未能生成有效答复，请重试。"
)


class DSMLStreamFilter:
    """Hold incomplete tag prefixes and discard tool payloads before emitting text."""

    def __init__(self) -> None:
        self.pending = ""
        self.blocks: list[str] = []
        self.had_markup = False

    @staticmethod
    def _candidate(text: str) -> bool:
        rest = text[1:].lstrip()
        if rest.startswith("/"):
            rest = rest[1:].lstrip()
        return _DSML_MARKER.startswith(rest) or rest.startswith(_DSML_MARKER)

    def append(self, chunk: str) -> str:
        self.pending += chunk
        visible: list[str] = []
        while self.pending:
            opening = re.search(r"[<＜]", self.pending)
            index = opening.start() if opening else len(self.pending)
            if not self.blocks:
                visible.append(self.pending[:index])
            self.pending = self.pending[index:]
            if not self.pending:
                break
            if not self._candidate(self.pending):
                if not self.blocks:
                    visible.append(self.pending[0])
                self.pending = self.pending[1:]
                continue
            end = re.search(r"[>＞]", self.pending)
            if end is None:
                break
            tag = self.pending[:end.end()]
            self.pending = self.pending[end.end():]
            self.had_markup = True
            match = _DSML_TAG_RE.match(tag)
            if match:
                closing, kind = match.groups()
                if closing and kind in self.blocks:
                    index = len(self.blocks) - 1 - self.blocks[::-1].index(kind)
                    del self.blocks[index:]
                elif not closing and kind in {"calls", "invoke", "parameter"}:
                    self.blocks.append(kind)
        return "".join(visible)

    def flush(self) -> str:
        tail, self.pending = self.pending, ""
        if self.blocks or ("｜" in tail and self._candidate(tail)):
            self.had_markup = True
            return ""
        return tail


def strip_dsml_tool_call_markup(text: str) -> tuple[str, bool]:
    """Remove DSML tool-call markup; returns (cleaned_text, changed)."""
    if not text:
        return text, False
    stream = DSMLStreamFilter()
    cleaned = stream.append(text) + stream.flush()
    if stream.had_markup:
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, cleaned != text
