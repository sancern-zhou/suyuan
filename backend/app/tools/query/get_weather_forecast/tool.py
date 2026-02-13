"""
Get Weather Forecast Tool (UDF v2.0 Compliant)

LLM可调用的天气预报查询工具

功能：
- 实时调用 Open-Meteo Forecast API
- 返回未来7-16天的天气预报
- 支持逐小时和每日预报
- 包含边界层高度预报（关键！）
- 完全符合 UDF v2.0 规范
"""
from typing import Dict, Any, Optional
from datetime import datetime
import structlog
import uuid

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.schemas.unified import (
    UnifiedData,
    DataMetadata,
    UnifiedDataRecord,
    DataType,
    DataStatus,
    VisualBlock,
)

logger = structlog.get_logger()


class GetWeatherForecastTool(LLMTool):
    """
    天气预报查询工具 (UDF v2.0)

    给LLM提供获取天气预报的能力
    注意：此工具实时调用API，不从数据库读取
    """

    def __init__(self):
        function_schema = {
            "name": "get_weather_forecast",
            "description": """获取指定位置的天气预报（未来7-16天），包含温度、降水、风速、边界层高度等气象要素。

支持获取今天和历史数据：
- 使用 past_days=1 可以获取昨天完整数据 + 今天00:00到当前时刻的数据 + 未来7天预报
- 适合需要完整当天数据的场景（如污染溯源分析）
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "纬度"
                    },
                    "lon": {
                        "type": "number",
                        "description": "经度"
                    },
                    "location_name": {
                        "type": "string",
                        "description": "位置名称（用于显示）"
                    },
                    "forecast_days": {
                        "type": "integer",
                        "description": "预报天数（1-16），默认7天",
                        "minimum": 1,
                        "maximum": 16
                    },
                    "past_days": {
                        "type": "integer",
                        "description": "获取过去天数（0-5），默认0。设置为1可获取今天和昨天的完整数据",
                        "minimum": 0,
                        "maximum": 5
                    },
                    "hourly": {
                        "type": "boolean",
                        "description": "是否返回逐小时预报，默认true"
                    },
                    "daily": {
                        "type": "boolean",
                        "description": "是否返回每日预报，默认true"
                    }
                },
                "required": ["lat", "lon"]
            }
        }

        super().__init__(
            name="get_weather_forecast",
            description="Get weather forecast (real-time API call, UDF v2.0 compliant)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.2.0",
            requires_context=True  # Context-Aware V2: 需要 ExecutionContext 保存数据
        )

        self.client = OpenMeteoClient()

    async def execute(
        self,
        lat: float,
        lon: float,
        location_name: Optional[str] = None,
        forecast_days: int = 7,
        past_days: int = 0,
        hourly: bool = True,
        daily: bool = True,
        context=None,  # ExecutionContext - Context-Aware V2架构
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行天气预报查询 (UDF v2.0 + Context-Aware V2)

        Args:
            lat: 纬度
            lon: 经度
            location_name: 位置名称（用于显示）
            forecast_days: 预报天数（1-16）
            past_days: 获取过去天数（0-5），设置为1可获取今天和昨天的完整数据
            hourly: 是否返回逐小时预报
            daily: 是否返回每日预报
            context: ExecutionContext - 用于保存数据到session_memory

        Returns:
            Dict: UDF v2.0 格式的预报数据，包含 data_id

        Note:
            使用 past_days=1 可以获取：
            - 昨天完整24小时数据
            - 今天00:00到当前时刻的数据（分析场数据）
            - 未来7天预报数据
        """
        data_id = f"weather_forecast_{uuid.uuid4().hex[:12]}"

        try:
            logger.info(
                "weather_forecast_query_started",
                data_id=data_id,
                lat=lat,
                lon=lon,
                location=location_name,
                forecast_days=forecast_days,
                past_days=past_days
            )

            # 实时调用 API（支持 past_days）
            forecast_data = await self.client.fetch_forecast(
                lat=lat,
                lon=lon,
                forecast_days=forecast_days,
                past_days=past_days,
                hourly=hourly,
                daily=daily
            )

            # 构建数据记录列表
            records = []

            # 逐小时预报数据
            if hourly and "hourly" in forecast_data:
                hourly_data = forecast_data["hourly"]
                time_list = hourly_data.get("time", [])

                for i, time_str in enumerate(time_list):
                    record = UnifiedDataRecord(
                        timestamp=datetime.fromisoformat(time_str.replace("Z", "+00:00")),
                        lat=lat,
                        lon=lon,
                        station_name=location_name,
                        measurements={
                            # 温度
                            "temperature": hourly_data.get("temperature_2m", [])[i] if i < len(hourly_data.get("temperature_2m", [])) else None,
                            # 湿度
                            "humidity": hourly_data.get("relative_humidity_2m", [])[i] if i < len(hourly_data.get("relative_humidity_2m", [])) else None,
                            # 露点
                            "dew_point": hourly_data.get("dew_point_2m", [])[i] if i < len(hourly_data.get("dew_point_2m", [])) else None,
                            # 风速
                            "wind_speed": hourly_data.get("wind_speed_10m", [])[i] if i < len(hourly_data.get("wind_speed_10m", [])) else None,
                            # 风向
                            "wind_direction": hourly_data.get("wind_direction_10m", [])[i] if i < len(hourly_data.get("wind_direction_10m", [])) else None,
                            # 阵风
                            "wind_gusts": hourly_data.get("wind_gusts_10m", [])[i] if i < len(hourly_data.get("wind_gusts_10m", [])) else None,
                            # 气压
                            "surface_pressure": hourly_data.get("surface_pressure", [])[i] if i < len(hourly_data.get("surface_pressure", [])) else None,
                            # 降水
                            "precipitation": hourly_data.get("precipitation", [])[i] if i < len(hourly_data.get("precipitation", [])) else None,
                            "precipitation_probability": hourly_data.get("precipitation_probability", [])[i] if i < len(hourly_data.get("precipitation_probability", [])) else None,
                            # 天气代码
                            "weather_code": hourly_data.get("weather_code", [])[i] if i < len(hourly_data.get("weather_code", [])) else None,
                            # 云量
                            "cloud_cover": hourly_data.get("cloud_cover", [])[i] if i < len(hourly_data.get("cloud_cover", [])) else None,
                            # 能见度
                            "visibility": hourly_data.get("visibility", [])[i] if i < len(hourly_data.get("visibility", [])) else None,
                            # 边界层高度（关键！）
                            "boundary_layer_height": hourly_data.get("boundary_layer_height", [])[i] if i < len(hourly_data.get("boundary_layer_height", [])) else None,
                        }
                    )
                    records.append(record)

            # 构建元数据
            metadata = DataMetadata(
                data_id=data_id,
                data_type=DataType.WEATHER,
                schema_version="v2.0",
                record_count=len(records),
                station_name=location_name,
                lat=lat,
                lon=lon,
                time_range={
                    "start": forecast_data.get("hourly", {}).get("time", [""])[0] if hourly else "",
                    "end": forecast_data.get("hourly", {}).get("time", [""])[-1] if hourly else ""
                },
                granularity="hourly" if hourly else "daily",
                source="Open-Meteo Forecast API",
                tool_version="2.1.0",
                parameters={
                    "forecast_days": forecast_days,
                    "past_days": past_days,
                    "hourly": hourly,
                    "daily": daily
                },
                field_mapping_applied=True,
                field_mapping_info={
                    "standard_fields_used": [
                        "temperature", "humidity", "dew_point", "wind_speed",
                        "wind_direction", "wind_gusts", "surface_pressure",
                        "precipitation", "precipitation_probability", "weather_code",
                        "cloud_cover", "visibility", "boundary_layer_height"
                    ],
                    "original_api_fields": {
                        "temperature": "temperature_2m",
                        "humidity": "relative_humidity_2m",
                        "dew_point": "dew_point_2m",
                        "wind_speed": "wind_speed_10m",
                        "wind_direction": "wind_direction_10m",
                        "wind_gusts": "wind_gusts_10m"
                    }
                }
            )

            # 构建摘要
            daily_summary = ""
            if daily and "daily" in forecast_data:
                daily_data = forecast_data["daily"]
                max_temps = daily_data.get("temperature_2m_max", [])
                min_temps = daily_data.get("temperature_2m_min", [])
                if max_temps and min_temps:
                    temp_range = f"{min(min_temps):.1f}~{max(max_temps):.1f}°C"
                    daily_summary = f"未来{len(max_temps)}天预报，温度范围{temp_range}"

            # 根据 past_days 调整摘要说明
            if past_days > 0:
                summary = f"天气预报查询成功 ({location_name or f'({lat},{lon})'})。包含过去{past_days}天 + {daily_summary}。包含今天00:00到当前时刻的完整数据及边界层高度，可用于污染溯源分析。"
            else:
                summary = f"天气预报查询成功 ({location_name or f'({lat},{lon})'})。{daily_summary}。包含边界层高度预报数据，可用于污染扩散条件分析。"

            # 【Context-Aware V2】保存数据到 session_memory
            saved_data_id = None

            logger.info(
                "weather_forecast_save_data_attempt",
                has_context=context is not None,
                has_records=records is not None,
                records_count=len(records) if records else 0,
                context_type=type(context).__name__ if context else None
            )

            if context is not None and records:
                try:
                    # 转换 UnifiedDataRecord 为字典
                    records_dicts = [r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in records]

                    logger.info(
                        "weather_forecast_calling_save_data",
                        records_count=len(records_dicts),
                        schema="weather"
                    )

                    # ✅ 修复：save_data() 是同步方法，不需要 await
                    saved_data_id = context.save_data(
                        data=records_dicts,
                        schema="weather",
                        metadata={
                            "lat": lat,
                            "lon": lon,
                            "location": location_name,
                            "forecast_days": forecast_days,
                            "past_days": past_days,
                            "source": "Open-Meteo Forecast API"
                        }
                    )

                    logger.info(
                        "weather_forecast_data_saved",
                        original_id=data_id,
                        saved_id=saved_data_id,
                        records_count=len(records_dicts)
                    )
                    # 更新摘要，包含保存的data_id
                    summary = f"{summary} 数据已保存为 {saved_data_id}。"
                except Exception as save_error:
                    logger.error(
                        "weather_forecast_data_save_failed",
                        error=str(save_error),
                        error_type=type(save_error).__name__,
                        data_id=data_id,
                        exc_info=True
                    )
            else:
                logger.warning(
                    "weather_forecast_skip_data_save",
                    reason="context is None or records is empty",
                    has_context=context is not None,
                    has_records=records is not None
                )

            # 构建 UDF v2.0 格式返回
            result = UnifiedData(
                status=DataStatus.SUCCESS,
                success=True,
                data=records,
                metadata=metadata,
                summary=summary,
            )

            # 如果成功保存数据，添加 data_id 到返回结果
            result_dict = result.dict()
            if saved_data_id:
                result_dict["data_id"] = saved_data_id

            logger.info(
                "weather_forecast_query_successful",
                data_id=data_id,
                saved_data_id=saved_data_id,
                lat=lat,
                lon=lon,
                hourly_points=len(records),
                daily_days=forecast_days
            )

            return result_dict

        except Exception as e:
            logger.error(
                "weather_forecast_query_failed",
                data_id=data_id,
                lat=lat,
                lon=lon,
                error=str(e),
                exc_info=True
            )

            # 返回 UDF v2.0 格式的错误响应
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                metadata=DataMetadata(
                    data_id=data_id,
                    data_type=DataType.WEATHER,
                    schema_version="v2.0",
                    record_count=0,
                    station_name=location_name,
                    lat=lat,
                    lon=lon,
                    source="Open-Meteo Forecast API (failed)"
                ),
                summary=f"天气预报查询失败: {str(e)}"
            ).dict()
