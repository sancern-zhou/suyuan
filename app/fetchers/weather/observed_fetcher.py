"""
Observed Weather Data Fetcher

定时获取实时观测气象数据并存入数据库
"""
from typing import List
from datetime import datetime
import asyncio
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.db.repositories.weather_repo import WeatherRepository

logger = structlog.get_logger()


class ObservedDataPoint:
    """观测数据点（用于传递数据）"""

    def __init__(
        self,
        station_id: str,
        time: datetime,
        lat: float = None,               # ← 新增
        lon: float = None,               # ← 新增
        station_name: str = None,        # ← 新增
        temperature_2m: float = None,
        relative_humidity_2m: float = None,
        dew_point_2m: float = None,
        wind_speed_10m: float = None,
        wind_direction_10m: float = None,
        surface_pressure: float = None,
        precipitation: float = None,
        cloud_cover: float = None,
        visibility: float = None,
        data_source: str = "Open-Meteo",
        data_quality: str = "good"
    ):
        self.station_id = station_id
        self.time = time
        self.lat = lat                    # ← 新增
        self.lon = lon                    # ← 新增
        self.station_name = station_name  # ← 新增
        self.temperature_2m = temperature_2m
        self.relative_humidity_2m = relative_humidity_2m
        self.dew_point_2m = dew_point_2m
        self.wind_speed_10m = wind_speed_10m
        self.wind_direction_10m = wind_direction_10m
        self.surface_pressure = surface_pressure
        self.precipitation = precipitation
        self.cloud_cover = cloud_cover
        self.visibility = visibility
        self.data_source = data_source
        self.data_quality = data_quality

    def to_dict(self):
        """转换为字典（用于数据库存储）"""
        return {
            "station_id": self.station_id,
            "time": self.time,
            "lat": self.lat,                      # ← 新增
            "lon": self.lon,                      # ← 新增
            "station_name": self.station_name,    # ← 新增
            "temperature_2m": self.temperature_2m,
            "relative_humidity_2m": self.relative_humidity_2m,
            "dew_point_2m": self.dew_point_2m,
            "wind_speed_10m": self.wind_speed_10m,
            "wind_direction_10m": self.wind_direction_10m,
            "surface_pressure": self.surface_pressure,
            "precipitation": self.precipitation,
            "cloud_cover": self.cloud_cover,
            "visibility": self.visibility,
            "data_source": self.data_source,
            "data_quality": self.data_quality,
        }


class ObservedWeatherFetcher(DataFetcher):
    """
    实时观测数据获取后台

    功能：
    - 每小时运行一次
    - 获取所有活跃站点的当前观测数据
    - 存入数据库
    """

    def __init__(self):
        super().__init__(
            name="observed_weather_fetcher",
            description="Observed weather data fetcher",
            schedule="0 * * * *",  # 每小时整点
            version="1.0.0"
        )
        self.client = OpenMeteoClient()
        self.repo = WeatherRepository()

    async def fetch_and_store(self):
        """
        获取并存储观测数据

        工作流程：
        1. 获取活跃站点
        2. 遍历站点
        3. 调用 API 获取当前观测数据
        4. 存入数据库
        """
        current_time = datetime.now()

        logger.info("starting_observed_weather_fetch", time=current_time.isoformat())

        try:
            # 1. 获取活跃站点
            stations = await self.repo.get_active_stations()

            if not stations:
                logger.warning("no_active_stations_found")
                return

            logger.info("stations_fetched", count=len(stations))

            success_count = 0
            failed_count = 0

            # 2. 遍历站点
            for station in stations:
                try:
                    # 调用 API 获取当前天气
                    data = await self.client.fetch_current_weather(
                        lat=station.lat,
                        lon=station.lon
                    )

                    # 解析并构造数据点
                    data_point = self._parse_current_data(
                        station_id=station.station_id,
                        data=data,
                        lat=station.lat,                  # ← 新增
                        lon=station.lon,                  # ← 新增
                        station_name=station.station_name # ← 新增
                    )

                    if data_point:
                        # 存入数据库
                        success = await self.repo.save_observed_data(data_point)

                        if success:
                            success_count += 1
                        else:
                            failed_count += 1

                    # 避免 API 限流
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(
                        "observed_station_fetch_failed",
                        station_id=station.station_id,
                        lat=station.lat,
                        lon=station.lon,
                        error=str(e)
                    )
                    failed_count += 1

            logger.info(
                "observed_weather_fetch_complete",
                time=current_time.isoformat(),
                success=success_count,
                failed=failed_count,
                total=len(stations)
            )

        except Exception as e:
            logger.error(
                "observed_weather_fetch_error",
                time=current_time.isoformat(),
                error=str(e)
            )

    def _parse_current_data(
        self,
        station_id: str,
        data: dict,
        lat: float = None,           # ← 新增
        lon: float = None,           # ← 新增
        station_name: str = None     # ← 新增
    ) -> ObservedDataPoint:
        """
        解析 Open-Meteo API 返回的当前天气数据

        Args:
            station_id: 站点ID
            data: API响应数据
            lat: 站点纬度
            lon: 站点经度
            station_name: 站点名称

        Returns:
            ObservedDataPoint: 观测数据点
        """
        try:
            current = data.get("current", {})

            # 时间字符串转换
            time_str = current.get("time")
            if not time_str:
                logger.warning("no_time_in_current_data", station_id=station_id)
                return None

            # 解析时间
            time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

            # 构造数据点
            data_point = ObservedDataPoint(
                station_id=station_id,
                time=time,
                lat=lat,                          # ← 新增
                lon=lon,                          # ← 新增
                station_name=station_name,        # ← 新增
                temperature_2m=current.get("temperature_2m"),
                relative_humidity_2m=current.get("relative_humidity_2m"),
                dew_point_2m=current.get("dew_point_2m"),
                wind_speed_10m=current.get("wind_speed_10m"),
                wind_direction_10m=current.get("wind_direction_10m"),
                surface_pressure=current.get("surface_pressure"),
                precipitation=current.get("precipitation"),
                cloud_cover=current.get("cloud_cover"),
                data_source="Open-Meteo",
                data_quality="good"
            )

            return data_point

        except Exception as e:
            logger.error(
                "parse_current_data_failed",
                station_id=station_id,
                error=str(e)
            )
            return None
