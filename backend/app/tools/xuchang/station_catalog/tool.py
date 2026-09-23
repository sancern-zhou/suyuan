"""
许昌站点目录查询工具（问数生图专属）

解决乡镇站/常规站"记不住名称与编码、不知道归属"的问题：
- 按名称模糊搜索站点，返回站点编码与归属区县
- 按区县展开下辖站点
- 站点编码与名称双向解析，作为 query_airdata_platform 的查询参数依据
- 可选将站点目录文档同步进项目知识库，供知识图谱问答乡镇归属
"""
from __future__ import annotations

from typing import Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .catalog import StationCatalogError
from .provider import XuchangStationCatalogProvider

logger = structlog.get_logger()


class XuchangStationCatalogTool(LLMTool):
    """许昌空气监测站点目录解析工具"""

    def __init__(self, provider: XuchangStationCatalogProvider | None = None) -> None:
        self._provider = provider or XuchangStationCatalogProvider()
        function_schema = {
            "name": "xuchang_station_catalog",
            "description": (
                "许昌市空气监测站点目录解析。按站点名称（支持模糊与简称，如“和尚桥镇”）、"
                "站点编码（含唯一编码）或区县解析站点，返回站点编码、名称、归属区县、坐标（如有）与站点类型。"
                "乡镇站编码为自定义编码（如 1107B），必须先通过本工具解析后再调用 query_airdata_platform 查数据"
                "（filters 用 field=code, operator=in）；不要凭猜测把乡镇名称直接当编码使用。"
                "station_type=township 乡镇站（含坐标，归属从名称解析），regular 常规站（国控等，含唯一编码），all 全部。"
                "action=sync_knowledge_graph 可将站点目录文档同步进项目知识库并触发图谱构建（维护操作，平时无需调用）。"
            ),
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
                        "description": "站点编码列表（乡镇站如 1107B，常规站唯一编码如 411000405）",
                    },
                    "districts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "区县名称列表（如 襄城县、禹州），展开该区县下辖站点",
                    },
                    "station_type": {
                        "type": "string",
                        "enum": ["township", "regular", "all"],
                        "description": "站点类别：township 乡镇站、regular 常规站、all 全部，默认 all",
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "强制从中台重建目录缓存（默认 false，缓存 7 天）",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["lookup", "sync_knowledge_graph"],
                        "description": "lookup 查询目录（默认）；sync_knowledge_graph 同步站点目录文档到知识库并触发图谱构建",
                    },
                },
            },
        }

        super().__init__(
            name="xuchang_station_catalog",
            description="Resolve Xuchang monitoring station directory (township & regular stations)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        districts: list[str] | None = None,
        station_type: str = "all",
        refresh: bool = False,
        action: str = "lookup",
        **_: Any,
    ) -> dict[str, Any]:
        if action == "sync_knowledge_graph":
            return await self._sync_knowledge_graph(force_refresh=bool(refresh))
        try:
            stations_payload, catalog = await self._provider.resolve_legacy(
                stations=stations,
                station_codes=station_codes,
                districts=districts,
                station_type=station_type
                if station_type in ("township", "regular", "all")
                else "all",
                refresh=bool(refresh),
            )
        except StationCatalogError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "xuchang_station_catalog_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))

        district_names = [item.get("name") for item in (catalog.get("districts") or [])]
        metadata = {
            "tool_name": self.name,
            "station_count": len(stations_payload),
            "from_cache": bool(catalog.get("from_cache")),
            "districts": district_names,
        }

        if not stations_payload:
            requested = list(stations or []) + list(station_codes or [])
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    **metadata,
                    "unresolved": requested,
                    "message": "目录中未匹配到站点",
                },
                "summary": (
                    f"未匹配到站点 {requested}；可用区县：{'、'.join(district_names)}。"
                    "可只用名称简称重试或按区县展开。"
                ),
            }

        summary_parts = [f"解析到 {len(stations_payload)} 个站点"]
        if stations_payload and stations_payload[0].get("station_type") == "township":
            summary_parts.append("（乡镇站编码可直接用于 query_airdata_platform 的 code 过滤）")
        return {
            "status": "success",
            "success": True,
            "data": stations_payload,
            "metadata": metadata,
            "summary": "，".join(summary_parts),
        }

    async def _sync_knowledge_graph(self, force_refresh: bool) -> dict[str, Any]:
        from .graph_seed import sync_station_knowledge_graph

        try:
            result = await sync_station_knowledge_graph(force_catalog_refresh=force_refresh)
        except StationCatalogError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "xuchang_station_graph_sync_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(f"站点目录知识库同步失败: {exc}")
        return {
            "status": "success",
            "success": True,
            "data": result,
            "metadata": {"tool_name": self.name, **result},
            "summary": (
                f"站点目录已同步到知识库 {result.get('kb_name')}（文档 {result.get('filename')}，"
                f"乡镇站 {result.get('township_count')} 个、常规站 {result.get('regular_count')} 个），"
                "图谱构建将由知识库管线完成。"
            ),
        }

    def _failed(self, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {"tool_name": self.name},
            "summary": f"站点目录解析失败: {message}",
        }
