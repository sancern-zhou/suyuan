"""
Agent tool wrapper for the air quality data quality monitor service.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.services.air_quality_data_quality_monitor import (
    DataQualityMonitorConfig,
    run_air_quality_data_quality_monitor,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class AirQualityDataQualityMonitorTool(LLMTool):
    """Run deterministic station data quality checks and persist issue packages."""

    def __init__(self) -> None:
        function_schema = {
            "name": "air_quality_data_quality_monitor",
            "description": (
                "每小时巡检城市最近24小时站点小时监测数据，按同城站点偏差、趋势一致性、"
                "PM2.5/PM10协同变化、NO2/O3规律等规则识别疑似数据质量问题。"
                "只有发现疑似问题时才落盘生成 quality_package.json。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市列表，例如 ['广州'] 或 ['广州', '佛山']",
                    },
                    "city": {
                        "type": "string",
                        "description": "单城市名称；当 cities 为空时使用",
                    },
                    "hours": {
                        "type": "integer",
                        "description": "回看小时数，默认24",
                    },
                    "station_type": {
                        "type": "string",
                        "description": "站点类型，默认国控",
                    },
                    "output_root": {
                        "type": "string",
                        "description": "固定输出目录；相对路径基于 backend 目录",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 YYYY-MM-DD HH:MM:SS；默认当前整点",
                    },
                },
                "required": [],
            },
        }
        super().__init__(
            name="air_quality_data_quality_monitor",
            description="Detect suspected air quality monitoring data quality issues and persist issue packages.",
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
            config = DataQualityMonitorConfig(
                cities=selected_cities,
                hours=max(6, int(hours or 24)),
                station_type=station_type or "国控",
                output_root=Path(output_root) if output_root else None,
                end_time=self._parse_time(end_time),
                session_id=getattr(context, "session_id", "data_quality_monitor_tool"),
            )
            result = await run_air_quality_data_quality_monitor(config=config, context=context)
            result["data"] = {
                "issue_count": result.get("issue_count", 0),
                "issue_packages": result.get("issue_packages", []),
                "output_root": result.get("output_root"),
            }
            return result
        except Exception as exc:
            logger.error("air_quality_data_quality_monitor_failed", error=str(exc), exc_info=True)
            return {
                "success": False,
                "summary": f"空气质量数据质量巡检失败: {str(exc)}",
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
