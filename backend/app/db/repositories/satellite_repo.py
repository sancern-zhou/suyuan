"""
Satellite Data Repository

数据访问层 - 火点数据（NASA FIRMS）
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import FireHotspot
from app.db.database import async_session
import structlog

logger = structlog.get_logger()


class SatelliteRepository:
    """
    卫星数据Repository

    提供火点数据的数据库操作：
    - 保存火点数据
    - 查询火点数据（按区域、时间、置信度）
    - 统计火点数量
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        """
        初始化Repository

        Args:
            session: 数据库会话（可选，不提供则自动创建）
        """
        self.session = session

    async def save_fire_hotspots(
        self,
        hotspots: List[dict],
        batch_size: int = 100
    ) -> int:
        """
        批量保存火点数据

        Args:
            hotspots: 火点数据列表
            batch_size: 批次大小

        Returns:
            int: 成功保存的记录数
        """
        if not hotspots:
            return 0

        saved_count = 0

        try:
            async with async_session() as session:
                # 批量插入
                for i in range(0, len(hotspots), batch_size):
                    batch = hotspots[i:i + batch_size]

                    fire_records = [
                        FireHotspot(
                            lat=h["lat"],
                            lon=h["lon"],
                            brightness=h.get("brightness"),
                            frp=h.get("frp"),
                            confidence=h.get("confidence"),
                            acq_datetime=h["acq_datetime"],
                            satellite=h.get("satellite"),
                            daynight=h.get("daynight"),
                            scan=h.get("scan"),
                            track=h.get("track"),
                            bright_t31=h.get("bright_t31"),
                            data_source=h.get("data_source", "NASA_FIRMS"),
                            version=h.get("version")
                        )
                        for h in batch
                    ]

                    session.add_all(fire_records)
                    await session.commit()
                    saved_count += len(fire_records)

                    logger.debug(
                        "fire_batch_saved",
                        batch_num=i // batch_size + 1,
                        batch_size=len(fire_records)
                    )

            logger.info(
                "fire_hotspots_saved",
                total=len(hotspots),
                saved=saved_count
            )

            return saved_count

        except Exception as e:
            logger.error("fire_save_failed", error=str(e), exc_info=True)
            raise

    async def get_fire_hotspots(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        start_time: datetime,
        end_time: datetime,
        min_confidence: int = 70
    ) -> List[FireHotspot]:
        """
        查询指定区域和时间的火点数据

        Args:
            min_lat: 最小纬度
            max_lat: 最大纬度
            min_lon: 最小经度
            max_lon: 最大经度
            start_time: 开始时间
            end_time: 结束时间
            min_confidence: 最小置信度（默认70）

        Returns:
            List[FireHotspot]: 火点数据列表
        """
        try:
            async with async_session() as session:
                stmt = select(FireHotspot).where(
                    and_(
                        FireHotspot.lat >= min_lat,
                        FireHotspot.lat <= max_lat,
                        FireHotspot.lon >= min_lon,
                        FireHotspot.lon <= max_lon,
                        FireHotspot.acq_datetime >= start_time,
                        FireHotspot.acq_datetime <= end_time,
                        FireHotspot.confidence >= min_confidence
                    )
                ).order_by(FireHotspot.acq_datetime.desc())

                result = await session.execute(stmt)
                hotspots = result.scalars().all()

                logger.info(
                    "fire_query_complete",
                    count=len(hotspots),
                    bbox=f"{min_lat},{min_lon},{max_lat},{max_lon}",
                    time_range=f"{start_time} to {end_time}"
                )

                return hotspots

        except Exception as e:
            logger.error("fire_query_failed", error=str(e), exc_info=True)
            return []

    async def get_fire_hotspots_by_radius(
        self,
        center_lat: float,
        center_lon: float,
        radius_km: float,
        start_time: datetime,
        end_time: datetime,
        min_confidence: int = 70
    ) -> List[FireHotspot]:
        """
        查询指定中心点半径范围内的火点数据

        Args:
            center_lat: 中心点纬度
            center_lon: 中心点经度
            radius_km: 半径（公里）
            start_time: 开始时间
            end_time: 结束时间
            min_confidence: 最小置信度

        Returns:
            List[FireHotspot]: 火点数据列表
        """
        # 简化的矩形边界框计算（1度约111km）
        deg_offset = radius_km / 111.0

        min_lat = center_lat - deg_offset
        max_lat = center_lat + deg_offset
        min_lon = center_lon - deg_offset
        max_lon = center_lon + deg_offset

        return await self.get_fire_hotspots(
            min_lat, max_lat, min_lon, max_lon,
            start_time, end_time, min_confidence
        )

    async def count_fire_hotspots(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        start_time: datetime,
        end_time: datetime,
        min_confidence: int = 70
    ) -> int:
        """
        统计火点数量

        Args:
            参数同get_fire_hotspots

        Returns:
            int: 火点数量
        """
        hotspots = await self.get_fire_hotspots(
            min_lat, max_lat, min_lon, max_lon,
            start_time, end_time, min_confidence
        )
        return len(hotspots)

    async def get_fire_frp_sum(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        start_time: datetime,
        end_time: datetime,
        min_confidence: int = 70
    ) -> float:
        """
        计算火点辐射功率总和

        Args:
            参数同get_fire_hotspots

        Returns:
            float: FRP总和 (MW)
        """
        hotspots = await self.get_fire_hotspots(
            min_lat, max_lat, min_lon, max_lon,
            start_time, end_time, min_confidence
        )

        total_frp = sum(h.frp for h in hotspots if h.frp is not None)
        return total_frp

    async def get_latest_fire_time(self) -> Optional[datetime]:
        """
        获取数据库中最新火点的时间

        Returns:
            Optional[datetime]: 最新火点时间，无数据则返回None
        """
        try:
            async with async_session() as session:
                stmt = select(FireHotspot.acq_datetime).order_by(
                    FireHotspot.acq_datetime.desc()
                ).limit(1)

                result = await session.execute(stmt)
                latest_time = result.scalar_one_or_none()

                return latest_time

        except Exception as e:
            logger.error("fire_latest_time_query_failed", error=str(e))
            return None


# 导出
__all__ = ["SatelliteRepository"]
