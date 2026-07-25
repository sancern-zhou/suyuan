"""
Session memory implementation (ASCII only).

This module stores intermediate artefacts produced during an agent run.
It supports LLM driven compression, filesystem persistence, and optional
registration in the structured Data Registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import structlog

from app.schemas.common import DataQualityReport, FieldStats, ValidationIssue, ValidationSeverity
from app.services.data_registry import data_registry
from app.agent.memory.tool_protocol_repair import repair_tool_result_pairing

logger = structlog.get_logger()


_llm_service = None
MAX_TOOL_RESULT_RECORDS = 24
MAX_TOOL_RESULT_STRING_CHARS = 8_000
MAX_TOOL_RESULT_JSON_CHARS = 200_000  # 支持完整的21城市统计对比结果
MAX_RESTORED_CONTENT_PREVIEW_CHARS = 2_000

CONTENT_PREVIEW_TOOL_NAMES = {
    "read_file",
    "parse_pdf",
    "read_docx",
    "read_pptx",
    "knowledge_document_reader",
    "web_fetch",
}


def _todo_status_counts(items: Any) -> Dict[str, int]:
    if not isinstance(items, list):
        return {
            "total_count": 0,
            "completed_count": 0,
            "in_progress_count": 0,
            "pending_count": 0,
        }

    counts = {
        "total_count": len(items),
        "completed_count": 0,
        "in_progress_count": 0,
        "pending_count": 0,
    }
    for item in items:
        status = item.get("status") if isinstance(item, dict) else None
        if status == "completed":
            counts["completed_count"] += 1
        elif status == "in_progress":
            counts["in_progress_count"] += 1
        elif status == "pending":
            counts["pending_count"] += 1
    return counts


def _compact_todo_items(items: Any, max_items: int = 8) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    compacted: List[Dict[str, Any]] = []
    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue
        compacted.append({
            "content": _truncate_string(str(item.get("content", "")), 180),
            "status": item.get("status"),
        })
    if len(items) > max_items:
        compacted.append({
            "_truncated": True,
            "original_count": len(items),
            "sampled_count": len(compacted),
        })
    return compacted


def _is_todowrite_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata")
    return isinstance(metadata, dict) and metadata.get("generator") == "TodoWrite"


def _compact_todowrite_result_for_history(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    active_items = data.get("active_items") if isinstance(data, dict) else []
    submitted_items = data.get("new_items") or data.get("items")

    counts = {
        "total_count": result.get("total_count"),
        "completed_count": result.get("completed_count"),
        "in_progress_count": result.get("in_progress_count"),
        "pending_count": result.get("pending_count"),
    }
    if not all(isinstance(value, int) for value in counts.values()):
        counts = _todo_status_counts(submitted_items)

    all_completed = bool(result.get("all_completed") or data.get("all_completed"))
    no_op = bool(result.get("no_op") or data.get("no_op"))
    changed = bool(data.get("changed", not no_op))

    active_summary = _compact_todo_items(active_items)
    summary = result.get("summary")
    if not summary:
        if all_completed:
            summary = "Legacy task list completed; active task list cleared."
        elif no_op:
            summary = "Legacy task list unchanged; continue business work."
        else:
            summary = "Legacy task list updated."
    else:
        summary = str(summary).replace("TodoWrite", "legacy task list")

    return {
        "status": result.get("status", "success"),
        "success": bool(result.get("success", True)),
        "tool_name": "LegacyTaskState",
        "housekeeping": True,
        "no_op": no_op,
        "all_completed": all_completed,
        "changed": changed,
        **counts,
        "active_items": active_summary,
        "summary": summary,
        "metadata": {
            "generator": "legacy_task_state",
            "history_compacted": True,
            "omitted_fields": ["rendered", "items", "old_items", "new_items"],
        },
    }


def _prepare_tool_input_for_history(tool_name: str, tool_input: Any) -> Any:
    """Return a compact assistant tool_use input for LLM-facing history.

    Current-turn draw.io create history intentionally preserves XML. Edit calls
    receive current_xml from runtime state, so that injected XML is never useful
    LLM-facing context and should not be echoed back into history.
    """
    if (
        tool_name == "create_drawio_board"
        and isinstance(tool_input, dict)
        and str(tool_input.get("operation") or "").strip().lower() == "edit"
    ):
        return _compact_drawio_tool_input_for_history(tool_input)
    return tool_input


def _compact_drawio_tool_input_for_history(value: Any) -> Any:
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        compacted_items = []
        for item in value:
            compacted = _compact_drawio_tool_input_for_history(item)
            if compacted != {}:
                compacted_items.append(compacted)
        return compacted_items

    if not isinstance(value, dict):
        return value

    compacted: Dict[str, Any] = {}
    for key, item in value.items():
        if key in {"xml", "current_xml", "currentXml", "drawio_xml"}:
            continue
        compacted_value = _compact_drawio_tool_input_for_history(item)
        if compacted_value == {}:
            continue
        compacted[key] = compacted_value
    return compacted


def _compact_drawio_payload_for_history(value: Any) -> Any:
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return [_compact_drawio_payload_for_history(item) for item in value]

    if not isinstance(value, dict):
        return value

    compacted: Dict[str, Any] = {}
    for key, item in value.items():
        if key in {"xml", "current_xml", "currentXml", "drawio_xml"} and isinstance(item, str):
            compacted[f"{key}_omitted"] = True
            compacted[f"{key}_length"] = len(item)
            continue
        compacted[key] = _compact_drawio_payload_for_history(item)
    return compacted


def _is_drawio_board_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata")
    data = result.get("data")
    return (
        isinstance(metadata, dict)
        and metadata.get("generator") == "create_drawio_board"
    ) or (
        isinstance(data, dict)
        and data.get("artifact_kind") == "drawio_board"
    )


def _compact_drawio_result_for_history(result: Dict[str, Any]) -> Dict[str, Any]:
    compacted = _compact_drawio_payload_for_history(result)
    if not isinstance(compacted, dict):
        return compacted

    data = compacted.get("data") if isinstance(compacted.get("data"), dict) else {}
    title = data.get("title") or result.get("summary") or "Draw.io Board"
    artifact_id = data.get("artifact_id") or data.get("board_id")
    compacted["llm_resume"] = {
        "artifact_ready": bool(compacted.get("success", True)),
        "artifact_kind": "drawio_board",
        "artifact_id": artifact_id,
        "title": title,
        "xml_omitted": True,
        "next_action": "answer_user_without_recreating_board",
        "instruction": (
            "create_drawio_board 已成功生成可编辑画板并返回给前端；"
            "不要再次调用 create_drawio_board 仅为了确认生成结果。"
        ),
    }
    return compacted


def _safe_content_preview(value: Any, max_chars: int = 500) -> str:
    """Return a bounded text preview for arbitrary persisted message content."""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)

    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _sample_sequence(items: List[Any], max_items: int = MAX_TOOL_RESULT_RECORDS) -> List[Any]:
    if len(items) <= max_items:
        return items
    head_count = max_items // 2
    tail_count = max_items - head_count
    return items[:head_count] + items[-tail_count:]


def _truncate_string(value: str, max_chars: int = MAX_TOOL_RESULT_STRING_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return f"{value[:max_chars]}\n\n...[truncated {omitted} chars]"


def _compact_tool_result_value(value: Any, *, path: str = "") -> Any:
    """Return a bounded copy suitable for LLM-facing tool_result history."""
    if isinstance(value, str):
        return _truncate_string(value)

    if isinstance(value, list):
        sampled = _sample_sequence(value)
        compacted = [
            _compact_tool_result_value(item, path=f"{path}[]")
            for item in sampled
        ]
        if len(value) > len(sampled):
            compacted.append({
                "_truncated": True,
                "original_count": len(value),
                "sampled_count": len(sampled),
                "strategy": "head_tail",
            })
        return compacted

    if isinstance(value, dict):
        compacted: Dict[str, Any] = {}
        for key, item in value.items():
            # 列表类型字段采样（data/rows/records/resultData）
            if key in {"data", "rows", "records", "resultData"} and isinstance(item, list):
                sampled = _sample_sequence(item)
                compacted[key] = [
                    _compact_tool_result_value(row, path=f"{path}.{key}[]")
                    for row in sampled
                ]
                if len(item) > len(sampled):
                    metadata = compacted.setdefault("metadata", {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                        compacted["metadata"] = metadata
                    metadata["tool_result_sampling"] = {
                        "field": key,
                        "original_count": len(item),
                        "sampled_count": len(sampled),
                        "strategy": "head_tail",
                    }
                continue

            # 字典类型字段（result/visuals）不进行键采样
            # 这些字段包含聚合统计或可视化配置，应该是"全有或全无"
            # 只在JSON序列化超过60,000字符时才触发最小化截断
            compacted[key] = _compact_tool_result_value(item, path=f"{path}.{key}")

        return compacted

    return value


def _minimal_tool_result(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "success": True,
            "summary": _safe_content_preview(value, 2_000),
            "tool_result_truncated": True,
        }

    keep_keys = {
        "success", "status", "summary", "error", "error_type", "data_id",
        "data_ids", "report_data_id", "report_data_ids", "file_path", "count", "total_count", "sample_count",
        "original_count", "metadata", "has_chart", "chart_summary",
        "source_data_ids", "source_report_data_ids",
        "refs", "context_refs", "llm_resume", "content_preview", "visual_ids",
    }
    minimal = {k: _compact_tool_result_value(v) for k, v in value.items() if k in keep_keys}
    if "summary" not in minimal:
        minimal["summary"] = _safe_content_preview(value, 2_000)
    minimal["tool_result_truncated"] = True
    minimal["truncation_reason"] = "serialized tool_result exceeded history budget"
    return minimal


def _append_unique(items: List[Dict[str, Any]], item: Dict[str, Any], key: str) -> None:
    value = item.get(key)
    if not value:
        return
    if any(existing.get(key) == value for existing in items):
        return
    items.append({k: v for k, v in item.items() if v is not None})


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def _compact_data_ref(data_id: Any, usage: str) -> Dict[str, Any]:
    return {
        "data_id": str(data_id),
        "usage": usage,
        "tool": "read_data_registry",
    }


def _explicit_refs(value: Any) -> Dict[str, Any]:
    """Return only tool-declared refs with list-of-dict buckets."""
    if not isinstance(value, dict):
        return {}
    refs: Dict[str, Any] = {}
    for key, items in value.items():
        if not isinstance(items, list):
            continue
        compacted = [item for item in items if isinstance(item, dict)]
        if compacted:
            refs[key] = compacted
    return refs


def _merge_context_refs(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for refs in (base, extra):
        if not isinstance(refs, dict):
            continue
        for key, items in refs.items():
            if not isinstance(items, list):
                continue
            bucket = merged.setdefault(key, [])
            for item in items:
                if isinstance(item, dict) and item not in bucket:
                    bucket.append(item)
    return merged


def _collect_visuals(result_dict: Dict[str, Any], data_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    visuals: List[Dict[str, Any]] = []
    for candidate in [result_dict.get("visuals"), data_payload.get("visuals")]:
        if isinstance(candidate, list):
            for visual in candidate:
                if isinstance(visual, dict):
                    _append_unique(visuals, visual, "id")
    return visuals


def _extract_context_refs(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    data_payload = _as_dict(result_dict.get("data"))
    refs: Dict[str, Any] = _merge_context_refs(
        _explicit_refs(result_dict.get("refs")),
        _explicit_refs(data_payload.get("refs")),
    )

    data_refs: List[Dict[str, Any]] = []
    for key, usage in (
        ("data_id", "primary"),
        ("report_data_id", "report"),
    ):
        value = result_dict.get(key) or data_payload.get(key)
        if value:
            _append_unique(data_refs, _compact_data_ref(value, usage), "data_id")
    for key, usage in (
        ("data_ids", "primary"),
        ("report_data_ids", "report"),
        ("source_data_ids", "source"),
    ):
        for value in _as_list(result_dict.get(key) or data_payload.get(key)):
            if value:
                _append_unique(data_refs, _compact_data_ref(value, usage), "data_id")
    if data_refs:
        refs = _merge_context_refs(refs, {"data": data_refs})

    return refs


def _llm_resume_for_restore(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    resume = result_dict.get("llm_resume")
    if not isinstance(resume, dict):
        return {}
    compacted: Dict[str, Any] = {}
    for key, value in resume.items():
        if isinstance(value, str):
            compacted[key] = _truncate_string(value, MAX_RESTORED_CONTENT_PREVIEW_CHARS)
        elif isinstance(value, (int, float, bool)) or value is None:
            compacted[key] = value
        elif isinstance(value, list):
            compacted[key] = _compact_tool_result_value(value)
        elif isinstance(value, dict):
            compacted[key] = _compact_tool_result_value(value)
        else:
            compacted[key] = str(value)
    return compacted


def _content_preview_for_restore(tool_name: str | None, result_dict: Dict[str, Any]) -> str | None:
    llm_resume = _llm_resume_for_restore(result_dict)
    resume_preview = llm_resume.get("content_preview")
    if isinstance(resume_preview, str) and resume_preview:
        return resume_preview

    if tool_name not in CONTENT_PREVIEW_TOOL_NAMES:
        return None

    data_payload = _as_dict(result_dict.get("data"))
    content = data_payload.get("content") or result_dict.get("content")
    if not isinstance(content, str) or not content:
        return None
    return _truncate_string(content, MAX_RESTORED_CONTENT_PREVIEW_CHARS)


def _prepare_tool_result_for_history(result: Dict[str, Any]) -> Dict[str, Any]:
    if _is_todowrite_result(result):
        compacted_todo = _compact_todowrite_result_for_history(result)
        logger.info(
            "todowrite_tool_result_compacted_for_history",
            no_op=compacted_todo.get("no_op"),
            all_completed=compacted_todo.get("all_completed"),
            active_count=len(compacted_todo.get("active_items", [])),
            total_count=compacted_todo.get("total_count"),
        )
        return compacted_todo

    compacted = _compact_tool_result_value(result)
    try:
        serialized = json.dumps(compacted, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.warning(
            "tool_result_json_serialize_failed",
            error=str(e),
            error_type=type(e).__name,
            result_keys=list(result.keys()) if isinstance(result, dict) else "not_dict"
        )
        return _minimal_tool_result(result)

    logger.info(
        "tool_result_compacted",
        serialized_len=len(serialized),
        max_allowed=MAX_TOOL_RESULT_JSON_CHARS,
        exceeds_threshold=len(serialized) > MAX_TOOL_RESULT_JSON_CHARS,
        compacted_keys=list(compacted.keys()) if isinstance(compacted, dict) else "not_dict"
    )

    if len(serialized) <= MAX_TOOL_RESULT_JSON_CHARS:
        return compacted

    logger.warning(
        "tool_result_exceeds_threshold",
        serialized_len=len(serialized),
        max_allowed=MAX_TOOL_RESULT_JSON_CHARS,
        will_apply_minimal=True
    )

    minimal = _minimal_tool_result(compacted)
    try:
        serialized = json.dumps(minimal, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return {
            "success": bool(result.get("success", False)) if isinstance(result, dict) else True,
            "summary": _safe_content_preview(result, 2_000),
            "tool_result_truncated": True,
        }

    if len(serialized) <= MAX_TOOL_RESULT_JSON_CHARS:
        return minimal

    minimal["summary"] = _truncate_string(str(minimal.get("summary", "")), 4_000)
    minimal["metadata"] = _safe_content_preview(minimal.get("metadata"), 4_000)
    return minimal


def _get_llm_service():
    """Lazy import for the optional LLM compression service."""
    global _llm_service
    if _llm_service is None:
        try:
            from app.services.llm_service import LLMService

            _llm_service = LLMService()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "session_memory_llm_service_unavailable",
                error=str(exc),
                message="Falling back to simple compression",
            )
            _llm_service = False
    return _llm_service if _llm_service is not False else None


@dataclass
class ConversationTurn:
    """Simple structure that stores a conversation message."""

    role: str  # "user" or "assistant"
    content: str | List[Dict[str, Any]]  # ✅ 支持 Anthropic content blocks 格式
    timestamp: str
    type: Optional[str] = None  # "user"/"thought"/"tool_use"/"tool_result"/"final"
    thought: Optional[str] = None  # LLM thought for this assistant turn
    data: Optional[Dict[str, Any]] = None  # Additional data (for tool_use/tool_result)
    tool_use_id: Optional[str] = None  # ✅ Anthropic: tool_use.id 或 tool_result.tool_use_id
    is_error: Optional[bool] = None  # ✅ Anthropic: tool_result is_error 标记


class SessionMemory:
    """
    会话记忆管理器

    核心职责：
    - 管理对话历史
    - 管理 data files
    - 提供 LLM 格式的历史消息

    缓存友好策略（参考 learn-claude-code）：
    - 只追加策略：历史消息永不删除、永不修改
    - 完整保留：所有对话历史传递给 LLM
    - 缓存优化：通过只追加保持前缀不变，实现 KV Cache 命中
    - 成本节省：避免破坏缓存可节省 80-90% 成本

    设计理念：
    - 传统"滑动窗口"会破坏缓存，导致成本反而上升
    - 依赖模型自身的上下文压缩能力和缓存折扣
    - 使用子 Agent 隔离复杂任务，保持主上下文干净
    """

    # 不再限制历史消息数量，采用只追加策略
    # MAX_HISTORY_TURNS 已移除，参考 https://github.com/anthropics/learn-claude-code
    """Layer-2 memory that persists intermediate artefacts to disk."""

    def __init__(
        self,
        session_id: str,
        base_dir: str = None,
        use_llm_compression: bool = True,
    ) -> None:
        self.session_id = session_id
        # 使用项目目录而不是系统临时目录，避免 /tmp 下产生大量空文件夹
        if base_dir is None:
            # 使用 backend_data_registry/sessions 作为会话目录
            project_root = Path(__file__).parent.parent.parent.parent  # backend 目录
            base_dir = project_root / "backend_data_registry" / "sessions"
        self.session_dir = Path(base_dir) / f"agent_session_{session_id}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.use_llm_compression = use_llm_compression
        self.compressed_iterations: List[Dict[str, Any]] = []
        self.data_files: Dict[str, str] = {}
        self.data_registry_refs: Dict[str, str] = {}
        self.conversation_history: List[ConversationTurn] = []
        self.llm_source_until_sequence: Optional[int] = None

        # ✅ 修复：初始化 data_registry 引用（溯源模式需要）
        # 使用全局单例，确保所有模式兼容
        self.data_registry = data_registry

        logger.info(
            "session_memory_initialized",
            session_id=session_id,
            directory=str(self.session_dir),
            use_llm_compression=use_llm_compression,
            has_data_registry=True,
        )

    # ------------------------------------------------------------------ #
    # Compression helpers
    # ------------------------------------------------------------------ #
    async def compress_iteration_with_llm(
        self,
        iteration: Dict[str, Any],
    ) -> str:
        """Generate a short summary using the configured LLM service."""

        llm_service = _get_llm_service()
        if not llm_service:
            return self._simple_compress(iteration)

        action = iteration.get("action", {})
        observation = iteration.get("observation", {})

        observation_data = observation.get("sampled_data")
        if observation_data is None:
            observation_data = observation.get("data")

        data_preview = ""
        if observation_data is not None:
            try:
                data_preview = json.dumps(observation_data, ensure_ascii=False)[:500]
            except TypeError:
                data_preview = str(observation_data)[:500]

        prompt = (
            "You are an expert at compressing agent execution steps while preserving CRITICAL information. "
            "Summarize the following agent step in 2-3 short sentences, but you MUST preserve:\n"
            "1. ALL data_id references - use SHORT ALIASES (e.g., 'PMF:abc12345' for 'pmf_result:v1:abc12345...')\n"
            "2. The tool name and key parameters\n"
            "3. Any notable findings, results, or errors\n"
            "4. Success/failure status\n\n"
            "ID Alias Format Rules:\n"
            "- Extract schema from data_id (before first ':')\n"
            "- Take first 8 characters of hash (after last ':')\n"
            "- Format: 'SCHEMA:abcdef12' (uppercase, compact)\n"
            "- Examples:\n"
            "  'pmf_result:v1:abc12345...' → 'PMF:abc12345'\n"
            "  'vocs_unified:v1:def6789...' → 'VOCS:def6789'\n"
            "  'obm_ofp_result:v1:xyz...' → 'OBM:xyz12345'\n\n"
            "Format: [ToolName] [Status] :: [Key info with ID alias] :: [Result summary]\n\n"
            f"Thought: {iteration.get('thought', '')}\n"
            f"Action: {action.get('tool', 'FINISH')}\n"
            f"Action Args: {action.get('args', {})}\n"
            f"Observation success: {observation.get('success', False)}\n"
            f"Observation summary: {observation.get('summary', '')}\n"
            f"Data ID: {observation.get('data_id', 'N/A')}\n"
            f"Data Ref: {observation.get('data_ref', 'N/A')}\n"
            f"Observation data preview: {data_preview}\n\n"
            "IMPORTANT: Create a short, readable ID alias for any data_id you see!"
        )

        try:
            # ✅ 使用 Anthropic Messages API（所有provider统一格式）
            if llm_service.anthropic_client is None:
                logger.warning(
                    "session_memory_anthropic_client_not_initialized",
                    provider=llm_service.provider,
                )
                return self._simple_compress(iteration)

            response = await llm_service.anthropic_client.messages.create(
                model=llm_service.model,
                max_tokens=150,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            # 提取文本内容（Anthropic格式）
            if response.content:
                # content是列表，找到第一个text block
                for block in response.content:
                    if block.type == "text":
                        return block.text.strip()

            # 如果没有text block，返回空字符串
            logger.warning(
                "session_memory_no_text_content",
                provider=llm_service.provider,
                content_blocks=len(response.content) if response.content else 0,
            )
            return ""

        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "session_memory_llm_compress_failed",
                error=str(exc),
            )
            return self._simple_compress(iteration)

    def _simple_compress(self, iteration: Dict[str, Any]) -> str:
        """Fallback summariser that relies only on local content.

        方案A优化：使用智能ID别名替代短格式ID
        - 从长格式ID生成可读别名
        - 格式：SCHEMA:hash8 (如 PMF:a406373a)
        - 保持信息完整性的同时节省token
        """

        def _create_id_alias(data_id: str) -> str:
            """创建智能ID别名"""
            if not data_id or ":" not in data_id:
                return data_id

            # 解析 schema:v1:hash 格式
            parts = data_id.split(":")
            if len(parts) >= 3:
                schema = parts[0]
                hash_part = parts[-1][:8]  # 取前8位hash
                # 转换为大写并简化schema
                if "_" in schema:
                    schema = schema.split("_")[0].upper()  # pmf_result → PMF
                else:
                    schema = schema.upper()
                return f"{schema}:{hash_part}"

            return data_id[:12]  # fallback: 取前12字符

        action = iteration.get("action", {})
        observation = iteration.get("observation", {})

        if action.get("type") == "TOOL_CALL":
            tool_name = action.get('tool', 'UNKNOWN_TOOL')
            success = observation.get('success', False)
            status = '[OK]' if success else '[FAIL]'

            # 优先保留data_id/report_data_id信息 - 使用智能别名
            data_id = (
                observation.get('data_id')
                or observation.get('data_ref')
                or observation.get('report_data_id')
            )
            if data_id:
                id_alias = _create_id_alias(data_id)
                data_id_str = f" (ID: {id_alias})"
            else:
                data_id_str = ""

            summary = f"{tool_name} {status}{data_id_str}"

            # 添加摘要
            if observation.get("summary"):
                summary += f" :: {observation['summary']}"
            elif observation.get("error"):
                summary += f" :: {observation['error']}"

            return summary

        answer = action.get("answer") or observation.get("summary")
        if answer:
            answer_text = " ".join(str(answer).split())
            return answer_text[:180] + ("..." if len(answer_text) > 180 else "")
        return "No significant observation recorded."

    def compress_iteration(self, iteration: Dict[str, Any]) -> str:
        """Compress an iteration and store it inside memory."""

        if self.use_llm_compression:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    summary = self._simple_compress(iteration)
                else:
                    summary = loop.run_until_complete(
                        self.compress_iteration_with_llm(iteration)
                    )
            except RuntimeError:
                summary = self._simple_compress(iteration)
        else:
            summary = self._simple_compress(iteration)

        self.compressed_iterations.append(
            {
                "summary": summary,
                "timestamp": iteration.get("timestamp", datetime.utcnow().isoformat()),
                "action_type": iteration.get("action", {}).get("type"),
            }
        )

        logger.debug(
            "session_memory_iteration_compressed",
            summary=summary,
            total=len(self.compressed_iterations),
        )
        return summary

    # ------------------------------------------------------------------ #
    # Data persistence and registry integration
    # ------------------------------------------------------------------ #
    def save_data_to_file(
        self,
        data: Any,
        data_id: str,
        *,
        file_format: str = "json",
        registry_schema: Optional[str] = None,
        registry_version: str = "v1",
        registry_metadata: Optional[Dict[str, Any]] = None,
        quality_report: Optional[DataQualityReport] = None,
        field_stats: Optional[Iterable[FieldStats]] = None,
    ) -> str:
        """Persist data to DataRegistry (backend_data_registry/).

        所有数据统一存储到 backend_data_registry/ 目录，不再使用会话临时目录。
        """

        if file_format != "json":
            # 非 JSON 格式保存到会话目录（用于 Markdown 报告等）
            safe_filename = data_id.replace(":", "_")
            path = self.session_dir / f"{safe_filename}.{file_format}"
            with path.open("w", encoding="utf-8") as stream:
                stream.write(str(data))
            self.data_files[data_id] = str(path)
            logger.info("session_memory_non_json_saved", data_id=data_id, path=str(path))
            return str(path)

        # JSON 数据统一保存到 DataRegistry
        quality_report_obj = self._coerce_quality_report(quality_report)
        field_stats_list = self._coerce_field_stats(field_stats)

        # 构建 metadata
        metadata = {"session_id": self.session_id}
        if registry_metadata:
            metadata.update(registry_metadata)

        # 使用 data_id 中指定的 schema，如果没有则使用传入的 registry_schema
        if registry_schema is None:
            # 从 data_id 中提取 schema (格式: "schema:v1:hash")
            parts = data_id.split(":")
            if len(parts) >= 1:
                registry_schema = parts[0]
            else:
                registry_schema = "unknown"

        # 检查数据格式
        if not isinstance(data, list):
            # 非列表数据（如单个对象）保存到会话目录
            safe_filename = data_id.replace(":", "_")
            path = self.session_dir / f"{safe_filename}.{file_format}"
            with path.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, default=str)
            self.data_files[data_id] = str(path)
            logger.info("session_memory_non_list_saved", data_id=data_id, path=str(path))
            return str(path)

        # 检查是否所有项都是字典
        if not all(isinstance(item, dict) for item in data):
            # 混合类型数据保存到会话目录
            safe_filename = data_id.replace(":", "_")
            path = self.session_dir / f"{safe_filename}.{file_format}"
            with path.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, default=str)
            self.data_files[data_id] = str(path)
            logger.info("session_memory_mixed_type_saved", data_id=data_id, path=str(path))
            return str(path)

        # 标准列表字典数据 - 保存到 DataRegistry
        try:
            # ✅ 修复：传入 data_id 参数，避免 register_dataset 重新生成 ID 导致不匹配
            entry = data_registry.register_dataset(
                schema=registry_schema,
                version=registry_version,
                records=data,  # type: ignore[arg-type]
                quality_report=quality_report_obj,
                field_stats=field_stats_list,
                metadata=metadata,
                data_id=data_id,  # ✅ 传入完整的 data_id (schema:v1:hash 格式)
            )
            registry_id = entry.data_id
            self.data_registry_refs[data_id] = registry_id
            self.data_files[data_id] = str(entry.dataset_path)

            logger.info(
                "session_memory_data_saved_to_registry",
                data_id=data_id,
                registry_id=registry_id,
                dataset_path=str(entry.dataset_path),
                record_count=len(data),
            )
            return str(entry.dataset_path)

        except Exception as exc:
            logger.error(
                "session_memory_registry_register_failed",
                data_id=data_id,
                error=str(exc),
                exc_info=True,
            )
            # 降级：保存到会话目录
            safe_filename = data_id.replace(":", "_")
            path = self.session_dir / f"{safe_filename}.{file_format}"
            with path.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, default=str)
            self.data_files[data_id] = str(path)
            return str(path)

    def get_registry_id(self, data_id: str) -> Optional[str]:
        """Return the registry identifier for a persisted dataset."""

        return self.data_registry_refs.get(data_id)

    def load_data_from_file(self, data_id: str) -> Optional[Any]:
        """Load data from disk if it exists."""

        # 【修复】添加空值检查
        if data_id is None:
            logger.warning(
                "session_memory_data_id_is_none",
                data_id=data_id,
                available_ids=list(self.data_files.keys())[:5]
            )
            return None

        file_path = self.data_files.get(data_id)
        if not file_path:
            # ✅ 增强：尝试从 DataRegistry 查找文件
            safe_filename = data_id.replace(":", "_")
            registry_path = self.data_registry.base_dir / "datasets" / f"{safe_filename}.json"

            logger.info(
                "session_memory_trying_registry_path",
                data_id=data_id,
                safe_filename=safe_filename,
                registry_path=str(registry_path),
                registry_exists=registry_path.exists()
            )

            if registry_path.exists():
                logger.info(
                    "session_memory_file_found_in_registry",
                    data_id=data_id,
                    registry_path=str(registry_path)
                )
                file_path = str(registry_path)
            else:
                # 尝试从 session_dir 查找（备用）
                logger.warning(
                    "session_memory_file_not_registered",
                    data_id=data_id,
                    available_ids=list(self.data_files.keys())[:5],  # 只显示前5个
                    registry_path=str(registry_path)
                )

                alternative_path = self.session_dir / f"{safe_filename}.json"

                if alternative_path.exists():
                    logger.info(
                        "session_memory_file_found_by_pattern",
                        data_id=data_id,
                        alternative_path=str(alternative_path)
                    )
                    file_path = str(alternative_path)
                else:
                    return None

        path = Path(file_path)
        if not path.exists():
            logger.warning("session_memory_file_missing", data_id=data_id, path=str(path))
            return None

        try:
            if path.suffix == ".json":
                # 自定义数字解析：保持整数为整数类型
                def parse_int(value_str):
                    """解析整数字符串为整数"""
                    return int(value_str)

                def parse_float(value_str):
                    """解析浮点数字符串为浮点数"""
                    return float(value_str)

                with path.open("r", encoding="utf-8") as stream:
                    return json.load(stream, parse_int=parse_int, parse_float=parse_float)

            with path.open("r", encoding="utf-8") as stream:
                return stream.read()
        except Exception as e:
            logger.error(
                "session_memory_file_load_error",
                data_id=data_id,
                path=str(path),
                error=str(e)
            )
            return None

    # ------------------------------------------------------------------ #
    # Convenience helpers
    # ------------------------------------------------------------------ #
    def update_todo(
        self,
        completed: List[str],
        pending: List[str],
        data_status: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render and persist a TODO markdown document."""

        sections = ["# Task Progress\n"]

        if completed:
            sections.append("\n## Completed\n")
            sections.extend(f"- [x] {item}\n" for item in completed)

        if pending:
            sections.append("\n## Pending\n")
            sections.extend(f"- [ ] {item}\n" for item in pending)

        if data_status:
            status_labels = {
                "completed": "[done]",
                "in_progress": "[doing]",
            }
            sections.append("\n## Data Collection Status\n")
            for name, status in data_status.items():
                label = status_labels.get(status, "[paused]")
                sections.append(f"- {label} {name}\n")

        return self.save_data_to_file(
            "".join(sections),
            "todo",
            file_format="md",
        )

    def update_agent_context(
        self,
        goal: str,
        findings: Optional[List[str]] = None,
        data_status: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render and persist an AGENT.md markdown document."""

        sections = ["# Agent Context\n", f"\n## Goal\n{goal}\n"]

        if data_status:
            status_labels = {
                "completed": "[done]",
                "in_progress": "[doing]",
            }
            sections.append("\n## Data Collection Status\n")
            for name, status in data_status.items():
                label = status_labels.get(status, "[paused]")
                sections.append(f"- {label} {name}\n")

        if findings:
            sections.append("\n## Key Findings\n")
            sections.extend(f"- {finding}\n" for finding in findings)

        return self.save_data_to_file(
            "".join(sections),
            "AGENT",
            file_format="md",
        )

    def get_compressed_summary(self) -> str:
        """Return a markdown style summary of earlier steps."""

        if not self.compressed_iterations:
            return ""

        lines = ["Earlier steps summary:\n"]
        for index, item in enumerate(self.compressed_iterations, start=1):
            lines.append(f"{index}. {item['summary']}\n")
        return "".join(lines)

    def get_file_references(self) -> Dict[str, str]:
        """Expose the mapping between data identifiers and file paths."""

        return dict(self.data_files)

    def compact_completed_drawio_turns_for_next_user_turn(self) -> None:
        """Compact completed draw.io XML before a new user turn starts.

        The active agent turn keeps full XML so the model can reason over the
        exact tool output. Once a new user message arrives, frontend
        board_context.current_xml becomes the authoritative XML source and old
        tool XML must leave ordinary conversation history.
        """
        compacted_count = 0
        for turn in self.conversation_history:
            if turn.type == "tool_use" and isinstance(turn.content, list):
                for block in turn.content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use" or block.get("name") != "create_drawio_board":
                        continue
                    tool_input = block.get("input")
                    if isinstance(tool_input, dict) and any(
                        key in tool_input for key in ("xml", "current_xml", "currentXml", "drawio_xml")
                    ):
                        block["input"] = _compact_drawio_tool_input_for_history(tool_input)
                        compacted_count += 1

            if turn.type == "tool_result" and isinstance(turn.content, list):
                for block in turn.content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    content = block.get("content")
                    if not isinstance(content, str):
                        continue
                    try:
                        payload = json.loads(content)
                    except Exception:
                        continue
                    if not _is_drawio_board_result(payload):
                        continue
                    compacted_payload = _compact_drawio_result_for_history(payload)
                    block["content"] = json.dumps(compacted_payload, ensure_ascii=False, indent=2, default=str)
                    compacted_count += 1
                    if isinstance(turn.data, dict):
                        result_data = turn.data.get("result")
                        if isinstance(result_data, dict) and _is_drawio_board_result(result_data):
                            turn.data["result"] = _compact_drawio_result_for_history(result_data)

        if compacted_count:
            logger.info(
                "drawio_history_compacted_for_next_user_turn",
                session_id=self.session_id,
                compacted_count=compacted_count,
            )

    def add_user_message(self, content: str | List[Dict[str, Any]]) -> None:
        """Record a user utterance."""
        self.compact_completed_drawio_turns_for_next_user_turn()
        self._append_conversation_turn("user", content, type="user")
        logger.debug(
            "add_user_message_called",
            session_id=self.session_id,
            content_preview=_safe_content_preview(content, 100),
            history_length=len(self.conversation_history)
        )

    def add_assistant_message(self, content: str, thought: Optional[str] = None, thinking_blocks: Optional[List[Dict[str, Any]]] = None) -> None:
        """Record an assistant response.

        Args:
            content: 助手回复文本
            thought: 思考摘要
            thinking_blocks: LLM 返回的原始 thinking content blocks（DeepSeek 等兼容 API
                           要求在后续请求中回传这些 blocks，不传则按普通字符串存储）
        """
        if thinking_blocks:
            # ✅ 使用 Anthropic content blocks 格式存储（保留 thinking blocks）
            # DeepSeek 等兼容 API 要求：assistant 消息必须原样回传 thinking blocks
            content_blocks = list(thinking_blocks) + [{"type": "text", "text": content}]

            # ✅ 调试日志：打印 thinking blocks 的内容
            logger.info(
                "add_assistant_message_with_thinking_blocks",
                session_id=self.session_id,
                thinking_blocks_count=len(thinking_blocks),
                thinking_blocks_types=[b.get("type") for b in thinking_blocks],
                thinking_blocks_preview=[str(b)[:200] for b in thinking_blocks[:2]],
                content_blocks_count=len(content_blocks),
                content_blocks_types=[b.get("type") for b in content_blocks]
            )

            self.conversation_history.append(
                ConversationTurn(
                    role="assistant",
                    content=content_blocks,
                    timestamp=datetime.utcnow().isoformat(),
                    type="final",
                    thought=thought
                )
            )
        else:
            self._append_conversation_turn("assistant", content, thought=thought, type="final")

        logger.debug(
            "add_assistant_message_called",
            session_id=self.session_id,
            content_preview=content[:100],
            history_length=len(self.conversation_history),
            has_thought=thought is not None,
            has_thinking_blocks=thinking_blocks is not None and len(thinking_blocks) > 0
        )

    # 向后兼容旧接口
    def add_assistant_response(self, content: str) -> None:
        self.add_assistant_message(content)

    def add_tool_result_message(
        self,
        tool_use_id: str,
        result: Dict[str, Any],
        is_error: bool = False
    ) -> None:
        """
        添加 Anthropic 格式的 tool_result 消息

        Args:
            tool_use_id: 关联的 tool_use.id
            result: 工具执行结果
            is_error: 是否为错误结果
        """
        history_result = _prepare_tool_result_for_history(result)
        # 序列化瘦身后的结果为 JSON 字符串，避免单条 tool_result 占满上下文
        result_json = json.dumps(history_result, ensure_ascii=False, indent=2, default=str)

        # 构建 Anthropic content block 格式
        content_block = {
            "type": "tool_result",
            "content": result_json,
            "is_error": is_error,
            "tool_use_id": tool_use_id
        }

        self.conversation_history.append(
            ConversationTurn(
                role="user",  # Anthropic: tool_result 使用 user 角色
                content=[content_block],  # 存储为 content block 列表
                timestamp=datetime.utcnow().isoformat(),
                type="tool_result",
                tool_use_id=tool_use_id,
                is_error=is_error,
                # ✅ 修复：data 字段不包含 tool_use_id，因为它已经在 ConversationTurn 属性中
                # 但需要在 data 中添加 tool_name（从 result.metadata.generator 推断）
                data={
                    "tool_use_id": tool_use_id,
                    "tool_name": result.get("metadata", {}).get("generator", "") if isinstance(result, dict) else "",
                    "is_error": is_error,
                    "result": history_result
                }
            )
        )

        logger.debug(
            "add_tool_result_message_called",
            session_id=self.session_id,
            tool_use_id=tool_use_id,
            is_error=is_error,
            history_length=len(self.conversation_history)
        )

    def add_streaming_tool_results(
        self,
        tool_executions: List[Dict[str, Any]],
        thinking_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        批量添加流式工具执行结果到对话历史（Anthropic 格式）

        当 LLM 在流式输出过程中并行调用多个工具时，所有 tool_use blocks
        属于同一个 assistant 消息，所有 tool_result blocks 属于同一个 user 消息。
        这是 Anthropic Messages API 的标准格式。

        Args:
            tool_executions: 工具执行列表，每项包含:
                {
                    "tool_name": str,
                    "tool_use_id": str,
                    "tool_input": Dict,
                    "result": Dict,
                    "is_error": bool,
                }
            thinking_blocks: LLM 返回的原始 thinking content blocks（DeepSeek 等兼容 API
                           要求在后续请求中回传这些 blocks）
        """
        if not tool_executions:
            return

        # ✅ 调试日志：检查 thinking_blocks 参数
        logger.info(
            "add_streaming_tool_results_check",
            session_id=self.session_id,
            tool_count=len(tool_executions),
            has_thinking_blocks=thinking_blocks is not None,
            thinking_blocks_count=len(thinking_blocks) if thinking_blocks else 0,
            thinking_blocks_types=[b.get("type") for b in thinking_blocks] if thinking_blocks else []
        )

        # ✅ 如果 thinking_blocks 是空列表，当作 None 处理
        # DeepSeek 可能不返回 thinking blocks，即使启用了 thinking mode
        if thinking_blocks and len(thinking_blocks) == 0:
            logger.info(
                "add_streaming_tool_results_empty_thinking",
                session_id=self.session_id,
                reason="thinking_blocks is empty list, treating as None"
            )
            thinking_blocks = None

        # 1. 构建 assistant 消息：thinking blocks + 所有 tool_use content blocks
        # ✅ DeepSeek 等兼容 API 要求：如果 LLM 返回了 thinking blocks，
        # 后续请求必须将它们原样回传，否则报 400 错误
        assistant_content_blocks = []

        # 先添加 thinking blocks（必须在 tool_use 之前，符合 Anthropic 规范）
        if thinking_blocks:
            logger.info(
                "add_streaming_tool_results_adding_thinking",
                session_id=self.session_id,
                thinking_count=len(thinking_blocks)
            )
            assistant_content_blocks.extend(thinking_blocks)

        for te in tool_executions:
            assistant_content_blocks.append({
                "type": "tool_use",
                "id": te["tool_use_id"],
                "name": te["tool_name"],
                "input": _prepare_tool_input_for_history(te["tool_name"], te["tool_input"]),
            })

        self.conversation_history.append(
            ConversationTurn(
                role="assistant",
                content=assistant_content_blocks,
                timestamp=datetime.utcnow().isoformat(),
                type="tool_use",
                tool_use_id=tool_executions[0]["tool_use_id"] if len(tool_executions) == 1 else None,
                data={"tool_use": {
                    "type": "TOOL_CALLS" if len(tool_executions) > 1 else "TOOL_CALL",
                    "tools": [{"tool": te["tool_name"], "args": te["tool_input"], "tool_call_id": te["tool_use_id"]} for te in tool_executions],
                }},
            )
        )

        # 2. 构建 user 消息：包含所有 tool_result content blocks
        user_content_blocks = []
        history_results: List[Dict[str, Any]] = []
        for te in tool_executions:
            history_result = _prepare_tool_result_for_history(te["result"])
            history_results.append(history_result)
            result_json = json.dumps(history_result, ensure_ascii=False, indent=2, default=str)
            user_content_blocks.append({
                "type": "tool_result",
                "content": result_json,
                "is_error": te.get("is_error", False),
                "tool_use_id": te["tool_use_id"],
            })

        # ✅ 修复：统一 data 字段格式，确保前端能正确读取 visuals
        # 单个工具：data={"result": {...}}
        # 多个工具：data={"results": [{...}, {...}]}
        if len(tool_executions) == 1:
            # 单个工具：使用 result 格式（与 add_tool_result_message 一致）
            te = tool_executions[0]
            data_field = {
                "tool_use_id": te["tool_use_id"],
                "tool_name": te["tool_name"],
                "is_error": te.get("is_error", False),
                "result": history_results[0]
            }
        else:
            # 多个工具：使用 results 格式
            data_field = {
                "tool_use_id": tool_executions[0]["tool_use_id"],  # 主工具ID
                "tool_name": tool_executions[0]["tool_name"],  # 主工具名称
                "is_error": any(te.get("is_error", False) for te in tool_executions),
                "results": history_results
            }

        self.conversation_history.append(
            ConversationTurn(
                role="user",
                content=user_content_blocks,
                timestamp=datetime.utcnow().isoformat(),
                type="tool_result",
                tool_use_id=tool_executions[0]["tool_use_id"] if len(tool_executions) == 1 else None,
                is_error=any(te.get("is_error", False) for te in tool_executions),
                data=data_field,
            )
        )

        logger.debug(
            "add_streaming_tool_results_called",
            session_id=self.session_id,
            tool_count=len(tool_executions),
            history_length=len(self.conversation_history),
        )

    def _display_tool_use_block(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = msg.get("data")
        if not isinstance(data, dict):
            return None

        tool_use_id = data.get("tool_use_id")
        tool_name = data.get("tool_name")
        tool_input = data.get("input")

        if tool_input is None:
            tool_use = data.get("tool_use")
            tools = tool_use.get("tools") if isinstance(tool_use, dict) else None
            if isinstance(tools, list) and tools:
                first_tool = tools[0] if isinstance(tools[0], dict) else {}
                tool_use_id = tool_use_id or first_tool.get("tool_call_id")
                tool_name = tool_name or first_tool.get("tool")
                tool_input = first_tool.get("args")

        if not tool_use_id or not tool_name:
            return None

        return {
            "type": "tool_use",
            "id": tool_use_id,
            "name": tool_name,
            "input": _prepare_tool_input_for_history(tool_name, tool_input or {}),
        }

    def _display_tool_use_id(self, msg: Dict[str, Any]) -> Optional[str]:
        block = self._display_tool_use_block(msg)
        if not block:
            return None
        return block.get("id")

    def _display_tool_result_id(self, msg: Dict[str, Any]) -> Optional[str]:
        data = msg.get("data")
        if not isinstance(data, dict):
            return None
        if "result" not in data and not isinstance(data.get("results"), list):
            return None
        tool_use_id = data.get("tool_use_id")
        return tool_use_id if isinstance(tool_use_id, str) and tool_use_id else None

    def _paired_display_tool_ids(self, messages: List[Dict[str, Any]]) -> set[str]:
        tool_use_ids = {
            tool_use_id
            for tool_use_id in (
                self._display_tool_use_id(msg)
                for msg in messages
                if msg.get("type") == "tool_use"
            )
            if tool_use_id
        }
        tool_result_ids = {
            tool_result_id
            for tool_result_id in (
                self._display_tool_result_id(msg)
                for msg in messages
                if msg.get("type") == "tool_result"
            )
            if tool_result_id
        }
        return tool_use_ids & tool_result_ids

    def _lightweight_tool_result_for_restore(
        self,
        data: Dict[str, Any],
        result: Any,
    ) -> Dict[str, Any]:
        result_dict = result if isinstance(result, dict) else {}
        tool_name = data.get("tool_name") or result_dict.get("tool_name")
        tool_use_id = data.get("tool_use_id")
        is_error = bool(data.get("is_error", False))

        lightweight: Dict[str, Any] = {
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "status": result_dict.get("status") or ("error" if is_error else "success"),
            "is_error": is_error,
        }

        summary_text = (
            result_dict.get("summary_text")
            or result_dict.get("summary")
            or result_dict.get("message")
            or result_dict.get("error")
        )
        if summary_text:
            summary_key = "summary_text" if result_dict.get("summary_text") else "summary"
            lightweight[summary_key] = _truncate_string(str(summary_text), 2_000)

        for key in ("data_id", "data_ids", "report_data_id", "report_data_ids"):
            value = result_dict.get(key) or data.get(key)
            if value:
                lightweight[key] = value

        context_refs = _extract_context_refs(result_dict)
        if context_refs:
            lightweight["context_refs"] = context_refs

        llm_resume = _llm_resume_for_restore(result_dict)
        if llm_resume:
            lightweight["llm_resume"] = llm_resume

        content_preview = _content_preview_for_restore(tool_name, result_dict)
        if content_preview:
            lightweight["content_preview"] = content_preview

        visual_ids = []
        data_payload = _as_dict(result_dict.get("data"))
        visuals = _collect_visuals(result_dict, data_payload)
        if visuals:
            visual_ids = [
                visual.get("id")
                for visual in visuals
                if isinstance(visual, dict) and visual.get("id")
            ]
        if visual_ids:
            lightweight["visual_ids"] = visual_ids

        has_reference = any(
            lightweight.get(key)
            for key in ("data_id", "data_ids", "report_data_id", "report_data_ids")
        )
        if "summary" not in lightweight and "summary_text" not in lightweight:
            if lightweight.get("data_id"):
                lightweight["summary"] = (
                    f"结果已保存为 data_id={lightweight['data_id']}，可用 read_data_registry 读取。"
                )
            elif lightweight.get("data_ids"):
                lightweight["summary"] = (
                    f"结果已保存为 data_ids={lightweight['data_ids']}，可用 read_data_registry 读取。"
                )
            elif result:
                lightweight["summary"] = _safe_content_preview(result, 800)
            else:
                lightweight["summary"] = "工具结果已恢复为轻量摘要；原始结果未包含可提取摘要。"

        keep_keys = {
            "status", "summary", "summary_text", "message", "error",
            "data_id", "data_ids", "report_data_id", "report_data_ids",
            "tool_name", "tool_use_id", "is_error", "visuals",
            "context_refs", "content_preview", "llm_resume",
        }
        result_keys = set(result_dict.keys()) if isinstance(result, dict) else set()
        if result_keys - keep_keys or visual_ids or not has_reference:
            lightweight["result_truncated"] = True

        return {key: value for key, value in lightweight.items() if value is not None}

    def _display_tool_result_blocks(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = msg.get("data")
        if not isinstance(data, dict):
            return []

        tool_use_id = data.get("tool_use_id")
        result_values: List[Any]
        if isinstance(data.get("results"), list):
            result_values = data["results"]
        elif "result" in data:
            result_values = [data.get("result")]
        else:
            result_values = []

        if not tool_use_id or not result_values:
            return []

        blocks: List[Dict[str, Any]] = []
        for result in result_values:
            history_result = self._lightweight_tool_result_for_restore(data, result)
            blocks.append({
                "type": "tool_result",
                "content": json.dumps(history_result, ensure_ascii=False, indent=2, default=str),
                "is_error": bool(data.get("is_error", False)),
                "tool_use_id": tool_use_id,
            })
        return blocks

    @classmethod
    def project_history_messages_for_llm(
        cls,
        messages: List[Dict[str, Any]],
        *,
        session_id: str = "llm_history_projection",
    ) -> List[Dict[str, Any]]:
        """Project persisted transcript rows into LLM-native message format."""
        projector = cls.__new__(cls)
        projector.session_id = session_id
        projector.use_llm_compression = False
        projector.compressed_iterations = []
        projector.data_files = {}
        projector.data_registry_refs = {}
        projector.conversation_history = []
        projector.load_history_messages(messages)
        return projector.get_messages_for_llm(repair_strategy="conservative")

    def load_history_messages(self, messages: List[Dict[str, Any]]) -> None:
        """
        批量导入历史对话消息（用于会话恢复）

        Args:
            messages: 历史消息列表。前端展示型 thought/tool_use/tool_result
                     事件不会作为普通文本恢复到 LLM 上下文；只有用户消息、
                     最终回复和原生 Anthropic content blocks 会被恢复。
        """
        if not messages:
            logger.warning("load_history_messages_empty", session_id=self.session_id)
            return

        logger.info(
            "load_history_messages_start",
            session_id=self.session_id,
            input_count=len(messages),
            first_message_type=messages[0].get("type") if messages else None,
            first_message_keys=list(messages[0].keys()) if messages else None,
            current_history_length=len(self.conversation_history)
        )

        max_source_sequence = max(
            (
                msg.get("sequence_number")
                for msg in messages
                if isinstance(msg.get("sequence_number"), int)
            ),
            default=None,
        )
        if max_source_sequence is not None:
            self.llm_source_until_sequence = max_source_sequence

        loaded_count = 0
        skipped_count = 0
        error_count = 0
        paired_display_tool_ids = self._paired_display_tool_ids(messages)
        pending_tool_uses: List[Dict[str, Any]] = []
        pending_tool_results: List[Dict[str, Any]] = []

        def flush_tool_uses(timestamp: Optional[str] = None) -> None:
            nonlocal loaded_count
            if not pending_tool_uses:
                return
            self.conversation_history.append(
                ConversationTurn(
                    role="assistant",
                    content=list(pending_tool_uses),
                    timestamp=timestamp or datetime.utcnow().isoformat(),
                    type="tool_use",
                    tool_use_id=pending_tool_uses[0].get("id") if len(pending_tool_uses) == 1 else None,
                    data={"restored_from_display_transcript": True},
                )
            )
            pending_tool_uses.clear()
            loaded_count += 1

        def flush_tool_results(timestamp: Optional[str] = None) -> None:
            nonlocal loaded_count
            if not pending_tool_results:
                return
            self.conversation_history.append(
                ConversationTurn(
                    role="user",
                    content=list(pending_tool_results),
                    timestamp=timestamp or datetime.utcnow().isoformat(),
                    type="tool_result",
                    tool_use_id=pending_tool_results[0].get("tool_use_id") if len(pending_tool_results) == 1 else None,
                    is_error=any(bool(block.get("is_error")) for block in pending_tool_results),
                    data={"restored_from_display_transcript": True},
                )
            )
            pending_tool_results.clear()
            loaded_count += 1

        for msg in messages:
            try:
                msg_type = msg.get("type")
                timestamp = msg.get("timestamp", datetime.utcnow().isoformat())

                is_native_content_blocks = isinstance(msg.get("content"), list)

                if msg_type in {"tool_use", "tool_result"} and not is_native_content_blocks:
                    # Display transcript tool rows are UI/runtime events. Replaying
                    # them on a later turn makes stale failures and old tool output
                    # compete with the user's current request. Native content blocks
                    # produced inside the active LLM session are still handled below.
                    skipped_count += 1
                    continue

                if msg_type == "tool_use" and not is_native_content_blocks:
                    tool_use_block = self._display_tool_use_block(msg)
                    if tool_use_block:
                        if tool_use_block.get("id") not in paired_display_tool_ids:
                            skipped_count += 1
                            continue
                        flush_tool_results(timestamp)
                        pending_tool_uses.append(tool_use_block)
                        continue

                if msg_type == "tool_result" and not is_native_content_blocks:
                    tool_result_id = self._display_tool_result_id(msg)
                    if tool_result_id not in paired_display_tool_ids:
                        skipped_count += 1
                        continue
                    tool_result_blocks = self._display_tool_result_blocks(msg)
                    if tool_result_blocks:
                        flush_tool_uses(timestamp)
                        pending_tool_results.extend(tool_result_blocks)
                        continue

                flush_tool_uses(timestamp)
                flush_tool_results(timestamp)

                if "role" in msg and "content" in msg:
                    content = msg["content"]
                    role = msg["role"]

                    if msg_type == "scheduled_task_event":
                        skipped_count += 1
                        continue

                    # 若 content 为 content blocks 列表，根据 block 类型修正 role 和 type
                    if isinstance(content, list):
                        content_types = {
                            block.get("type")
                            for block in content
                            if isinstance(block, dict)
                        }
                        if "tool_result" in content_types:
                            role = "user"
                            msg_type = "tool_result"
                        elif "tool_use" in content_types:
                            role = "assistant"
                            msg_type = "tool_use"
                    elif msg_type in {"thought", "tool_use", "tool_result", "start", "error", "interrupted"}:
                        # These rows are UI/display transcript events. Replaying
                        # them as assistant/user text teaches the model to emit
                        # pseudo tool calls such as "[思考] 准备调用工具...".
                        skipped_count += 1
                        continue

                    self.conversation_history.append(
                        ConversationTurn(
                            role=role,
                            content=content,
                            timestamp=timestamp,
                            type=msg_type,
                            data=msg.get("data") if isinstance(msg.get("data"), dict) else None,
                            tool_use_id=msg.get("tool_use_id"),
                            is_error=msg.get("is_error"),
                        )
                    )
                    loaded_count += 1
                    continue

                # 支持 ReAct 事件格式
                if "type" in msg:
                    data = msg.get("data", {})

                    # 提取消息内容
                    if msg_type in {"thought", "tool_use", "tool_result", "start", "error", "interrupted"}:
                        skipped_count += 1
                    elif msg_type == "complete":
                        answer = data.get("answer", "")
                        if answer:
                            self.conversation_history.append(
                                ConversationTurn(
                                    role="assistant",
                                    content=answer,
                                    timestamp=data.get("timestamp", datetime.utcnow().isoformat())
                                )
                            )
                            loaded_count += 1
                        else:
                            skipped_count += 1
                    elif msg_type == "final":
                        # final 类型（前端格式，等同于 complete）
                        answer = data.get("answer", "") if isinstance(data, dict) else ""
                        content = msg.get("content", "")
                        if answer or content:
                            self.conversation_history.append(
                                ConversationTurn(
                                    role="assistant",
                                    content=answer or content,
                                    timestamp=data.get("timestamp") if isinstance(data, dict) else msg.get("timestamp", datetime.utcnow().isoformat())
                                )
                            )
                            loaded_count += 1
                        else:
                            skipped_count += 1
                    elif msg_type == "user":
                        # user 类型（前端格式）
                        content = msg.get("content", "")
                        if content:
                            self.conversation_history.append(
                                ConversationTurn(
                                    role="user",
                                    content=content,
                                    timestamp=timestamp
                                )
                            )
                            loaded_count += 1
                        else:
                            skipped_count += 1
                    else:
                        logger.debug(
                            "load_history_messages_unknown_type",
                            session_id=self.session_id,
                            msg_type=msg_type,
                            msg_keys=list(msg.keys())
                        )
                        skipped_count += 1
                else:
                    logger.debug(
                        "load_history_messages_unrecognized_format",
                        session_id=self.session_id,
                        msg_keys=list(msg.keys())
                    )
                    skipped_count += 1

            except Exception as e:
                error_count += 1
                logger.error(
                    "load_history_message_failed",
                    session_id=self.session_id,
                    message=msg,
                    error=str(e)
                )

        flush_tool_uses()
        flush_tool_results()

        logger.info(
            "history_messages_loaded",
            session_id=self.session_id,
            total_input=len(messages),
            successfully_loaded=loaded_count,
            skipped=skipped_count,
            errors=error_count,
            final_history_length=len(self.conversation_history),
            previous_history_length=len(self.conversation_history) - loaded_count
        )

    def _append_conversation_turn(self, role: str, content: str | List[Dict[str, Any]], thought: Optional[str] = None, type: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.conversation_history.append(
            ConversationTurn(
                role=role,
                content=content,
                timestamp=datetime.utcnow().isoformat(),
                type=type,
                thought=thought,
                data=data
            )
        )

    def get_conversation_history(self, last_n_turns: int = 3) -> str:
        """Return the latest conversation turns in plain text."""

        if not self.conversation_history:
            return ""

        selected = self.conversation_history[-last_n_turns * 2 :]
        return "\n".join(f"{turn.role}: {turn.content}" for turn in selected)

    def get_messages_for_llm(self, *, repair_strategy: str = "api_safe") -> List[Dict[str, Any]]:
        """
        Return conversation history in Anthropic Messages API format.

        V3 架构：输出 Anthropic 原生 content blocks 格式。
        - assistant 消息的 action 类型：输出 tool_use content blocks
        - user 消息的 tool_result 类型：输出 tool_result content blocks
        - 其他消息：纯文本

        缓存友好策略（参考 learn-claude-code）：
        - 只追加：所有历史消息完整传递，不删除、不修改
        - 缓存优化：保持前缀不变，实现 KV Cache 命中

        Returns:
            List of message dictionaries in Anthropic API format
        """
        if not self.conversation_history:
            logger.warning(
                "get_messages_for_llm_empty",
                session_id=self.session_id,
                history_length=0,
                data_files_count=len(self.data_files)
            )
            return []

        all_turns = self.conversation_history
        messages = []

        for turn in all_turns:
            # ✅ 如果 content 已经是 Anthropic content blocks 格式，直接使用
            if isinstance(turn.content, list):
                # 提取 block 类型用于判断 role
                content_types = {
                    block.get("type")
                    for block in turn.content
                    if isinstance(block, dict)
                }

                # tool_result blocks 必须放在 user 消息中（Anthropic API 规范）
                if "tool_result" in content_types:
                    messages.append({
                        "role": "user",
                        "content": turn.content
                    })
                    continue

                # tool_use blocks 必须放在 assistant 消息中
                if "tool_use" in content_types:
                    messages.append({
                        "role": "assistant",
                        "content": turn.content
                    })
                    continue

                # 其他 content blocks（thinking, text 等）按照原 role 输出
                messages.append({
                    "role": turn.role,
                    "content": turn.content
                })
                continue

            # ✅ 如果 content 是字符串，包装成 text block
            # 完全忽略内部事件类型（turn.type, turn.thought, turn.reasoning）
            # 这些是前端显示用的元数据，不应该传递给 LLM
            messages.append({
                "role": turn.role,
                "content": turn.content,
            })

        messages = repair_tool_result_pairing(messages, strategy=repair_strategy)

        logger.info(
            "get_messages_for_llm_success",
            session_id=self.session_id,
            total_history_length=len(self.conversation_history),
            messages_count=len(messages),
            content_block_count=sum(1 for m in messages if isinstance(m.get("content"), list)),
            strategy="append_only_anthropic_native"
        )

        return messages

    def update_messages(self, compressed_messages: List[Dict[str, Any]]) -> None:
        """
        Update conversation history with compressed messages from token manager.

        Replaces the existing conversation history with compressed/summarized messages.
        This is called after token compression to reduce context window usage.

        Args:
            compressed_messages: List of messages in LLM API format after compression
        """
        # Clear existing history
        self.conversation_history.clear()

        # Convert compressed messages back to ConversationTurn format
        for msg in compressed_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Preserve Anthropic content block format. Fallback compression may
            # return original tool_use/tool_result blocks; converting them to
            # text would break provider pairing on the next request.
            if isinstance(content, list):
                content_types = {
                    block.get("type")
                    for block in content
                    if isinstance(block, dict)
                }
                if "tool_result" in content_types:
                    role = "user"
                    msg_type = "tool_result"
                elif "tool_use" in content_types:
                    role = "assistant"
                    msg_type = "tool_use"
                else:
                    msg_type = msg.get("type")

                self.conversation_history.append(
                    ConversationTurn(
                        role=role,
                        content=content,
                        timestamp=datetime.utcnow().isoformat(),
                        type=msg_type,
                        tool_use_id=msg.get("tool_use_id"),
                        is_error=msg.get("is_error"),
                    )
                )
                continue
            elif isinstance(content, dict):
                content = content.get("text", "")

            # Skip empty messages
            if not content:
                continue

            # Parse JSON format for assistant messages
            thought = None
            if role == "assistant":
                # 尝试解析 JSON 格式
                try:
                    # 去除可能的代码块标记
                    parse_content = content.strip()
                    if parse_content.startswith("```json"):
                        parse_content = parse_content[7:]  # 去掉 ```json
                    if parse_content.startswith("```"):
                        parse_content = parse_content[3:]  # 去掉 ```
                    if parse_content.endswith("```"):
                        parse_content = parse_content[:-3]  # 去掉结尾的 ```
                    parse_content = parse_content.strip()

                    parsed = json.loads(parse_content)
                    if isinstance(parsed, dict) and "thought" in parsed:
                        # 工具调用格式：提取 thought/observation
                        thought = parsed.get("thought")
                        content = parsed.get("observation", parsed.get("content", content))
                except (json.JSONDecodeError, ValueError, AttributeError):
                    # 解析失败，保持原格式（向后兼容旧格式）
                    # 尝试解析旧的 Markdown 格式
                    if content.startswith("## 思考\n"):
                        obs_marker = "\n\n## 观察\n"
                        obs_idx = content.find(obs_marker)
                        if obs_idx != -1:
                            # 提取思考内容（但不单独存储 reasoning）
                            thought = content[len("## 思考\n"):obs_idx]
                            content = content[obs_idx + len(obs_marker):]

            self.conversation_history.append(
                ConversationTurn(
                    role=role,
                    content=content,
                    timestamp=datetime.utcnow().isoformat(),
                    type=msg.get("type"),
                    thought=thought,
                )
            )
        
        logger.info(
            "session_messages_updated",
            session_id=self.session_id,
            message_count=len(self.conversation_history),
        )

    def cleanup(self) -> None:
        """Remove any session specific files from the filesystem."""

        for path in self.session_dir.glob("*"):
            try:
                path.unlink()
            except OSError:  # pragma: no cover - best effort
                logger.warning("session_memory_cleanup_failed", path=str(path))

        self.compressed_iterations.clear()
        self.data_files.clear()
        self.data_registry_refs.clear()
        self.conversation_history.clear()

        logger.info("session_memory_cleaned", session_id=self.session_id)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _coerce_quality_report(
        self,
        original: Optional[Any],
    ) -> Optional[DataQualityReport]:
        if original is None:
            return None
        if isinstance(original, DataQualityReport):
            return original
        if isinstance(original, dict):
            issues_data = original.get("issues") or []
            issues: List[ValidationIssue] = []
            for item in issues_data:
                if isinstance(item, ValidationIssue):
                    issues.append(item)
                elif isinstance(item, dict):
                    level = item.get("level", "info")
                    try:
                        level_enum = ValidationSeverity(level)
                    except ValueError:
                        level_enum = ValidationSeverity.INFO
                    issues.append(
                        ValidationIssue(
                            level=level_enum,
                            code=item.get("code", "unknown"),
                            message=item.get("message", ""),
                            field=item.get("field"),
                            index=item.get("index"),
                        )
                    )
            try:
                return DataQualityReport(
                    schema_type=original.get("schema", ""),  # 修复字段名
                    total_records=original.get("total_records", 0),
                    valid_records=original.get("valid_records", 0),
                    issues=issues,
                    missing_rate=original.get("missing_rate", 0.0),
                    summary=original.get("summary"),
                )
            except Exception:  # pragma: no cover - defensive
                logger.warning(
                    "session_memory_quality_report_coerce_failed",
                    payload=original,
                )
                return None
        return None

    def _coerce_field_stats(
        self,
        original: Optional[Iterable[Any]],
    ) -> Optional[List[FieldStats]]:
        if original is None:
            return None

        stats: List[FieldStats] = []
        for item in original:
            if isinstance(item, FieldStats):
                stats.append(item)
            elif isinstance(item, dict):
                try:
                    stats.append(
                        FieldStats(
                            name=item.get("name", ""),
                            minimum=item.get("minimum"),
                            maximum=item.get("maximum"),
                            mean=item.get("mean"),
                            missing=item.get("missing", 0),
                            total=item.get("total", 0),
                        )
                    )
                except Exception:  # pragma: no cover - defensive
                    logger.warning(
                        "session_memory_field_stats_coerce_failed",
                        payload=item,
                    )
        return stats or None
