"""
Open-Meteo API Client

封装 Open-Meteo API 调用，供 Fetchers 使用
"""
from typing import Dict, Any, List
import asyncio
import httpx
import structlog

logger = structlog.get_logger()


class OpenMeteoClient:
    """
    Open-Meteo API 客户端

    提供对 Open-Meteo API 的封装，包括：
    - ERA5 历史数据
    - 实时观测数据
    - 预报数据
    """

    def __init__(self):
        self.era5_api_url = "https://archive-api.open-meteo.com/v1/archive"
        self.forecast_api_url = "https://api.open-meteo.com/v1/forecast"
        self.timeout = 60  # 增加超时时间到60秒
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 2  # 重试延迟（秒）

        # ERA5 变量列表
        self.era5_variables = [
            "temperature_2m",
            "relative_humidity_2m",
            "dew_point_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "surface_pressure",
            "precipitation",
            "cloud_cover",
            "shortwave_radiation",
            "visibility",
            "boundary_layer_height",
        ]

        # ERA5 压力层变量列表（用于风廓线数据）
        self.era5_pressure_level_variables = [
            "wind_speed_1000hPa",
            "wind_direction_1000hPa",
            "temperature_1000hPa",
            "wind_speed_925hPa",
            "wind_direction_925hPa",
            "temperature_925hPa",
            "wind_speed_850hPa",
            "wind_direction_850hPa",
            "temperature_850hPa",
            "wind_speed_700hPa",
            "wind_direction_700hPa",
            "temperature_700hPa",
            "wind_speed_500hPa",
            "wind_direction_500hPa",
            "temperature_500hPa",
            "wind_speed_400hPa",
            "wind_direction_400hPa",
            "temperature_400hPa",
            "wind_speed_300hPa",
            "wind_direction_300hPa",
            "temperature_300hPa",
            "wind_speed_250hPa",
            "wind_direction_250hPa",
            "temperature_250hPa",
            "wind_speed_200hPa",
            "wind_direction_200hPa",
            "temperature_200hPa",
            "wind_speed_150hPa",
            "wind_direction_150hPa",
            "temperature_150hPa",
            "wind_speed_100hPa",
            "wind_direction_100hPa",
            "temperature_100hPa",
        ]

        # 预报变量列表
        self.forecast_hourly_variables = [
            "temperature_2m",
            "relative_humidity_2m",
            "dew_point_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "surface_pressure",
            "precipitation",
            "precipitation_probability",
            "weather_code",
            "cloud_cover",
            "visibility",
            "boundary_layer_height",  # 关键！
            "shortwave_radiation",  # 短波辐射 (W/m²) - 判断辐射冷却
            "uv_index",  # 紫外辐射指数
        ]

        self.forecast_daily_variables = [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "weather_code",
            "sunshine_duration",  # 日照时长
            "uv_index_max",  # 最大紫外指数
        ]

        # 当前天气变量列表
        self.current_variables = [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "is_day",
            "precipitation",
            "rain",
            "showers",
            "snowfall",
            "weather_code",
            "cloud_cover",
            "surface_pressure",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "uv_index",  # 当前紫外指数
        ]

    async def fetch_era5_data(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        获取 ERA5 历史数据（带重试机制）

        Args:
            lat: 纬度
            lon: 经度
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            Dict: API 响应数据

        Raises:
            Exception: API 调用失败
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(self.era5_variables),
            "timezone": "UTC",
        }

        # 创建带连接池的 httpx 客户端
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(timeout=self.timeout, limits=limits) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.get(self.era5_api_url, params=params)

                    if response.status_code == 200:
                        logger.debug(
                            "era5_api_success",
                            lat=lat,
                            lon=lon,
                            date=start_date,
                            attempt=attempt + 1
                        )
                        return response.json()
                    elif response.status_code == 429:
                        # 限流错误，等待后重试
                        if attempt < self.max_retries:
                            wait_time = self.retry_delay * (attempt + 1)
                            logger.warning(
                                "era5_api_rate_limited",
                                lat=lat,
                                lon=lon,
                                attempt=attempt + 1,
                                retry_in=wait_time
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise Exception(
                                f"ERA5 API rate limit exceeded after {self.max_retries} retries"
                            )
                    else:
                        raise Exception(
                            f"ERA5 API error: {response.status_code} - {response.text}"
                        )

                except (httpx.TimeoutException, httpx.ConnectError, httpx.ConnectTimeout) as e:
                    if attempt < self.max_retries:
                        wait_time = self.retry_delay * (attempt + 1)
                        logger.warning(
                            "era5_api_retry",
                            lat=lat,
                            lon=lon,
                            attempt=attempt + 1,
                            max_retries=self.max_retries,
                            error=str(e),
                            retry_in=wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error("era5_api_failed", lat=lat, lon=lon, error=str(e))
                        raise Exception(f"ERA5 API connection failed after {self.max_retries} retries: {str(e)}")

                except Exception as e:
                    # 非网络错误，直接抛出
                    logger.error("era5_api_failed", lat=lat, lon=lon, error=str(e))
                    raise

        # 理论上不会到达这里，但为了类型安全
        raise Exception("Unexpected error in fetch_era5_data")

    async def fetch_current_weather(
        self,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """
        获取实时天气数据

        Args:
            lat: 纬度
            lon: 经度

        Returns:
            Dict: API 响应数据

        Raises:
            Exception: API 调用失败
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(self.current_variables),
            "timezone": "UTC",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.forecast_api_url, params=params)

                if response.status_code == 200:
                    logger.debug(
                        "current_weather_api_success",
                        lat=lat,
                        lon=lon
                    )
                    return response.json()
                else:
                    raise Exception(
                        f"Current weather API error: {response.status_code} - {response.text}"
                    )
        except httpx.TimeoutException:
            logger.error("current_weather_api_timeout", lat=lat, lon=lon)
            raise Exception("Current weather API timeout")
        except Exception as e:
            logger.error("current_weather_api_failed", lat=lat, lon=lon, error=str(e))
            raise

    async def fetch_forecast(
        self,
        lat: float,
        lon: float,
        forecast_days: int = 7,
        past_days: int = 0,
        hourly: bool = True,
        daily: bool = True
    ) -> Dict[str, Any]:
        """
        获取天气预报数据（支持获取过去天数）

        Args:
            lat: 纬度
            lon: 经度
            forecast_days: 预报天数 (1-16)
            past_days: 获取过去天数 (0-5)，用于获取今天和昨天的数据
            hourly: 是否包含逐小时预报
            daily: 是否包含每日预报

        Returns:
            Dict: API 响应数据，包含：
                - hourly: 逐小时数据（如果 hourly=True）
                - daily: 每日数据（如果 daily=True）
                - 重要：包含 boundary_layer_height（边界层高度）
                - past_days>0 时，包含过去的历史分析数据

        Raises:
            Exception: API 调用失败

        Note:
            使用 past_days=1 可以获取：
            - 昨天完整24小时数据
            - 今天00:00到当前时刻的数据（分析场数据，非预报）
            - 未来7天预报数据
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "UTC",
            "forecast_days": min(forecast_days, 16),  # 最多16天
            "past_days": min(past_days, 5),  # 最多5天历史数据
        }

        # 添加逐小时预报变量
        if hourly:
            params["hourly"] = ",".join(self.forecast_hourly_variables)

        # 添加每日预报变量
        if daily:
            params["daily"] = ",".join(self.forecast_daily_variables)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.forecast_api_url, params=params)

                if response.status_code == 200:
                    logger.info(
                        "forecast_api_success",
                        lat=lat,
                        lon=lon,
                        forecast_days=forecast_days,
                        past_days=past_days,
                        hourly=hourly,
                        daily=daily
                    )
                    return response.json()
                else:
                    raise Exception(
                        f"Forecast API error: {response.status_code} - {response.text}"
                    )
        except httpx.TimeoutException:
            logger.error("forecast_api_timeout", lat=lat, lon=lon)
            raise Exception("Forecast API timeout")
        except Exception as e:
            logger.error("forecast_api_failed", lat=lat, lon=lon, error=str(e))
            raise

    async def fetch_era5_pressure_level_data(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
        pressure_levels: List[int] = None
    ) -> Dict[str, Any]:
        """
        获取 ERA5 压力层数据（风廓线）

        用于获取不同气压高度层的气象数据，构建精确的风廓线

        Args:
            lat: 纬度
            lon: 经度
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            pressure_levels: 气压层列表，默认 [1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100]

        Returns:
            Dict: API 响应数据，包含多高度层风速、风向、温度

        Raises:
            Exception: API 调用失败
        """
        if pressure_levels is None:
            pressure_levels = [1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100]

        # 构建压力层变量列表
        variables = []
        for level in pressure_levels:
            for var in ["wind_speed", "wind_direction", "temperature"]:
                variables.append(f"{var}_{level}hPa")

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(variables),
            "timezone": "UTC",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.era5_api_url, params=params)

                if response.status_code == 200:
                    logger.debug(
                        "era5_pressure_level_api_success",
                        lat=lat,
                        lon=lon,
                        date=start_date,
                        pressure_levels=pressure_levels
                    )
                    return response.json()
                else:
                    raise Exception(
                        f"ERA5 Pressure Level API error: {response.status_code} - {response.text}"
                    )
        except httpx.TimeoutException:
            logger.error("era5_pressure_level_api_timeout", lat=lat, lon=lon)
            raise Exception("ERA5 Pressure Level API timeout")
        except Exception as e:
            logger.error("era5_pressure_level_api_failed", lat=lat, lon=lon, error=str(e))
            raise
