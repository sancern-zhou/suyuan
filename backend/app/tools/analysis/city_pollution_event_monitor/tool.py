"""
Agent tool wrapper for the city pollution event monitor service.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.services.pollution_event_monitor import MonitorConfig, run_pollution_event_monitor
from app.utils.path_config import resolve_agent_path

logger = structlog.get_logger()


class CityPollutionEventMonitorTool(LLMTool):
    """Run deterministic city pollution event detection and evidence collection."""

    def __init__(self) -> None:
        function_schema = {
            "name": "city_pollution_event_monitor",
            "description": (
                "定时巡检城市最近24小时空气质量小时数据，自动做数据质量检查、污染过程识别，"
                "并在检测到明显变化或污染过程后采集站点小时、气象、PM2.5组分、VOCs组分数据，"
                "落盘生成 evidence_pack.json 供后续智能体假设验证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市列表，例如 ['广州'] 或 ['广州', '佛山']"
                    },
                    "city": {
                        "type": "string",
                        "description": "单城市名称；当 cities 为空时使用"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "回看小时数，默认24"
                    },
                    "station_type": {
                        "type": "string",
                        "description": "站点类型，默认国控"
                    },
                    "output_root": {
                        "type": "string",
                        "description": "固定输出目录"
                    },
                    "force_collect": {
                        "type": "boolean",
                        "description": "未识别事件时是否也采集一套基线证据包，默认false"
                    },
                    "include_components": {
                        "type": "boolean",
                        "description": "是否采集PM2.5和VOCs组分数据，默认true"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 YYYY-MM-DD HH:MM:SS；默认当前整点"
                    }
                },
                "required": []
            },
        }
        super().__init__(
            name="city_pollution_event_monitor",
            description="Detect city pollution process events and persist evidence packs.",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context,
        cities: Optional[List[str]] = None,
        city: Optional[str] = None,
        hours: int = 24,
        station_type: str = "国控",
        output_root: Optional[str] = None,
        force_collect: bool = False,
        include_components: bool = True,
        end_time: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        selected_cities = self._normalize_cities(cities=cities, city=city)
        if not selected_cities:
            return {
                "success": False,
                "summary": "请提供 city 或 cities 参数。",
                "data": {"error": "missing_city"},
            }

        try:
            config = MonitorConfig(
                cities=selected_cities,
                hours=max(2, int(hours or 24)),
                station_type=station_type or "国控",
                output_root=resolve_agent_path(output_root) if output_root else None,
                force_collect=bool(force_collect),
                include_components=bool(include_components),
                end_time=self._parse_time(end_time),
                session_id=getattr(context, "session_id", "pollution_monitor_tool"),
            )
            result = await run_pollution_event_monitor(config=config, context=context)
            event_artifacts = [
                artifact
                for city_result in result.get("cities", [])
                for artifact in city_result.get("event_artifacts", [])
            ]
            result["data"] = {
                "detected_event_count": result.get("detected_event_count", 0),
                "event_artifacts": event_artifacts,
                "output_root": result.get("output_root"),
            }
            return result
        except Exception as exc:
            logger.error("city_pollution_event_monitor_failed", error=str(exc), exc_info=True)
            return {
                "success": False,
                "summary": f"城市污染过程巡检失败: {str(exc)}",
                "data": {"error": str(exc)},
            }

    def _normalize_cities(self, cities: Optional[List[str]], city: Optional[str]) -> List[str]:
        raw = []
        if cities:
            raw.extend(cities)
        if city:
            raw.append(city)
        normalized = []
        seen = set()
        for item in raw:
            name = str(item).strip()
            if name and name not in seen:
                normalized.append(name)
                seen.add(name)
        return normalized

    def _parse_time(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = value.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return datetime.fromisoformat(text)
