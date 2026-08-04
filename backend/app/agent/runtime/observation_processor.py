"""Common observation post-processing."""

from __future__ import annotations

import structlog
from typing import Any, AsyncGenerator, Dict, Optional

from .event_bus import RuntimeEventBus
from .finalizer import Finalizer
from .types import PlannerResult, RunState

logger = structlog.get_logger()


class ObservationProcessor:
    """
    观察结果处理器

    ⚠️ 重要：不再提取visuals到state
    visuals应该从tool_result事件中直接获取，符合单一职责原则
    """

    def __init__(self, finalizer: Finalizer, event_bus: RuntimeEventBus, memory_manager=None) -> None:
        self.finalizer = finalizer
        self.events = event_bus
        self.memory = memory_manager

    async def process(
        self,
        state: RunState,
        planner_result: PlannerResult,
        action: Dict[str, Any],
        observation: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理观察结果

        ⚠️ 重要变更：
        - 移除visuals提取逻辑（visuals应该从tool_result获取）
        - 保留knowledge_qa_workflow的sources处理（用于知识溯源）
        - 保留图表记录功能（用于memory追踪）
        """
        state.last_observation = observation

        # ✅ 处理 knowledge_qa_workflow 的知识溯源数据
        # （保留用于知识溯源功能）
        tool_name = action.get("tool") or ""
        if tool_name == "knowledge_qa_workflow" and observation.get("success"):
            data = observation.get("data", {})
            if isinstance(data, dict):
                sources = data.get("sources")
                if sources and isinstance(sources, list):
                    state.workflow_sources = sources
                    # ❌ 移除：不再提取visuals到state
                    # state.workflow_visuals = observation.get("visuals", [])

        # ✅ 记录图表观测（用于memory追踪，但不提取到state）
        if observation.get("visuals") and isinstance(observation.get("visuals"), list):
            self._record_chart_observations(observation, action)

        # ✅ 处理直接响应（workflow工具直接返回答案）
        direct_response = self._extract_direct_response(state, observation)
        if direct_response:
            async for event in self.finalizer.complete(
                state,
                direct_response,
                planner_result=planner_result,
                thought=planner_result.thought,
            ):
                yield event

    def capture_last_knowledge_sources(self, state: RunState) -> bool:
        """
        捕获知识溯源数据

        ⚠️ 重要：只捕获sources，不捕获visuals
        """
        # ✅ 如果已经有知识溯源数据，直接返回
        if state.workflow_sources:
            return True

        last_result = state.last_single_tool_result
        if not last_result:
            return False
        tool_observation = last_result.get("observation", {})
        tool_name = last_result.get("tool_name", "")
        if not isinstance(tool_observation, dict):
            return False
        if not tool_observation.get("success"):
            return False

        # 处理 knowledge_qa_workflow 工具
        if tool_name == "knowledge_qa_workflow":
            data = tool_observation.get("data", {})
            sources = data.get("sources") if isinstance(data, dict) else None
            if sources:
                state.workflow_sources = sources
                # ❌ 移除：不再提取visuals到state
                # state.workflow_visuals = tool_observation.get("visuals", [])
                return True

        return False

    def _extract_direct_response(self, state: RunState, observation: Dict[str, Any]) -> Optional[str]:
        """
        提取直接响应

        ⚠️ 重要：只提取sources，不提取visuals
        """
        metadata = observation.get("metadata", {}) if isinstance(observation, dict) else {}
        if not metadata.get("can_emit_response") or not observation.get("success"):
            return None
        data = observation.get("data", {})
        if not isinstance(data, dict):
            return None
        response_field = metadata.get("response_field", "response")
        response = data.get(response_field, "")
        if not response:
            return None
        state.workflow_sources = data.get("sources", [])
        # ❌ 移除：不再提取visuals到state
        # state.workflow_visuals = observation.get("visuals", [])
        return response

    def _record_chart_observations(self, observation: Dict[str, Any], action: Dict[str, Any]) -> None:
        """
        记录图表观测（用于memory追踪）

        ⚠️ 注意：此方法只记录图表信息到memory，不提取到state
        """
        if not self.memory or not hasattr(self.memory, "add_chart_observation"):
            return
        visuals = observation.get("visuals")
        if not isinstance(visuals, list):
            return
        source_tools = self._source_tools(action)
        for idx, visual in enumerate(visuals):
            if not isinstance(visual, dict):
                continue
            meta = visual.get("meta", {}) if isinstance(visual.get("meta"), dict) else {}
            if "data" in visual:
                chart_data = visual.get("data", {}) if isinstance(visual.get("data"), dict) else {}
                series = chart_data.get("series", []) if isinstance(chart_data.get("series"), dict) else []
                first_series = series[0] if isinstance(series, list) and series and isinstance(series[0], dict) else {}
                title = chart_data.get("title", {}) if isinstance(chart_data.get("title"), dict) else {}
                chart_info = {
                    "visual_id": visual.get("id", f"visual_{idx}"),
                    "chart_id": visual.get("id", f"echarts_{idx}"),
                    "chart_type": visual.get("type", first_series.get("type", "unknown")),
                    "chart_title": visual.get("title", title.get("text", "")),
                    "file_path": self._first_source_file_path(meta),
                    "source_tools": source_tools,
                    "schema_version": meta.get("schema_version", "echarts_standard"),
                }
            else:
                payload = visual.get("payload", {}) if isinstance(visual.get("payload"), dict) else {}
                chart_info = {
                    "visual_id": visual.get("id", f"visual_{idx}"),
                    "chart_id": payload.get("id", f"chart_{idx}"),
                    "chart_type": payload.get("type", "unknown"),
                    "chart_title": payload.get("title", ""),
                    "file_path": self._first_source_file_path(meta),
                    "source_tools": source_tools,
                    "schema_version": "v2.0",
                }
            self.memory.add_chart_observation(chart_info)

    def _source_tools(self, action: Dict[str, Any]) -> list[str]:
        """获取来源工具列表"""
        if action.get("type") == "TOOL_CALLS":
            return [tool.get("tool", "") for tool in action.get("tools", []) if isinstance(tool, dict)]
        tool_name = action.get("tool")
        return [tool_name] if tool_name else []

    def _first_source_file_path(self, meta: Dict[str, Any]) -> Any:
        """获取第一个源数据文件路径。"""
        source_paths = meta.get("source_file_paths")
        if isinstance(source_paths, list) and source_paths:
            return source_paths[0]
        return meta.get("file_path")
