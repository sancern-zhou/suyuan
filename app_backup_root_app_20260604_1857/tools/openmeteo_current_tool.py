"""
Open-Meteo Observed Weather Tool.

使用 Open-Meteo Current Weather API 获取实时观测数据
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
import structlog

from app.tools.observed_weather_tool import (
    ObservedWeatherTool,
    ObservedDataPoint,
    DataQuality
)

logger = structlog.get_logger()


class OpenMeteoCurrentTool(ObservedWeatherTool):
    """
    Open-Meteo 实时观测数据工具

    优势:
    - 完全免费，无需API Key
    - 免费额度: 10,000次/天
    - 数据格式统一
    - 全球覆盖
    """

    def __init__(self):
        super().__init__(
            name="openmeteo_current",
            description="Open-Meteo实时观测数据（免费，无需API Key）"
        )
        self.api_url = "https://api.open-meteo.com/v1/forecast"
        self.timeout = 10

    async def fetch_current(
        self,
        lat: float,
        lon: float,
        station_id: Optional[str] = None
    ) -> Optional[ObservedDataPoint]:
        """
        获取实时观测数据

        Args:
            lat: 纬度
            lon: 经度
            station_id: 站点ID（可选，仅用于标识）

        Returns:
            ObservedDataPoint 或 None
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "cloud_cover",
                "pressure_msl",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m"
            ],
            "timezone": "UTC"  # 使用UTC时间统一存储
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.api_url, params=params)

            if response.status_code != 200:
                logger.error(
                    "openmeteo_current_api_error",
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return None

            data = response.json()
            current = data.get("current", {})

            if not current:
                logger.warning("openmeteo_current_no_data", lat=lat, lon=lon)
                return None

            # 解析时间（ISO格式）
            time_str = current.get("time")
            if time_str:
                time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                time = datetime.utcnow()

            # 生成站点ID（如果未提供）
            if not station_id:
                station_id = f"openmeteo_{lat:.2f}_{lon:.2f}"

            # 转换为标准格式
            data_point = ObservedDataPoint(
                time=time,
                station_id=station_id,
                station_name=None,  # Open-Meteo不提供站点名称
                lat=data.get("latitude", lat),
                lon=data.get("longitude", lon),
                temperature_2m=current.get("temperature_2m"),
                relative_humidity_2m=current.get("relative_humidity_2m"),
                dew_point_2m=None,  # Open-Meteo Current不提供露点
                wind_speed_10m=current.get("wind_speed_10m"),
                wind_direction_10m=current.get("wind_direction_10m"),
                surface_pressure=current.get("surface_pressure"),
                precipitation=current.get("precipitation"),
                cloud_cover=current.get("cloud_cover"),
                visibility=None,  # Current API不提供能见度
                data_source="openmeteo_current",
                data_quality=DataQuality.GOOD,  # 模型数据，质量良好
                raw_data=current  # 保留原始数据
            )

            logger.info(
                "openmeteo_current_fetched",
                station_id=station_id,
                time=time.isoformat(),
                temp=data_point.temperature_2m
            )

            return data_point

        except httpx.TimeoutException:
            logger.error("openmeteo_current_timeout", lat=lat, lon=lon)
            return None
        except Exception as e:
            logger.error(
                "openmeteo_current_error",
                lat=lat,
                lon=lon,
                error=str(e)
            )
            return None

    async def fetch_historical(
        self,
        lat: float,
        lon: float,
        date: str,
        station_id: Optional[str] = None
    ) -> List[ObservedDataPoint]:
        """
        获取历史观测数据（使用Archive API）

        注意: Open-Meteo Archive API 提供的是ERA5再分析数据，
             不是实际观测值，这里返回空列表，让其他工具处理
        """
        logger.info(
            "openmeteo_current_skip_historical",
            reason="use_archive_api_instead"
        )
        return []

    def get_metadata(self) -> Dict[str, Any]:
        """获取工具元数据"""
        return {
            "name": self.name,
            "description": self.description,
            "version": "1.0.0",
            "provider": "Open-Meteo",
            "api_url": self.api_url,
            "requires_key": False,
            "api_limit": "10,000 requests/day",
            "data_quality": "good",
            "data_type": "model_based",  # 基于数值模型
            "supported_variables": [
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "wind_direction_10m",
                "surface_pressure",
                "precipitation",
                "cloud_cover"
            ],
            "coverage": "global",
            "temporal_resolution": "hourly",
            "update_frequency": "15 minutes",
            "notes": "免费、无需API Key、全球覆盖"
        }


# 工具实例
openmeteo_current_tool = OpenMeteoCurrentTool()
