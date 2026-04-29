"""Context diagnostics for prompt assembly.

This module is intentionally read-only: it reports context composition but does
not prune, compact, or mutate messages. Pruning policies belong in the next
stage.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ...utils.token_budget import token_budget_manager

logger = structlog.get_logger()


class ContextDiagnostics:
    """Build compact diagnostics for context and tool-schema size."""

    def __init__(self, top_n: int = 8) -> None:
        self.top_n = top_n

    def build_report(
        self,
        *,
        mode: str,
        iteration: int,
        context_tokens: Dict[str, Any],
        tool_schemas: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Return a structured size report for the current planner call."""
        schema_items = self._analyze_tool_schemas(tool_schemas)
        message_items = self._analyze_messages(conversation_history or [])
        tool_result_items = self._analyze_tool_results(conversation_history or [])

        tool_schema_chars = sum(item["chars"] for item in schema_items)
        tool_schema_tokens_est = int(tool_schema_chars / 1.5)
        total_without_tools = context_tokens.get("total") or 0

        return {
            "mode": mode,
            "iteration": iteration,
            "totals": {
                "system_tokens": context_tokens.get("system"),
                "user_tokens": context_tokens.get("user"),
                "history_tokens": context_tokens.get("history"),
                "tool_schema_chars": tool_schema_chars,
                "tool_schema_tokens_est": tool_schema_tokens_est,
                "total_without_tools": total_without_tools,
                "total_with_tools_est": total_without_tools + tool_schema_tokens_est,
                "tool_count": len(tool_schemas),
                "message_count": len(conversation_history or []),
                "tool_result_count": len(tool_result_items),
            },
            "top_tool_schemas": schema_items[: self.top_n],
            "top_history_messages": message_items[: self.top_n],
            "top_tool_results": tool_result_items[: self.top_n],
        }

    def log_report(
        self,
        *,
        mode: str,
        iteration: int,
        context_tokens: Dict[str, Any],
        tool_schemas: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Build and emit diagnostics as a single structured log entry."""
        report = self.build_report(
            mode=mode,
            iteration=iteration,
            context_tokens=context_tokens,
            tool_schemas=tool_schemas,
            conversation_history=conversation_history,
        )
        logger.info("context_diagnostics", **report)
        return report

    def _analyze_tool_schemas(self, tool_schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for schema in tool_schemas:
            serialized = self._safe_json(schema)
            params = schema.get("parameters") if isinstance(schema, dict) else None
            properties = params.get("properties", {}) if isinstance(params, dict) else {}
            items.append({
                "name": schema.get("name", "<unknown>") if isinstance(schema, dict) else "<unknown>",
                "chars": len(serialized),
                "tokens_est": int(len(serialized) / 1.5),
                "description_chars": len(schema.get("description") or "") if isinstance(schema, dict) else 0,
                "property_count": len(properties) if isinstance(properties, dict) else 0,
            })
        return sorted(items, key=lambda item: item["chars"], reverse=True)

    def _analyze_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for index, message in enumerate(messages, start=1):
            serialized = self._safe_json(message)
            content = message.get("content")
            block_types = self._content_block_types(content)
            tool_names = self._tool_call_names(content)
            tool_result_count = sum(1 for t in block_types if t == "tool_result")
            items.append({
                "index": index,
                "role": message.get("role", "<unknown>"),
                "chars": len(serialized),
                "tokens": token_budget_manager.count_tokens(serialized),
                "content_kind": "blocks" if isinstance(content, list) else type(content).__name__,
                "block_types": block_types,
                "tool_names": tool_names,
                "tool_result_count": tool_result_count,
            })
        return sorted(items, key=lambda item: item["chars"], reverse=True)

    def _analyze_tool_results(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for message_index, message in enumerate(messages, start=1):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block_index, block in enumerate(content):
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                payload = block.get("content")
                serialized = self._safe_json(payload)
                parsed_payload = self._parse_payload(payload)
                items.append({
                    "message_index": message_index,
                    "block_index": block_index,
                    "tool_use_id": block.get("tool_use_id") or block.get("id"),
                    "chars": len(serialized),
                    "tokens": token_budget_manager.count_tokens(serialized),
                    "payload_kind": type(payload).__name__,
                    "status": self._find_first_key(parsed_payload, ["status"]),
                    "success": self._find_first_key(parsed_payload, ["success"]),
                    "tool_name": self._find_first_key(parsed_payload, ["tool_name"]),
                    "has_data_id": self._contains_key(parsed_payload, {"data_id", "data_ids"}),
                    "has_visual_id": self._contains_key(parsed_payload, {"visual_id", "visual_ids"}),
                    "summary_chars": len(str(self._find_first_key(parsed_payload, ["summary"]) or "")),
                    "top_level_keys": self._top_level_keys(parsed_payload),
                })
        return sorted(items, key=lambda item: item["chars"], reverse=True)

    def _safe_json(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)

    def _parse_payload(self, payload: Any) -> Any:
        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return payload
            try:
                return json.loads(stripped)
            except Exception:
                return payload
        if isinstance(payload, list):
            text_parts = []
            for item in payload:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            if text_parts:
                joined = "\n".join(text_parts).strip()
                try:
                    return json.loads(joined)
                except Exception:
                    return joined
        return payload

    def _content_block_types(self, content: Any) -> List[str]:
        if not isinstance(content, list):
            return []
        block_types = []
        for block in content:
            if isinstance(block, dict):
                block_types.append(str(block.get("type", "<unknown>")))
        return block_types

    def _tool_call_names(self, content: Any) -> List[str]:
        if not isinstance(content, list):
            return []
        names = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name")
                if isinstance(name, str):
                    names.append(name)
        return names

    def _find_first_key(self, value: Any, keys: List[str]) -> Any:
        if isinstance(value, dict):
            for key in keys:
                if key in value:
                    return value[key]
            for child in value.values():
                found = self._find_first_key(child, keys)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._find_first_key(child, keys)
                if found is not None:
                    return found
        return None

    def _contains_key(self, value: Any, keys: set[str]) -> bool:
        return self._find_first_key(value, keys) is not None

    def _top_level_keys(self, value: Any) -> List[str]:
        if isinstance(value, dict):
            return list(value.keys())[:12]
        return []
