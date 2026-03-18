#!/usr/bin/env python3
"""
ERA5数据补齐脚本（简化版）

直接从API获取ERA5数据并存储到数据库
无需初始化整个应用
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
import structlog

# 设置日志
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from app.external_apis.openmeteo_client import OpenMeteoClient
    from app.db.repositories.weather_repo import WeatherRepository
except ImportError as e:
    logger.error("import_failed", error=str(e))
    sys.exit(1)


class SimpleERA5Fill:
    """简化的ERA5数据补齐工具"""

    def __init__(self):
        self.client = OpenMeteoClient()
        self.repo = WeatherRepository()

    async def fill_date_range(self, start_date: str, end_date: str, lat: float = None, lon: float = None):
        """
        补齐指定时间范围的ERA5数据

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            lat: 纬度（可选，默认为None，获取所有网格点）
            lon: 经度（可选，默认为None，获取所有网格点）
        """
        try:
            # 验证日期格式
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            if start_dt >= end_dt:
                raise ValueError("开始日期必须早于结束日期")

            # 计算总天数
            total_days = (end_dt - start_dt).days + 1
            logger.info(
                "era5_fill_start",
                start_date=start_date,
                end_date=end_date,
                total_days=total_days
            )

            # 获取目标网格点
            if lat is not None and lon is not None:
                # 使用指定的单个网格点
                grid_points = [(lat, lon)]
                logger.info("using_single_grid_point", lat=lat, lon=lon)
            else:
                # 获取所有活跃站点的网格点
                grid_points = await self._get_all_grid_points()
                logger.info("using_all_grid_points", count=len(grid_points))

            if not grid_points:
                logger.warning("no_grid_points_available")
                return

            # 遍历每一天
            current_dt = start_dt
            day_index = 0

            while current_dt <= end_dt:
                date_str = current_dt.strftime("%Y-%m-%d")
                day_index += 1

                logger.info(
                    f"[{day_index}/{total_days}] processing_date",
                    date=date_str,
                    progress=f"{(day_index/total_days)*100:.1f}%"
                )

                # 获取这一天的数据
                await self._fetch_day_data(date_str, grid_points)

                # 切换到下一天
                current_dt += timedelta(days=1)

                # 避免API限流
                await asyncio.sleep(0.2)

            logger.info("era5_fill_complete")

        except Exception as e:
            logger.error("era5_fill_failed", error=str(e), exc_info=True)
            raise

    async def _get_all_grid_points(self):
        """获取所有活跃站点的网格点"""
        try:
            stations = await self.repo.get_active_stations()

            if not stations:
                logger.warning("no_active_stations_found")
                return []

            grid_points = set()

            for station in stations:
                # 四舍五入到0.25°网格
                grid_lat = round(station.lat * 4) / 4
                grid_lon = round(station.lon * 4) / 4

                grid_points.add((grid_lat, grid_lon))

            logger.info(
                "grid_points_generated",
                stations=len(stations),
                unique_grid_points=len(grid_points)
            )

            return list(grid_points)

        except Exception as e:
            logger.error("get_grid_points_failed", error=str(e))
            return []

    async def _fetch_day_data(self, date_str: str, grid_points):
        """获取指定日期的所有网格点数据"""
        success_count = 0
        failed_count = 0
        skipped_count = 0

        for lat, lon in grid_points:
            try:
                # 检查数据是否已存在
                if await self.repo.era5_data_exists(lat, lon, date_str):
                    skipped_count += 1
                    logger.debug(f"data_exists {lat},{lon},{date_str}")
                    continue

                # 调用API获取数据
                logger.debug(f"fetching {lat},{lon},{date_str}")
                data = await self.client.fetch_era5_data(
                    lat=lat,
                    lon=lon,
                    start_date=date_str,
                    end_date=date_str
                )

                # 存入数据库
                records_saved = await self.repo.save_era5_data(lat, lon, data)

                if records_saved > 0:
                    success_count += 1
                    logger.debug(
                        "era5_point_success",
                        lat=lat,
                        lon=lon,
                        date=date_str,
                        records=records_saved
                    )
                else:
                    failed_count += 1

                # 避免API限流
                await asyncio.sleep(0.1)

            except Exception as e:
                failed_count += 1
                logger.error(
                    "era5_point_failed",
                    lat=lat,
                    lon=lon,
                    date=date_str,
                    error=str(e)
                )

        # 输出当天统计
        total = len(grid_points)
        logger.info(
            f"day_complete {date_str}",
            success=success_count,
            failed=failed_count,
            skipped=skipped_count,
            total=total,
            success_rate=f"{(success_count/total)*100:.1f}%" if total > 0 else "N/A"
        )


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="ERA5数据补齐工具（简化版）")
    parser.add_argument(
        "--start",
        type=str,
        default="2025-11-07",
        help="开始日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2025-11-25",
        help="结束日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=None,
        help="纬度（可选，指定单个网格点）"
    )
    parser.add_argument(
        "--lon",
        type=float,
        default=None,
        help="经度（可选，指定单个网格点）"
    )

    args = parser.parse_args()

    logger.info("era5_data_fill_tool", args=args)

    # 创建补齐工具并执行
    fill_tool = SimpleERA5Fill()

    if args.lat is not None and args.lon is not None:
        logger.info("using_specific_grid_point", lat=args.lat, lon=args.lon)

    await fill_tool.fill_date_range(args.start, args.end, args.lat, args.lon)

    logger.info("era5_data_fill_script_completed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("era5_fill_interrupted_by_user")
    except Exception as e:
        logger.error("era5_fill_script_failed", error=str(e))
        sys.exit(1)
