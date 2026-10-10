"""
许昌站点目录查询工具（问数生图专属）

解决站点"记不住名称与编码、不知道归属"的问题：
- 按名称模糊搜索站点，返回站点编码与归属区县
- 按区县展开下辖站点（乡镇站/国控站/县级站）
- 站点编码与名称双向解析，作为 query_airdata_platform 与
  SsfbSiteHour（execute_crawler_sql_query）的查询参数依据
- lookup_henan_cities / lookup_henan_districts 返回河南全省城市组
  （含济源）与区县目录，作为 SsfbCityHour 等采集表查询的编码依据
- 可选将站点目录文档同步进项目知识库，供知识图谱问答乡镇归属
"""
from __future__ import annotations

from typing import Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .catalog import (
    StationCatalogError,
    henan_cities as filter_henan_cities,
    henan_districts as filter_henan_districts,
)
from .provider import XuchangStationCatalogProvider

logger = structlog.get_logger()

STATION_TYPE_CHOICES = ("township", "regular", "county", "all")
HENAN_ACTIONS = ("lookup_henan_cities", "lookup_henan_districts")


class XuchangStationCatalogTool(LLMTool):
    """许昌空气监测站点目录解析工具"""

    def __init__(self, provider: XuchangStationCatalogProvider | None = None) -> None:
        self._provider = provider or XuchangStationCatalogProvider()
        function_schema = {
            "name": "xuchang_station_catalog",
            "description": (
                "许昌市空气监测站点目录与河南城市/区县目录解析。按站点名称（支持模糊与简称，"
                "如“和尚桥镇”）、站点编码（含唯一编码）或区县解析站点，返回站点编码、名称、"
                "归属区县、坐标（如有）与站点类型。"
                "乡镇站编码为自定义编码（如 1107B），必须先通过本工具解析后再调用 "
                "query_airdata_platform 查数据（filters 用 field=code, operator=in）；"
                "县级站 station_code/site_id 为河南实时发布系统数字编码（如 232），"
                "用于 execute_crawler_sql_query 查 SsfbSiteHour/SsfbSiteDay（SiteID 过滤）；"
                "不要凭猜测把名称直接当编码使用。"
                "station_type=township 乡镇站（含坐标），regular 国控站（含唯一编码），"
                "county 县级站（河南实时发布系统，市控/省控），all 全部。"
                "action=lookup_henan_cities 返回河南 18 城市组清单（含济源市，group_id 用于 "
                "SsfbCityHour 的 GroupID 过滤）；action=lookup_henan_districts 返回全省区县清单，"
                "可用 cities 参数按所属城市过滤（如 [\"许昌市\",\"郑州市\"]）。"
                "action=sync_knowledge_graph 可将站点目录文档同步进项目知识库并触发图谱构建"
                "（维护操作，平时无需调用）。"
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
                        "description": "站点编码列表（乡镇站如 1107B，国控站唯一编码如 411000405，县级站数字编码如 232）",
                    },
                    "districts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "区县名称列表（如 襄城县、禹州），展开该区县下辖站点",
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表（如 许昌市、济源），action=lookup_henan_cities 时过滤城市，action=lookup_henan_districts 时按所属城市过滤区县",
                    },
                    "station_type": {
                        "type": "string",
                        "enum": list(STATION_TYPE_CHOICES),
                        "description": "站点类别：township 乡镇站、regular 国控站、county 县级站、all 全部，默认 all",
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "强制重建目录缓存（默认 false，缓存 7 天）",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["lookup", *HENAN_ACTIONS, "sync_knowledge_graph"],
                        "description": "lookup 查询站点目录（默认）；lookup_henan_cities 全省城市组清单；lookup_henan_districts 全省区县清单；sync_knowledge_graph 同步站点目录文档到知识库并触发图谱构建",
                    },
                },
            },
        }

        super().__init__(
            name="xuchang_station_catalog",
            description=(
                "Resolve Xuchang monitoring station directory (township/regular/county) "
                "plus Henan city & district directories"
            ),
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        districts: list[str] | None = None,
        cities: list[str] | None = None,
        station_type: str = "all",
        refresh: bool = False,
        action: str = "lookup",
        **_: Any,
    ) -> dict[str, Any]:
        if action == "sync_knowledge_graph":
            return await self._sync_knowledge_graph(force_refresh=bool(refresh))
        if action in HENAN_ACTIONS:
            return await self._lookup_henan_directory(
                action, names=cities, refresh=bool(refresh)
            )
        try:
            stations_payload, catalog = await self._provider.resolve_legacy(
                stations=stations,
                station_codes=station_codes,
                districts=districts,
                station_type=station_type
                if station_type in STATION_TYPE_CHOICES
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
            "hidden_station_count": int(catalog.get("hidden_station_count") or 0),
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
        station_types = {item.get("station_type") for item in stations_payload}
        if "township" in station_types:
            summary_parts.append("（乡镇站编码可直接用于 query_airdata_platform 的 code 过滤）")
        if "county" in station_types:
            summary_parts.append(
                "（县级站编码用于 execute_crawler_sql_query 查 SsfbSiteHour/SsfbSiteDay 的 SiteID 过滤）"
            )
        return {
            "status": "success",
            "success": True,
            "data": stations_payload,
            "metadata": metadata,
            "summary": "，".join(summary_parts),
        }

    async def _lookup_henan_directory(
        self, action: str, names: list[str] | None, refresh: bool
    ) -> dict[str, Any]:
        try:
            catalog = await self._provider.load_catalog(refresh)
        except StationCatalogError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "xuchang_station_catalog_henan_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))
        if action == "lookup_henan_cities":
            rows = filter_henan_cities(catalog, names)
            label = "河南城市组目录（含济源市）"
            hint = "group_id 用于 execute_crawler_sql_query 查 SsfbCityHour/SsfbCityDay 的 GroupID 过滤"
        else:
            rows = filter_henan_districts(catalog, names)
            label = "河南区县目录"
            hint = "区县可用于站点归属与聚合口径说明"
        return {
            "status": "success" if rows else "empty",
            "success": True,
            "data": rows,
            "metadata": {
                "tool_name": self.name,
                "entry_count": len(rows),
                "from_cache": bool(catalog.get("from_cache")),
            },
            "summary": f"{label} {len(rows)} 条；{hint}。",
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
                f"乡镇站 {result.get('township_count')} 个、国控站 {result.get('regular_count')} 个），"
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
