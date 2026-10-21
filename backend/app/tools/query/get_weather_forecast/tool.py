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
from app.utils.weather_time import (
    BEIJING, WEATHER_QUERY_GUIDANCE, normalize_weather_record, open_meteo_time,
    weather_data_structure, weather_output_metadata,
)
from app.schemas.unified import (
    UnifiedData,
    DataMetadata,
    UnifiedDataRecord,
    DataType,
    DataStatus,
    VisualBlock,
)

logger = structlog.get_logger()

INLINE_RECORD_LIMIT = 24
FORECAST_UNITS = {"boundary_layer_height": "m", "shortwave_radiation": "W/m2", "wind_speed": "m/s", "wind_gusts": "m/s"}


def _wind_mps(value, unit):
    if value is None:
        return None
    if unit not in {"km/h", "m/s", "mph", "kn"}:
        raise ValueError("Missing or unsupported forecast wind unit")
    return value * {"km/h": 1 / 3.6, "m/s": 1, "mph": 0.44704, "kn": 1.852 / 3.6}[unit]


def _weather_data_structure(
    *,
    record_count: int,
    returned_records: int,
    externalized: bool,
) -> Dict[str, Any]:
    """Describe both the inline preview and persisted weather JSON shape."""
    return weather_data_structure(record_count, returned_records, externalized)


def _head_tail_sample(records: list[UnifiedDataRecord]) -> list[UnifiedDataRecord]:
    head_size = INLINE_RECORD_LIMIT // 2
    tail_size = INLINE_RECORD_LIMIT - head_size
    return records[:head_size] + records[-tail_size:]


class GetWeatherForecastTool(LLMTool):
    """
    天气预报查询工具 (UDF v2.0)

    给LLM提供获取天气预报的能力
    注意：此工具实时调用API，不从数据库读取
    """

    def __init__(self):
        function_schema = {
            "name": "get_weather_forecast",
            "description": """获取指定位置的Open-Meteo模式预报，包含边界层高度(m)、短波辐射(W/m²)、温度、降水、风速(m/s)。

【工具选择与调用】
1. 今天（含00:00至当前已过小时）和未来的边界层高度、短波辐射：直接使用本工具，不要先用get_weather_data试查未来，也不要用站点温湿度估算边界层高度。
2. 仅查今天：forecast_days=1,past_days=0；昨天到今天：forecast_days=1,past_days=1；过去5天缺口：past_days=5。forecast_days从今天开始计数且包含今天（1=今天，4=今天及后三个日历日）。
3. 今天之前超过5天的历史网格：使用get_weather_data；跨时段分别查询，根据实际覆盖范围合并并按timestamp去重，保留每段来源。纯ERA5发布有延迟，不能用ERA5接口补当天。
4. 本工具必须提供lat/lon；location_name仅是显示名，不做地理解析。坐标取自项目城市代表点、用户指定位置或历史工具返回的网格坐标，不猜测坐标。
5. 查询“截至此刻”时只保留timestamp<=用户截止时刻的记录；不得将今天尚未到来的小时计入已发生时段。字段为空就报告缺失，不用0或估算值补齐。

【时间、单位与来源】
past_days=0包含北京时间今天00:00起的数据；past_days=1增加昨天，最多可补过去5天。
时间已为北京时间（+08:00），禁止再次加8小时。短波辐射为标注时刻之前一小时平均值。
短波辐射字段为measurements.shortwave_radiation，单位W/m²；不要使用每日累计辐射(MJ/m²)替代。边界层高度字段为measurements.boundary_layer_height，单位m。
这是模式数据（Open-Meteo Forecast），即便时间已过去也不能称为实测或ERA5再分析；不同来源衔接时按时间去重并保留来源。

按北京时间日历日返回，包含今天尚未到来的小时；统计“截至某时刻”必须先按截止时间过滤完整数据。

返回约定：
- 不超过24条时，data包含全部记录，不生成外部数据文件
- 超过24条时，data返回首尾共24条样本，file_path指向完整JSON数组
- data_structure明确描述JSON根类型和嵌套字段；不要调用Python探测数据结构
- 需要分析外部化明细时，使用execute_python的load_data(file_path)直接加载
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
                        "description": "从北京时间今天起的日历天数（含今天，1-16），默认7；1=仅今天，4=今天及后三天",
                        "minimum": 1,
                        "maximum": 16
                    },
                    "past_days": {
                        "type": "integer",
                        "description": "额外包含今天之前的天数（0-5），默认0已含今天00:00起全部小时；1增加昨天，用于补历史库近期缺口",
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

        function_schema["description"] += WEATHER_QUERY_GUIDANCE
        super().__init__(
            name="get_weather_forecast",
            description="Get weather forecast (real-time API call, UDF v2.0 compliant)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.3.0",  # 更新版本号：修复 Context-Aware V2 方法签名
            requires_context=True  # Context-Aware V2: 需要 ExecutionContext 保存数据
        )

        self.client = OpenMeteoClient()

    async def execute(
        self,
        context,  # Context-Aware V2: ExecutionContext 对象（第1个参数）
        lat: float,
        lon: float,
        location_name: Optional[str] = None,
        forecast_days: int = 7,
        past_days: int = 0,
        hourly: bool = True,
        daily: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行天气预报查询 (UDF v2.0 + Context-Aware V2)

        Args:
            context: ExecutionContext - 用于保存数据到session_memory
            lat: 纬度
            lon: 经度
            location_name: 位置名称（用于显示）
            forecast_days: 预报天数（1-16）
            past_days: 获取过去天数（0-5），设置为1可获取今天和昨天的完整数据
            hourly: 是否返回逐小时预报
            daily: 是否返回每日预报

        Returns:
            Dict: UDF v2.0 格式的预报数据，持久化成功时包含 file_path

        Note:
            使用 past_days=1 可以获取：
            - 昨天完整24小时数据
            - 今天00:00到当前时刻的模式数据（非站点实测）
            - 未来7天预报数据
        """
        try:
            logger.info(
                "weather_forecast_query_started",
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
                daily=daily,
                timezone="Asia/Shanghai",
            )

            # 构建数据记录列表
            records = []

            # 逐小时预报数据
            if hourly and "hourly" in forecast_data:
                hourly_data = forecast_data["hourly"]
                time_list = hourly_data.get("time", [])
                hourly_units = forecast_data.get("hourly_units", {})

                for i, time_str in enumerate(time_list):
                    record = UnifiedDataRecord(
                        timestamp=open_meteo_time(time_str, forecast_data).astimezone(BEIJING),
                        lat=lat,
                        lon=lon,
                        station_name=location_name,
                        metadata={"data_source": "Open-Meteo Forecast", "timezone": "Asia/Shanghai", "units": FORECAST_UNITS, "shortwave_radiation_interval": "preceding_hour_mean"},
                        measurements={
                            # 温度
                            "temperature": hourly_data.get("temperature_2m", [])[i] if i < len(hourly_data.get("temperature_2m", [])) else None,
                            # 湿度
                            "humidity": hourly_data.get("relative_humidity_2m", [])[i] if i < len(hourly_data.get("relative_humidity_2m", [])) else None,
                            # 露点
                            "dew_point": hourly_data.get("dew_point_2m", [])[i] if i < len(hourly_data.get("dew_point_2m", [])) else None,
                            # 风速
                            "wind_speed": _wind_mps(hourly_data.get("wind_speed_10m", [])[i], hourly_units.get("wind_speed_10m")) if i < len(hourly_data.get("wind_speed_10m", [])) else None,
                            # 风向
                            "wind_direction": hourly_data.get("wind_direction_10m", [])[i] if i < len(hourly_data.get("wind_direction_10m", [])) else None,
                            # 阵风
                            "wind_gusts": _wind_mps(hourly_data.get("wind_gusts_10m", [])[i], hourly_units.get("wind_gusts_10m")) if i < len(hourly_data.get("wind_gusts_10m", [])) else None,
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
                            "shortwave_radiation": hourly_data.get("shortwave_radiation", [])[i] if i < len(hourly_data.get("shortwave_radiation", [])) else None,
                        }
                    )
                    records.append(record)

            # 构建元数据
            metadata = DataMetadata(
                data_type=DataType.WEATHER,
                schema_version="v2.0",
                record_count=len(records),
                station_name=location_name,
                lat=lat,
                lon=lon,
                time_range={
                    "start": records[0].timestamp.isoformat() if records else "",
                    "end": records[-1].timestamp.isoformat() if records else ""
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
                        "cloud_cover", "visibility", "boundary_layer_height", "shortwave_radiation"
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
                # 过滤 None 值（API 对较远日期可能返回 null）
                valid_max_temps = [t for t in max_temps if t is not None]
                valid_min_temps = [t for t in min_temps if t is not None]
                if valid_max_temps and valid_min_temps:
                    temp_range = f"{min(valid_min_temps):.1f}~{max(valid_max_temps):.1f}°C"
                    daily_summary = f"未来{len(max_temps)}天预报，温度范围{temp_range}"

            # 根据 past_days 调整摘要说明
            if past_days > 0:
                summary = f"天气预报查询成功 ({location_name or f'({lat},{lon})'})。请求过去{past_days}天及从今天起{forecast_days}天的模式数据。{daily_summary}。实际覆盖范围见actual_time_range；截至时刻的统计需先过滤。"
            else:
                summary = f"天气预报查询成功 ({location_name or f'({lat},{lon})'})。{daily_summary}。包含边界层高度预报数据，可用于污染扩散条件分析。"

            summary += " 时间为北京时间(+08:00)，勿再加8小时；风速m/s，边界层高度m，短波辐射W/m²（前一小时平均）；来源Open-Meteo Forecast模式数据，非实测。"

            # Keep small datasets inline. Persist large datasets and return a
            # bounded preview so the model can inspect the shape immediately.
            records_dicts = [normalize_weather_record(r.model_dump(mode="json")) for r in records]
            record_metadata = weather_output_metadata(records_dicts)
            warnings = []
            saved_file_path = None
            externalized = len(records) > INLINE_RECORD_LIMIT
            inline_records = _head_tail_sample(records) if externalized else records

            logger.info(
                "weather_forecast_save_data_attempt",
                has_context=context is not None,
                has_records=records is not None,
                records_count=len(records) if records else 0,
                externalized=externalized,
                context_type=type(context).__name__ if context else None
            )

            if context is not None and records and externalized:
                try:
                    # 转换 UnifiedDataRecord 为字典

                    logger.info(
                        "weather_forecast_calling_save_data",
                        records_count=len(records_dicts),
                        schema="weather"
                    )

                    saved_file_path = context.save_data(
                        data=records_dicts,
                        schema="weather",
                        metadata={
                            "lat": lat,
                            "lon": lon,
                            "location": location_name,
                            "forecast_days": forecast_days,
                            "past_days": past_days,
                            "source": "Open-Meteo Forecast API",
                            "field_mapping_applied": True,
                            "root_type": "array",
                            "timezone": "Asia/Shanghai",
                            **record_metadata,
                        }
                    )
                    logger.info(
                        "weather_forecast_data_saved",
                        file_path=saved_file_path,
                        records_count=len(records_dicts)
                    )
                    summary = f"{summary} 文件路径: {saved_file_path}。"
                except Exception as save_error:
                    saved_file_path = None
                    warnings.append({"code": "DATA_SAVE_FAILED", "message": "数据文件保存失败，完整记录已内联返回；不得声称已保存文件。"})
                    externalized = False
                    inline_records = records
                    logger.error(
                        "weather_forecast_data_save_failed",
                        error=str(save_error),
                        error_type=type(save_error).__name__,
                        exc_info=True
                    )
            elif externalized:
                externalized = False
                inline_records = records
                logger.warning(
                    "weather_forecast_skip_data_save",
                    reason="context is None",
                    has_context=context is not None,
                    has_records=records is not None
                )

            # 构建 UDF v2.0 格式返回
            result = UnifiedData(
                status=DataStatus.SUCCESS,
                success=True,
                data=inline_records,
                metadata=metadata,
                summary=summary,
            )

            result_dict = result.model_dump(mode="json")
            result_dict["data"] = _head_tail_sample(records_dicts) if externalized else records_dicts
            result_dict["metadata"].update({**record_metadata, "shortwave_radiation_interval": "preceding_hour_mean"})
            result_dict["warnings"] = warnings
            if warnings:
                result_dict["status"] = "partial"
                result_dict["summary"] += " 数据文件保存失败，完整记录已内联返回。"
            if hourly and not records_dicts:
                result_dict.update(status="empty", success=False, error_code="NO_DATA", summary="上游未返回逐小时气象数据。")
            result_dict.update({
                "data_complete": not externalized,
                "record_count": len(records),
                "returned_records": len(inline_records),
                "sample_strategy": "head_tail" if externalized else "complete",
                "data_structure": _weather_data_structure(
                    record_count=len(records),
                    returned_records=len(inline_records),
                    externalized=externalized,
                ),
            })
            result_dict["metadata"]["context_data"] = {
                "inline_record_limit": INLINE_RECORD_LIMIT,
                "externalized": externalized,
                "data_structure": result_dict["data_structure"],
            }
            if saved_file_path:
                result_dict["file_path"] = saved_file_path
                result_dict["metadata"]["file_path"] = saved_file_path

            logger.info(
                "weather_forecast_query_successful",
                file_path=saved_file_path,
                lat=lat,
                lon=lon,
                hourly_points=len(records),
                returned_records=len(inline_records),
                externalized=externalized,
                daily_days=forecast_days
            )

            return result_dict

        except Exception as e:
            logger.error(
                "weather_forecast_query_failed",
                lat=lat,
                lon=lon,
                error=str(e),
                exc_info=True
            )

            # 返回 UDF v2.0 格式的错误响应
            result = UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                metadata=DataMetadata(
                    data_type=DataType.WEATHER,
                    schema_version="v2.0",
                    record_count=0,
                    station_name=location_name,
                    lat=lat,
                    lon=lon,
                    source="Open-Meteo Forecast API (failed)"
                ),
                summary=f"天气预报查询失败: {str(e)}"
            ).model_dump(mode="json")
            result["error_code"] = "WEATHER_QUERY_FAILED"
            return result
