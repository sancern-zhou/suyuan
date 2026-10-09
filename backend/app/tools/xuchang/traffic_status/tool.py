"""许昌站点周边实时路况查询工具

接入百度地图实时路况查询（Traffic API），供专家/问数模式研判
站点周边交通活动对空气质量的扰动：
- around：以经纬度为圆心的圆形区域路况（radius 上限 1000 米）
- road：按道路名称查询单条道路的双向路况

坐标来源必须可信（resolve_station_geo / xuchang_station_catalog / 用户给定），
返回整体路况评价与逐条道路拥堵明细；数据分钟级更新，仅代表查询时刻状态。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .client import BaiduTrafficClient, BaiduTrafficError

logger = structlog.get_logger()


class XuchangTrafficStatusTool(LLMTool):
    """许昌站点周边实时路况查询工具"""

    def __init__(self, client: BaiduTrafficClient | None = None) -> None:
        self._client = client
        function_schema = {
            "name": "query_xuchang_traffic_status",
            "description": (
                "许昌站点周边实时路况查询（百度地图实时路况查询 Traffic API，分钟级更新）。"
                "query_type=around 查询经纬度周边圆形区域：返回整体路况评价（畅通/缓行/拥堵/严重拥堵）、"
                "路况文字综述与范围内逐条道路的拥堵路段明细；query_type=road 按道路名称"
                "（road_name 如 建安大道，city 默认许昌市）查询单条道路的双向路况与拥堵距离。"
                "经纬度必须来自 resolve_station_geo、xuchang_station_catalog 或用户明确提供，"
                "禁止编造；coord_type 标明传入坐标系：wgs84（GPS，站点目录坐标通常是它）、"
                "gcj02（国测局，地图取点坐标）。radius 取值 1~1000 米，road_grade 可按道路等级过滤"
                "（0全部 1高速 2环路快速路 3主干路 4次干路 5支路）。"
                "注意：平均车速、拥堵距离、10分钟趋势仅在存在拥堵路段时返回，"
                "全畅通时只有整体评价与道路清单；结果仅代表查询时刻，不可当作历史规律。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["around", "road"],
                        "description": "around 圆形区域路况（默认）；road 指定道路路况",
                    },
                    "latitude": {
                        "type": "number",
                        "description": "中心点纬度（query_type=around 必填）",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "中心点经度（query_type=around 必填）",
                    },
                    "coord_type": {
                        "type": "string",
                        "enum": ["wgs84", "gcj02", "bd09ll"],
                        "description": "传入经纬度的坐标系，默认 wgs84",
                    },
                    "radius": {
                        "type": "number",
                        "description": "查询半径（米），1~1000，默认 1000",
                    },
                    "road_grade": {
                        "type": "number",
                        "description": "道路等级过滤：0全部（默认）、1高速、2环路快速路、3主干路、4次干路、5支路",
                    },
                    "road_name": {
                        "type": "string",
                        "description": "道路名称（query_type=road 必填，如 建安大道）",
                    },
                    "city": {
                        "type": "string",
                        "description": "城市（query_type=road 时有效，默认 许昌市）",
                    },
                },
            },
        }

        super().__init__(
            name="query_xuchang_traffic_status",
            description="Query real-time traffic status around Xuchang stations (Baidu Traffic API)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        query_type: str = "around",
        latitude: float | None = None,
        longitude: float | None = None,
        coord_type: str = "wgs84",
        radius: int = 1000,
        road_grade: int = 0,
        road_name: str | None = None,
        city: str = "许昌市",
        **_: Any,
    ) -> dict[str, Any]:
        client = self._client or BaiduTrafficClient()
        try:
            if query_type == "around":
                if latitude is None or longitude is None:
                    return self._failed("query_type=around 时必须提供 latitude 与 longitude")
                payload = await client.query_around(
                    latitude=latitude,
                    longitude=longitude,
                    radius=int(radius),
                    coord_type=coord_type if coord_type in ("wgs84", "gcj02", "bd09ll") else "wgs84",
                    road_grade=int(road_grade),
                )
                return self._format_around(payload, latitude, longitude, radius, coord_type)
            if query_type == "road":
                if not road_name:
                    return self._failed("query_type=road 时必须提供 road_name")
                payload = await client.query_road(road_name=road_name, city=city)
                return self._format_road(payload, road_name, city)
            return self._failed(f"未知 query_type: {query_type}")
        except BaiduTrafficError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "xuchang_traffic_status_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))

    def _format_around(
        self,
        payload: dict[str, Any],
        latitude: float,
        longitude: float,
        radius: int,
        coord_type: str,
    ) -> dict[str, Any]:
        evaluation = payload.get("evaluation") or {}
        status_desc = evaluation.get("status_desc") or self._status_text(evaluation.get("status"))
        roads_raw = payload.get("road_traffic") or []
        roads = [
            {
                "road_name": item.get("road_name"),
                "congestion_sections": item.get("congestion_sections") or [],
            }
            for item in roads_raw
        ]
        sections = [sec for road in roads for sec in road["congestion_sections"]]

        summary = f"周边 {radius} 米范围整体路况：{status_desc}。共 {len(roads)} 条道路"
        if sections:
            summary += f"，其中 {len(sections)} 个拥堵路段（明细含车速、拥堵距离与10分钟趋势）"
        else:
            summary += "，当前无拥堵路段（车速等明细仅在拥堵时返回）"

        return {
            "status": "success",
            "success": True,
            "data": {
                "query_type": "around",
                "center": {"latitude": round(float(latitude), 6), "longitude": round(float(longitude), 6)},
                "coord_type_input": coord_type,
                "coord_type_output": "gcj02",
                "radius": int(radius),
                "evaluation": evaluation,
                "description": payload.get("description", ""),
                "roads": roads,
                "queried_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
            "metadata": {
                "tool_name": self.name,
                "source": "baidu_traffic_api",
                "road_count": len(roads),
                "congestion_section_count": len(sections),
            },
            "summary": summary,
        }

    def _format_road(
        self,
        payload: dict[str, Any],
        road_name: str,
        city: str,
    ) -> dict[str, Any]:
        evaluation = payload.get("evaluation") or {}
        status_desc = evaluation.get("status_desc") or self._status_text(evaluation.get("status"))
        sections = payload.get("congestion_sections") or []

        summary = f"{city} {road_name}：{status_desc}"
        if sections:
            summary += f"，{len(sections)} 个拥堵路段（明细含车速、拥堵距离与10分钟趋势）"
        else:
            summary += "，当前无拥堵路段"

        return {
            "status": "success",
            "success": True,
            "data": {
                "query_type": "road",
                "city": city,
                "road_name": road_name,
                "evaluation": evaluation,
                "description": payload.get("description", ""),
                "congestion_sections": sections,
                "queried_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
            "metadata": {
                "tool_name": self.name,
                "source": "baidu_traffic_api",
                "congestion_section_count": len(sections),
            },
            "summary": summary,
        }

    @staticmethod
    def _status_text(status: Any) -> str:
        return {0: "未知", 1: "畅通", 2: "缓行", 3: "拥堵", 4: "严重拥堵"}.get(status, "未知")

    def _failed(self, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {"tool_name": self.name},
            "summary": f"路况查询失败: {message}",
        }
