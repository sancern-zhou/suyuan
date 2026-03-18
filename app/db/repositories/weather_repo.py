"""
Weather Data Repository

气象数据仓库层，封装数据库操作
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
import structlog

from app.db.database import async_session
from app.db.models import ERA5ReanalysisData, ObservedWeatherData, WeatherStation

logger = structlog.get_logger()


class WeatherRepository:
    """气象数据仓库"""

    async def get_active_stations(self) -> List[WeatherStation]:
        """
        获取所有活跃的气象站点

        Returns:
            List[WeatherStation]: 站点列表
        """
        async with async_session() as session:
            result = await session.execute(
                select(WeatherStation).where(WeatherStation.is_active == True)
            )
            return result.scalars().all()

    async def save_era5_data(
        self,
        lat: float,
        lon: float,
        data: Dict[str, Any]
    ) -> int:
        """
        保存 ERA5 数据到数据库

        Args:
            lat: 纬度
            lon: 经度
            data: Open-Meteo API 返回的数据

        Returns:
            int: 保存的记录数
        """
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        if not times:
            logger.warning("no_time_data", lat=lat, lon=lon)
            return 0

        records = []

        for i, time_str in enumerate(times):
            # 安全获取值
            def safe_get(key, index):
                values = hourly.get(key, [])
                return values[index] if index < len(values) else None

            record = {
                "time": datetime.fromisoformat(time_str.replace("Z", "+00:00")),
                "lat": lat,
                "lon": lon,
                "temperature_2m": safe_get("temperature_2m", i),
                "relative_humidity_2m": safe_get("relative_humidity_2m", i),
                "dew_point_2m": safe_get("dew_point_2m", i),
                "wind_speed_10m": safe_get("wind_speed_10m", i),
                "wind_direction_10m": safe_get("wind_direction_10m", i),
                "wind_gusts_10m": safe_get("wind_gusts_10m", i),
                "surface_pressure": safe_get("surface_pressure", i),
                "precipitation": safe_get("precipitation", i),
                "cloud_cover": safe_get("cloud_cover", i),
                "shortwave_radiation": safe_get("shortwave_radiation", i),
                "visibility": safe_get("visibility", i),
                "boundary_layer_height": safe_get("boundary_layer_height", i),
                "data_source": "ERA5",
            }

            records.append(record)

        # 批量插入，冲突时更新
        async with async_session() as session:
            stmt = insert(ERA5ReanalysisData).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["time", "lat", "lon"],
                set_={
                    "temperature_2m": stmt.excluded.temperature_2m,
                    "relative_humidity_2m": stmt.excluded.relative_humidity_2m,
                    "dew_point_2m": stmt.excluded.dew_point_2m,
                    "wind_speed_10m": stmt.excluded.wind_speed_10m,
                    "wind_direction_10m": stmt.excluded.wind_direction_10m,
                    "wind_gusts_10m": stmt.excluded.wind_gusts_10m,
                    "surface_pressure": stmt.excluded.surface_pressure,
                    "precipitation": stmt.excluded.precipitation,
                    "cloud_cover": stmt.excluded.cloud_cover,
                    "shortwave_radiation": stmt.excluded.shortwave_radiation,
                    "visibility": stmt.excluded.visibility,
                    "boundary_layer_height": stmt.excluded.boundary_layer_height,
                }
            )

            await session.execute(stmt)
            await session.commit()

        logger.info("era5_data_saved", lat=lat, lon=lon, records=len(records))
        return len(records)

    async def era5_data_exists(
        self,
        lat: float,
        lon: float,
        date: str
    ) -> bool:
        """
        检查 ERA5 数据是否已存在

        Args:
            lat: 纬度
            lon: 经度
            date: 日期 (YYYY-MM-DD)

        Returns:
            bool: 数据是否存在
        """
        try:
            async with async_session() as session:
                start_time = datetime.fromisoformat(f"{date}T00:00:00")
                end_time = datetime.fromisoformat(f"{date}T23:59:59")

                result = await session.execute(
                    select(ERA5ReanalysisData).where(
                        ERA5ReanalysisData.lat == lat,
                        ERA5ReanalysisData.lon == lon,
                        ERA5ReanalysisData.time >= start_time,
                        ERA5ReanalysisData.time <= end_time
                    ).limit(1)
                )

                return result.first() is not None
        except Exception as e:
            logger.error("data_exists_check_failed", lat=lat, lon=lon, error=str(e))
            return False

    async def save_observed_data(
        self,
        data_point: Any  # ObservedDataPoint
    ) -> bool:
        """
        保存观测数据到数据库

        Args:
            data_point: ObservedDataPoint 实例

        Returns:
            bool: 是否保存成功
        """
        try:
            record = data_point.to_dict()

            async with async_session() as session:
                stmt = insert(ObservedWeatherData).values(record)

                # 冲突时更新
                stmt = stmt.on_conflict_do_update(
                    index_elements=["time", "station_id"],
                    set_={
                        "temperature_2m": stmt.excluded.temperature_2m,
                        "relative_humidity_2m": stmt.excluded.relative_humidity_2m,
                        "dew_point_2m": stmt.excluded.dew_point_2m,
                        "wind_speed_10m": stmt.excluded.wind_speed_10m,
                        "wind_direction_10m": stmt.excluded.wind_direction_10m,
                        "surface_pressure": stmt.excluded.surface_pressure,
                        "precipitation": stmt.excluded.precipitation,
                        "cloud_cover": stmt.excluded.cloud_cover,
                        "visibility": stmt.excluded.visibility,
                        "data_source": stmt.excluded.data_source,
                        "data_quality": stmt.excluded.data_quality,
                    }
                )

                await session.execute(stmt)
                await session.commit()

            logger.info(
                "observed_data_saved",
                station_id=data_point.station_id,
                time=data_point.time.isoformat()
            )
            return True
        except Exception as e:
            logger.error(
                "observed_data_save_failed",
                station_id=data_point.station_id,
                error=str(e)
            )
            return False

    async def get_weather_data(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        end_time: datetime
    ) -> List[ERA5ReanalysisData]:
        """
        查询气象数据（给 LLM Tool 使用）

        Args:
            lat: 纬度
            lon: 经度
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            List[ERA5ReanalysisData]: 气象数据列表
        """
        from datetime import datetime as dt
        query_start = dt.now()

        logger.info(
            "weather_query_start",
            lat=lat,
            lon=lon,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )

        try:
            async with async_session() as session:
                logger.debug(
                    "weather_db_session_created",
                    lat=lat,
                    lon=lon
                )

                result = await session.execute(
                    select(ERA5ReanalysisData).where(
                        ERA5ReanalysisData.lat == lat,
                        ERA5ReanalysisData.lon == lon,
                        ERA5ReanalysisData.time >= start_time,
                        ERA5ReanalysisData.time <= end_time
                    ).order_by(ERA5ReanalysisData.time)
                )

                data = result.scalars().all()
                query_duration = (dt.now() - query_start).total_seconds()

                logger.info(
                    "weather_query_success",
                    lat=lat,
                    lon=lon,
                    record_count=len(data),
                    query_duration_seconds=query_duration
                )

                return data

        except Exception as e:
            query_duration = (dt.now() - query_start).total_seconds()
            logger.error(
                "weather_query_failed",
                lat=lat,
                lon=lon,
                error=str(e),
                error_type=type(e).__name__,
                query_duration_seconds=query_duration,
                exc_info=True
            )
            raise

    async def get_observed_data(
        self,
        station_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[ObservedWeatherData]:
        """
        查询观测数据（给 LLM Tool 使用）

        Args:
            station_id: 站点ID
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            List[ObservedWeatherData]: 观测数据列表
        """
        async with async_session() as session:
            result = await session.execute(
                select(ObservedWeatherData).where(
                    ObservedWeatherData.station_id == station_id,
                    ObservedWeatherData.time >= start_time,
                    ObservedWeatherData.time <= end_time
                ).order_by(ObservedWeatherData.time)
            )
            return result.scalars().all()
