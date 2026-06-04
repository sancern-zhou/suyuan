"""
Open-Meteo ERA5 Client for Trajectory Analysis (MVP Version)

专门用于气象轨迹分析的Open-Meteo ERA5数据客户端
提供简化的气象数据获取功能，无需认证
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import httpx
import structlog

logger = structlog.get_logger()


class OpenMeteoERA5Client:
    """
    Open-Meteo ERA5数据客户端 - MVP版本

    专门用于轨迹分析的气象数据获取
    特点：无需认证、简单易用、适合快速原型开发
    """

    BASE_URL = "https://archive-api.open-meteo.com/v1/era5"

    def __init__(self):
        self.timeout = 60  # 60秒超时

    async def fetch_era5_for_trajectory(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        hours_backward: int = 72
    ) -> Dict[str, Any]:
        """
        获取ERA5气象数据用于轨迹分析

        Args:
            lat: 纬度
            lon: 经度
            start_time: 轨迹起始时间（UTC）
            hours_backward: 回溯小时数

        Returns:
            ERA5气象数据（包含u/v风速、气压层级）

        示例返回:
        {
            "success": True,
            "data": {
                "hourly": {
                    "time": ["2025-11-19T00:00", ...],
                    "temperature_2m": [18.5, ...],
                    "pressure_msl": [1013.2, ...],
                    "windspeed_10m": [5.2, ...],
                    "winddirection_10m": [135.0, ...],
                    "temperature_850hPa": [10.2, ...],
                    "geopotential_height_850hPa": [1500, ...]
                }
            },
            "metadata": {
                "source": "open-meteo-era5",
                "lat": 23.13,
                "lon": 113.26,
                "time_range": "2025-11-16 to 2025-11-19"
            }
        }
        """
        try:
            # 计算时间范围（支持正向和反向轨迹）
            # hours_backward > 0: 反向轨迹（回溯过去）
            # hours_backward < 0: 正向轨迹（预测未来，实际使用历史数据模拟）
            time_end = start_time
            time_start = start_time - timedelta(hours=hours_backward)

            # 确保start_date <= end_date
            start_date = min(time_start, time_end).date()
            end_date = max(time_start, time_end).date()

            logger.info(
                "era5_fetch_start",
                lat=lat,
                lon=lon,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                hours_backward=hours_backward
            )

            # 构建API请求参数
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "hourly": [
                    # 地面变量
                    "temperature_2m",
                    "pressure_msl",  # 海平面气压
                    "windspeed_10m",
                    "winddirection_10m",

                    # 多层级气压数据（用于轨迹计算）
                    "temperature_850hPa",
                    "temperature_700hPa",
                    "temperature_500hPa",
                    "geopotential_height_850hPa",
                    "geopotential_height_700hPa",
                    "geopotential_height_500hPa",

                    # 边界层高度
                    "boundary_layer_height"
                ],
                "timezone": "UTC"
            }

            # 转换数组为逗号分隔字符串
            params["hourly"] = ",".join(params["hourly"])

            # 发起HTTP请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()

            # 解析响应
            data = response.json()

            # 验证数据完整性
            if "hourly" not in data or "time" not in data.get("hourly", {}):
                raise ValueError("ERA5 API返回数据格式不完整")

            hours_count = len(data["hourly"]["time"])

            logger.info(
                "era5_fetch_success",
                lat=lat,
                lon=lon,
                hours=hours_count,
                time_range=f"{start_date} to {end_date}"
            )

            return {
                "success": True,
                "data": data,
                "metadata": {
                    "source": "open-meteo-era5",
                    "lat": lat,
                    "lon": lon,
                    "time_range": f"{start_date} to {end_date}",
                    "hours_count": hours_count,
                    "api_url": self.BASE_URL
                }
            }

        except httpx.TimeoutException:
            logger.error("era5_api_timeout", lat=lat, lon=lon)
            return {
                "success": False,
                "error": "ERA5 API请求超时",
                "metadata": {"source": "open-meteo-era5"}
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "era5_api_http_error",
                lat=lat,
                lon=lon,
                status_code=e.response.status_code,
                error=str(e)
            )
            return {
                "success": False,
                "error": f"ERA5 API HTTP错误: {e.response.status_code}",
                "metadata": {"source": "open-meteo-era5"}
            }

        except Exception as e:
            logger.error("era5_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "metadata": {"source": "open-meteo-era5"}
            }
