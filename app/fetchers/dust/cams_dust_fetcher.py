"""
CAMS Dust Forecast Data Fetcher

定时获取CAMS沙尘气溶胶预报数据
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
import structlog
from app.fetchers.base.fetcher_interface import DataFetcher
from app.external_apis.cams_client import CAMSClient
from app.db.repositories.dust_repo import DustRepository

logger = structlog.get_logger()


class CAMSDustFetcher(DataFetcher):
    """
    CAMS沙尘预报数据获取后台

    功能：
    - 每6小时采集CAMS沙尘预报数据
    - 覆盖中国及周边区域
    - 存入数据库供LLM查询

    数据来源: Copernicus Atmosphere Monitoring Service (CAMS)
    预报范围: 5天（120小时）
    时间分辨率: 3小时
    """

    def __init__(self):
        super().__init__(
            name="cams_dust_fetcher",
            description="CAMS dust aerosol forecast data fetcher",
            schedule="0 */6 * * *",  # 每6小时运行（00:00, 06:00, 12:00, 18:00）
            version="1.0.0"
        )
        self.client = CAMSClient()
        self.repo = DustRepository()

        # 中国及周边区域范围
        self.china_bounds = {
            "min_lat": 15.0,   # 南海区域
            "max_lat": 55.0,   # 东北区域
            "min_lon": 70.0,   # 西部边境
            "max_lon": 140.0   # 东部海域
        }

        # 预报时长（小时）
        self.forecast_hours = 120  # 5天

    async def fetch_and_store(self):
        """
        获取并存储沙尘预报数据

        流程:
        1. 检查依赖库（cdsapi, xarray, netCDF4）
        2. 调用CAMS API获取5天沙尘预报
        3. 解析NetCDF数据
        4. 提取网格点数据
        5. 批量存入数据库
        6. 清理旧数据（保留7天）

        Note: CAMS数据处理较慢，可能需要3-5分钟
        """
        try:
            logger.info("cams_dust_fetch_start")

            # 1. 检查依赖库
            deps = self.client.check_dependencies()
            missing_deps = [name for name, installed in deps.items() if not installed]

            if missing_deps:
                logger.error(
                    "cams_dependencies_missing",
                    missing=missing_deps,
                    instructions=self.client.get_installation_instructions()
                )
                raise Exception(
                    f"缺少依赖库: {', '.join(missing_deps)}. "
                    "请运行: pip install cdsapi xarray netCDF4"
                )

            # 2. 获取CAMS预报数据
            forecast_data = await self.client.fetch_dust_forecast(
                min_lat=self.china_bounds["min_lat"],
                max_lat=self.china_bounds["max_lat"],
                min_lon=self.china_bounds["min_lon"],
                max_lon=self.china_bounds["max_lon"],
                forecast_hours=self.forecast_hours
            )

            if not forecast_data.get("success"):
                raise Exception("CAMS API返回失败")

            logger.info(
                "cams_data_fetched",
                variables=list(forecast_data.get("variables", {}).keys()),
                coords=forecast_data.get("coordinates", {}).keys()
            )

            # 3. 提取和格式化数据
            dust_records = self._extract_dust_records(forecast_data)

            logger.info(
                "cams_data_extracted",
                total_records=len(dust_records)
            )

            # 4. 存入数据库
            if dust_records:
                saved_count = await self.repo.save_dust_forecasts(dust_records)

                logger.info(
                    "cams_dust_fetch_complete",
                    fetched=len(dust_records),
                    saved=saved_count
                )
            else:
                logger.warning("cams_no_data_extracted")

            # 5. 清理旧数据（保留7天）
            deleted_count = await self.repo.delete_old_forecasts(days_to_keep=7)

            if deleted_count > 0:
                logger.info(
                    "cams_old_data_cleaned",
                    deleted=deleted_count
                )

        except Exception as e:
            logger.error(
                "cams_dust_fetch_failed",
                error=str(e),
                exc_info=True
            )
            raise

    def _extract_dust_records(self, forecast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从CAMS NetCDF数据中提取沙尘记录

        Args:
            forecast_data: 解析后的CAMS数据

        Returns:
            List[Dict]: 沙尘预报记录列表
        """
        records = []

        try:
            # 获取坐标
            lats = forecast_data["coordinates"]["latitude"]
            lons = forecast_data["coordinates"]["longitude"]
            times = forecast_data["coordinates"]["time"]

            # 获取变量数据
            variables = forecast_data["variables"]

            # 提取dust AOD数据
            dust_aod_data = variables.get("dust_aerosol_optical_depth_550nm", {}).get("data")
            pm10_data = variables.get("particulate_matter_10um", {}).get("data")

            if not dust_aod_data:
                logger.warning("cams_no_dust_aod_data")
                return records

            # 预报发布时间（当前时间）
            forecast_time = datetime.now()

            # 遍历所有网格点和时间
            for t_idx, time_str in enumerate(times):
                valid_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                leadtime_hour = int((valid_time - forecast_time).total_seconds() / 3600)

                for lat_idx, lat in enumerate(lats):
                    for lon_idx, lon in enumerate(lons):
                        # 提取数值（处理多维数组）
                        try:
                            if len(dust_aod_data) > t_idx:
                                dust_aod = dust_aod_data[t_idx][lat_idx][lon_idx]
                            else:
                                dust_aod = None

                            if pm10_data and len(pm10_data) > t_idx:
                                pm10 = pm10_data[t_idx][lat_idx][lon_idx]
                            else:
                                pm10 = None

                            # 跳过无效数据
                            if dust_aod is None or dust_aod < 0:
                                continue

                            # 只保留有意义的沙尘数据（AOD > 0.1）
                            if dust_aod < 0.1:
                                continue

                            record = {
                                "lat": float(lat),
                                "lon": float(lon),
                                "forecast_time": forecast_time,
                                "valid_time": valid_time,
                                "leadtime_hour": leadtime_hour,
                                "dust_aod_550nm": float(dust_aod),
                                "pm10_concentration": float(pm10) if pm10 is not None else None,
                                "data_source": "CAMS",
                                "model_version": forecast_data.get("metadata", {}).get("model_version")
                            }

                            records.append(record)

                        except (IndexError, TypeError, ValueError) as e:
                            logger.debug(
                                "cams_grid_point_skip",
                                lat=lat,
                                lon=lon,
                                time=time_str,
                                error=str(e)
                            )
                            continue

            logger.info(
                "cams_records_extracted",
                total=len(records),
                grid_points=len(lats) * len(lons),
                time_steps=len(times)
            )

            return records

        except Exception as e:
            logger.error(
                "cams_extraction_failed",
                error=str(e),
                exc_info=True
            )
            return []


# 导出
__all__ = ["CAMSDustFetcher"]
