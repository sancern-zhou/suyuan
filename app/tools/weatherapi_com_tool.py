"""
WeatherAPI.com Observed Weather Tool.

使用 WeatherAPI.com API 获取观测数据
需要免费API Key: https://www.weatherapi.com/signup.aspx
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
import structlog
import os

from app.tools.observed_weather_tool import (
    ObservedWeatherTool,
    ObservedDataPoint,
    DataQuality
)

logger = structlog.get_logger()


class WeatherAPIDotComTool(ObservedWeatherTool):
    """
    WeatherAPI.com 观测数据工具

    优势:
    - 免费额度大: 1,000,000次/月
    - 数据字段丰富
    - 支持实时和历史数据

    劣势:
    - 需要API Key
    - 历史数据需要付费计划
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            name="weatherapi_com",
            description="WeatherAPI.com观测数据（需要API Key）"
        )

        # 从环境变量或参数获取API Key
        self.api_key = api_key or os.getenv("WEATHERAPI_KEY")

        self.current_url = "http://api.weatherapi.com/v1/current.json"
        self.history_url = "http://api.weatherapi.com/v1/history.json"
        self.timeout = 10

        # 如果没有API Key，禁用工具
        if not self.api_key:
            self.enabled = False
            logger.warning(
                "weatherapi_disabled",
                reason="no_api_key",
                hint="Set WEATHERAPI_KEY in .env"
            )

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
            station_id: 站点ID（可选）

        Returns:
            ObservedDataPoint 或 None
        """
        if not self.api_key:
            logger.error("weatherapi_no_api_key")
            return None

        params = {
            "key": self.api_key,
            "q": f"{lat},{lon}",
            "aqi": "no"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.current_url, params=params)

            if response.status_code == 401:
                logger.error("weatherapi_invalid_api_key")
                self.enabled = False  # 自动禁用
                return None

            if response.status_code != 200:
                logger.error(
                    "weatherapi_api_error",
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return None

            data = response.json()
            location = data.get("location", {})
            current = data.get("current", {})

            if not current:
                logger.warning("weatherapi_no_data", lat=lat, lon=lon)
                return None

            # 解析时间
            last_updated = current.get("last_updated")
            if last_updated:
                # WeatherAPI格式: "2025-10-28 00:15"
                time = datetime.strptime(last_updated, "%Y-%m-%d %H:%M")
            else:
                time = datetime.utcnow()

            # 生成站点ID
            if not station_id:
                station_id = f"weatherapi_{lat:.2f}_{lon:.2f}"

            # 转换单位: 能见度 km → m
            visibility_m = None
            if current.get("vis_km"):
                visibility_m = current.get("vis_km") * 1000

            # 转换为标准格式
            data_point = ObservedDataPoint(
                time=time,
                station_id=station_id,
                station_name=location.get("name"),
                lat=location.get("lat", lat),
                lon=location.get("lon", lon),
                temperature_2m=current.get("temp_c"),
                relative_humidity_2m=current.get("humidity"),
                dew_point_2m=None,  # WeatherAPI不直接提供露点
                wind_speed_10m=current.get("wind_kph"),
                wind_direction_10m=current.get("wind_degree"),
                surface_pressure=current.get("pressure_mb"),
                precipitation=current.get("precip_mm"),
                cloud_cover=current.get("cloud"),
                visibility=visibility_m,
                data_source="weatherapi_com",
                data_quality=DataQuality.GOOD,
                raw_data=current
            )

            logger.info(
                "weatherapi_current_fetched",
                station_id=station_id,
                station_name=data_point.station_name,
                temp=data_point.temperature_2m
            )

            return data_point

        except httpx.TimeoutException:
            logger.error("weatherapi_timeout", lat=lat, lon=lon)
            return None
        except Exception as e:
            logger.error(
                "weatherapi_error",
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
        获取历史观测数据（24小时）

        注意: 免费计划不支持历史数据，需要付费计划

        Args:
            lat: 纬度
            lon: 经度
            date: 日期 (YYYY-MM-DD)
            station_id: 站点ID（可选）

        Returns:
            ObservedDataPoint列表（24小时）
        """
        if not self.api_key:
            logger.error("weatherapi_no_api_key")
            return []

        params = {
            "key": self.api_key,
            "q": f"{lat},{lon}",
            "dt": date
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.history_url, params=params)

            if response.status_code == 403:
                logger.warning(
                    "weatherapi_history_requires_paid_plan",
                    hint="History API requires paid subscription"
                )
                return []

            if response.status_code != 200:
                logger.error(
                    "weatherapi_history_api_error",
                    status_code=response.status_code
                )
                return []

            data = response.json()
            location = data.get("location", {})
            forecast = data.get("forecast", {})
            forecastday = forecast.get("forecastday", [])

            if not forecastday:
                logger.warning("weatherapi_no_historical_data", date=date)
                return []

            day_data = forecastday[0]
            hours = day_data.get("hour", [])

            if not station_id:
                station_id = f"weatherapi_{lat:.2f}_{lon:.2f}"

            data_points = []

            for hour in hours:
                # 解析时间
                time_str = hour.get("time")
                if time_str:
                    time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                else:
                    continue

                visibility_m = None
                if hour.get("vis_km"):
                    visibility_m = hour.get("vis_km") * 1000

                data_point = ObservedDataPoint(
                    time=time,
                    station_id=station_id,
                    station_name=location.get("name"),
                    lat=location.get("lat", lat),
                    lon=location.get("lon", lon),
                    temperature_2m=hour.get("temp_c"),
                    relative_humidity_2m=hour.get("humidity"),
                    dew_point_2m=None,
                    wind_speed_10m=hour.get("wind_kph"),
                    wind_direction_10m=hour.get("wind_degree"),
                    surface_pressure=hour.get("pressure_mb"),
                    precipitation=hour.get("precip_mm"),
                    cloud_cover=hour.get("cloud"),
                    visibility=visibility_m,
                    data_source="weatherapi_com",
                    data_quality=DataQuality.GOOD,
                    raw_data=hour
                )

                data_points.append(data_point)

            logger.info(
                "weatherapi_historical_fetched",
                station_id=station_id,
                date=date,
                hours=len(data_points)
            )

            return data_points

        except httpx.TimeoutException:
            logger.error("weatherapi_history_timeout", date=date)
            return []
        except Exception as e:
            logger.error(
                "weatherapi_history_error",
                date=date,
                error=str(e)
            )
            return []

    def get_metadata(self) -> Dict[str, Any]:
        """获取工具元数据"""
        return {
            "name": self.name,
            "description": self.description,
            "version": "1.0.0",
            "provider": "WeatherAPI.com",
            "api_url": self.current_url,
            "requires_key": True,
            "api_key_configured": bool(self.api_key),
            "api_limit": "1,000,000 requests/month (free tier)",
            "data_quality": "good",
            "data_type": "observed",
            "supported_variables": [
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "wind_direction_10m",
                "surface_pressure",
                "precipitation",
                "cloud_cover",
                "visibility"
            ],
            "coverage": "global",
            "temporal_resolution": "hourly",
            "update_frequency": "real-time",
            "notes": "免费额度大，但历史数据需要付费计划"
        }


# 工具实例
weatherapi_com_tool = WeatherAPIDotComTool()
