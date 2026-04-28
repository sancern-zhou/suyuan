"""Repair strict provider tool_use/tool_result message pairing."""

from __future__ import annotations

import json
from typing import Any, Dict, List


class TranscriptRepairer:
    """Best-effort repair for Anthropic-style message dicts."""

    def repair(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not messages:
            return messages

        repaired: List[Dict[str, Any]] = []
        pending_tool_ids: list[str] = []
        seen_result_ids: set[str] = set()

        for message in messages:
            role = message.get("role")
            content = message.get("content")
            content_types = self._content_types(content)

            if role == "assistant" and "tool_use" in content_types:
                if pending_tool_ids:
                    repaired.extend(self._missing_results(pending_tool_ids, seen_result_ids))
                    pending_tool_ids = []
                repaired.append(message)
                pending_tool_ids = self._tool_use_ids(content)
                continue

            if role == "user" and "tool_result" in content_types:
                result_blocks = []
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tool_use_id = block.get("tool_use_id")
                    if not tool_use_id or tool_use_id in seen_result_ids:
                        continue
                    if pending_tool_ids and tool_use_id not in pending_tool_ids:
                        continue
                    seen_result_ids.add(tool_use_id)
                    result_blocks.append(block)
                if result_blocks:
                    repaired.append({"role": "user", "content": result_blocks})
                    pending_tool_ids = [tid for tid in pending_tool_ids if tid not in seen_result_ids]
                continue

            if pending_tool_ids:
                repaired.extend(self._missing_results(pending_tool_ids, seen_result_ids))
                pending_tool_ids = []
            repaired.append(message)

        if pending_tool_ids:
            repaired.extend(self._missing_results(pending_tool_ids, seen_result_ids))

        return repaired

    def _content_types(self, content: Any) -> set[str]:
        if not isinstance(content, list):
            return set()
        return {block.get("type") for block in content if isinstance(block, dict)}

    def _tool_use_ids(self, content: Any) -> list[str]:
        if not isinstance(content, list):
            return []
        ids = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                ids.append(block["id"])
        return ids

    def _missing_results(self, tool_ids: list[str], seen_result_ids: set[str]) -> list[Dict[str, Any]]:
        blocks = []
        for tool_id in tool_ids:
            if tool_id in seen_result_ids:
                continue
            seen_result_ids.add(tool_id)
            blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "is_error": True,
                "content": json.dumps({
                    "success": False,
                    "error": "Missing tool result repaired before model call",
                }, ensure_ascii=False),
            })
        if not blocks:
            return []
        return [{"role": "user", "content": blocks}]
