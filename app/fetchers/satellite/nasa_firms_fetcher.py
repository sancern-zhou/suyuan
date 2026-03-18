"""
NASA FIRMS Fire Hotspot Data Fetcher

定时获取NASA FIRMS火点数据
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
import structlog
from app.fetchers.base.fetcher_interface import DataFetcher
from app.external_apis.nasa_firms_client import NASAFirmsClient
from app.db.repositories.satellite_repo import SatelliteRepository

logger = structlog.get_logger()


class NASAFirmsFetcher(DataFetcher):
    """
    NASA FIRMS火点数据获取后台

    功能：
    - 每小时爬取最近1小时的火点数据
    - 覆盖中国及周边区域
    - 存入数据库供LLM查询

    数据来源: NASA Fire Information for Resource Management System
    卫星: VIIRS (375m分辨率)
    更新频率: 每小时
    """

    def __init__(self):
        super().__init__(
            name="nasa_firms_fetcher",
            description="NASA FIRMS fire hotspot data fetcher",
            schedule="0 * * * *",  # 每小时整点运行
            version="1.0.0"
        )
        self.client = NASAFirmsClient()
        self.repo = SatelliteRepository()

        # 中国及周边区域边界框
        # 格式: min_lon, min_lat, max_lon, max_lat
        self.china_bbox = "73,18,136,54"

    async def fetch_and_store(self):
        """
        获取并存储火点数据

        流程:
        1. 调用NASA FIRMS API获取最近24小时数据
        2. 清洗和转换数据格式
        3. 过滤低置信度火点（confidence < 70）
        4. 批量存入数据库

        Note: 使用24小时而不是1小时是因为：
        - 避免数据延迟导致遗漏
        - 数据库会自动去重（基于时间+坐标）
        - 保证数据完整性
        """
        try:
            logger.info("nasa_firms_fetch_start")

            # 1. 获取最近24小时的火点数据
            # Note: FIRMS数据有3小时延迟，使用24小时窗口确保完整性
            raw_fires = await self.client.fetch_recent_fires(
                region=self.china_bbox,
                satellite="VIIRS_SNPP_NRT",  # 375m高分辨率
                days=1  # 最近24小时
            )

            if not raw_fires:
                logger.info("nasa_firms_no_data")
                return

            logger.info(
                "nasa_firms_data_fetched",
                total_count=len(raw_fires)
            )

            # 2. 清洗和转换数据
            cleaned_fires = self._clean_fire_data(raw_fires)

            # 3. 过滤低置信度火点
            high_confidence_fires = [
                f for f in cleaned_fires
                if f.get("confidence", 0) >= 70  # 只保留高置信度火点
            ]

            logger.info(
                "nasa_firms_data_filtered",
                total=len(cleaned_fires),
                high_confidence=len(high_confidence_fires),
                confidence_threshold=70
            )

            # 4. 存入数据库
            if high_confidence_fires:
                saved_count = await self.repo.save_fire_hotspots(
                    high_confidence_fires
                )

                logger.info(
                    "nasa_firms_fetch_complete",
                    fetched=len(raw_fires),
                    cleaned=len(cleaned_fires),
                    high_confidence=len(high_confidence_fires),
                    saved=saved_count
                )
            else:
                logger.info("nasa_firms_no_high_confidence_fires")

        except Exception as e:
            logger.error(
                "nasa_firms_fetch_failed",
                error=str(e),
                exc_info=True
            )
            raise

    def _clean_fire_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        清洗火点数据

        转换:
        - 数据类型转换 (字符串 -> 数字/时间)
        - 时间格式转换 (YYYY-MM-DD + HHMM -> datetime)
        - 坐标验证
        - 缺失值处理

        Args:
            raw_data: NASA FIRMS API返回的原始数据

        Returns:
            List[Dict]: 清洗后的火点数据
        """
        cleaned = []

        for fire in raw_data:
            try:
                # 解析采集时间 (UTC)
                acq_datetime = self._parse_datetime(
                    fire["acq_date"],
                    fire["acq_time"]
                )

                # 验证坐标有效性
                lat = float(fire["latitude"])
                lon = float(fire["longitude"])

                if not self._is_valid_coordinate(lat, lon):
                    logger.warning(
                        "nasa_firms_invalid_coordinate",
                        lat=lat,
                        lon=lon
                    )
                    continue

                cleaned_fire = {
                    "lat": lat,
                    "lon": lon,
                    "brightness": float(fire.get("brightness", 0)),
                    "frp": float(fire.get("frp", 0)),  # Fire Radiative Power (MW)
                    "confidence": int(fire.get("confidence", 0)),
                    "acq_datetime": acq_datetime,
                    "satellite": fire.get("satellite", "Unknown"),
                    "daynight": fire.get("daynight", "D"),
                    "scan": float(fire.get("scan", 0)),
                    "track": float(fire.get("track", 0)),
                    "bright_t31": float(fire.get("bright_t31", 0)),
                    "data_source": "NASA_FIRMS",
                    "version": fire.get("version", "")
                }

                cleaned.append(cleaned_fire)

            except (ValueError, KeyError) as e:
                logger.warning(
                    "nasa_firms_parse_error",
                    error=str(e),
                    fire_data=fire
                )
                continue

        return cleaned

    def _parse_datetime(self, date_str: str, time_str: str) -> datetime:
        """
        解析NASA FIRMS时间格式

        Args:
            date_str: YYYY-MM-DD
            time_str: HHMM (UTC)

        Returns:
            datetime: UTC时间
        """
        # 补齐时间为4位 (例如: "100" -> "0100")
        time_padded = time_str.zfill(4)

        # 组合日期和时间
        datetime_str = f"{date_str} {time_padded[:2]}:{time_padded[2:4]}:00"

        return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")

    def _is_valid_coordinate(self, lat: float, lon: float) -> bool:
        """
        验证坐标有效性

        Args:
            lat: 纬度
            lon: 经度

        Returns:
            bool: 坐标是否有效
        """
        # 纬度范围: -90 ~ 90
        # 经度范围: -180 ~ 180
        # 中国及周边: lat 18-54, lon 73-136
        return (
            -90 <= lat <= 90 and
            -180 <= lon <= 180 and
            15 <= lat <= 55 and
            70 <= lon <= 140
        )


# 导出
__all__ = ["NASAFirmsFetcher"]
