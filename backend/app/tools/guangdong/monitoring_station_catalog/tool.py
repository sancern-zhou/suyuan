"""广东监测体系站点地理目录工具（query / 监测问数子模式）。"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.station_directory import StationQuery
from app.services.station_directory.format import records_to_payload
from app.tools.base.tool_interface import LLMTool, ToolCategory

from .provider import MonitoringStationCatalogProvider

logger = structlog.get_logger()

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

_TOOL_SUMMARY = (
    "广东监测体系站点地理查询。按站点名称（模糊/简称）、监测平台站点编码、城市、区县或站点类型"
    "解析监测站，返回站点名称、监测平台唯一编码、城市/区县归属、站点类型（国控/省控/市控/区县控/"
    "乡镇控/背景站/区域站/交通站/专项站）、经纬度与地址。覆盖监测平台站点地理快照（约 450 站，"
    "与 query_gd_suncere_* 取数工具同源，城市归属已按行政区划码校正）。"
    "返回的 station_code 是监测平台唯一编码，供 query_gd_suncere_* 系列工具使用；"
    "采集库 SQL（execute_crawler_sql_query）按站点名称/城市过滤。"
    "注意：本目录的类型体系没有'组分站'标记，少数组分站（如深圳莲花山）类型为空或归入专项站，"
    "组分站名录、某城市有无组分站、VOCs/颗粒物组分监测能力一律用 component_station_catalog"
    "（超站组分 38 站清单），运维单位/运维人员/停用站等运维台账口径用 guangdong_station_catalog。"
    "不要凭猜测把站点名当编码使用。"
)


class MonitoringStationCatalogTool(LLMTool):
    """监测体系站点地理目录查询工具。"""

    def __init__(self, provider: MonitoringStationCatalogProvider | None = None) -> None:
        self._provider = provider or MonitoringStationCatalogProvider()
        function_schema = {
            "name": "monitoring_station_catalog",
            "description": _TOOL_SUMMARY,
            "parameters": {
                "type": "object",
                "properties": {
                    "stations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点名称列表，支持模糊或简称匹配",
                    },
                    "station_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "监测平台站点编码（唯一编码）列表，精确匹配",
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表（如 广州、深圳市），展开该城市下辖监测站",
                    },
                    "districts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "区县名称列表（如 从化区、博罗县），展开该区县下辖监测站",
                    },
                    "station_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点类型列表：国控/省控/市控/区县控/乡镇控/背景站/区域站/交通站/专项站（或 全部）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"返回条数上限，默认 {DEFAULT_LIMIT}，最大 {MAX_LIMIT}",
                    },
                },
            },
        }
        super().__init__(
            name="monitoring_station_catalog",
            description="Resolve Guangdong monitoring station geolocation directory",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        cities: list[str] | None = None,
        districts: list[str] | None = None,
        station_types: list[str] | None = None,
        limit: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        requested_limit = self._normalize_limit(limit)
        query = StationQuery.create(
            station_names=stations,
            station_codes=station_codes,
            cities=cities,
            districts=districts,
            station_types=station_types,
        )
        try:
            records = await self._provider.list_stations(query)
        except Exception as exc:
            logger.error(
                "monitoring_station_catalog_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))

        payload = records_to_payload(records, limit=requested_limit)
        if not records:
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {"tool_name": self.name, "station_count": 0},
                "summary": (
                    "监测站目录中未匹配到站点；请用名称简称、城市名或站点类型重试。"
                    "若在找组分站（VOCs/颗粒物组分），本目录不含组分站类型标记，"
                    "请改用 component_station_catalog（超站组分站清单）。"
                ),
            }
        all_records = await self._provider.list_stations(None)
        metadata = {
            "tool_name": self.name,
            "station_count": len(records),
            "directory_total": len(all_records),
            "returned": len(payload),
            "cities": sorted({item.city for item in all_records if item.city}),
        }
        summary = f"解析到 {len(records)} 个监测站"
        if len(payload) < len(records):
            summary += f"（按 limit 返回前 {len(payload)} 条）"
        summary += "；station_code 为监测平台唯一编码，城市归属已按行政区划码校正。"
        return {
            "status": "success",
            "success": True,
            "data": payload,
            "metadata": metadata,
            "summary": summary,
        }

    @staticmethod
    def _normalize_limit(limit: int | None) -> int:
        if limit is None:
            return DEFAULT_LIMIT
        try:
            value = int(limit)
        except (TypeError, ValueError):
            return DEFAULT_LIMIT
        return max(1, min(value, MAX_LIMIT))

    def _failed(self, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {"tool_name": self.name},
            "summary": f"监测站目录解析失败: {message}",
        }
