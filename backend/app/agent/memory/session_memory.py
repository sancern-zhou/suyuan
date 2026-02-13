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


class SessionMemory:
    """Layer-2 memory that persists intermediate artefacts to disk."""

    def __init__(
        self,
        session_id: str,
        base_dir: str = "/tmp",
        use_llm_compression: bool = True,
    ) -> None:
        self.session_id = session_id
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
        """Persist data on disk and optionally register the dataset."""

        # Sanitize filename for Windows - replace colons with underscores
        safe_filename = data_id.replace(":", "_")
        path = self.session_dir / f"{safe_filename}.{file_format}"

        if file_format == "json":
            with path.open("w", encoding="utf-8") as stream:
                # Use default handler for datetime serialization
                json.dump(
                    data,
                    stream,
                    ensure_ascii=False,
                    indent=2,
                    default=str  # Convert datetime and other non-serializable objects to strings
                )
        elif file_format == "md":
            with path.open("w", encoding="utf-8") as stream:
                stream.write(str(data))
        else:
            raise ValueError(f"Unsupported format: {file_format}")

        self.data_files[data_id] = str(path)

        quality_report_obj = self._coerce_quality_report(quality_report)
        field_stats_list = self._coerce_field_stats(field_stats)

        should_register = (
            file_format == "json"
            and registry_schema
            and isinstance(data, list)
            and all(isinstance(item, dict) for item in data)
        )

        registry_id = None
        if should_register:
            metadata = {"session_id": self.session_id}
            if registry_metadata:
                metadata.update(registry_metadata)

            try:
                entry = data_registry.register_dataset(
                    schema=registry_schema,
                    version=registry_version,
                    records=data,  # type: ignore[arg-type]
                    quality_report=quality_report_obj,
                    field_stats=field_stats_list,
                    metadata=metadata,
                )
                registry_id = entry.data_id
                self.data_registry_refs[data_id] = registry_id
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "session_memory_registry_register_failed",
                    data_id=data_id,
                    error=str(exc),
                )

        logger.info(
            "session_memory_data_saved",
            data_id=data_id,
            path=str(path),
            registry_id=registry_id,
            data_files_count=len(self.data_files),
            data_files_keys=list(self.data_files.keys())[-3:]  # 显示最近3个键
        )
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
            # ✅ 增强：尝试用不同的方法查找文件
            logger.warning(
                "session_memory_file_not_registered",
                data_id=data_id,
                available_ids=list(self.data_files.keys())[:5]  # 只显示前5个
            )

            # 尝试基于文件名模式匹配
            safe_filename = data_id.replace(":", "_")
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
                with path.open("r", encoding="utf-8") as stream:
                    return json.load(stream)

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

    def add_assistant_message(self, content: str) -> None:
        """Record an assistant response."""
        self._append_conversation_turn("assistant", content)
        logger.debug(
            "add_assistant_message_called",
            session_id=self.session_id,
            content_preview=content[:100],
            history_length=len(self.conversation_history)
        )

    # 向后兼容旧接口
    def add_assistant_response(self, content: str) -> None:
        self.add_assistant_message(content)

    def _append_conversation_turn(self, role: str, content: str) -> None:
        self.conversation_history.append(
            ConversationTurn(
                role=role,
                content=content,
                timestamp=datetime.utcnow().isoformat(),
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

        messages = []
        for turn in self.conversation_history:
            messages.append({
                "role": turn.role,
                "content": turn.content,
            })

        logger.debug(
            "get_messages_for_llm_success",
            session_id=self.session_id,
            history_length=len(self.conversation_history),
            messages_count=len(messages)
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
            
            self.conversation_history.append(
                ConversationTurn(
                    role=role,
                    content=content,
                    timestamp=datetime.utcnow().isoformat(),
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
