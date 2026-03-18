"""
天机气象数据获取工具 (Tianji Weather Data Tool)

基于中科天机API的高精度气象数据获取工具

功能：
1. 获取19个压力层的高空气象数据（轨迹分析）
2. 获取多高度层风廓线数据（30m-170m）
3. 获取地面气象观测数据
4. 获取辐射、云量、降水等辅助数据
5. 支持15分钟/1小时时间分辨率
6. 支持最多45天预报时长

特点：
- 全球范围覆盖
- Context-Aware V2架构
- UDF v2.0标准格式输出
- 完美替代GDAS/GFS数据

版本: v1.0.0
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Union, TYPE_CHECKING
from datetime import datetime, timedelta
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.external_apis.tianji_weather_client import TianjiWeatherClient
from app.schemas.unified import UnifiedDataRecord, DataMetadata, DataType, DataStatus

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetTianjiWeatherTool(LLMTool):
    """
    天机气象数据获取工具

    提供对中科天机高精度气象预报数据的访问
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化天机气象工具

        Args:
            api_key: API认证密钥，如果不提供则从环境变量读取
        """
        if api_key is None:
            import os
            api_key = os.getenv("TIANJI_API_KEY")

        if not api_key:
            raise ValueError(
                "天机API密钥未提供。请设置TIANJI_API_KEY环境变量"
                "或在初始化时传入api_key参数"
            )

        function_schema = {
            "name": "get_tianji_weather",
            "description": """
基于中科天机API获取高精度气象数据。

**特点**：
- 全球范围覆盖，任意经纬度查询
- 15分钟/1小时时间分辨率
- 19个压力层高空气象数据
- 多高度层风廓线数据（30m-170m）
- 最多45天预报时长

**功能**：
1. 高空气象场数据（轨迹分析核心数据）
   - U/V风分量（19个压力层：1000hPa-100hPa）
   - 温度、位势高度、比湿、相对湿度
   - 垂直速度（omega）

2. 近地面气象要素
   - 2米温度、湿度
   - 10米/100米风速风向
   - 地表气压、降水

3. 风廓线数据（风机分析专用）
   - 30m-170m多高度层风速风向
   - 适合风机选址、风资源评估

4. 辅助气象数据
   - 辐射（总辐射、散辐射、直辐射）
   - 云量（总云量、低云量）
   - 对流有效位能（CAPE）

**参数**：
- lat/lon: 查询位置坐标
- data_type: 数据类型（atmospheric_for_trajectory, surface_observation, wind_profile）
- start_time: 起始时间
- forecast_hours: 预报小时数（最多45天）
- time_resolution: 时间分辨率（15min 或 1h）

**返回格式**：
- UDF v2.0统一数据格式
- 包含完整的气象要素和元数据
- 适合轨迹分析和可视化
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "纬度（-90到90度）"
                    },
                    "lon": {
                        "type": "number",
                        "description": "经度（-180到180度）"
                    },
                    "data_type": {
                        "type": "string",
                        "enum": [
                            "atmospheric_for_trajectory",  # 高空气象场（轨迹分析）
                            "surface_observation",         # 地面观测
                            "wind_profile"                 # 风廓线数据
                        ],
                        "description": "数据类型",
                        "default": "atmospheric_for_trajectory"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "起始时间（ISO 8601格式，默认当前时间）"
                    },
                    "forecast_hours": {
                        "type": "integer",
                        "description": "预报小时数（1-1080小时，默认72）",
                        "minimum": 1,
                        "maximum": 1080,
                        "default": 72
                    },
                    "time_resolution": {
                        "type": "string",
                        "enum": ["15min", "1h"],
                        "description": "时间分辨率（15分钟或1小时，默认1h）",
                        "default": "1h"
                    }
                },
                "required": ["lat", "lon"]
            }
        }

        super().__init__(
            name="get_tianji_weather",
            description="Get high-precision meteorological data from Tianji Weather API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True  # Context-Aware V2
        )

        # 初始化天机API客户端
        self.tianji_client = TianjiWeatherClient(api_key=api_key)
        logger.info("tianji_weather_tool_initialized", api_key_prefix=api_key[:8] + "...")

    async def execute(
        self,
        context: ExecutionContext,
        lat: float,
        lon: float,
        data_type: str = "atmospheric_for_trajectory",
        start_time: Optional[str] = None,
        forecast_hours: int = 72,
        time_resolution: str = "1h",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行天机气象数据获取

        Args:
            context: ExecutionContext for data storage
            lat: 纬度
            lon: 经度
            data_type: 数据类型
            start_time: 起始时间
            forecast_hours: 预报小时数
            time_resolution: 时间分辨率

        Returns:
            Dict: UDF v2.0格式的气象数据
        """
        try:
            # 处理时间参数
            if start_time:
                try:
                    start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                except:
                    start_datetime = datetime.utcnow()
            else:
                start_datetime = datetime.utcnow()

            logger.info(
                "tianji_weather_query_started",
                lat=lat,
                lon=lon,
                data_type=data_type,
                start_time=start_datetime.isoformat(),
                forecast_hours=forecast_hours,
                time_resolution=time_resolution,
                session_id=context.session_id
            )

            # 根据数据类型选择获取方式
            if data_type == "atmospheric_for_trajectory":
                result = await self._fetch_atmospheric_data(
                    lat=lat,
                    lon=lon,
                    start_time=start_datetime,
                    forecast_hours=forecast_hours,
                    time_resolution=time_resolution
                )
            elif data_type == "surface_observation":
                result = await self._fetch_surface_data(
                    lat=lat,
                    lon=lon
                )
            elif data_type == "wind_profile":
                result = await self._fetch_wind_profile_data(
                    lat=lat,
                    lon=lon,
                    start_time=start_datetime,
                    forecast_hours=min(24, forecast_hours)  # 风廓线最多24小时
                )
            else:
                raise ValueError(f"不支持的数据类型: {data_type}")

            if not result["success"]:
                return self._create_error_response(result["error"], lat, lon)

            # 保存数据到Context
            data_id = await self._save_to_context(
                context=context,
                data=result["data"],
                lat=lat,
                lon=lon,
                data_type=data_type,
                metadata=result["metadata"]
            )

            # 构建UDF v2.0响应
            return self._build_udf_response(
                data=result["data"],
                data_id=data_id,
                lat=lat,
                lon=lon,
                data_type=data_type,
                metadata=result["metadata"]
            )

        except Exception as e:
            logger.error(
                "tianji_weather_query_failed",
                lat=lat,
                lon=lon,
                data_type=data_type,
                error=str(e),
                exc_info=True
            )
            return self._create_error_response(str(e), lat, lon)

    async def _fetch_atmospheric_data(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        forecast_hours: int,
        time_resolution: str
    ) -> Dict[str, Any]:
        """获取高空气象场数据（轨迹分析专用）"""
        try:
            tianji_result = await self.tianji_client.fetch_trajectory_meteorology(
                lat=lat,
                lon=lon,
                start_time=start_time,
                hours_forward=forecast_hours,
                time_resolution=time_resolution
            )

            if not tianji_result["success"]:
                return {"success": False, "error": tianji_result["error"]}

            # 转换为UnifiedDataRecord格式
            records = []
            time_series = tianji_result["data"].get("time_series", [])

            for i, point in enumerate(time_series):
                # 提取高空数据
                measurements = {}

                # 19个压力层数据
                for level in [1000, 925, 850, 800, 700, 600, 500, 400, 300, 200, 100]:
                    level_key = f"level_{level}"
                    if level_key in point:
                        level_data = point[level_key]
                        for var, value in level_data.items():
                            measurements[f"{var}_{level}hPa"] = value

                # 地面数据
                if "surface" in point:
                    for var, value in point["surface"].items():
                        measurements[var] = value

                # 其他要素
                other_vars = ["tp", "prer", "cldt", "cldl", "cape", "slp"]
                for var in other_vars:
                    if var in point and point[var] is not None:
                        measurements[var] = point[var]

                records.append(UnifiedDataRecord(
                    timestamp=datetime.fromisoformat(point["timestamp"]),
                    lat=lat,
                    lon=lon,
                    measurements=measurements,
                    metadata={
                        "data_source": "tianji_weather",
                        "type": "atmospheric_profile",
                        "hour_index": i,
                        "total_hours": len(time_series)
                    }
                ))

            return {
                "success": True,
                "data": records,
                "metadata": {
                    **tianji_result["metadata"],
                    "record_count": len(records),
                    "schema_type": "atmospheric_weather",
                    "generator": "get_tianji_weather",
                    "scenario": "trajectory_analysis"
                }
            }

        except Exception as e:
            logger.error("tianji_atmospheric_fetch_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def _fetch_surface_data(
        self,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """获取地面观测数据"""
        try:
            tianji_result = await self.tianji_client.fetch_current_weather(
                lat=lat,
                lon=lon,
                variables=["t2m", "rh2m", "ws10m", "wd10m", "psfc", "tp", "cldt"]
            )

            if not tianji_result["success"]:
                return {"success": False, "error": tianji_result["error"]}

            # 转换为UnifiedDataRecord格式
            surface_data = tianji_result["data"]
            if not surface_data:
                return {"success": False, "error": "无地面观测数据"}

            # 单位转换
            measurements = {}
            for var, value in surface_data.items():
                if var == "t2m" and value is not None:
                    measurements["temperature_2m"] = value - 273.15  # K转°C
                elif var == "psfc" and value is not None:
                    measurements["surface_pressure"] = value / 100.0  # Pa转hPa
                elif value is not None:
                    measurements[var] = float(value)

            records = [UnifiedDataRecord(
                timestamp=datetime.utcnow(),
                lat=lat,
                lon=lon,
                measurements=measurements,
                metadata={
                    "data_source": "tianji_weather",
                    "type": "surface_observation"
                }
            )]

            return {
                "success": True,
                "data": records,
                "metadata": {
                    **tianji_result["metadata"],
                    "record_count": 1,
                    "schema_type": "surface_weather",
                    "generator": "get_tianji_weather",
                    "scenario": "current_observation"
                }
            }

        except Exception as e:
            logger.error("tianji_surface_fetch_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def _fetch_wind_profile_data(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        forecast_hours: int
    ) -> Dict[str, Any]:
        """获取风廓线数据"""
        try:
            tianji_result = await self.tianji_client.fetch_wind_profile(
                lat=lat,
                lon=lon,
                start_time=start_time,
                hours_forward=forecast_hours
            )

            if not tianji_result["success"]:
                return {"success": False, "error": tianji_result["error"]}

            # 风廓线数据转换
            records = []
            time_series = tianji_result["data"].get("data", [])

            for i, point in enumerate(time_series):
                # 提取多高度层风速风向
                wind_profile = {}
                for height in [30, 50, 70, 100, 150]:
                    ws_key = f"ws{height}m"
                    wd_key = f"wd{height}m"
                    if ws_key in point and wd_key in point:
                        wind_profile[f"wind_speed_{height}m"] = point[ws_key]
                        wind_profile[f"wind_direction_{height}m"] = point[wd_key]

                if wind_profile:
                    records.append(UnifiedDataRecord(
                        timestamp=datetime.fromisoformat(point["time"].replace("+08:00", "+08:00")),
                        lat=lat,
                        lon=lon,
                        measurements=wind_profile,
                        metadata={
                            "data_source": "tianji_weather",
                            "type": "wind_profile",
                            "hour_index": i
                        }
                    ))

            return {
                "success": True,
                "data": records,
                "metadata": {
                    **tianji_result["metadata"],
                    "record_count": len(records),
                    "schema_type": "wind_profile",
                    "generator": "get_tianji_weather",
                    "scenario": "wind_resource_analysis"
                }
            }

        except Exception as e:
            logger.error("tianji_wind_profile_fetch_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def _save_to_context(
        self,
        context: ExecutionContext,
        data: List[UnifiedDataRecord],
        lat: float,
        lon: float,
        data_type: str,
        metadata: Dict[str, Any]
    ) -> str:
        """保存数据到Context"""
        try:
            # 根据数据类型确定schema
            schema_map = {
                "atmospheric_for_trajectory": "atmospheric_weather",
                "surface_observation": "surface_weather",
                "wind_profile": "wind_profile"
            }
            schema = schema_map.get(data_type, "weather")

            # 保存到Context
            data_id = context.data_manager.save_data(
                data=data,
                schema=schema,
                quality_report=None,
                field_stats=None,
                metadata={
                    "lat": lat,
                    "lon": lon,
                    "data_type": data_type,
                    "schema_version": "v2.0",
                    "generator": "get_tianji_weather",
                    "api_source": "tianji_weather"
                }
            )

            logger.info("tianji_weather_data_saved", data_id=data_id, record_count=len(data))
            return data_id

        except Exception as e:
            logger.error("tianji_data_save_failed", error=str(e))
            raise

    def _build_udf_response(
        self,
        data: List[UnifiedDataRecord],
        data_id: str,
        lat: float,
        lon: float,
        data_type: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建UDF v2.0响应"""
        return {
            "status": "success",
            "success": True,
            "data": data,
            "metadata": {
                **metadata,
                "data_id": data_id,
                "schema_version": "v2.0",
                "field_mapping_applied": True,
                "field_mapping_info": {
                    "record_count": len(data),
                    "source_data_ids": [data_id]
                }
            },
            "summary": (
                f"✅ 天机气象数据获取成功。"
                f"数据类型: {data_type}，"
                f"记录数: {len(data)}，"
                f"位置: ({lat:.2f}, {lon:.2f})，"
                f"数据源: 中科天机。"
            )
        }

    def _create_error_response(
        self,
        error: str,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "get_tianji_weather",
                "error": error,
                "lat": lat,
                "lon": lon
            },
            "summary": f"❌ 天机气象数据获取失败: {error}"
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            return await self.tianji_client.health_check()
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 导出
__all__ = ["GetTianjiWeatherTool"]
