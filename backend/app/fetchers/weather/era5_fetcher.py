"""
ERA5 Data Fetcher (Guangdong Version)

定时获取广东省ERA5历史气象数据并存入数据库
修改为广东省全境网格点覆盖
"""
from typing import List, Tuple
from datetime import datetime, timedelta
import asyncio
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.db.repositories.weather_repo import WeatherRepository

logger = structlog.get_logger()


class ERA5Fetcher(DataFetcher):
    """
    ERA5 历史数据获取后台（广东省版）

    功能：
    - 每天凌晨2点运行
    - 获取昨天的 ERA5 数据
    - 覆盖广东省全境825个网格点
    - 存入数据库
    """

    def __init__(self):
        super().__init__(
            name="era5_fetcher",
            description="ERA5 historical weather data fetcher (Guangdong Province)",
            schedule="0 2 * * *",  # 每天2点
            version="2.1.0"  # 版本更新：添加重试机制和API限流处理
        )
        self.client = OpenMeteoClient()
        self.repo = WeatherRepository()
        # 广东省地理范围
        self.region = {
            'min_lat': 20.0,   # 最南端：徐闻（约20°N）
            'max_lat': 26.0,   # 最北端：连州（约26°N）
            'min_lon': 109.0,  # 最西端：廉江（约109°E）
            'max_lon': 117.0   # 最东端：潮州（约117°E）
        }

    async def fetch_and_store(self):
        """
        获取并存储 ERA5 数据

        工作流程：
        1. 生成广东省网格点（825个）
        2. 批次处理网格点
        3. 检查数据是否已存在
        4. 调用 API 获取数据（带重试机制）
        5. 存入数据库
        """
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info("starting_era5_fetch", date=yesterday)

        try:
            # 1. 获取广东省网格点
            grid_points = await self._get_target_grid_points()

            if not grid_points:
                logger.warning("no_grid_points_found")
                return

            logger.info("guangdong_grid_points_generated", count=len(grid_points))

            success_count = 0
            failed_count = 0
            skipped_count = 0

            # 2. 批次处理网格点（减小并发以避免API限流）
            batch_size = 3
            max_retries = 3
            retry_delay = 2

            for i in range(0, len(grid_points), batch_size):
                batch = grid_points[i:i+batch_size]

                tasks = []
                for lat, lon in batch:
                    task = self._fetch_single_point_with_retry(lat, lon, yesterday, max_retries, retry_delay)
                    tasks.append(task)

                # 等待当前批次完成
                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # 处理结果
                    for result in results:
                        if isinstance(result, Exception):
                            failed_count += 1
                        elif result == "success":
                            success_count += 1
                        elif result == "skipped":
                            skipped_count += 1
                except Exception as e:
                    logger.error(f"batch_processing_failed", batch=i//batch_size+1, error=str(e))
                    failed_count += len(batch)

                # 批次间延迟（增加延迟时间以避免API限流）
                if i + batch_size < len(grid_points):
                    await asyncio.sleep(3)  # 从0.2秒增加到3秒

            logger.info(
                "era5_fetch_complete",
                date=yesterday,
                region="广东省",
                grid_count=len(grid_points),
                success=success_count,
                failed=failed_count,
                skipped=skipped_count,
                total=len(grid_points),
                success_rate=f"{(success_count/len(grid_points))*100:.1f}%" if len(grid_points) > 0 else "N/A"
            )

        except Exception as e:
            logger.error("era5_fetch_error", date=yesterday, error=str(e))

    async def _get_target_grid_points(self) -> List[Tuple[float, float]]:
        """
        获取广东省目标网格点

        策略：生成广东省全境的ERA5网格点
        - 广东省范围：20°N - 26°N, 109°E - 117°E
        - 分辨率：0.25° × 0.25°
        - 总网格点：约825个
        """
        grid_points = set()
        grid_spacing = 0.25  # ERA5标准分辨率

        # 生成网格点
        lat = self.region['min_lat']
        while lat <= self.region['max_lat']:
            lon = self.region['min_lon']
            while lon <= self.region['max_lon']:
                # 对齐到ERA5 0.25°网格
                grid_lat = round(lat / grid_spacing) * grid_spacing
                grid_lon = round(lon / grid_spacing) * grid_spacing

                # 检查是否在广东省范围内
                if (self.region['min_lat'] <= grid_lat <= self.region['max_lat'] and
                    self.region['min_lon'] <= grid_lon <= self.region['max_lon']):
                    grid_points.add((round(grid_lat, 2), round(grid_lon, 2)))

                lon += grid_spacing
            lat += grid_spacing

        result = list(grid_points)

        # 计算网格覆盖范围
        lats = [p[0] for p in result]
        lons = [p[1] for p in result]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)

        logger.info(
            "guangdong_grid_points_generated",
            province="广东省",
            latitude_range=f"{lat_min}°N - {lat_max}°N",
            longitude_range=f"{lon_min}°E - {lon_max}°E",
            grid_spacing=f"{grid_spacing}°",
            grid_count=len(result),
            sample_points=result[:5]  # 显示前5个网格点作为示例
        )

        return result

    async def _fetch_single_point_with_retry(
        self,
        lat: float,
        lon: float,
        date_str: str,
        max_retries: int = 3,
        retry_delay: int = 2
    ) -> str:
        """
        获取单个网格点的数据（带重试机制）

        Args:
            lat: 纬度
            lon: 经度
            date_str: 日期字符串
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            str: "success", "skipped", 或 "failed"
        """
        for attempt in range(max_retries + 1):
            try:
                # 检查数据是否已存在
                if await self.repo.era5_data_exists(lat, lon, date_str):
                    return "skipped"

                # 调用API获取数据
                data = await self.client.fetch_era5_data(
                    lat=lat,
                    lon=lon,
                    start_date=date_str,
                    end_date=date_str
                )

                # 存入数据库
                records_saved = await self.repo.save_era5_data(lat, lon, data)

                if records_saved > 0:
                    return "success"
                else:
                    return "failed"

            except Exception as e:
                error_msg = str(e)

                # 检查是否是限流错误
                if "429" in error_msg or "Too many concurrent requests" in error_msg:
                    if attempt < max_retries:
                        wait_time = retry_delay * (attempt + 1)  # 指数退避
                        logger.warning(
                            f"rate_limit_hit {date_str} (lat={lat}, lon={lon})",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            retry_in=wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"rate_limit_max_retries_exceeded {date_str}",
                            lat=lat,
                            lon=lon,
                            attempts=attempt + 1
                        )
                        return "failed"
                else:
                    # 非限流错误，记录并返回
                    logger.debug(
                        "era5_single_point_failed",
                        lat=lat,
                        lon=lon,
                        date=date_str,
                        error=str(e)
                    )
                    return "failed"

        return "failed"

    async def fetch_and_store_for_date(self, date_str: str) -> dict:
        """
        获取并存储指定日期的 ERA5 数据（用于手动补采历史数据）

        Args:
            date_str: 日期字符串 (YYYY-MM-DD)

        Returns:
            dict: 执行结果，包含 success_count, failed_count, skipped_count 等
        """
        logger.info("starting_era5_fetch_for_date", date=date_str)

        try:
            # 1. 获取广东省网格点
            grid_points = await self._get_target_grid_points()

            if not grid_points:
                logger.warning("no_grid_points_found")
                return {
                    "success": False,
                    "message": "No grid points found",
                    "date": date_str,
                    "success_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0
                }

            logger.info("guangdong_grid_points_generated", count=len(grid_points))

            success_count = 0
            failed_count = 0
            skipped_count = 0

            # 2. 批次处理网格点
            batch_size = 3
            max_retries = 3
            retry_delay = 2

            for i in range(0, len(grid_points), batch_size):
                batch = grid_points[i:i+batch_size]

                tasks = []
                for lat, lon in batch:
                    task = self._fetch_single_point_with_retry(lat, lon, date_str, max_retries, retry_delay)
                    tasks.append(task)

                # 等待当前批次完成
                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, Exception):
                            failed_count += 1
                        elif result == "success":
                            success_count += 1
                        elif result == "skipped":
                            skipped_count += 1
                except Exception as e:
                    logger.error("batch_processing_failed", batch=i//batch_size+1, error=str(e))
                    failed_count += len(batch)

                # 批次间延迟
                if i + batch_size < len(grid_points):
                    await asyncio.sleep(3)

            result = {
                "success": failed_count == 0,
                "message": f"ERA5 data fetch for {date_str} completed",
                "date": date_str,
                "region": "Guangdong Province",
                "grid_count": len(grid_points),
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "success_rate": f"{(success_count/len(grid_points))*100:.1f}%" if len(grid_points) > 0 else "N/A"
            }

            logger.info("era5_fetch_for_date_complete", **result)
            return result

        except Exception as e:
            logger.error("era5_fetch_for_date_error", date=date_str, error=str(e))
            return {
                "success": False,
                "message": str(e),
                "date": date_str,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0
            }
