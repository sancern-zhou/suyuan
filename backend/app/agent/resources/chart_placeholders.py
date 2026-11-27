"""Resolve published file references to session-scoped chart resource IDs."""
from __future__ import annotations

import re

import structlog

from app.agent.resources.resource_service import SessionResourceService, normalize_chart_path

logger = structlog.get_logger(__name__)

CHART_PREFIX = "[[chart:"
CHART_UNAVAILABLE = "【图表不可用】"
RESOURCE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_MAX_MARKER_LENGTH = 2048
_QUOTE_PREFIX = r"(?: {0,3}>[ \t]?)*"
_FENCE = re.compile(rf"(?m)^(?P<quote>{_QUOTE_PREFIX}) {{0,3}}(?P<delimiter>`{{3,}}|~{{3,}})[^\n]*(?:\n|$)")
_QUOTE_LINE = re.compile(rf"^{_QUOTE_PREFIX}")
_TOKEN = re.compile(r"`+|\\\\|\\\[|\[\[chart:([^\r\n]*?)(?:\]\]|(?=\r?$))", re.M)


def _fence_end(text: str, fence: re.Match) -> int:
    delimiter = fence["delimiter"]
    quote_depth = fence["quote"].count(">")
    close = re.compile(r" {0,3}" + delimiter[0] + r"{%d,}[ \t]*\r?$" % len(delimiter))
    position = fence.end()
    while position < len(text):
        end = text.find("\n", position)
        if end < 0:
            end = len(text)
        line = text[position:end]
        prefix = _QUOTE_LINE.match(line)[0]
        if prefix.count(">") < quote_depth:
            return position
        position = end + 1
        if prefix.count(">") == quote_depth and close.fullmatch(line[len(prefix):]):
            break
    return position


def _chart_markers(text: str):
    """Yield markers outside escaped text, fenced code and matched code spans."""
    if CHART_PREFIX not in text:
        return
    position = 0
    fence = _FENCE.search(text)
    while position < len(text):
        token = _TOKEN.search(text, position)
        if fence and (not token or fence.start() <= token.start()):
            position = _fence_end(text, fence)
            fence = _FENCE.search(text, position) if position < len(text) else None
            continue
        if not token:
            break
        position = token.end()
        if token[0].startswith("`"):
            close = re.compile(r"(?<!`)" + token[0] + r"(?!`)").search(
                text, position, fence.start() if fence else len(text)
            )
            if close:
                position = close.end()
        elif token[1] is not None:
            line_start = text.rfind("\n", 0, token.start()) + 1
            prefix = text[line_start:token.start()]
            quote = _QUOTE_LINE.match(prefix)[0]
            indent = prefix[len(quote):]
            if not indent.strip() and (len(indent) >= 4 or "\t" in indent):
                continue
            value = token[1] if token[0].endswith("]]") and len(token[0]) <= _MAX_MARKER_LENGTH else ""
            yield token.start(), token.end(), value


def collect_placeholder_ids(text: str) -> set[str]:
    return {value for _, _, value in _chart_markers(text or "") if RESOURCE_ID_PATTERN.fullmatch(value)}


def _rewrite(text: str, markers, replacements: dict[str, str]) -> str:
    parts = []
    position = 0
    for start, end, value in markers:
        parts.append(text[position:start])
        resource_id = replacements.get(value)
        parts.append(f"{CHART_PREFIX}{resource_id}]]" if resource_id else CHART_UNAVAILABLE)
        position = end
    parts.append(text[position:])
    return "".join(parts)


def redact_chart_paths(text: str) -> str:
    """Keep settled resource markers, redact unpublished path markers in display text."""
    markers = list(_chart_markers(text or ""))
    if not markers:
        return text
    return _rewrite(text, markers, {
        value: value for _, _, value in markers if RESOURCE_ID_PATTERN.fullmatch(value)
    })


async def normalize_chart_placeholders(
    text: str,
    session_id: str | None,
    service: SessionResourceService | None = None,
) -> str:
    if not text or CHART_PREFIX not in text:
        return text
    markers = list(_chart_markers(text))
    if not markers:
        return text
    values = {value for _, _, value in markers if value}
    path_keys = {
        value: key for value in values
        if not RESOURCE_ID_PATTERN.fullmatch(value) and (key := normalize_chart_path(value))
    }
    replacements = {}
    try:
        if session_id and path_keys:
            catalog = service or SessionResourceService.database()
            matches = await catalog.find_inline_charts_by_paths(session_id, path_keys)
            for value, key in path_keys.items():
                records = matches.get(key, [])
                if len(records) == 1:
                    replacements[value] = records[0].resource_id
    except Exception:
        logger.exception("chart_reference_lookup_failed", session_id=session_id)
    if values - replacements.keys() or any(not value for _, _, value in markers):
        logger.info("chart_reference_unresolved", session_id=session_id,
                    missing=len(values - replacements.keys()), malformed=sum(not value for _, _, value in markers))
    return _rewrite(text, markers, replacements)


class ChartDraftFilter:
    """Hide in-flight chart markers until the accepted terminal answer replaces the draft.

    The original planner text is retained for final parsing, including literal code.
    A chart reference may span arbitrary chunks. Once its prefix is recognized, only
    its closing delimiter or newline is tracked, so long invalid input stays bounded.
    """

    def __init__(self) -> None:
        self._prefix = ""
        self._inside = False
        self._close_pending = False

    def append(self, chunk: str) -> str:
        output = []
        for char in chunk:
            if self._inside:
                if char in "\r\n" or (char == "]" and self._close_pending):
                    self._inside = False
                    self._close_pending = False
                    if char in "\r\n":
                        output.append(char)
                else:
                    self._close_pending = char == "]"
                continue
            self._prefix += char
            while self._prefix and not CHART_PREFIX.startswith(self._prefix):
                output.append(self._prefix[0])
                self._prefix = self._prefix[1:]
            if self._prefix == CHART_PREFIX:
                output.append(CHART_UNAVAILABLE)
                self._prefix = ""
                self._inside = True
        return "".join(output)

    def flush(self) -> str:
        prefix, self._prefix = self._prefix, ""
        self._inside = self._close_pending = False
        return prefix
