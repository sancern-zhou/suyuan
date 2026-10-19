"""Sanitize provider-native tool-call markup leaked into answer text."""

from __future__ import annotations

import re

_DSML_INVOKE_BLOCK_RE = re.compile(
    r"[<＜]｜｜DSML｜｜ invoke\b.*?[<＜]\s*/\s*｜｜DSML｜｜ invoke\s*[>＞]",
    re.DOTALL,
)
_DSML_TAG_RE = re.compile(
    r"[<＜]\s*/\s*｜｜DSML｜｜[^>＞]*[>＞]|[<＜]｜｜DSML｜｜[^>＞]*[>＞]"
)

DSML_TOOL_CALL_BLOCKED_NOTICE = (
    "交付阶段检测到模型试图以文本形式调用工具，已按流程拦截；"
    "前序取数与计算结果已保存，可查看文件结果或重新交办。"
)


def strip_dsml_tool_call_markup(text: str) -> tuple[str, bool]:
    """Remove DSML tool-call markup; returns (cleaned_text, changed)."""
    if not text or "DSML" not in text:
        return text, False
    cleaned = _DSML_INVOKE_BLOCK_RE.sub("", text)
    cleaned = _DSML_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, cleaned != text
