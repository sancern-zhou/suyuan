"""
NASA FIRMS API Client

NASA Fire Information for Resource Management System (FIRMS)
提供全球火点数据，用于识别生物质燃烧污染源
"""
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime, timedelta
import csv
from io import StringIO
import structlog
import asyncio

logger = structlog.get_logger()


class NASAFirmsClient:
    """
    NASA FIRMS API客户端

    提供火点数据查询功能：
    - VIIRS (375m分辨率，推荐)
    - MODIS (1km分辨率)

    数据来源: https://firms.modaps.eosdis.nasa.gov/
    """

    def __init__(self, api_key: str = "699228d5b8d9c0767417ef80c6d2e07b"):
        """
        初始化NASA FIRMS客户端

        Args:
            api_key: NASA FIRMS MAP KEY
        """
        self.base_url = "https://firms.modaps.eosdis.nasa.gov"
        self.api_key = api_key
        self.timeout = 60

    async def fetch_recent_fires(
        self,
        region: str = "china",
        satellite: str = "VIIRS_SNPP_NRT",
        days: int = 1,
        date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近N天的火点数据

        Args:
            region: 区域名称（如"china"）或经纬度范围（如"73,18,136,54"）
            satellite: 卫星平台
                - VIIRS_SNPP_NRT: Suomi NPP卫星，375m分辨率（推荐）
                - VIIRS_NOAA20_NRT: NOAA-20卫星，375m分辨率
                - MODIS_NRT: MODIS，1km分辨率
            days: 查询天数（1-10天）
            date: 查询日期（YYYY-MM-DD格式），默认为今天

        Returns:
            List[Dict]: 火点数据列表，每个火点包含：
                - latitude: 纬度
                - longitude: 经度
                - brightness: 亮温 (K)
                - scan: 扫描角度
                - track: 轨迹角度
                - acq_date: 采集日期
                - acq_time: 采集时间 (HHMM UTC)
                - satellite: 卫星标识
                - confidence: 置信度 (0-100)
                - version: 数据版本
                - bright_t31: 通道31亮温 (K)
                - frp: 火灾辐射功率 (MW)
                - daynight: 昼/夜 (D/N)

        Raises:
            Exception: API调用失败
        """
        # 确定查询日期
        if date is None:
            query_date = datetime.now().strftime("%Y-%m-%d")
        else:
            query_date = date

        # 构建API URL
        # API格式: /api/area/csv/{MAP_KEY}/{source}/{area}/{day_range}/{date}
        url = f"{self.base_url}/api/area/csv/{self.api_key}/{satellite}/{region}/{days}/{query_date}"

        try:
            logger.info(
                "nasa_firms_fetch_start",
                url=url,
                region=region,
                satellite=satellite,
                days=days,
                date=query_date
            )

            # 【修复】使用标准httpx配置（移除不兼容的Retry配置）
            timeout_config = httpx.Timeout(
                connect=30.0,  # 连接超时30秒
                read=60.0,     # 读取超时60秒
                write=30.0,    # 写入超时30秒
                pool=30.0      # 连接池超时30秒
            )

            async with httpx.AsyncClient(
                timeout=timeout_config,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as client:
                response = await client.get(url, follow_redirects=True)

                if response.status_code == 200:
                    # 解析CSV格式数据
                    fires = self._parse_csv(response.text)

                    logger.info(
                        "nasa_firms_fetch_success",
                        count=len(fires),
                        region=region,
                        satellite=satellite
                    )

                    return fires

                elif response.status_code == 404:
                    # 无数据返回空列表
                    logger.warning(
                        "nasa_firms_no_data",
                        region=region,
                        date=query_date
                    )
                    return []

                else:
                    error_msg = f"NASA FIRMS API error: {response.status_code} - {response.text[:200]}"
                    logger.error(
                        "nasa_firms_fetch_failed",
                        status_code=response.status_code,
                        error=response.text[:200]
                    )
                    raise Exception(error_msg)

        except httpx.TimeoutException as e:
            logger.error("nasa_firms_timeout", region=region, date=query_date, error=str(e))
            raise Exception(f"NASA FIRMS API timeout after {self.timeout}s")

        except asyncio.CancelledError as e:
            logger.error("nasa_firms_cancelled", region=region, date=query_date)
            raise Exception(f"NASA FIRMS API request was cancelled: {str(e)}")

        except httpx.ConnectError as e:
            logger.error("nasa_firms_connect_error", region=region, date=query_date, error=str(e))
            raise Exception(f"NASA FIRMS API connection error: {str(e)}")

        except Exception as e:
            logger.error("nasa_firms_error", error=str(e), region=region, exc_info=True)
            raise

    async def fetch_fires_by_bbox(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        satellite: str = "VIIRS_SNPP_NRT",
        days: int = 1,
        date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        根据经纬度范围查询火点数据

        Args:
            min_lat: 最小纬度
            max_lat: 最大纬度
            min_lon: 最小经度
            max_lon: 最大经度
            satellite: 卫星平台
            days: 查询天数
            date: 查询日期

        Returns:
            List[Dict]: 火点数据列表
        """
        # FIRMS API格式: min_lon,min_lat,max_lon,max_lat
        bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"

        return await self.fetch_recent_fires(
            region=bbox,
            satellite=satellite,
            days=days,
            date=date
        )

    def _parse_csv(self, csv_text: str) -> List[Dict[str, Any]]:
        """
        解析CSV格式的火点数据

        Args:
            csv_text: CSV文本

        Returns:
            List[Dict]: 解析后的火点数据列表
        """
        if not csv_text or csv_text.strip() == "":
            return []

        try:
            reader = csv.DictReader(StringIO(csv_text))
            fires = []

            for row in reader:
                # 转换数据类型
                fire = {
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "brightness": float(row["brightness"]),
                    "scan": float(row.get("scan", 0)),
                    "track": float(row.get("track", 0)),
                    "acq_date": row["acq_date"],
                    "acq_time": row["acq_time"],
                    "satellite": row["satellite"],
                    "confidence": self._parse_confidence(row["confidence"]),
                    "version": row.get("version", ""),
                    "bright_t31": float(row.get("bright_t31", 0)),
                    "frp": float(row["frp"]),
                    "daynight": row.get("daynight", "D")
                }
                fires.append(fire)

            return fires

        except Exception as e:
            logger.error("nasa_firms_parse_error", error=str(e))
            return []

    def _parse_confidence(self, confidence_str: str) -> int:
        """
        解析置信度

        VIIRS置信度: low/nominal/high
        MODIS置信度: 0-100数字

        Args:
            confidence_str: 置信度字符串

        Returns:
            int: 数字置信度 (0-100)
        """
        # 如果是数字，直接返回
        try:
            return int(confidence_str)
        except ValueError:
            pass

        # VIIRS文本置信度转换
        confidence_map = {
            "low": 30,
            "nominal": 70,
            "high": 90
        }

        return confidence_map.get(confidence_str.lower(), 50)


# 导出
__all__ = ["NASAFirmsClient"]
