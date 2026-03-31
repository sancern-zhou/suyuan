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

logger = structlog.get_logger()


_llm_service = None


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
    """Simple structure that stores a user or assistant message."""

    role: str
    content: str
    timestamp: str
    thought: Optional[str] = None  # LLM thought for this assistant turn
    reasoning: Optional[str] = None  # LLM reasoning process (detailed reasoning)


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
        # 使用跨平台的临时目录（Windows: C:\Users\xxx\AppData\Local\Temp, Linux: /tmp）
        if base_dir is None:
            base_dir = tempfile.gettempdir()
        self.session_dir = Path(base_dir) / f"agent_session_{session_id}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.use_llm_compression = use_llm_compression
        self.compressed_iterations: List[Dict[str, Any]] = []
        self.data_files: Dict[str, str] = {}
        self.data_registry_refs: Dict[str, str] = {}
        self.conversation_history: List[ConversationTurn] = []

        logger.info(
            "session_memory_initialized",
            session_id=session_id,
            directory=str(self.session_dir),
            use_llm_compression=use_llm_compression,
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
            if llm_service.provider in {"openai", "deepseek", "minimax", "mimo"}:
                response = await llm_service.client.chat.completions.create(
                    model=llm_service.config["model"],
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0.3,
                )
                return response.choices[0].message.content.strip()

            if llm_service.provider == "anthropic":
                response = await llm_service.client.messages.create(
                    model=llm_service.config["model"],
                    max_tokens=150,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text.strip()

            logger.warning(
                "session_memory_unknown_llm_provider",
                provider=llm_service.provider,
            )
            return self._simple_compress(iteration)

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

            # 优先保留data_id信息 - 使用智能别名
            data_id = observation.get('data_id') or observation.get('data_ref')
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

    def add_user_message(self, content: str) -> None:
        """Record a user utterance."""
        self._append_conversation_turn("user", content)
        logger.debug(
            "add_user_message_called",
            session_id=self.session_id,
            content_preview=content[:100],
            history_length=len(self.conversation_history)
        )

    def add_assistant_message(self, content: str, thought: Optional[str] = None, reasoning: Optional[str] = None) -> None:
        """Record an assistant response."""
        self._append_conversation_turn("assistant", content, thought=thought, reasoning=reasoning)
        logger.debug(
            "add_assistant_message_called",
            session_id=self.session_id,
            content_preview=content[:100],
            history_length=len(self.conversation_history),
            has_thought=thought is not None,
            has_reasoning=reasoning is not None
        )

    # 向后兼容旧接口
    def add_assistant_response(self, content: str) -> None:
        self.add_assistant_message(content)

    def load_history_messages(self, messages: List[Dict[str, Any]]) -> None:
        """
        批量导入历史对话消息（用于会话恢复）

        Args:
            messages: 历史消息列表，格式为 [{"type": "thought/action/observation/...", "data": {...}}]
                     或标准格式 [{"role": "user/assistant", "content": "..."}]
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

        loaded_count = 0
        skipped_count = 0
        error_count = 0

        for msg in messages:
            try:
                # 支持 ReAct 事件格式
                if "type" in msg:
                    msg_type = msg.get("type")
                    data = msg.get("data", {})

                    # 提取消息内容
                    if msg_type == "thought":
                        content = data.get("thought", "")
                        if content:
                            self.conversation_history.append(
                                ConversationTurn(
                                    role="assistant",
                                    content=f"[思考] {content}",
                                    timestamp=data.get("timestamp", datetime.utcnow().isoformat())
                                )
                            )
                            loaded_count += 1
                        else:
                            skipped_count += 1
                    elif msg_type == "action":
                        tool_calls = data.get("tool_calls", [])
                        if tool_calls:
                            content = f"[行动] 调用工具: {', '.join([t.get('tool_name', '') for t in tool_calls])}"
                            self.conversation_history.append(
                                ConversationTurn(
                                    role="assistant",
                                    content=content,
                                    timestamp=data.get("timestamp", datetime.utcnow().isoformat())
                                )
                            )
                            loaded_count += 1
                        else:
                            skipped_count += 1
                    elif msg_type == "observation":
                        result = data.get("result", "")
                        if result:
                            # 截断过长的结果
                            summary = result[:500] + "..." if len(str(result)) > 500 else result
                            self.conversation_history.append(
                                ConversationTurn(
                                    role="assistant",
                                    content=f"[观察] {summary}",
                                    timestamp=data.get("timestamp", datetime.utcnow().isoformat())
                                )
                            )
                            loaded_count += 1
                        else:
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
                                    timestamp=msg.get("timestamp", datetime.utcnow().isoformat())
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
                # 支持标准消息格式
                elif "role" in msg and "content" in msg:
                    self.conversation_history.append(
                        ConversationTurn(
                            role=msg["role"],
                            content=msg["content"],
                            timestamp=msg.get("timestamp", datetime.utcnow().isoformat())
                        )
                    )
                    loaded_count += 1
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

    def _append_conversation_turn(self, role: str, content: str, thought: Optional[str] = None, reasoning: Optional[str] = None) -> None:
        self.conversation_history.append(
            ConversationTurn(
                role=role,
                content=content,
                timestamp=datetime.utcnow().isoformat(),
                thought=thought,
                reasoning=reasoning
            )
        )

    def get_conversation_history(self, last_n_turns: int = 3) -> str:
        """Return the latest conversation turns in plain text."""

        if not self.conversation_history:
            return ""

        selected = self.conversation_history[-last_n_turns * 2 :]
        return "\n".join(f"{turn.role}: {turn.content}" for turn in selected)

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """
        Return conversation history in LLM API format for token management.

        Converts internal ConversationTurn objects to OpenAI-compatible message format:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        ✅ 同时传递 reasoning（详细推理）和 thought（简洁思考），提供层次化信息

        缓存友好策略（参考 learn-claude-code）：
        - 只追加：所有历史消息完整传递，不删除、不修改
        - 缓存优化：保持前缀不变，实现 KV Cache 命命
        - 成本节省：避免破坏缓存可节省 80-90% 成本
        - 参考：https://github.com/anthropics/learn-claude-code

        Returns:
            List of message dictionaries in LLM API format
        """
        if not self.conversation_history:
            logger.warning(
                "get_messages_for_llm_empty",
                session_id=self.session_id,
                history_length=0,
                data_files_count=len(self.data_files)
            )
            return []

        # ✅ 返回所有历史消息，采用只追加策略（缓存友好）
        all_turns = self.conversation_history

        messages = []
        for turn in all_turns:
            if turn.role == "assistant":
                # ✅ 区分两种格式：
                # 1. 工具调用（有 thought/reasoning）→ JSON 格式
                # 2. 纯文本回复（无 thought/reasoning）→ 保持纯文本
                if turn.thought or turn.reasoning:
                    # 有思考过程：使用 JSON 格式
                    json_obj = {
                        "thought": turn.thought or "",
                        "reasoning": turn.reasoning or turn.thought or "",
                        "observation": turn.content
                    }
                    content = json.dumps(json_obj, ensure_ascii=False, indent=2)
                else:
                    # 纯文本回复：保持原样，不包装
                    content = turn.content
            else:
                content = turn.content

            messages.append({
                "role": turn.role,
                "content": content,
            })

        logger.info(
            "get_messages_for_llm_success",
            session_id=self.session_id,
            total_history_length=len(self.conversation_history),
            messages_count=len(messages),
            strategy="append_only_cache_friendly"
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

            # Skip empty messages
            if not content:
                continue

            # Parse JSON format for assistant messages
            thought = None
            reasoning = None
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
                        # 工具调用格式：提取 thought/reasoning/observation
                        thought = parsed.get("thought")
                        reasoning = parsed.get("reasoning")
                        content = parsed.get("observation", parsed.get("content", content))
                except (json.JSONDecodeError, ValueError, AttributeError):
                    # 解析失败，保持原格式（向后兼容旧格式）
                    # 尝试解析旧的 Markdown 格式
                    if content.startswith("## 思考\n"):
                        obs_marker = "\n\n## 观察\n"
                        obs_idx = content.find(obs_marker)
                        if obs_idx != -1:
                            reasoning = content[len("## 思考\n"):obs_idx]
                            content = content[obs_idx + len(obs_marker):]

            self.conversation_history.append(
                ConversationTurn(
                    role=role,
                    content=content,
                    timestamp=datetime.utcnow().isoformat(),
                    thought=thought,
                    reasoning=reasoning,
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
