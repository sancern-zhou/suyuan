"""
ERA5 Data Fetcher (Jining City Version)

定时获取济宁市ERA5历史气象数据并存入数据库
支持站点级数据抓取
"""
from typing import List, Tuple, Dict
from datetime import datetime, timedelta
import asyncio
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.db.repositories.weather_repo import WeatherRepository

logger = structlog.get_logger()


class JiningERA5Fetcher(DataFetcher):
    """
    ERA5 历史数据获取后台（济宁市版）

    功能：
    - 每天凌晨2点运行
    - 获取昨天的 ERA5 数据
    - 覆盖济宁市全境网格点
    - 支持站点级数据抓取
    - 存入数据库
    """

    def __init__(self):
        super().__init__(
            name="jining_era5_fetcher",
            description="ERA5 historical weather data fetcher (Jining City)",
            schedule="0 2 * * *",  # 每天2点
            version="1.0.0"
        )
        self.client = OpenMeteoClient()
        self.repo = WeatherRepository()

        # 济宁市监测站点信息
        self.stations = {
            "11149A": {"name": "火炬城", "lat": 35.42884, "lon": 116.6232},
            "11152A": {"name": "北湖区(市污水处理厂)", "lat": 35.3767, "lon": 116.5814},
            "11173A": {"name": "任城区站点", "lat": 35.5593, "lon": 116.8249},
            "11362A": {"name": "市第七中学", "lat": 35.4054, "lon": 116.5907},
            "1352A": {"name": "文体南路1号", "lat": 35.3921, "lon": 116.5648},
            "1353A": {"name": "任和路", "lat": 35.4566, "lon": 116.6075},
        }

        # 济宁市中心点（城市预报中心点）
        self.city_center = {
            "name": "济宁市中区(城市预报中心点)",
            "lat": 35.4143,
            "lon": 116.5871
        }

    async def fetch_and_store(self):
        """
        获取并存储 ERA5 数据

        工作流程：
        1. 获取所有站点数据点
        2. 添加市中心数据点
        3. 批次处理数据点
        4. 检查数据是否已存在
        5. 调用 API 获取数据（带重试机制）
        6. 存入数据库
        """
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info("starting_jining_era5_fetch", date=yesterday)

        try:
            # 1. 获取所有站点数据点
            station_points = await self._get_station_points()

            # 2. 添加市中心数据点
            city_center_point = await self._get_city_center_point()

            # 合并所有数据点
            all_points = station_points + [city_center_point]

            if not all_points:
                logger.warning("no_data_points_found")
                return

            logger.info(
                "jining_data_points_generated",
                station_count=len(station_points),
                city_center_count=1,
                total=len(all_points)
            )

            success_count = 0
            failed_count = 0
            skipped_count = 0

            # 3. 批次处理数据点（减小并发以避免API限流）
            batch_size = 3
            max_retries = 3
            retry_delay = 2

            for i in range(0, len(all_points), batch_size):
                batch = all_points[i:i+batch_size]

                tasks = []
                for point_info in batch:
                    task = self._fetch_single_point_with_retry(
                        point_info,
                        yesterday,
                        max_retries,
                        retry_delay
                    )
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
                    logger.error(
                        "batch_processing_failed",
                        batch=i//batch_size+1,
                        error=str(e)
                    )
                    failed_count += len(batch)

                # 批次间延迟（避免API限流）
                if i + batch_size < len(all_points):
                    await asyncio.sleep(3)

            logger.info(
                "jining_era5_fetch_complete",
                date=yesterday,
                region="济宁市",
                station_count=len(station_points),
                city_center_count=1,
                total=len(all_points),
                success=success_count,
                failed=failed_count,
                skipped=skipped_count,
                success_rate=f"{(success_count/len(all_points))*100:.1f}%" if len(all_points) > 0 else "N/A"
            )

        except Exception as e:
            logger.error("jining_era5_fetch_error", date=yesterday, error=str(e))

    async def _get_station_points(self) -> List[Dict]:
        """
        获取济宁市监测站点数据点

        Returns:
            List[Dict]: 站点信息列表
        """
        station_points = []

        for station_id, station_info in self.stations.items():
            # 对齐到ERA5 0.25°网格
            grid_spacing = 0.25
            grid_lat = round(station_info["lat"] / grid_spacing) * grid_spacing
            grid_lon = round(station_info["lon"] / grid_spacing) * grid_spacing

            point_info = {
                "station_id": station_id,
                "name": station_info["name"],
                "original_lat": station_info["lat"],
                "original_lon": station_info["lon"],
                "lat": round(grid_lat, 2),
                "lon": round(grid_lon, 2),
                "type": "station"
            }

            station_points.append(point_info)

        logger.info(
            "jining_station_points_generated",
            city="济宁市",
            station_count=len(station_points),
            stations=[p["name"] for p in station_points]
        )

        return station_points

    async def _get_city_center_point(self) -> Dict:
        """
        获取济宁市中心点数据点

        Returns:
            Dict: 市中心点信息
        """
        # 对齐到ERA5 0.25°网格
        grid_spacing = 0.25
        grid_lat = round(self.city_center["lat"] / grid_spacing) * grid_spacing
        grid_lon = round(self.city_center["lon"] / grid_spacing) * grid_spacing

        point_info = {
            "name": self.city_center["name"],
            "original_lat": self.city_center["lat"],
            "original_lon": self.city_center["lon"],
            "lat": round(grid_lat, 2),
            "lon": round(grid_lon, 2),
            "type": "city_center"
        }

        logger.info(
            "jining_city_center_point_generated",
            city="济宁市",
            name=point_info["name"],
            original_coords=f"{self.city_center['lat']}, {self.city_center['lon']}",
            grid_coords=f"{grid_lat}, {grid_lon}"
        )

        return point_info

    async def _fetch_single_point_with_retry(
        self,
        point_info: Dict,
        date_str: str,
        max_retries: int = 3,
        retry_delay: int = 2
    ) -> str:
        """
        获取单个数据点的数据（带重试机制）

        Args:
            point_info: 数据点信息（包含 lat, lon, type, name 等）
            date_str: 日期字符串
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            str: "success", "skipped", 或 "failed"
        """
        lat = point_info["lat"]
        lon = point_info["lon"]
        point_type = point_info.get("type", "grid")
        point_name = point_info.get("name", f"{lat}_{lon}")

        for attempt in range(max_retries + 1):
            try:
                # 检查数据是否已存在
                if await self.repo.era5_data_exists(lat, lon, date_str):
                    logger.debug(
                        "data_already_exists",
                        type=point_type,
                        name=point_name,
                        lat=lat,
                        lon=lon,
                        date=date_str
                    )
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
                    logger.info(
                        "era5_data_saved",
                        type=point_type,
                        name=point_name,
                        lat=lat,
                        lon=lon,
                        date=date_str,
                        records=records_saved
                    )
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
                            "rate_limit_hit",
                            type=point_type,
                            name=point_name,
                            lat=lat,
                            lon=lon,
                            date=date_str,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            retry_in=wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            "rate_limit_max_retries_exceeded",
                            type=point_type,
                            name=point_name,
                            lat=lat,
                            lon=lon,
                            date=date_str,
                            attempts=attempt + 1
                        )
                        return "failed"
                else:
                    # 非限流错误，记录并返回
                    logger.debug(
                        "era5_single_point_failed",
                        type=point_type,
                        name=point_name,
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
        logger.info("starting_jining_era5_fetch_for_date", date=date_str)

        try:
            # 1. 获取所有站点数据点
            station_points = await self._get_station_points()

            # 2. 获取市中心数据点
            city_center_point = await self._get_city_center_point()

            # 合并所有数据点
            all_points = station_points + [city_center_point]

            if not all_points:
                logger.warning("no_data_points_found")
                return {
                    "success": False,
                    "message": "No data points found",
                    "date": date_str,
                    "success_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0
                }

            logger.info(
                "jining_data_points_generated",
                station_count=len(station_points),
                city_center_count=1,
                total=len(all_points)
            )

            success_count = 0
            failed_count = 0
            skipped_count = 0

            # 3. 批次处理数据点
            batch_size = 3
            max_retries = 3
            retry_delay = 2

            for i in range(0, len(all_points), batch_size):
                batch = all_points[i:i+batch_size]

                tasks = []
                for point_info in batch:
                    task = self._fetch_single_point_with_retry(
                        point_info,
                        date_str,
                        max_retries,
                        retry_delay
                    )
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
                    logger.error(
                        "batch_processing_failed",
                        batch=i//batch_size+1,
                        error=str(e)
                    )
                    failed_count += len(batch)

                # 批次间延迟
                if i + batch_size < len(all_points):
                    await asyncio.sleep(3)

            result = {
                "success": failed_count == 0,
                "message": f"Jining ERA5 data fetch for {date_str} completed",
                "date": date_str,
                "region": "Jining City",
                "station_count": len(station_points),
                "city_center_count": 1,
                "total_count": len(all_points),
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "success_rate": f"{(success_count/len(all_points))*100:.1f}%" if len(all_points) > 0 else "N/A"
            }

            logger.info("jining_era5_fetch_for_date_complete", **result)
            return result

        except Exception as e:
            logger.error("jining_era5_fetch_for_date_error", date=date_str, error=str(e))
            return {
                "success": False,
                "message": str(e),
                "date": date_str,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0
            }

    async def fetch_station_data(self, station_id: str, date_str: str = None) -> dict:
        """
        获取指定站点的 ERA5 数据

        Args:
            station_id: 站点ID（如 "11149A"）
            date_str: 日期字符串 (YYYY-MM-DD)，默认为昨天

        Returns:
            dict: 执行结果
        """
        if station_id not in self.stations:
            return {
                "success": False,
                "message": f"Station {station_id} not found",
                "station_id": station_id
            }

        if date_str is None:
            date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        station_info = self.stations[station_id]

        # 对齐到ERA5网格
        grid_spacing = 0.25
        grid_lat = round(station_info["lat"] / grid_spacing) * grid_spacing
        grid_lon = round(station_info["lon"] / grid_spacing) * grid_spacing

        point_info = {
            "station_id": station_id,
            "name": station_info["name"],
            "original_lat": station_info["lat"],
            "original_lon": station_info["lon"],
            "lat": round(grid_lat, 2),
            "lon": round(grid_lon, 2),
            "type": "station"
        }

        logger.info(
            "fetching_station_era5_data",
            station_id=station_id,
            station_name=station_info["name"],
            date=date_str,
            original_coords=f"{station_info['lat']}, {station_info['lon']}",
            grid_coords=f"{grid_lat}, {grid_lon}"
        )

        result = await self._fetch_single_point_with_retry(point_info, date_str)

        return {
            "success": result == "success",
            "message": f"Station {station_id} data fetch completed",
            "station_id": station_id,
            "station_name": station_info["name"],
            "date": date_str,
            "result": result,
            "original_coords": f"{station_info['lat']}, {station_info['lon']}",
            "grid_coords": f"{grid_lat}, {grid_lon}"
        }
