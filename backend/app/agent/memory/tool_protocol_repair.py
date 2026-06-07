"""Repair Anthropic tool_use/tool_result protocol pairs in LLM history."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Literal, Set

RepairStrategy = Literal["conservative", "api_safe"]

SYNTHETIC_TOOL_RESULT_CONTENT = "[Tool result missing during session restore]"


def _content_blocks(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _tool_use_ids(message: Dict[str, Any]) -> List[str]:
    if message.get("role") != "assistant":
        return []
    return [
        block["id"]
        for block in _content_blocks(message)
        if block.get("type") == "tool_use" and isinstance(block.get("id"), str)
    ]


def _tool_result_ids(message: Dict[str, Any]) -> List[str]:
    if message.get("role") != "user":
        return []
    return [
        block["tool_use_id"]
        for block in _content_blocks(message)
        if block.get("type") == "tool_result"
        and isinstance(block.get("tool_use_id"), str)
    ]


def _copy_with_content(message: Dict[str, Any], content: Any) -> Dict[str, Any]:
    copied = deepcopy(message)
    copied["content"] = content
    return copied


def repair_tool_result_pairing(
    messages: List[Dict[str, Any]],
    *,
    strategy: RepairStrategy = "conservative",
) -> List[Dict[str, Any]]:
    """Return messages with valid adjacent assistant tool_use/user tool_result pairs.

    conservative:
        Drop orphan tool_results, duplicate tool IDs, and assistant tool_use
        blocks without matching results.

    api_safe:
        Same cleanup, but insert synthetic error tool_results for unresolved
        assistant tool_use blocks so the provider payload remains protocol-valid.
    """
    repaired: List[Dict[str, Any]] = []
    seen_tool_use_ids: Set[str] = set()
    index = 0

    while index < len(messages):
        message = messages[index]

        if message.get("role") != "assistant":
            if message.get("role") == "user" and _tool_result_ids(message):
                # A user message with tool_result blocks must immediately follow
                # an assistant tool_use message. Otherwise these are orphaned.
                non_tool_content = [
                    block
                    for block in _content_blocks(message)
                    if block.get("type") != "tool_result"
                ]
                if non_tool_content:
                    repaired.append(_copy_with_content(message, non_tool_content))
                elif not isinstance(message.get("content"), list):
                    repaired.append(deepcopy(message))
                index += 1
                continue
            repaired.append(deepcopy(message))
            index += 1
            continue

        blocks = _content_blocks(message)
        if not blocks:
            repaired.append(deepcopy(message))
            index += 1
            continue

        tool_use_blocks = []
        non_tool_blocks = []
        for block in blocks:
            if block.get("type") != "tool_use":
                non_tool_blocks.append(block)
                continue
            tool_use_id = block.get("id")
            if not isinstance(tool_use_id, str) or tool_use_id in seen_tool_use_ids:
                continue
            seen_tool_use_ids.add(tool_use_id)
            tool_use_blocks.append(block)

        if not tool_use_blocks:
            if non_tool_blocks:
                repaired.append(_copy_with_content(message, non_tool_blocks))
            index += 1
            continue

        next_message = messages[index + 1] if index + 1 < len(messages) else None
        next_is_user = isinstance(next_message, dict) and next_message.get("role") == "user"
        next_blocks = _content_blocks(next_message) if next_is_user else []
        tool_use_id_set = {block["id"] for block in tool_use_blocks}

        kept_result_blocks = []
        kept_non_tool_result_blocks = []
        seen_result_ids: Set[str] = set()
        for block in next_blocks:
            if block.get("type") != "tool_result":
                kept_non_tool_result_blocks.append(block)
                continue
            tool_result_id = block.get("tool_use_id")
            if tool_result_id not in tool_use_id_set or tool_result_id in seen_result_ids:
                continue
            seen_result_ids.add(tool_result_id)
            kept_result_blocks.append(block)

        matched_tool_use_blocks = [
            block for block in tool_use_blocks if block["id"] in seen_result_ids
        ]
        missing_tool_use_blocks = [
            block for block in tool_use_blocks if block["id"] not in seen_result_ids
        ]

        if strategy == "api_safe":
            synthetic_blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": SYNTHETIC_TOOL_RESULT_CONTENT,
                    "is_error": True,
                }
                for block in missing_tool_use_blocks
            ]
            matched_tool_use_blocks = tool_use_blocks
            kept_result_blocks = [*synthetic_blocks, *kept_result_blocks]

        assistant_content = [*non_tool_blocks, *matched_tool_use_blocks]
        if assistant_content:
            repaired.append(_copy_with_content(message, assistant_content))

        if matched_tool_use_blocks and (kept_result_blocks or kept_non_tool_result_blocks):
            if next_is_user:
                repaired.append(
                    _copy_with_content(
                        next_message,
                        [*kept_result_blocks, *kept_non_tool_result_blocks],
                    )
                )
                index += 2
                continue
            repaired.append({
                "role": "user",
                "content": kept_result_blocks,
            })

        index += 1

    return repaired
