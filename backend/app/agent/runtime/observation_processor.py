"""Common observation post-processing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from .event_bus import RuntimeEventBus
from .finalizer import Finalizer
from .types import PlannerResult, RunState


class ObservationProcessor:
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
        state.last_observation = observation

        if observation.get("visuals") and isinstance(observation.get("visuals"), list):
            state.workflow_visuals.extend(observation["visuals"])
            self._record_chart_observations(observation, action)
            yield self.events.result({
                "status": observation.get("status", "success"),
                "success": observation.get("success", True),
                "visuals": observation["visuals"],
                "metadata": observation.get("metadata", {}),
                "summary": observation.get("summary", ""),
            })

        async for event in self._document_events(observation):
            yield event

        direct_response = self._extract_direct_response(state, observation)
        if direct_response:
            async for event in self.finalizer.complete(
                state,
                direct_response,
                planner_result=planner_result,
                thought=planner_result.thought,
                reasoning=planner_result.reasoning,
            ):
                yield event

    def capture_last_knowledge_sources(self, state: RunState) -> bool:
        last_result = state.last_single_tool_result
        if not last_result:
            return False
        tool_observation = last_result.get("observation", {})
        tool_name = last_result.get("tool_name", "")
        if tool_name != "knowledge_qa_workflow" or not isinstance(tool_observation, dict):
            return False
        if not tool_observation.get("success"):
            return False
        data = tool_observation.get("data", {})
        sources = data.get("sources") if isinstance(data, dict) else None
        if not sources:
            return False
        state.workflow_sources = sources
        state.workflow_visuals = tool_observation.get("visuals", [])
        state.direct_from_workflow = True
        return True

    def _extract_direct_response(self, state: RunState, observation: Dict[str, Any]) -> Optional[str]:
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
        state.direct_from_workflow = True
        state.workflow_sources = data.get("sources", [])
        state.workflow_visuals = observation.get("visuals", [])
        return response

    async def _document_events(self, observation: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        for result_data, metadata in self._iter_result_payloads(observation):
            inner = result_data.get("data", {}) if isinstance(result_data.get("data"), dict) else {}
            pdf_preview = result_data.get("pdf_preview") or inner.get("pdf_preview")
            markdown_preview = result_data.get("markdown_preview") or inner.get("markdown_preview")
            html_preview = result_data.get("html_preview") or inner.get("html_preview")
            file_path = (
                result_data.get("file_path") or result_data.get("path") or
                result_data.get("source_file") or result_data.get("output_file") or
                inner.get("file_path") or inner.get("path")
            )

            if pdf_preview or markdown_preview:
                yield self.events.office_document({
                    "file_path": file_path,
                    "generator": metadata.get("generator"),
                    "summary": result_data.get("summary", ""),
                    "timestamp": datetime.now().isoformat(),
                    **({"pdf_preview": pdf_preview} if pdf_preview else {}),
                    **({"markdown_preview": markdown_preview} if markdown_preview else {}),
                })

            if html_preview:
                yield self.events.notebook_document({
                    "file_path": file_path,
                    "file_type": inner.get("file_type", "notebook"),
                    "generator": metadata.get("generator"),
                    "summary": result_data.get("summary", ""),
                    "timestamp": datetime.now().isoformat(),
                    "html_preview": html_preview,
                })

    def _iter_result_payloads(self, observation: Dict[str, Any]):
        if not isinstance(observation, dict):
            return
        if observation.get("tool_results"):
            for item in observation.get("tool_results", []):
                result = item.get("result", {})
                if isinstance(result, dict):
                    yield result, item.get("metadata", {})
            return
        yield observation, observation.get("metadata", {})

    def _record_chart_observations(self, observation: Dict[str, Any], action: Dict[str, Any]) -> None:
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
                series = chart_data.get("series", []) if isinstance(chart_data, dict) else []
                first_series = series[0] if isinstance(series, list) and series and isinstance(series[0], dict) else {}
                title = chart_data.get("title", {}) if isinstance(chart_data.get("title"), dict) else {}
                chart_info = {
                    "visual_id": visual.get("id", f"visual_{idx}"),
                    "chart_id": visual.get("id", f"echarts_{idx}"),
                    "chart_type": visual.get("type", first_series.get("type", "unknown")),
                    "chart_title": visual.get("title", title.get("text", "")),
                    "data_id": self._first_source_data_id(meta),
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
                    "data_id": self._first_source_data_id(meta),
                    "source_tools": source_tools,
                    "schema_version": "v2.0",
                }
            self.memory.add_chart_observation(chart_info)

    def _source_tools(self, action: Dict[str, Any]) -> list[str]:
        if action.get("type") == "TOOL_CALLS":
            return [tool.get("tool", "") for tool in action.get("tools", []) if isinstance(tool, dict)]
        tool_name = action.get("tool")
        return [tool_name] if tool_name else []

    def _first_source_data_id(self, meta: Dict[str, Any]) -> Any:
        source_ids = meta.get("source_data_ids")
        if isinstance(source_ids, list) and source_ids:
            return source_ids[0]
        return meta.get("data_id")
