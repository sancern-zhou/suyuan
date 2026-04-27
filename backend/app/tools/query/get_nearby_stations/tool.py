"""
附近站点查询工具 (GetNearbyStationsTool)

根据目标站点查询周边一定范围内的所有站点信息。
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class StationInfo(BaseModel):
    """站点信息模型"""
    station_id: str = Field(..., description="站点ID")
    station_name: str = Field(..., description="站点名称")
    city: str = Field(..., description="城市名称")
    latitude: float = Field(..., description="纬度")
    longitude: float = Field(..., description="经度")
    distance_km: float = Field(..., description="距离目标站点的距离（公里）")
    direction: Optional[str] = Field(None, description="相对方向（N/NE/E/SE/S/SW/W/NW）")


class GetNearbyStationsTool(LLMTool):
    """
    附近站点查询工具

    功能：
    1. 根据目标站点坐标查询周边站点
    2. 计算距离和方向
    3. 支持自定义搜索半径
    """

    # ✅ 输入适配器规则（支持宽进严出）
    TOOL_RULES = {
        "field_mapping": {
            # 支持多种参数名称映射
            "target_lat": ["lat", "latitude", "target_lat"],
            "target_lon": ["lon", "longitude", "target_lon"],
            "radius_km": ["radius", "radius_km", "range"],
            "station_type": ["station_type", "type"]
        },
        "default_values": {
            "radius_km": 50.0,
            "station_type": None
        }
    }

    def __init__(self):
        """初始化工具"""
        function_schema = {
            "name": "get_nearby_stations",
            "description": "查询附近的站点信息（根据坐标和半径）",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_lat": {
                        "type": "number",
                        "description": "目标站点纬度"
                    },
                    "target_lon": {
                        "type": "number",
                        "description": "目标站点经度"
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "搜索半径（公里），默认50",
                        "default": 50.0
                    },
                    "station_type": {
                        "type": "string",
                        "description": "站点类型过滤（可选）"
                    }
                },
                "required": ["target_lat", "target_lon"]
            }
        }

        super().__init__(
            name="get_nearby_stations",
            description="查询附近的站点信息（根据坐标和半径）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

        self._station_cache: Dict[str, List[Dict[str, Any]]] = {}

    async def execute(
        self,
        target_lat: float,
        target_lon: float,
        radius_km: float = 50.0,
        station_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行附近站点查询

        Args:
            target_lat: 目标站点纬度
            target_lon: 目标站点经度
            radius_km: 搜索半径（公里），默认50km
            station_type: 站点类型过滤（可选）

        Returns:
            包含附近站点列表的字典
        """
        try:
            # TODO: 这里应该调用实际的站点查询API或数据库
            # 当前返回模拟数据
            nearby_stations = await self._query_nearby_stations(
                target_lat, target_lon, radius_km, station_type
            )

            result = {
                "success": True,
                "status": "success",
                "data": {
                    "target_location": {
                        "latitude": target_lat,
                        "longitude": target_lon
                    },
                    "search_radius_km": radius_km,
                    "station_count": len(nearby_stations),
                    "stations": nearby_stations
                },
                "summary": f"查询到 {len(nearby_stations)} 个附近站点"
            }

            logger.info(
                "nearby_stations_queried",
                target_lat=target_lat,
                target_lon=target_lon,
                radius_km=radius_km,
                station_count=len(nearby_stations)
            )

            return result

        except Exception as e:
            logger.error(
                "nearby_stations_query_failed",
                target_lat=target_lat,
                target_lon=target_lon,
                error=str(e)
            )
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "data": {"stations": []},
                "summary": f"查询失败: {str(e)}"
            }

    async def _query_nearby_stations(
        self,
        target_lat: float,
        target_lon: float,
        radius_km: float,
        station_type: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        查询附近站点（内部方法）

        Args:
            target_lat: 目标纬度
            target_lon: 目标经度
            radius_km: 搜索半径
            station_type: 站点类型

        Returns:
            站点信息列表
        """
        # TODO: 实现实际的站点查询逻辑
        # 这里应该调用：
        # 1. 广东省站点API
        # 2. 或者查询站点数据库
        # 3. 或者读取站点配置文件

        # 当前返回空列表，需要后续实现
        return []

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        计算两点间距离（Haversine公式）

        Args:
            lat1, lon1: 点1坐标
            lat2, lon2: 点2坐标

        Returns:
            距离（公里）
        """
        import math

        R = 6371.0  # 地球半径（公里）

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _calculate_direction(self, lat1: float, lon1: float, lat2: float, lon2: float) -> str:
        """
        计算方向角

        Args:
            lat1, lon1: 点1坐标
            lat2, lon2: 点2坐标

        Returns:
            方向（N/NE/E/SE/S/SW/W/NW）
        """
        import math

        delta_lon = math.radians(lon2 - lon1)
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)

        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
             math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))

        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360

        # 转换为8方向
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = round(bearing / 45) % 8

        return directions[index]
