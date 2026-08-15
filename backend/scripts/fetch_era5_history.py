"""
批量获取ERA5历史数据脚本

一次性获取指定时间范围的ERA5数据到数据库
用法: python scripts/fetch_era5_history.py --start-date 2025-01-01 --end-date 2025-11-10
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple
import structlog

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.external_apis.openmeteo_client import OpenMeteoClient
from app.db.repositories.weather_repo import WeatherRepository

logger = structlog.get_logger()


class ERA5HistoryFetcher:
    """ERA5历史数据批量获取器"""

    def __init__(self):
        self.client = OpenMeteoClient()
        self.repo = WeatherRepository()

    async def fetch_date_range(
        self,
        start_date: str,
        end_date: str,
        skip_existing: bool = True
    ):
        """
        获取指定日期范围的ERA5数据

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            skip_existing: 是否跳过已存在的数据
        """
        logger.info(
            "starting_batch_fetch",
            start_date=start_date,
            end_date=end_date,
            skip_existing=skip_existing
        )

        # 1. 获取目标网格点
        grid_points = await self._get_target_grid_points()

        if not grid_points:
            logger.error("no_grid_points_found")
            return

        logger.info(
            "grid_points_generated",
            count=len(grid_points),
            points=grid_points[:3]
        )

        # 2. 生成日期列表
        dates = self._generate_date_list(start_date, end_date)
        logger.info("dates_to_fetch", count=len(dates), dates=dates[:5])

        # 3. 批量获取
        total_tasks = len(grid_points) * len(dates)
        completed = 0
        success = 0
        failed = 0
        skipped = 0

        for date in dates:
            logger.info(f"processing_date", date=date)

            for lat, lon in grid_points:
                try:
                    # 检查是否已存在
                    if skip_existing:
                        if await self.repo.era5_data_exists(lat, lon, date):
                            skipped += 1
                            completed += 1
                            continue

                    # 调用API获取数据
                    data = await self.client.fetch_era5_data(
                        lat=lat,
                        lon=lon,
                        start_date=date,
                        end_date=date
                    )

                    # 存入数据库
                    records_saved = await self.repo.save_era5_data(lat, lon, data)

                    if records_saved > 0:
                        success += 1
                        logger.info(
                            "data_saved",
                            date=date,
                            lat=lat,
                            lon=lon,
                            records=records_saved
                        )
                    else:
                        logger.warning(
                            "no_data_returned",
                            date=date,
                            lat=lat,
                            lon=lon
                        )

                    completed += 1

                    # 避免API限流
                    await asyncio.sleep(0.2)

                    # 定期打印进度
                    if completed % 10 == 0:
                        progress = (completed / total_tasks) * 100
                        logger.info(
                            "progress_update",
                            completed=completed,
                            total=total_tasks,
                            progress=f"{progress:.1f}%",
                            success=success,
                            failed=failed,
                            skipped=skipped
                        )

                except Exception as e:
                    failed += 1
                    completed += 1
                    logger.error(
                        "fetch_failed",
                        date=date,
                        lat=lat,
                        lon=lon,
                        error=str(e)
                    )

        logger.info(
            "batch_fetch_complete",
            total=total_tasks,
            success=success,
            failed=failed,
            skipped=skipped,
            date_range=f"{start_date} to {end_date}"
        )

    async def _get_target_grid_points(self) -> List[Tuple[float, float]]:
        """
        获取目标网格点

        策略：
        1. 获取所有活跃站点
        2. 四舍五入到 0.25° 网格（ERA5 分辨率）
        3. 对关键站点，添加周围 3x3 网格
        """
        grid_points = set()

        # 获取活跃站点
        stations = await self.repo.get_active_stations()

        if not stations:
            logger.warning("no_active_stations_found")
            return []

        for station in stations:
            # 四舍五入到 0.25° 网格
            grid_lat = round(station.lat * 4) / 4
            grid_lon = round(station.lon * 4) / 4

            grid_points.add((grid_lat, grid_lon))

            # 对关键站点添加周围网格（3x3）
            if hasattr(station, 'has_upper_air') and station.has_upper_air:
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        neighbor_lat = grid_lat + i * 0.25
                        neighbor_lon = grid_lon + j * 0.25
                        grid_points.add((neighbor_lat, neighbor_lon))

        logger.info(
            "target_grid_points_generated",
            count=len(grid_points),
            stations=len(stations)
        )

        return list(grid_points)

    def _generate_date_list(self, start_date: str, end_date: str) -> List[str]:
        """生成日期列表"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        return dates


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="批量获取ERA5历史数据")
    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-01-01",
        help="开始日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        help="结束日期 (YYYY-MM-DD)，默认为昨天"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新获取已存在的数据"
    )

    args = parser.parse_args()

    logger.info(
        "script_started",
        start_date=args.start_date,
        end_date=args.end_date,
        force=args.force
    )

    fetcher = ERA5HistoryFetcher()
    await fetcher.fetch_date_range(
        start_date=args.start_date,
        end_date=args.end_date,
        skip_existing=not args.force
    )

    logger.info("script_completed")


if __name__ == "__main__":
    asyncio.run(main())
