"""
Hybrid memory manager (ASCII only).

This module coordinates the memory layers:
1. Working memory (recent iterations).
2. Session memory (compressed history + filesystem storage).

Note: Long-term memory (vector storage) has been removed due to ineffective retrieval.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import json

import structlog

from .working_memory import WorkingMemory
from .session_memory import SessionMemory

logger = structlog.get_logger()


class HybridMemoryManager:
    """Entry point that orchestrates the memory layers (without long-term memory)."""

    def __init__(
        self,
        session_id: str,
        *,
        max_working_iterations: int = 20,  # 恒定保留20条详细记录
        working_context_limit: int = 50000,  # 大幅增加字符限制
        large_data_threshold: int = 5000,
        batch_compress_threshold: int = 11,  # 第11次触发首次压缩
        compress_batch_size: int = 10,  # 每次压缩10条
    ) -> None:
        self.session_id = session_id
        self.large_data_threshold = large_data_threshold

        self.working = WorkingMemory(
            max_iterations=max_working_iterations,
            batch_compress_threshold=batch_compress_threshold,
            compress_batch_size=compress_batch_size,
            max_context_chars=working_context_limit,
        )
        self.session = SessionMemory(session_id=session_id)

        logger.debug(
            "hybrid_memory_initialized",
            session_id=session_id,
            max_working=max_working_iterations,
            batch_compress_threshold=batch_compress_threshold,
            compress_batch_size=compress_batch_size,
            threshold=large_data_threshold,
            intelligent_context=False,  # 标记：已简化上下文管理
            longterm_memory=False  # 标记：已禁用长期记忆
        )

    # ------------------------------------------------------------------ #
    # Iteration handling
    # ------------------------------------------------------------------ #
    def add_iteration(
        self,
        thought: str,
        action: Dict[str, Any],
        observation: Dict[str, Any],
    ) -> None:
        """Add a new iteration and manage large payloads.

        简化逻辑：既然所有工具都已保存数据到context，
        HybridMemoryManager只需检查是否有data_id并直接引用，
        无需重复保存数据。
        """

        # 【方案A简化】直接处理observation，不进行重复外部化
        processed_observation = self._process_observation(observation, action)

        compressed_batches = self.working.add_iteration(thought, action, processed_observation)
        if compressed_batches:
            # 批量压缩所有迭代记录
            for iteration in compressed_batches:
                self.session.compress_iteration(iteration)

    def _process_observation(
        self,
        observation: Dict[str, Any],
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        简化的observation处理：直接使用已有的data_id，无重复外部化。

        由于所有工具都已通过context.save_data()保存数据，
        HybridMemoryManager只需检查observation中的data_id并直接引用，
        无需重复保存数据。
        """

        data = observation.get("data")
        if data is None:
            # data为None的情况（如get_component_data成功场景），直接返回
            return observation

        # 优先使用已有的长格式ID（方案A：data_id可能在metadata中）
        existing_data_id = observation.get("data_id")
        if not existing_data_id:
            # 方案A：从metadata中获取data_id
            metadata = observation.get("metadata", {})
            existing_data_id = metadata.get("data_id")

        if existing_data_id and ":" in existing_data_id:
            data_id = existing_data_id
            logger.debug(
                "hybrid_memory_using_existing_data_id",
                data_id=data_id,
                source="observation"
            )

            # 检查数据是否已保存过
            if data_id in self.session.data_files:
                logger.debug(
                    "hybrid_memory_data_already_saved",
                    data_id=data_id,
                    action="skip_duplicate_save"
                )

                # 构建轻量级payload，直接引用已有数据
                path = self.session.data_files[data_id]
                registry_id = self.session.get_registry_id(data_id)
                sampled_data = self._sample_data(data)

                return {
                    "success": observation.get("success"),
                    "summary": observation.get("summary"),
                    "error": observation.get("error"),
                    "data_id": data_id,
                    "data_ref": data_id,
                    "data_path": path,
                    "data_registry_id": registry_id,
                    "sampled_data": sampled_data,
                    "total_records": len(data) if isinstance(data, list) else None,
                    "instructions": (
                        f"如需完整数据，请调用 load_data_from_memory(data_ref='{data_id}') 获取数组。"
                    ),
                }
            else:
                # 数据未保存（不应该发生，因为所有工具都保存了），但仍需处理
                logger.warning(
                    "hybrid_memory_data_id_exists_but_not_saved",
                    data_id=data_id
                )
                # 返回原observation，让上层处理
                return observation
        else:
            # 没有data_id的情况（不应该发生，因为所有工具都返回data_id）
            # 但为了安全起见，仍然返回原observation
            logger.warning(
                "hybrid_memory_no_data_id_in_observation",
                has_data=(data is not None),
                observation_keys=list(observation.keys())
            )
            return observation

    # ------------------------------------------------------------------ #
    # Helper utilities
    # ------------------------------------------------------------------ #
    def _sample_data(self, data: Any, max_items: int = 20) -> Any:
        """Return a lightweight preview of the provided data."""

        if isinstance(data, list):
            # 检查是否包含Pydantic模型（如UnifiedDataRecord）
            if data and hasattr(data[0], 'dict'):
                # Pydantic模型列表：转换为字典列表
                sampled_items = []
                items = data if len(data) <= max_items else data[::max(1, len(data) // max_items)][:max_items]
                for item in items:
                    try:
                        sampled_items.append(item.dict())
                    except Exception:
                        # 转换失败则跳过
                        continue
                return sampled_items
            else:
                # 普通对象列表
                if len(data) <= max_items:
                    return data
                step = max(1, len(data) // max_items)
                return data[::step][:max_items]

        if isinstance(data, dict):
            preview = {}
            for key, value in data.items():
                preview[key] = self._sample_data(value, max_items)
            return preview

        if isinstance(data, str):
            return data[:2000] + "..." if len(data) > 2000 else data

        # 检查是否是Pydantic模型单个对象
        if hasattr(data, 'dict') and not isinstance(data, (dict, list, str)):
            try:
                return data.dict()
            except Exception:
                # 转换失败则返回字符串表示
                return str(data)

        return data

    # ------------------------------------------------------------------ #
    # Context accessors
    # ------------------------------------------------------------------ #
    def get_context_for_llm(self, include_raw_data: bool = False) -> str:
        """
        Build a consolidated context string for the LLM.

        Args:
            include_raw_data: 是否包含原始数据（而非仅data_ref）
        """
        sections = []

        # 🔥 新增：突出显示连续对话提醒
        sections.append("=" * 80 + "\n")
        sections.append("[WARNING] 连续对话模式：这是连续对话的一部分！\n")
        sections.append("请务必结合以下历史上下文理解用户连续意图。\n")
        sections.append("=" * 80 + "\n\n")

        conversation_history = self.session.get_conversation_history()
        if conversation_history:
            sections.append("=== 对话历史（重要） ===\n")
            sections.append(conversation_history)
            sections.append("\n\n")

        # 新增：关键信息高亮
        recent_iterations = self.working.get_iterations()
        if recent_iterations:
            sections.append("=== 近期分析步骤（关键信息） ===\n")
            for i, iteration in enumerate(recent_iterations[-5:], 1):  # 只显示最近5次
                sections.append(f"\n步骤 {i}:\n")
                sections.append(f"  思考: {iteration.get('thought', '')[:100]}...\n")
                action = iteration.get('action', {})
                if action.get('type') == 'TOOL_CALL':
                    sections.append(f"  行动: 调用 {action.get('tool', '未知工具')}\n")
                observation = iteration.get('observation', {})
                if observation.get('summary'):
                    sections.append(f"  结果: {observation['summary']}\n")
            sections.append("\n\n")

        sections.append("=== 压缩历史（摘要） ===\n")
        sections.append(self.session.get_compressed_summary())
        sections.append("\n\n")

        if include_raw_data:
            sections.append("=== 详细步骤 ===\n")
            sections.append(self.working.get_context_for_llm(include_raw_data=False))

        return "".join(sections)

    async def get_enhanced_context_for_llm(
        self,
        query: str,
        iteration: int,
        include_raw_data: bool = True
    ) -> str:
        """
        为LLM获取上下文（简化版）

        简化策略：直接返回工作记忆，不做任何复杂裁剪。

        Args:
            query: 用户查询（保留接口兼容性，暂未使用）
            iteration: 当前迭代次数（保留接口兼容性，暂未使用）
            include_raw_data: 是否包含原始数据

        Returns:
            上下文字符串
        """
        # 直接返回工作记忆的上下文（已包含对话历史）
        return self.working.get_context_for_llm(include_raw_data=include_raw_data)

    # Note: enhance_with_longterm() 和 save_session_to_longterm() 已删除
    # 原因：长期记忆检索无效，经常误导Agent

    def cleanup(self) -> None:
        """Remove any session-specific artefacts."""

        self.working.clear()
        self.session.cleanup()
        logger.info("hybrid_memory_cleaned", session_id=self.session_id)
