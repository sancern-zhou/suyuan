"""
Dust Data Repository

数据访问层 - 沙尘数据（CAMS）
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DustForecast, DustEvent
from app.db.database import async_session
import structlog

logger = structlog.get_logger()


class DustRepository:
    """
    沙尘数据Repository

    提供沙尘预报和事件数据的数据库操作：
    - 保存CAMS预报数据
    - 查询沙尘预报（按区域、时间）
    - 管理沙尘事件记录
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        """
        初始化Repository

        Args:
            session: 数据库会话（可选，不提供则自动创建）
        """
        self.session = session

    async def save_dust_forecasts(
        self,
        forecasts: List[dict],
        batch_size: int = 100
    ) -> int:
        """
        批量保存沙尘预报数据

        Args:
            forecasts: 沙尘预报数据列表
            batch_size: 批次大小

        Returns:
            int: 成功保存的记录数
        """
        if not forecasts:
            return 0

        saved_count = 0

        try:
            async with async_session() as session:
                # 批量插入
                for i in range(0, len(forecasts), batch_size):
                    batch = forecasts[i:i + batch_size]

                    dust_records = [
                        DustForecast(
                            lat=f["lat"],
                            lon=f["lon"],
                            forecast_time=f["forecast_time"],
                            valid_time=f["valid_time"],
                            leadtime_hour=f.get("leadtime_hour"),
                            dust_aod_550nm=f.get("dust_aod_550nm"),
                            total_aod_550nm=f.get("total_aod_550nm"),
                            dust_surface_concentration=f.get("dust_surface_concentration"),
                            dust_column_mass=f.get("dust_column_mass"),
                            pm10_concentration=f.get("pm10_concentration"),
                            data_source=f.get("data_source", "CAMS"),
                            model_version=f.get("model_version")
                        )
                        for f in batch
                    ]

                    session.add_all(dust_records)
                    await session.commit()
                    saved_count += len(dust_records)

                    logger.debug(
                        "dust_batch_saved",
                        batch_num=i // batch_size + 1,
                        batch_size=len(dust_records)
                    )

            logger.info(
                "dust_forecasts_saved",
                total=len(forecasts),
                saved=saved_count
            )

            return saved_count

        except Exception as e:
            logger.error("dust_save_failed", error=str(e), exc_info=True)
            raise

    async def get_dust_forecasts(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        start_time: datetime,
        end_time: datetime,
        min_dust_aod: Optional[float] = None
    ) -> List[DustForecast]:
        """
        查询指定区域和时间的沙尘预报数据

        Args:
            min_lat: 最小纬度
            max_lat: 最大纬度
            min_lon: 最小经度
            max_lon: 最大经度
            start_time: 开始时间（valid_time）
            end_time: 结束时间（valid_time）
            min_dust_aod: 最小沙尘AOD阈值（可选）

        Returns:
            List[DustForecast]: 沙尘预报数据列表
        """
        try:
            async with async_session() as session:
                # 构建查询条件
                conditions = [
                    DustForecast.lat >= min_lat,
                    DustForecast.lat <= max_lat,
                    DustForecast.lon >= min_lon,
                    DustForecast.lon <= max_lon,
                    DustForecast.valid_time >= start_time,
                    DustForecast.valid_time <= end_time
                ]

                if min_dust_aod is not None:
                    conditions.append(DustForecast.dust_aod_550nm >= min_dust_aod)

                stmt = select(DustForecast).where(
                    and_(*conditions)
                ).order_by(DustForecast.valid_time.desc())

                result = await session.execute(stmt)
                forecasts = result.scalars().all()

                logger.info(
                    "dust_query_complete",
                    count=len(forecasts),
                    bbox=f"{min_lat},{min_lon},{max_lat},{max_lon}",
                    time_range=f"{start_time} to {end_time}"
                )

                return forecasts

        except Exception as e:
            logger.error("dust_query_failed", error=str(e), exc_info=True)
            return []

    async def get_latest_dust_forecast(
        self,
        lat: float,
        lon: float,
        tolerance: float = 0.5
    ) -> Optional[DustForecast]:
        """
        获取指定位置的最新沙尘预报

        Args:
            lat: 纬度
            lon: 经度
            tolerance: 位置容差（度，默认0.5°）

        Returns:
            Optional[DustForecast]: 最新预报数据，无数据则返回None
        """
        try:
            async with async_session() as session:
                stmt = select(DustForecast).where(
                    and_(
                        DustForecast.lat >= lat - tolerance,
                        DustForecast.lat <= lat + tolerance,
                        DustForecast.lon >= lon - tolerance,
                        DustForecast.lon <= lon + tolerance
                    )
                ).order_by(DustForecast.valid_time.desc()).limit(1)

                result = await session.execute(stmt)
                forecast = result.scalar_one_or_none()

                return forecast

        except Exception as e:
            logger.error("dust_latest_query_failed", error=str(e))
            return None

    async def get_max_dust_aod_in_region(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[float]:
        """
        获取指定区域和时间范围内的最大沙尘AOD

        Args:
            min_lat: 最小纬度
            max_lat: 最大纬度
            min_lon: 最小经度
            max_lon: 最大经度
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            Optional[float]: 最大沙尘AOD，无数据则返回None
        """
        try:
            async with async_session() as session:
                stmt = select(func.max(DustForecast.dust_aod_550nm)).where(
                    and_(
                        DustForecast.lat >= min_lat,
                        DustForecast.lat <= max_lat,
                        DustForecast.lon >= min_lon,
                        DustForecast.lon <= max_lon,
                        DustForecast.valid_time >= start_time,
                        DustForecast.valid_time <= end_time
                    )
                )

                result = await session.execute(stmt)
                max_aod = result.scalar_one_or_none()

                return max_aod

        except Exception as e:
            logger.error("dust_max_aod_query_failed", error=str(e))
            return None

    async def save_dust_event(self, event: dict) -> int:
        """
        保存沙尘事件记录

        Args:
            event: 沙尘事件数据

        Returns:
            int: 事件ID
        """
        try:
            async with async_session() as session:
                dust_event = DustEvent(
                    event_name=event["event_name"],
                    event_date=event["event_date"],
                    event_duration_hours=event.get("event_duration_hours"),
                    min_lat=event.get("min_lat"),
                    max_lat=event.get("max_lat"),
                    min_lon=event.get("min_lon"),
                    max_lon=event.get("max_lon"),
                    affected_provinces=event.get("affected_provinces"),
                    intensity_level=event.get("intensity_level"),
                    max_dust_aod=event.get("max_dust_aod"),
                    max_pm10_concentration=event.get("max_pm10_concentration"),
                    min_visibility=event.get("min_visibility"),
                    source_region=event.get("source_region"),
                    transport_direction=event.get("transport_direction"),
                    data_source=event.get("data_source", "Manual"),
                    confidence_level=event.get("confidence_level"),
                    notes=event.get("notes")
                )

                session.add(dust_event)
                await session.commit()

                # 刷新以获取ID
                await session.refresh(dust_event)

                logger.info(
                    "dust_event_saved",
                    event_id=dust_event.id,
                    event_name=event["event_name"]
                )

                return dust_event.id

        except Exception as e:
            logger.error("dust_event_save_failed", error=str(e), exc_info=True)
            raise

    async def get_dust_events(
        self,
        start_date: datetime,
        end_date: datetime,
        intensity_level: Optional[str] = None
    ) -> List[DustEvent]:
        """
        查询沙尘事件

        Args:
            start_date: 开始日期
            end_date: 结束日期
            intensity_level: 强度等级过滤（可选："轻度"/"中度"/"重度"）

        Returns:
            List[DustEvent]: 沙尘事件列表
        """
        try:
            async with async_session() as session:
                conditions = [
                    DustEvent.event_date >= start_date,
                    DustEvent.event_date <= end_date
                ]

                if intensity_level:
                    conditions.append(DustEvent.intensity_level == intensity_level)

                stmt = select(DustEvent).where(
                    and_(*conditions)
                ).order_by(DustEvent.event_date.desc())

                result = await session.execute(stmt)
                events = result.scalars().all()

                logger.info(
                    "dust_events_query_complete",
                    count=len(events),
                    date_range=f"{start_date} to {end_date}"
                )

                return events

        except Exception as e:
            logger.error("dust_events_query_failed", error=str(e), exc_info=True)
            return []

    async def delete_old_forecasts(self, days_to_keep: int = 7) -> int:
        """
        删除旧的预报数据

        Args:
            days_to_keep: 保留天数（默认7天）

        Returns:
            int: 删除的记录数
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            async with async_session() as session:
                stmt = select(DustForecast).where(
                    DustForecast.valid_time < cutoff_date
                )

                result = await session.execute(stmt)
                old_forecasts = result.scalars().all()

                for forecast in old_forecasts:
                    await session.delete(forecast)

                await session.commit()

                logger.info(
                    "old_dust_forecasts_deleted",
                    count=len(old_forecasts),
                    cutoff_date=cutoff_date
                )

                return len(old_forecasts)

        except Exception as e:
            logger.error("dust_cleanup_failed", error=str(e), exc_info=True)
            return 0


# 导出
__all__ = ["DustRepository"]
