"""
Hybrid memory manager (ASCII only).

This module coordinates the memory layers:
1. Working memory (recent iterations).
2. Session memory (compressed history + filesystem storage).

Note: Long-term memory (vector storage) has been removed due to ineffective retrieval.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
import json

import structlog

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

        # 内联 recent_iterations
        self.recent_iterations: List[Dict[str, Any]] = []
        self.max_recent_iterations = max_working_iterations
        self.batch_compress_threshold = batch_compress_threshold
        self.compress_batch_size = compress_batch_size

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
        HybridMemoryManager只需检查是否有file_path并直接引用，
        无需重复保存数据。
        """

        # 【方案A简化】直接处理observation，不进行重复外部化
        processed_observation = self._process_observation(observation, action)

        # 内联 add_iteration 逻辑
        now_str = datetime.utcnow().isoformat()
        self.recent_iterations.append({
            "thought": thought,
            "action": action,
            "observation": processed_observation,
            "timestamp": now_str
        })

        # 批量压缩检查
        if len(self.recent_iterations) > self.batch_compress_threshold:
            # 压缩前 compress_batch_size 条记录
            to_compress = self.recent_iterations[:self.compress_batch_size]
            for iteration in to_compress:
                self.session.compress_iteration(iteration)
            # 保留后面的记录
            self.recent_iterations = self.recent_iterations[self.compress_batch_size:]

    def _process_observation(
        self,
        observation: Dict[str, Any],
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        简化的observation处理：直接使用已有的file_path，无重复外部化。

        由于所有工具都已通过context.save_data()保存数据，
        HybridMemoryManager只需检查 observation 中的 file_path 并直接引用，
        无需重复保存数据。
        """

        data = observation.get("data")
        refs = self._extract_observation_refs(observation)

        if data is None and not refs["file_paths"] and not refs["report_file_paths"]:
            # data为None且没有可引用结果的情况，直接返回
            return observation

        existing_path = refs["file_paths"][0] if refs["file_paths"] else None

        if existing_path:
            logger.debug(
                "hybrid_memory_using_existing_data_file",
                file_path=existing_path,
                source="observation"
            )

            if existing_path in self.session.data_files:
                logger.debug(
                    "hybrid_memory_data_already_saved",
                    file_path=existing_path,
                    action="skip_duplicate_save"
                )

                sampled_data = self._sample_data(data)

                return {
                    "success": observation.get("success"),
                    "summary": observation.get("summary"),
                    "error": observation.get("error"),
                    "file_path": existing_path,
                    "sampled_data": sampled_data,
                    "total_records": len(data) if isinstance(data, list) else None,
                }
            else:
                # 数据未保存（不应该发生，因为所有工具都保存了），但仍需处理
                logger.warning(
                    "hybrid_memory_data_file_not_registered",
                    file_path=existing_path
                )
                # 返回原observation，让上层处理
                return observation
        else:
            if refs["report_file_paths"]:
                logger.debug(
                    "hybrid_memory_using_existing_report_files",
                    report_file_paths=refs["report_file_paths"],
                    source="observation"
                )
                return {
                    "success": observation.get("success"),
                    "summary": observation.get("summary"),
                    "error": observation.get("error"),
                    "report_file_path": refs["report_file_paths"][0],
                    "report_file_paths": refs["report_file_paths"],
                    "data_role": "statistical_report",
                    "sampled_data": self._sample_data(data) if data is not None else None,
                    "total_records": len(data) if isinstance(data, list) else None,
                }

            if refs["file_paths"]:
                logger.debug(
                    "hybrid_memory_using_existing_data_files",
                    file_paths=refs["file_paths"],
                    source="observation"
                )
                return {
                    "success": observation.get("success"),
                    "summary": observation.get("summary"),
                    "error": observation.get("error"),
                    "file_path": refs["file_paths"][0],
                    "file_paths": refs["file_paths"],
                    "sampled_data": self._sample_data(data) if data is not None else None,
                    "total_records": len(data) if isinstance(data, list) else None,
                }

            # 没有数据或报告文件路径时返回原 observation。
            logger.warning(
                "hybrid_memory_no_data_file_in_observation",
                has_data=(data is not None),
                observation_keys=list(observation.keys())
            )
            return observation

    def _extract_observation_refs(self, observation: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract data and report registry references from a tool observation."""

        file_paths: List[str] = []
        report_file_paths: List[str] = []

        def add_unique(target: List[str], value: Any) -> None:
            if isinstance(value, str) and value and value not in target:
                target.append(value)
            elif isinstance(value, dict):
                nested = value.get("file_path")
                if isinstance(nested, str) and nested and nested not in target:
                    target.append(nested)

        def scan_mapping(payload: Any) -> None:
            if not isinstance(payload, dict):
                return

            add_unique(file_paths, payload.get("file_path"))
            add_unique(report_file_paths, payload.get("report_file_path"))

            for item in payload.get("file_paths") or []:
                add_unique(file_paths, item)
            for item in payload.get("report_file_paths") or []:
                add_unique(report_file_paths, item)

            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                add_unique(file_paths, metadata.get("file_path"))
                add_unique(report_file_paths, metadata.get("report_file_path"))
                for item in metadata.get("source_file_paths") or []:
                    add_unique(file_paths, item)
                for item in metadata.get("source_report_file_paths") or []:
                    add_unique(report_file_paths, item)

        scan_mapping(observation)
        for tool_result in observation.get("tool_results") or []:
            if not isinstance(tool_result, dict):
                continue
            scan_mapping(tool_result)
            scan_mapping(tool_result.get("result"))

        return {
            "file_paths": file_paths,
            "report_file_paths": report_file_paths,
        }

    def get_iterations(self) -> List[Dict[str, Any]]:
        """Return a copy of recent iterations."""
        return self.recent_iterations.copy()

    def add_chart_observation(self, chart_info: Dict[str, Any]) -> None:
        """Add a chart observation record to recent_iterations."""
        now_str = datetime.utcnow().isoformat()
        chart_observation = {
            "thought": f"图表已生成：{chart_info.get('chart_title', '无标题')}",
            "action": {
                "type": "CHART_GENERATED",
                "tool": chart_info.get("source_tool", "execute_echarts_python"),
                "chart_id": chart_info.get("chart_id", "未知图表"),
                "chart_type": chart_info.get("chart_type", "unknown")
            },
            "observation": {
                "success": True,
                "summary": chart_info.get("summary", "图表已生成"),
                "chart_id": chart_info.get("chart_id", "未知图表"),
                "chart_type": chart_info.get("chart_type", "unknown"),
                "chart_title": chart_info.get("chart_title", "无标题"),
                "file_path": chart_info.get("file_path"),
                "source_tool": chart_info.get("source_tool", "未知工具"),
                "has_chart": True
            },
            "timestamp": now_str
        }

        self.recent_iterations.append(chart_observation)

        logger.info(
            "hybrid_memory_chart_added",
            chart_id=chart_info.get("chart_id"),
            chart_type=chart_info.get("chart_type"),
            total_iterations=len(self.recent_iterations)
        )

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

    # Note: get_context_for_llm() and get_enhanced_context_for_llm() removed.
    # All context is managed via session.get_messages_for_llm() and
    # session.get_compressed_summary().

    def cleanup(self) -> None:
        """Remove any session-specific artefacts."""

        self.recent_iterations.clear()
        self.session.cleanup()
        logger.info("hybrid_memory_cleaned", session_id=self.session_id)
