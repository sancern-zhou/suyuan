"""广东站点目录查询工具。

解决"记不住站点名称与编码、不知道归属与运维人员"的问题：
- 按站点名称（模糊/简称）、编码（station_code/unique_code/station_id）或城市解析站点
- 返回站点基础信息、城市/区域归属、站点类型、运维单位、运维人员名册、经纬度与地址
- 支持"按运维单位/运维人员反查负责站点"，作为工单、告警等业务数据按站点过滤的前置解析
- 覆盖运维台账口径 432 站（主网 332 + 组分网 100）；组分站无经纬度/运维单位/运维人员，缺口如实声明
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .catalog import StationCatalogError, available_cities
from .provider import GuangdongStationCatalogProvider

logger = structlog.get_logger()

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

_TOOL_SUMMARY = (
    "广东运维站点目录解析。按站点名称（支持模糊与简称，如“从化天湖”）、站点编码"
    "（station_code/unique_code/station_id）或城市解析站点，返回站点编码、名称、城市归属、"
    "站点类型、运维单位、运维人员名册、经纬度与地址。覆盖运维台账在用站点（432 站口径 = 主网 332 + "
    "组分网 100，每日刷新），停用/废弃站点已在目录层屏蔽、不返回；组分站源系统无经纬度/运维单位/"
    "运维人员，工具会如实声明缺口。注意：台账的'组分站'类型（100 站）不区分 VOCs/颗粒物组分"
    "监测能力，回答'某城市有无 VOCs 站/颗粒物组分站'或按组分类型过滤时，"
    "用 component_station_catalog（超站组分 38 站清单，带能力标注）。"
    "按运维单位或运维人员反查负责站点用 operation_units/managers 参数。"
    "如需含停用站在内的历史站点信息，用 execute_guangdong_mart_sql 查 dim_station（status=0 为停用）；"
    "本工具用于名录与归属解析，不要凭猜测把站点名当编码使用。"
)


class GuangdongStationCatalogTool(LLMTool):
    """广东运维站点目录查询工具"""

    def __init__(self, provider: GuangdongStationCatalogProvider | None = None) -> None:
        self._provider = provider or GuangdongStationCatalogProvider()
        function_schema = {
            "name": "guangdong_station_catalog",
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
                        "description": "站点编码列表（station_code、unique_code 或 station_id，精确匹配）",
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表（如 广州、深圳市），展开该城市下辖站点",
                    },
                    "station_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点类型列表：国控站/省控站/市控站/乡镇站/区域站/省建站/VOC站/组分站（或 全部）",
                    },
                    "operation_units": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "运维单位名称列表（模糊匹配），反查该单位负责的站点",
                    },
                    "managers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "运维人员姓名列表（模糊匹配），反查该人员负责的站点",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "全局模糊关键字，匹配名称/编码/地址/城市/运维单位/人员",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"返回条数上限，默认 {DEFAULT_LIMIT}，最大 {MAX_LIMIT}",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["lookup", "refresh"],
                        "description": "lookup 查询目录（默认）；refresh 强制从 mart 重建目录缓存（缓存 24 小时，平时无需调用）",
                    },
                },
            },
        }

        super().__init__(
            name="guangdong_station_catalog",
            description="Resolve Guangdong ops station directory (info, city, operation unit, managers)",
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
        station_types: list[str] | None = None,
        operation_units: list[str] | None = None,
        managers: list[str] | None = None,
        keyword: str | None = None,
        limit: int | None = None,
        action: str = "lookup",
        **_: Any,
    ) -> dict[str, Any]:
        if action == "refresh":
            return await self._refresh()
        try:
            requested_limit = self._normalize_limit(limit)
            items, catalog = await self._provider.resolve_legacy(
                stations=stations,
                station_codes=station_codes,
                cities=cities,
                station_types=station_types,
                operation_units=operation_units,
                managers=managers,
                keyword=keyword,
                limit=requested_limit,
                refresh=False,
            )
        except StationCatalogError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "guangdong_station_catalog_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))

        metadata = self._metadata(catalog, len(items))
        if not items:
            requested = (
                list(stations or [])
                + list(station_codes or [])
                + list(cities or [])
                + list(operation_units or [])
                + list(managers or [])
            )
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    **metadata,
                    "unresolved": requested,
                    "available_cities": available_cities(catalog),
                    "message": "目录中未匹配到站点",
                },
                "summary": (
                    f"未匹配到站点 {requested}；可用城市：{'、'.join(available_cities(catalog))}。"
                    "可只用名称简称重试、按城市展开，或用 keyword 全局模糊查找。"
                ),
            }

        has_component = any(
            item.get("station_category") == "component" for item in items
        )
        result_main = sum(
            1 for item in items if item.get("station_category") != "component"
        )
        truncated = catalog.get("station_count", 0) > len(items) and (
            requested_limit is not None and len(items) >= requested_limit
        )
        scope = (
            f"（主网 {result_main} + 组分网 {len(items) - result_main}）"
            if has_component
            else ""
        )
        summary_parts = [f"解析到 {len(items)} 个站点{scope}"]
        if has_component:
            summary_parts.append(
                "组分站无经纬度/运维单位/运维人员（源系统未提供），相关字段为空属预期"
            )
        if metadata["generated_time"]:
            summary_parts.append(f"数据截至 {metadata['generated_time']}")
        if truncated:
            summary_parts.append(
                f"已达返回上限 {requested_limit} 条，可用 limit 参数调大或缩小过滤条件"
            )
        return {
            "status": "success",
            "success": True,
            "data": items,
            "metadata": metadata,
            "summary": "；".join(summary_parts) + "。",
        }

    async def _refresh(self) -> dict[str, Any]:
        try:
            catalog = await self._provider.load_catalog(refresh=True)
        except StationCatalogError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "guangdong_station_catalog_refresh_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(f"站点目录重建失败: {exc}")
        return {
            "status": "success",
            "success": True,
            "data": None,
            "metadata": self._metadata(catalog, int(catalog.get("station_count") or 0)),
            "summary": (
                f"站点目录已从 mart 重建：{catalog.get('station_count')} 站"
                f"（主网 {catalog.get('main_net_count')} + 组分网 {catalog.get('component_count')}）"
                + (
                    f"，已屏蔽停用站 {catalog.get('masked_inactive_count')} 个"
                    if int(catalog.get("masked_inactive_count") or 0)
                    else ""
                )
                + "。"
            ),
        }

    @staticmethod
    def _normalize_limit(limit: int | None) -> int | None:
        if limit is None:
            return DEFAULT_LIMIT
        try:
            value = int(limit)
        except (TypeError, ValueError):
            return DEFAULT_LIMIT
        return max(1, min(value, MAX_LIMIT))

    @staticmethod
    def _metadata(catalog: dict[str, Any], station_count: int) -> dict[str, Any]:
        generated_at = catalog.get("generated_at")
        generated_time = (
            datetime.fromtimestamp(float(generated_at)).strftime("%Y-%m-%d %H:%M")
            if generated_at
            else ""
        )
        return {
            "tool_name": "guangdong_station_catalog",
            "station_count": station_count,
            "directory_total": int(catalog.get("station_count") or 0),
            "main_net_count": int(catalog.get("main_net_count") or 0),
            "component_count": int(catalog.get("component_count") or 0),
            "masked_inactive_count": int(catalog.get("masked_inactive_count") or 0),
            "from_cache": bool(catalog.get("from_cache")),
            "generated_time": generated_time,
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
