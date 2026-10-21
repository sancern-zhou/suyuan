"""
附近站点查询工具 (GetNearbyStationsTool)

根据参考站点名称查询周边一定范围内的站点信息，结果来自站点查询服务真实接口。
"""

from typing import Dict, Any, Optional
import structlog

from app.services.external_apis import StationAPIClient
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class GetNearbyStationsTool(LLMTool):
    """
    附近站点查询工具

    功能：
    1. 根据参考站点名称查询周边站点
    2. 支持自定义搜索半径与返回数量
    """

    def __init__(self):
        function_schema = {
            "name": "get_nearby_stations",
            "description": "根据参考站点名称查询周边一定范围内的站点信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "station_name": {
                        "type": "string",
                        "description": "参考站点名称，支持模糊匹配"
                    },
                    "max_distance": {
                        "type": "number",
                        "description": "最大距离（公里），默认10",
                        "default": 10.0
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返回站点数量上限，默认5",
                        "default": 5
                    }
                },
                "required": ["station_name"]
            }
        }

        super().__init__(
            name="get_nearby_stations",
            description="根据参考站点名称查询周边站点信息",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

        self._client = StationAPIClient()

    async def execute(
        self,
        station_name: str,
        max_distance: float = 10.0,
        max_results: int = 5
    ) -> Dict[str, Any]:
        """
        执行附近站点查询

        Args:
            station_name: 参考站点名称
            max_distance: 最大距离（公里），默认10
            max_results: 返回数量上限，默认5

        Returns:
            包含附近站点列表的字典
        """
        name = str(station_name or "").strip()
        if not name:
            return {
                "success": False,
                "status": "error",
                "error": "station_name is required",
                "data": {"stations": []},
                "summary": "查询失败: 缺少参考站点名称",
            }
        try:
            nearby_stations = await self._client.get_nearby_stations(
                name, max_distance=max_distance, max_results=max_results
            )

            result = {
                "success": True,
                "status": "success",
                "data": {
                    "reference_station": name,
                    "search_radius_km": max_distance,
                    "station_count": len(nearby_stations),
                    "stations": nearby_stations,
                },
                "summary": f"查询到 {len(nearby_stations)} 个附近站点",
            }

            logger.info(
                "nearby_stations_queried",
                station_name=name,
                max_distance=max_distance,
                station_count=len(nearby_stations),
            )

            return result

        except Exception as e:
            logger.error(
                "nearby_stations_query_failed",
                station_name=name,
                error=str(e),
            )
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "data": {"stations": []},
                "summary": f"查询失败: {str(e)}",
            }
