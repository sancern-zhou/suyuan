"""
Get Current Weather Tool

LLM可调用的当前天气查询工具

功能：
- 实时调用 Open-Meteo Current Weather API
- 返回指定位置的当前实时天气状况
- 包含温度、湿度、风速、降水等实时数据
"""
from typing import Dict, Any, Optional
from datetime import datetime
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.external_apis.openmeteo_client import OpenMeteoClient

logger = structlog.get_logger()


class GetCurrentWeatherTool(LLMTool):
    """
    当前天气查询工具

    给LLM提供获取当前实时天气的能力
    注意：此工具实时调用API，不从数据库读取
    """

    def __init__(self):
        function_schema = {
            "name": "get_current_weather",
            "description": "获取指定位置的当前实时天气状况，包含温度、湿度、风速、降水、气压等实时气象要素",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "纬度"
                    },
                    "lon": {
                        "type": "number",
                        "description": "经度"
                    },
                    "location_name": {
                        "type": "string",
                        "description": "位置名称（用于显示）"
                    }
                },
                "required": ["lat", "lon"]
            }
        }

        super().__init__(
            name="get_current_weather",
            description="Get current weather conditions (real-time API call)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.client = OpenMeteoClient()

    async def execute(
        self,
        lat: float,
        lon: float,
        location_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行当前天气查询

        Args:
            lat: 纬度
            lon: 经度
            location_name: 位置名称（用于显示）

        Returns:
            Dict: 当前天气数据，包含：
                - location: 位置信息
                - current: 当前天气数据
                - observation_time: 观测时间
        """
        try:
            logger.info(
                "current_weather_query_started",
                lat=lat,
                lon=lon,
                location=location_name
            )

            # 实时调用 API（不从数据库读取）
            weather_data = await self.client.fetch_current_weather(
                lat=lat,
                lon=lon
            )

            # 解析并格式化数据
            result = self._format_current_weather(
                weather_data=weather_data,
                lat=lat,
                lon=lon,
                location_name=location_name
            )

            logger.info(
                "current_weather_query_successful",
                lat=lat,
                lon=lon,
                temperature=result.get("current", {}).get("temperature_2m")
            )

            return result

        except Exception as e:
            logger.error(
                "current_weather_query_failed",
                lat=lat,
                lon=lon,
                error=str(e),
                exc_info=True
            )
            # 返回 UDF v2.0 错误格式
            from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                data=[],
                metadata=DataMetadata(
                    data_id=f"current_weather_error:{id(e)}",
                    data_type=DataType.WEATHER,
                    schema_version="v2.0",  # ✅ UDF v2.0 标记
                    lat=lat,
                    lon=lon,
                    source="Open-Meteo Current Weather API",
                    scenario="current_weather_query",
                    generator="get_current_weather"
                ),
                summary=f"❌ 当前天气查询失败: {str(e)}",
                legacy_fields={
                    "location": {
                        "lat": lat,
                        "lon": lon,
                        "name": location_name
                    }
                }
            ).dict()

    def _format_current_weather(
        self,
        weather_data: Dict[str, Any],
        lat: float,
        lon: float,
        location_name: Optional[str]
    ) -> Dict[str, Any]:
        """
        格式化当前天气数据（UDF v2.0标准格式）

        Args:
            weather_data: API返回的原始数据
            lat: 纬度
            lon: 经度
            location_name: 位置名称

        Returns:
            Dict: UDF v2.0格式的当前天气数据
        """
        from app.schemas.unified import UnifiedData, DataStatus, DataType, DataMetadata, UnifiedDataRecord
        import math

        current = weather_data.get("current", {})

        # 构建UnifiedDataRecord，处理None值
        def safe_float(value):
            """安全转换为float，处理None值"""
            if value is None:
                return math.nan
            return value

        record = UnifiedDataRecord(
            timestamp=current.get("time", datetime.now().isoformat()),
            lat=lat,
            lon=lon,
            measurements={
                "temperature_2m": safe_float(current.get("temperature_2m")),
                "relative_humidity_2m": safe_float(current.get("relative_humidity_2m")),
                "apparent_temperature": safe_float(current.get("apparent_temperature")),
                "is_day": current.get("is_day"),
                "precipitation": safe_float(current.get("precipitation")),
                "rain": safe_float(current.get("rain")),
                "showers": safe_float(current.get("showers")),
                "snowfall": safe_float(current.get("snowfall")),
                "weather_code": current.get("weather_code"),
                "cloud_cover": safe_float(current.get("cloud_cover")),
                "surface_pressure": safe_float(current.get("surface_pressure")),
                "wind_speed_10m": safe_float(current.get("wind_speed_10m")),
                "wind_direction_10m": safe_float(current.get("wind_direction_10m")),
                "wind_gusts_10m": safe_float(current.get("wind_gusts_10m")),
            }
        )

        # 构建元数据
        metadata = DataMetadata(
            data_id=f"current_weather:{lat}:{lon}:{datetime.now().strftime('%Y%m%d%H%M%S')}",
            data_type=DataType.WEATHER,
            schema_version="v2.0",  # ✅ UDF v2.0 标记
            record_count=1,
            lat=lat,
            lon=lon,
            source="Open-Meteo Current Weather API",
            quality_score=0.9,
            # v2.0 新增字段
            scenario="current_weather_query",
            generator="get_current_weather"
        )

        # 构建摘要
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_speed = current.get("wind_speed_10m")
        summary = f"✅ 获取 {location_name or f'({lat}, {lon})'} 当前天气数据成功"
        if temp is not None:
            summary += f"：温度 {temp}°C"
        if humidity is not None:
            summary += f"，湿度 {humidity}%"
        if wind_speed is not None:
            summary += f"，风速 {wind_speed}km/h"

        # 返回UDF v2.0标准格式
        return UnifiedData(
            status=DataStatus.SUCCESS,
            success=True,
            data=[record],
            metadata=metadata,
            summary=summary,
            legacy_fields={
                "location": {
                    "lat": lat,
                    "lon": lon,
                    "name": location_name or f"({lat}, {lon})"
                },
                "observation_time": current.get("time", datetime.now().isoformat()),
                "data_source": "Open-Meteo Current Weather API",
                "timezone": weather_data.get("timezone", "UTC"),
                "elevation": weather_data.get("elevation"),
            }
        ).dict()
