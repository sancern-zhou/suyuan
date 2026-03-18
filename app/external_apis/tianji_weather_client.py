"""
天机气象API客户端 (Tianji Weather API Client)

提供对中科天机高精度气象预报数据的访问
支持轨迹分析、气象预报、风廓线等应用场景

特点:
- 全球范围覆盖
- 15分钟/1小时时间分辨率
- 19个压力层垂直数据
- 最多45天预报时长
- REST API (JSON格式)

版本: v1.0.0
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import httpx
import structlog
import asyncio
from pathlib import Path

logger = structlog.get_logger()


class TianjiWeatherClient:
    """
    天机气象API客户端

    提供高精度的气象数据访问，包括：
    1. 高空气象场数据（19个压力层）
    2. 近地面气象要素
    3. 风廓线数据（30m-170m）
    4. 辐射和云量数据
    """

    def __init__(self, api_key: str, use_beta: bool = True):
        """
        初始化天机API客户端

        Args:
            api_key: API认证密钥
            use_beta: 是否使用测试环境 (beta)
                - True: 使用beta测试接口 (https://api.tjweather.com/beta)
                - False: 使用正式生产接口 (https://api.tjweather.com)
                注意：当前提供的API密钥仅适用于beta接口
        """
        self.api_key = api_key
        self.base_url = "https://api.tjweather.com/beta" if use_beta else "https://api.tjweather.com"

        # 记录接口版本
        if use_beta:
            logger.info(
                "tianji_client_beta_version",
                message="使用beta测试接口，功能可能受限",
                api_url=self.base_url
            )
        else:
            logger.warning(
                "tianji_client_production_version",
                message="尝试使用正式生产接口，需要相应的API密钥",
                api_url=self.base_url
            )
        self.timeout = 60

        # 压力层列表（与HYSPLIT标准对齐）
        self.pressure_levels = [
            1000, 925, 850, 800, 700, 600, 500,
            400, 300, 200, 100
        ]

        # 轨迹分析所需的气象变量
        # 注意：当前使用beta接口，字段支持有限
        # 正式版本API密钥才支持完整字段
        self.trajectory_variables = {
            # 高空风场（轨迹计算必需）
            # 警告：beta版本当前不支持压力层数据
            "u_components": [f"u{level}" for level in self.pressure_levels],
            "v_components": [f"v{level}" for level in self.pressure_levels],
            "temperature": [f"t{level}" for level in self.pressure_levels],
            "geopotential_height": [f"h{level}" for level in self.pressure_levels],
            "vertical_velocity": [f"omg{level}" for level in self.pressure_levels],
            "specific_humidity": [f"q{level}" for level in self.pressure_levels],
            "relative_humidity": [f"rh{level}" for level in self.pressure_levels],

            # 地面观测（轨迹起始条件）
            # 已验证有效的字段：t2m, rh2m, ws10m, wd10m, tp
            # 不支持的字段：psfc, ws100m, wd100m
            "surface": ["t2m", "rh2m", "ws10m", "wd10m", "tp"],

            # 辅助数据
            # 不支持的字段：cape, slp, ssrd
            "boundary_layer": [],  # cape, slp - beta版本不支持
            "precipitation": ["tp"],  # 降水 - tp有效
            "radiation": [],  # ssrd - beta版本不支持
            "cloud": [],  # cldt, cldl - 未测试
        }

        logger.info("tianji_weather_client_initialized", api_key_prefix=api_key[:8] + "...")

    async def fetch_trajectory_meteorology(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        hours_forward: int = 72,
        time_resolution: str = "1h"
    ) -> Dict[str, Any]:
        """
        获取轨迹分析所需的气象数据

        Args:
            lat: 纬度
            lon: 经度
            start_time: 起始时间
            hours_forward: 向前预报小时数
            time_resolution: 时间分辨率 ("15min" 或 "1h")

        Returns:
            包含19层高空数据 + 地面数据的气象场数据
        """
        try:
            # 计算预报天数和小时数
            fcst_days = hours_forward // 24
            fcst_hours = hours_forward % 24

            # 构建坐标字符串（经度在前，纬度在后）
            location = f"{lon},{lat}"

            # 构建气象要素列表（轨迹分析必需）
            fields = []

            # 注意：天机API beta版本不支持压力层数据
            # 当前只使用地面观测数据

            # 1. 地面观测（轨迹起始条件）
            fields.extend(self.trajectory_variables["surface"])

            # 2. 辅助数据
            fields.extend(self.trajectory_variables["precipitation"])

            # 如果没有可用字段，返回错误
            if not fields:
                raise ValueError("天机API beta版本不支持轨迹分析所需的压力层数据")

            # 构建请求参数
            params = {
                "key": self.api_key,
                "loc": location,
                "t_res": time_resolution,
                "fcst_days": fcst_days,
                "fcst_hours": fcst_hours,
                "fields": ",".join(fields),
                "tz": 8  # 北京时区
            }

            logger.info(
                "tianji_trajectory_fetch_start",
                lat=lat,
                lon=lon,
                start_time=start_time.isoformat(),
                hours_forward=hours_forward,
                fields_count=len(fields)
            )

            # 发起API请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

            # 解析响应
            result = response.json()

            # 验证响应格式
            if result.get("code") != 200:
                raise ValueError(f"天机API错误: {result.get('message', '未知错误')}")

            # 转换数据格式
            trajectory_data = self._convert_to_trajectory_format(
                api_response=result,
                lat=lat,
                lon=lon,
                start_time=start_time
            )

            logger.info(
                "tianji_trajectory_fetch_success",
                lat=lat,
                lon=lon,
                time_points=len(trajectory_data.get("time_series", [])),
                variables=len(fields)
            )

            return {
                "success": True,
                "data": trajectory_data,
                "metadata": {
                    "source": "tianji_weather",
                    "api_url": self.base_url,
                    "lat": lat,
                    "lon": lon,
                    "time_resolution": time_resolution,
                    "pressure_levels": self.pressure_levels,
                    "forecast_hours": hours_forward
                }
            }

        except httpx.TimeoutException:
            logger.error("tianji_api_timeout", lat=lat, lon=lon)
            return {"success": False, "error": "天机API请求超时"}

        except httpx.HTTPStatusError as e:
            logger.error(
                "tianji_api_http_error",
                lat=lat,
                lon=lon,
                status_code=e.response.status_code
            )
            return {"success": False, "error": f"天机API HTTP错误: {e.response.status_code}"}

        except Exception as e:
            logger.error("tianji_trajectory_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {"success": False, "error": str(e)}

    async def fetch_current_weather(
        self,
        lat: float,
        lon: float,
        variables: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        获取当前天气数据

        Args:
            lat: 纬度
            lon: 经度
            variables: 要获取的气象变量列表

        Returns:
            当前天气数据
        """
        try:
            if variables is None:
                # 使用已验证有效的字段（不包含psfc等不支持的字段）
                variables = ["t2m", "rh2m", "ws10m", "wd10m"]

            location = f"{lon},{lat}"

            # API要求至少1小时的预报时间，不能为0
            params = {
                "key": self.api_key,
                "loc": location,
                "t_res": "1h",
                "fcst_days": 0,
                "fcst_hours": 1,  # 至少1小时
                "fields": ",".join(variables)
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

            result = response.json()

            if result.get("code") != 200:
                raise ValueError(f"天机API错误: {result.get('message')}")

            # 提取当前时刻数据（第一个时间点）
            current_data = {}
            if result.get("data", {}).get("data"):
                time_series = result["data"]["data"]
                if time_series:
                    current_data = time_series[0]

            logger.info(
                "tianji_current_weather_success",
                lat=lat,
                lon=lon,
                variables=variables
            )

            return {
                "success": True,
                "data": current_data,
                "metadata": {
                    "source": "tianji_weather",
                    "api_url": self.base_url,
                    "lat": lat,
                    "lon": lon
                }
            }

        except Exception as e:
            logger.error("tianji_current_weather_failed", lat=lat, lon=lon, error=str(e))
            return {"success": False, "error": str(e)}

    async def fetch_wind_profile(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        hours_forward: int = 24
    ) -> Dict[str, Any]:
        """
        获取风廓线数据（多高度层风速风向）

        Args:
            lat: 纬度
            lon: 经度
            start_time: 起始时间
            hours_forward: 向前预报小时数

        Returns:
            包含30m-170m风廓线的数据
        """
        try:
            location = f"{lon},{lat}"

            # 风廓线高度层
            wind_profile_heights = [30, 50, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150, 160, 170]

            # 构建风速风向字段列表
            fields = []
            for height in wind_profile_heights:
                fields.extend([f"ws{height}m", f"wd{height}m"])

            params = {
                "key": self.api_key,
                "loc": location,
                "t_res": "1h",
                "fcst_days": hours_forward // 24,
                "fcst_hours": hours_forward % 24,
                "fields": ",".join(fields)
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

            result = response.json()

            if result.get("code") != 200:
                raise ValueError(f"天机API错误: {result.get('message')}")

            logger.info(
                "tianji_wind_profile_success",
                lat=lat,
                lon=lon,
                heights=wind_profile_heights,
                hours=hours_forward
            )

            return {
                "success": True,
                "data": result["data"],
                "metadata": {
                    "source": "tianji_weather",
                    "heights": wind_profile_heights,
                    "api_url": self.base_url
                }
            }

        except Exception as e:
            logger.error("tianji_wind_profile_failed", lat=lat, lon=lon, error=str(e))
            return {"success": False, "error": str(e)}

    def _convert_to_trajectory_format(
        self,
        api_response: Dict[str, Any],
        lat: float,
        lon: float,
        start_time: datetime
    ) -> Dict[str, Any]:
        """
        将天机API响应转换为HYSPLIT轨迹计算可用的格式

        Args:
            api_response: 天机API原始响应
            lat: 纬度
            lon: 经度
            start_time: 起始时间

        Returns:
            转换后的气象数据格式
        """
        try:
            data = api_response.get("data", {})
            time_series = data.get("data", [])
            units = data.get("units", {})

            if not time_series:
                return {"error": "无时间序列数据"}

            # 构建时间序列
            processed_data = []

            for i, point in enumerate(time_series):
                timestamp_str = point.get("time", "")
                try:
                    # 解析时间（天机API返回格式: "2024-01-03T21:00+08:00"）
                    if "+08:00" in timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("+08:00", "+08:00"))
                    else:
                        timestamp = datetime.fromisoformat(timestamp_str)
                except:
                    timestamp = start_time + timedelta(hours=i)

                # 构建单点气象数据
                meteorology_point = {
                    "timestamp": timestamp.isoformat(),
                    "lat": lat,
                    "lon": lon,
                    "hour_index": i
                }

                # 提取高空数据（19个压力层）
                for level in self.pressure_levels:
                    level_data = {}
                    for var_type in ["u", "v", "t", "h", "omg", "q", "rh"]:
                        var_name = f"{var_type}{level}"
                        if var_name in point and point[var_name] is not None:
                            # 单位转换（K转°C，比湿保持kg/kg）
                            if var_type == "t" and point[var_name] is not None:
                                level_data[var_name] = float(point[var_name]) - 273.15  # K转°C
                            else:
                                level_data[var_name] = float(point[var_name])

                    if level_data:
                        meteorology_point[f"level_{level}"] = level_data

                # 提取地面数据
                surface_vars = ["t2m", "rh2m", "psfc", "ws10m", "wd10m", "ws100m", "wd100m"]
                surface_data = {}
                for var in surface_vars:
                    if var in point and point[var] is not None:
                        value = float(point[var])
                        # 单位转换
                        if var == "t2m":
                            value = value - 273.15  # K转°C
                        elif var == "psfc":
                            value = value / 100.0  # Pa转hPa
                        surface_data[var] = value

                if surface_data:
                    meteorology_point["surface"] = surface_data

                # 提取其他要素
                other_vars = ["tp", "prer", "cldt", "cldl", "cape", "slp"]
                for var in other_vars:
                    if var in point and point[var] is not None:
                        meteorology_point[var] = float(point[var])

                processed_data.append(meteorology_point)

            return {
                "time_series": processed_data,
                "pressure_levels": self.pressure_levels,
                "units": units,
                "total_points": len(processed_data)
            }

        except Exception as e:
            logger.error("tianji_data_conversion_failed", error=str(e))
            return {"error": f"数据转换失败: {str(e)}"}

    def get_available_variables(self) -> Dict[str, List[str]]:
        """
        获取所有可用的气象变量列表

        Returns:
            按类别分组的气象变量列表
        """
        return self.trajectory_variables.copy()

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查 - 测试API连接

        Returns:
            健康检查结果
        """
        try:
            # 使用北京坐标进行测试
            test_result = await self.fetch_current_weather(
                lat=39.9042,
                lon=116.4074,
                variables=["t2m"]
            )

            return {
                "status": "healthy" if test_result["success"] else "unhealthy",
                "api_accessible": test_result["success"],
                "test_location": "Beijing",
                "error": test_result.get("error") if not test_result["success"] else None
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "api_accessible": False,
                "error": str(e)
            }


# 导出
__all__ = ["TianjiWeatherClient"]
