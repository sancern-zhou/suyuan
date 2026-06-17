from __future__ import annotations

import html
import re
from typing import Literal


DEFAULT_DIAGRAM_DRAWIO_FONT_FAMILY = "FZXiaoBiaoSong-B05S"
DEFAULT_DIAGRAM_SVG_FONT_FAMILY = (
    "FZXiaoBiaoSong-B05S, Noto Sans CJK SC, Droid Sans Fallback, Arial, sans-serif"
)

RichTextRole = Literal["text", "sub", "sup"]
RichTextToken = tuple[RichTextRole, str]

_SCRIPT_BLOCK_PATTERN = re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_BLOCK_PATTERN = re.compile(r"<\s*style\b[^>]*>.*?<\s*/\s*style\s*>", re.IGNORECASE | re.DOTALL)
_ALLOWED_TAG_PATTERN = re.compile(r"<\s*(/?)\s*(sub|sup)\s*>", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
_EVENT_HANDLER_PATTERN = re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE)
_DANGEROUS_TEXT_TOKENS = (
    "javascript:",
    "data:text/html",
    "onclick",
    "onerror",
    "onload",
)

_SUBSCRIPT_TRANSLATION = str.maketrans({
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
    "₊": "+",
    "₋": "-",
})
_SUPERSCRIPT_TRANSLATION = str.maketrans({
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
})

_CHEMICAL_TOKEN_PATTERN = re.compile(
    r"(?P<unit>(?:μg|ug)/m3|(?:km|m)[23])"
    r"|(?P<pm>PM\s*(?:2[._]5|10))"
    r"|(?P<ion>(?:SO|NO|PO|NH)\s*\d+[+-]|(?:Mg|Ca|Al|Li|Na|K|F|Cl)\s*\d*[+-])"
    r"|(?P<n2o>N\s*2\s*O)"
    r"|(?P<oxide>(?:SO|NO|CO|O|CH)\s*\d+)",
    re.IGNORECASE,
)


def diagram_label_html(value: str) -> str:
    """Return safe Draw.io HTML label content with sub/sup markup."""
    return "".join(_token_to_html(role, text) for role, text in diagram_label_tokens(value))


def diagram_label_plain_text(value: str) -> str:
    """Return a readable plain-text version of a diagram label."""
    return "".join(text for _, text in diagram_label_tokens(value))


def diagram_label_tokens(value: str) -> list[RichTextToken]:
    text = _strip_blocked_content(str(value or ""))[:1000]
    tokens: list[RichTextToken] = []
    role: RichTextRole = "text"
    offset = 0
    for match in _ALLOWED_TAG_PATTERN.finditer(text):
        if match.start() > offset:
            tokens.extend(_tokens_from_plain_text(text[offset:match.start()], role))
        closing = bool(match.group(1))
        tag = match.group(2).lower()
        if closing:
            role = "text"
        else:
            role = "sub" if tag == "sub" else "sup"
        offset = match.end()
    if offset < len(text):
        tokens.extend(_tokens_from_plain_text(text[offset:], role))
    return _merge_tokens(tokens)


def _tokens_from_plain_text(value: str, forced_role: RichTextRole) -> list[RichTextToken]:
    text = _clean_text_chunk(value)
    if not text:
        return []
    if forced_role != "text":
        return [(forced_role, text.translate(_SUBSCRIPT_TRANSLATION).translate(_SUPERSCRIPT_TRANSLATION))]

    normalized = text.translate(_SUBSCRIPT_TRANSLATION).translate(_SUPERSCRIPT_TRANSLATION)
    tokens: list[RichTextToken] = []
    offset = 0
    for match in _CHEMICAL_TOKEN_PATTERN.finditer(normalized):
        if match.start() > offset:
            tokens.append(("text", normalized[offset:match.start()]))
        tokens.extend(_tokens_for_match(match))
        offset = match.end()
    if offset < len(normalized):
        tokens.append(("text", normalized[offset:]))
    return tokens


def _tokens_for_match(match: re.Match[str]) -> list[RichTextToken]:
    value = re.sub(r"\s+", "", match.group(0))
    if match.group("unit"):
        if value.endswith(("2", "3")):
            return [("text", value[:-1]), ("sup", value[-1])]
        return [("text", value)]
    if match.group("pm"):
        suffix = value[2:].replace("_", ".")
        return [("text", "PM"), ("sub", suffix)]
    if match.group("n2o"):
        return [("text", "N"), ("sub", "2"), ("text", "O")]
    if match.group("ion"):
        charge = value[-1]
        body = value[:-1]
        letters = re.match(r"[A-Za-zμ]+", body)
        if letters:
            base = letters.group(0)
            suffix = body[len(base):]
            result: list[RichTextToken] = [("text", base)]
            if suffix:
                result.append(("sub", suffix))
            result.append(("sup", charge))
            return result
        return [("text", value)]
    if match.group("oxide"):
        letters = re.match(r"[A-Za-zμ]+", value)
        if letters:
            base = letters.group(0)
            suffix = value[len(base):]
            return [("text", base), ("sub", suffix)]
    return [("text", value)]


def _token_to_html(role: RichTextRole, text: str) -> str:
    escaped = html.escape(text, quote=False)
    if role == "sub":
        return f"<sub>{escaped}</sub>"
    if role == "sup":
        return f"<sup>{escaped}</sup>"
    return escaped


def _strip_blocked_content(value: str) -> str:
    text = _SCRIPT_BLOCK_PATTERN.sub("", value)
    text = _STYLE_BLOCK_PATTERN.sub("", text)
    text = _EVENT_HANDLER_PATTERN.sub("", text)
    for token in _DANGEROUS_TEXT_TOKENS:
        text = re.sub(re.escape(token), "", text, flags=re.IGNORECASE)
    return text


def _clean_text_chunk(value: str) -> str:
    return _HTML_TAG_PATTERN.sub("", value)


def _merge_tokens(tokens: list[RichTextToken]) -> list[RichTextToken]:
    merged: list[RichTextToken] = []
    for role, text in tokens:
        if not text:
            continue
        if merged and merged[-1][0] == role:
            merged[-1] = (role, merged[-1][1] + text)
        else:
            merged.append((role, text))
    return merged


__all__ = [
    "DEFAULT_DIAGRAM_DRAWIO_FONT_FAMILY",
    "DEFAULT_DIAGRAM_SVG_FONT_FAMILY",
    "RichTextToken",
    "diagram_label_html",
    "diagram_label_plain_text",
    "diagram_label_tokens",
]
