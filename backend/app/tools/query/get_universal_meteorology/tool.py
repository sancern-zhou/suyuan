"""
Universal Meteorology Tool - 通用气象数据获取工具 (Context-Aware V2)

为任意环境空气监测站点获取完整气象参数：
- 实时观测数据（风速、风向、温度、湿度、气压等）
- 边界层高度数据
- 风廓线数据（多高度层）
- 预报数据（未来72小时）
- 历史参考数据（ERA5）

注意：此工具只负责数据获取，不进行业务分析。
业务分析应由ReAct Agent通过LLM推理完成。
遵循Context-Aware V2架构，返回UnifiedData格式。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Union, TYPE_CHECKING
from datetime import datetime, timedelta
import asyncio
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.db.repositories.weather_repo import WeatherRepository
from app.schemas.unified import UnifiedData, UnifiedDataRecord, DataMetadata, DataType, DataStatus
from app.utils.data_standardizer import get_data_standardizer  # UDF v2.0 数据标准化

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class UniversalMeteorologyTool(LLMTool):
    """
    通用气象数据获取工具 (Context-Aware V2)

    特点：
    - 任意坐标位置支持（无需预设站点）
    - 多数据源融合（实时+预报+历史）
    - 完整气象参数覆盖
    - 风廓线数据支持（优先ERA5压力层数据）
    - Context-Aware V2架构
    - 返回UnifiedData格式
    - 纯数据获取，无业务分析

    版本：v4.0.0
    - Context-Aware V2架构
    - UDF v1.0格式输出
    - 数据通过context.save_data()存储
    - 返回data_id而非完整数据
    """

    def __init__(self):
        function_schema = {
            "name": "get_universal_meteorology",
            "description": """获取任意环境空气监测站点的完整气象数据。

**Context-Aware V2工具，采用混合模式**

特点：
- 既返回完整数据给LLM智能分析，又保存data_id供下游工具使用
- 支持多数据源融合（实时+预报+历史+风廓线）
- 返回72小时完整预报序列（而非样本）
- 优先使用ERA5压力层数据构建11层风廓线

支持参数：
- 实时观测数据：10米风速、风向、温度、湿度、气压、降水、能见度
- 边界层高度：72小时逐小时序列
- 风廓线数据：多高度层风速风向（优先ERA5压力层数据，11个高度层）
- 预报数据：未来72小时逐小时预报（包含短波辐射、紫外指数等新增参数）
- 历史数据：ERA5再分析数据作为对比参考
⚠️ **必须提供经纬度坐标** - 如果不知道精确坐标，请先调用get_nearby_stations获取坐标

返回格式：
{
    "status": "success",
    "success": true,
    "data": [UnifiedDataRecord, ...],  # 完整的100+条气象记录，LLM可直接分析
    "data_id": "meteorology_unified:v1:32位十六进制字符串",  # 供下游工具使用
    "metadata": {
        "tool_name": "get_universal_meteorology",
        "record_count": 155,
        "schema": "meteorology_unified",
        "sample": [{"wind_speed_10m": 2.5, ...}, ...],  # 3条样本数据
        "available_fields": [...],  # 所有可用字段列表
        "era5_wind_profile": true,  # 是否使用ERA5压力层数据
        "data_completeness": {...}  # 数据完整性统计
    },
    "summary": "✅ 成功获取155条气象数据记录，包含72小时完整预报序列..."
}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "监测站点纬度"
                    },
                    "lon": {
                        "type": "number",
                        "description": "监测站点经度"
                    },
                    "station_name": {
                        "type": "string",
                        "description": "监测站点名称（可选）"
                    },
                    "include_wind_profile": {
                        "type": "boolean",
                        "description": "是否包含风廓线数据，默认true"
                    },
                    "include_forecast": {
                        "type": "boolean",
                        "description": "是否包含预报数据，默认true"
                    },
                    "include_historical": {
                        "type": "boolean",
                        "description": "是否包含历史参考数据，默认true"
                    }
                },
                "required": ["lat", "lon"]
            }
        }

        super().__init__(
            name="get_universal_meteorology",
            description="Get comprehensive meteorological data for any air monitoring station (Context-Aware V2)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="4.0.0",
            requires_context=True  # Context-Aware V2
        )

        self.client = OpenMeteoClient()
        self.repo = WeatherRepository()

    async def execute(
        self,
        context: ExecutionContext,
        lat: float,
        lon: float,
        station_name: Optional[str] = None,
        include_wind_profile: bool = True,
        include_forecast: bool = True,
        include_historical: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行通用气象数据获取（Context-Aware V2）

        Args:
            context: ExecutionContext for data storage
            lat: 纬度
            lon: 经度
            station_name: 站点名称
            include_wind_profile: 是否包含风廓线
            include_forecast: 是否包含预报
            include_historical: 是否包含历史参考

        Returns:
            Dict: UDF v1.0格式，包含data_id引用
        """
        try:
            logger.info(
                "universal_meteorology_query_started",
                lat=lat,
                lon=lon,
                station_name=station_name,
                session_id=context.session_id
            )

            # 并发获取多种数据源
            tasks = [
                self._get_realtime_weather(lat, lon),
                self._get_boundary_layer_data(lat, lon),
            ]

            wind_profile_data = None
            if include_wind_profile:
                # 风廓线数据在获取实时数据后调用，避免重复网络请求
                pass  # 先初始化，稍后调用

            if include_forecast:
                tasks.append(self._get_meteorological_forecast(lat, lon))

            if include_historical:
                tasks.append(self._get_historical_reference(lat, lon))

            # 等待所有数据获取完成
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 解析结果
            realtime_data = results[0] if not isinstance(results[0], Exception) else {}
            pbl_data = results[1] if not isinstance(results[1], Exception) else {}

            forecast_data = None
            historical_data = None
            data_index = 2

            if include_forecast:
                forecast_data = results[data_index] if not isinstance(results[data_index], Exception) else {}
                data_index += 1

            if include_historical:
                historical_data = results[data_index] if not isinstance(results[data_index], Exception) else {}

            # 在获取实时数据后，获取风廓线数据（避免重复网络请求）
            if include_wind_profile:
                wind_profile_data = await self._get_wind_profile_data(
                    lat, lon, realtime_data
                )

            # 融合数据（仅数据合并，无业务分析）
            comprehensive_data = self._merge_data(
                location={"lat": lat, "lon": lon, "name": station_name},
                realtime=realtime_data,
                pbl=pbl_data,
                wind_profile=wind_profile_data,
                forecast=forecast_data,
                historical=historical_data
            )

            logger.info(
                "universal_meteorology_query_completed",
                lat=lat,
                lon=lon,
                has_realtime=bool(realtime_data),
                has_pbl=bool(pbl_data),
                has_wind_profile=bool(wind_profile_data),
                has_forecast=bool(forecast_data),
                has_historical=bool(historical_data)
            )

            # ========== Context-Aware V2: 转换为UnifiedData格式并保存 ==========
            try:
                # 转换数据为UnifiedDataRecord格式
                records = []
                query_time = datetime.utcnow()

                # 1. 保存完整预报数据（72小时逐小时序列）
                if forecast_data and "hourly" in forecast_data:
                    hourly = forecast_data.get("hourly", {})
                    times = hourly.get("time", [])
                    if times:
                        # 获取所有参数的时间序列
                        temp_series = hourly.get("temperature_2m", [])
                        humidity_series = hourly.get("relative_humidity_2m", [])
                        wind_speed_series = hourly.get("wind_speed_10m", [])
                        wind_dir_series = hourly.get("wind_direction_10m", [])
                        wind_gusts_series = hourly.get("wind_gusts_10m", [])
                        pressure_series = hourly.get("surface_pressure", [])
                        precip_series = hourly.get("precipitation", [])
                        precip_prob_series = hourly.get("precipitation_probability", [])
                        cloud_cover_series = hourly.get("cloud_cover", [])
                        visibility_series = hourly.get("visibility", [])
                        pbl_series = hourly.get("boundary_layer_height", [])
                        radiation_series = hourly.get("shortwave_radiation", [])
                        uv_index_series = hourly.get("uv_index", [])

                        # 生成每小时的记录
                        for i, time_str in enumerate(times):
                            try:
                                timestamp = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                            except:
                                timestamp = query_time

                            # 安全获取数据
                            def safe_get(data_list, index, default=None):
                                if data_list and index < len(data_list):
                                    return data_list[index]
                                return default

                            records.append(UnifiedDataRecord(
                                timestamp=timestamp,
                                station_name=station_name,
                                lat=lat,
                                lon=lon,
                                measurements={
                                    "temperature_2m": safe_get(temp_series, i),
                                    "relative_humidity_2m": safe_get(humidity_series, i),
                                    "wind_speed_10m": safe_get(wind_speed_series, i),
                                    "wind_direction_10m": safe_get(wind_dir_series, i),
                                    "wind_gusts_10m": safe_get(wind_gusts_series, i),
                                    "surface_pressure": safe_get(pressure_series, i),
                                    "precipitation": safe_get(precip_series, i),
                                    "precipitation_probability": safe_get(precip_prob_series, i),
                                    "cloud_cover": safe_get(cloud_cover_series, i),
                                    "visibility": safe_get(visibility_series, i),
                                    "boundary_layer_height": safe_get(pbl_series, i),
                                    "shortwave_radiation": safe_get(radiation_series, i),  # 短波辐射 (W/m²)
                                    "uv_index": safe_get(uv_index_series, i)  # 紫外指数
                                },
                                metadata={
                                    "data_source": forecast_data.get("data_source"),
                                    "timezone": forecast_data.get("timezone"),
                                    "type": "forecast_hourly",
                                    "hour_index": i,
                                    "total_hours": len(times),
                                    "is_last_24h": i < 24,
                                    "is_last_72h": i < 72
                                }
                            ))

                # 2. 保存边界层高度逐小时序列
                if pbl_data and "boundary_layer_series" in pbl_data:
                    pbl_series = pbl_data.get("boundary_layer_series", [])
                    for i, entry in enumerate(pbl_series):
                        try:
                            timestamp = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
                        except:
                            timestamp = query_time

                        records.append(UnifiedDataRecord(
                            timestamp=timestamp,
                            station_name=station_name,
                            lat=lat,
                            lon=lon,
                            measurements={
                                "boundary_layer_height": entry.get("boundary_layer_height"),
                                "pbl_hour_index": i,
                                "is_past_hour": entry.get("is_past", False),
                                "is_future_hour": entry.get("is_future", False)
                            },
                            metadata={
                                "data_source": pbl_data.get("data_source"),
                                "type": "boundary_layer_hourly",
                                "total_pbl_hours": len(pbl_series),
                                "pbl_time": entry.get("time")
                            }
                        ))

                # 3. 保存当前实时数据
                if realtime_data:
                    realtime_time_str = realtime_data.get("time", "")
                    try:
                        realtime_time = datetime.fromisoformat(realtime_time.replace("Z", "+00:00")) if realtime_time else query_time
                    except:
                        realtime_time = query_time

                    records.append(UnifiedDataRecord(
                        timestamp=realtime_time,
                        station_name=station_name,
                        lat=lat,
                        lon=lon,
                        measurements={
                            "wind_speed_10m": realtime_data.get("wind_speed_10m"),
                            "wind_direction_10m": realtime_data.get("wind_direction_10m"),
                            "wind_gusts_10m": realtime_data.get("wind_gusts_10m"),
                            "temperature_2m": realtime_data.get("temperature_2m"),
                            "relative_humidity_2m": realtime_data.get("relative_humidity_2m"),
                            "apparent_temperature": realtime_data.get("apparent_temperature"),
                            "surface_pressure": realtime_data.get("surface_pressure"),
                            "precipitation": realtime_data.get("precipitation"),
                            "cloud_cover": realtime_data.get("cloud_cover"),
                            "visibility": realtime_data.get("visibility"),
                            "weather_code": realtime_data.get("weather_code"),
                            "uv_index": realtime_data.get("uv_index")  # 实时紫外指数
                        },
                        metadata={
                            "data_source": realtime_data.get("data_source"),
                            "time": realtime_time_str,
                            "type": "current_observation",
                            "is_day": "is_day" in realtime_data,
                            "has_precipitation": realtime_data.get("precipitation", 0) > 0
                        }
                    ))

                # 4. 保存历史ERA5数据样本（最近24小时）
                if historical_data and "wind_speed_stats" in historical_data:
                    # 创建历史统计记录
                    records.append(UnifiedDataRecord(
                        timestamp=query_time,
                        station_name=station_name,
                        lat=lat,
                        lon=lon,
                        measurements={
                            "historical_wind_speed_mean": historical_data.get("wind_speed_stats", {}).get("mean"),
                            "historical_wind_speed_min": historical_data.get("wind_speed_stats", {}).get("min"),
                            "historical_wind_speed_max": historical_data.get("wind_speed_stats", {}).get("max"),
                            "historical_temperature_mean": historical_data.get("temperature_stats", {}).get("mean"),
                            "historical_boundary_layer_mean": historical_data.get("boundary_layer_stats", {}).get("mean"),
                            "historical_boundary_layer_min": historical_data.get("boundary_layer_stats", {}).get("min"),
                            "historical_boundary_layer_max": historical_data.get("boundary_layer_stats", {}).get("max")
                        },
                        metadata={
                            "data_source": historical_data.get("data_source"),
                            "record_count": historical_data.get("record_count"),
                            "time_range": historical_data.get("time_range"),
                            "grid_location": historical_data.get("grid_location"),
                            "type": "historical_stats",
                            "period_days": 7
                        }
                    ))

                # 5. 保存风廓线数据（每个高度层一条记录）
                if wind_profile_data and "wind_profile" in wind_profile_data:
                    wind_profile = wind_profile_data.get("wind_profile", {})
                    for height, data in wind_profile.items():
                        if isinstance(data, dict) and "speed" in data:
                            # 从高度字符串提取数值（去掉'm'后缀）
                            try:
                                height_m = float(height.replace("m", ""))
                            except:
                                height_m = None

                            records.append(UnifiedDataRecord(
                                timestamp=query_time,
                                station_name=station_name,
                                lat=lat,
                                lon=lon,
                                measurements={
                                    "wind_speed": data.get("speed"),
                                    "wind_direction": data.get("direction"),
                                    "height": height_m
                                },
                                metadata={
                                    "data_source": data.get("source"),
                                    "pressure_level": data.get("pressure_level"),
                                    "type": "wind_profile",
                                    "height_str": height,
                                    "era5_data": wind_profile_data.get("era5_data", False)
                                }
                            ))

                # 6. 保存日统计摘要（预报）
                if forecast_data and "daily" in forecast_data:
                    daily = forecast_data.get("daily", {})
                    daily_times = daily.get("time", [])
                    if daily_times:
                        for i, date_str in enumerate(daily_times):
                            try:
                                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                            except:
                                date_obj = query_time

                            def safe_get_daily(data_list, index, default=None):
                                if data_list and index < len(data_list):
                                    return data_list[index]
                                return default

                            records.append(UnifiedDataRecord(
                                timestamp=date_obj,
                                station_name=station_name,
                                lat=lat,
                                lon=lon,
                                measurements={
                                    "daily_temperature_max": safe_get_daily(daily.get("temperature_2m_max"), i),
                                    "daily_temperature_min": safe_get_daily(daily.get("temperature_2m_min"), i),
                                    "daily_precipitation_sum": safe_get_daily(daily.get("precipitation_sum"), i),
                                    "daily_precipitation_probability_max": safe_get_daily(daily.get("precipitation_probability_max"), i),
                                    "daily_wind_speed_max": safe_get_daily(daily.get("wind_speed_10m_max"), i),
                                    "daily_wind_gusts_max": safe_get_daily(daily.get("wind_gusts_10m_max"), i),
                                    "daily_weather_code": safe_get_daily(daily.get("weather_code"), i)
                                },
                                metadata={
                                    "data_source": forecast_data.get("data_source"),
                                    "type": "daily_summary",
                                    "day_index": i,
                                    "total_days": len(daily_times)
                                }
                            ))

                # ========== 【UDF v2.0】数据标准化 ==========
                # 将 UnifiedDataRecord 转换为字典进行标准化
                data_standardizer = get_data_standardizer()
                records_dict_list = []
                for record in records:
                    record_dict = {
                        "timestamp": record.timestamp.isoformat() if hasattr(record.timestamp, 'isoformat') else record.timestamp,
                        "station_name": record.station_name,
                        "lat": record.lat,
                        "lon": record.lon,
                        # measurements 中的字段展平
                        "temperature_2m": record.measurements.get("temperature_2m"),
                        "relative_humidity_2m": record.measurements.get("relative_humidity_2m"),
                        "wind_speed_10m": record.measurements.get("wind_speed_10m"),
                        "wind_direction_10m": record.measurements.get("wind_direction_10m"),
                        "wind_gusts_10m": record.measurements.get("wind_gusts_10m"),
                        "surface_pressure": record.measurements.get("surface_pressure"),
                        "precipitation": record.measurements.get("precipitation"),
                        "cloud_cover": record.measurements.get("cloud_cover"),
                        "visibility": record.measurements.get("visibility"),
                        "boundary_layer_height": record.measurements.get("boundary_layer_height"),
                        "shortwave_radiation": record.measurements.get("shortwave_radiation"),
                        "uv_index": record.measurements.get("uv_index"),
                        "weather_code": record.measurements.get("weather_code"),
                        "apparent_temperature": record.measurements.get("apparent_temperature"),
                        "precipitation_probability": record.measurements.get("precipitation_probability"),
                        # 风廓线字段
                        "wind_speed": record.measurements.get("wind_speed"),
                        "wind_direction": record.measurements.get("wind_direction"),
                        "height": record.measurements.get("height"),
                        # 日统计字段
                        "daily_temperature_max": record.measurements.get("daily_temperature_max"),
                        "daily_temperature_min": record.measurements.get("daily_temperature_min"),
                        "daily_precipitation_sum": record.measurements.get("daily_precipitation_sum"),
                        "daily_wind_speed_max": record.measurements.get("daily_wind_speed_max"),
                        "daily_wind_gusts_max": record.measurements.get("daily_wind_gusts_max"),
                        "daily_precipitation_probability_max": record.measurements.get("daily_precipitation_probability_max"),
                        "daily_weather_code": record.measurements.get("daily_weather_code"),
                        # 历史统计字段
                        "historical_wind_speed_mean": record.measurements.get("historical_wind_speed_mean"),
                        "historical_wind_speed_min": record.measurements.get("historical_wind_speed_min"),
                        "historical_wind_speed_max": record.measurements.get("historical_wind_speed_max"),
                        "historical_temperature_mean": record.measurements.get("historical_temperature_mean"),
                        "historical_boundary_layer_mean": record.measurements.get("historical_boundary_layer_mean"),
                        "historical_boundary_layer_min": record.measurements.get("historical_boundary_layer_min"),
                        "historical_boundary_layer_max": record.measurements.get("historical_boundary_layer_max"),
                        # PBL 特定字段
                        "pbl_hour_index": record.measurements.get("pbl_hour_index"),
                        "is_past_hour": record.measurements.get("is_past_hour"),
                        "is_future_hour": record.measurements.get("is_future_hour"),
                    }
                    # 过滤掉 None 值（避免保存过多空字段）
                    record_dict = {k: v for k, v in record_dict.items() if v is not None}
                    records_dict_list.append(record_dict)

                # 应用数据标准化
                standardized_records = data_standardizer.standardize(records_dict_list)

                logger.info(
                    "meteorology_data_standardized",
                    original_count=len(records),
                    standardized_count=len(standardized_records),
                    field_mapping_info=data_standardizer.get_field_mapping_info()
                )

                # 构建metadata - 使用临时ID，稍后会更新
                metadata = DataMetadata(
                    data_id="temp_id",
                    data_type=DataType.WEATHER,
                    record_count=len(standardized_records),
                    station_name=station_name,
                    lat=lat,
                    lon=lon,
                    quality_score=0.95,
                    source="Open-Meteo + ERA5"
                )

                # 创建UnifiedData
                unified_data = UnifiedData(
                    status=DataStatus.SUCCESS,
                    success=True,
                    data=standardized_records,
                    metadata=metadata,
                    summary=f"成功获取{len(standardized_records)}条气象数据记录"
                )

                # 保存到context（传递标准化后的字典列表）
                data_id = context.data_manager.save_data(
                    data=standardized_records,  # List[Dict]，已标准化的数据
                    schema="meteorology_unified",
                    quality_report=None,
                    field_stats=None,
                    metadata={
                        "lat": lat,
                        "lon": lon,
                        "station_name": station_name,
                        "schema_version": "v2.0",  # UDF v2.0 标记
                        "field_mapping_applied": True,  # ✅ 标记已标准化
                        "field_mapping_info": data_standardizer.get_field_mapping_info(),
                        "include_wind_profile": include_wind_profile,
                        "include_forecast": include_forecast,
                        "include_historical": include_historical,
                        "era5_wind_profile": wind_profile_data.get("era5_data", False) if wind_profile_data else False,
                        "generator": "get_universal_meteorology",  # ✅ 工具名称
                        "scenario": "meteorology_analysis",  # ✅ 场景标识
                        "unified_data": unified_data.dict()  # 保存完整UnifiedData作为metadata
                    }
                )

                # 获取handle用于访问元数据
                handle = context.data_manager.get_handle(data_id)

                # 更新metadata的data_id为真实的data_id
                metadata.data_id = data_id

                # 生成样本预览（前3条记录）
                sample_preview = [record.dict() for record in records[:3]]

                # ========== 混合模式：既返回完整数据给LLM，又保存data_id供下游使用 ==========
                # 使用get_air_quality的成功模式：返回完整UnifiedData + data_id
                result = unified_data.dict()
                result["data_id"] = data_id  # 添加data_id字段

                # 在metadata中补充额外信息
                result["metadata"]["sample"] = sample_preview
                result["metadata"]["available_fields"] = [
                    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
                    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
                    "surface_pressure", "precipitation", "precipitation_probability",
                    "cloud_cover", "visibility", "boundary_layer_height",
                    "shortwave_radiation", "uv_index", "weather_code",
                    "daily_temperature_max", "daily_temperature_min",
                    "daily_wind_speed_max", "daily_precipitation_sum",
                    "historical_wind_speed_mean", "historical_boundary_layer_mean",
                    "wind_speed", "wind_direction", "height"
                ]
                result["metadata"]["era5_wind_profile"] = wind_profile_data.get("era5_data", False) if wind_profile_data else False
                result["metadata"]["data_completeness"] = {
                    "forecast_hourly_72h": True,
                    "current_observation": True,
                    "wind_profile_multi_level": True,
                    "historical_stats_7d": True,
                    "daily_summary_3d": True,
                    "shortwave_radiation": True,
                    "uv_index": True,
                    "precipitation_probability": True,
                    "weather_code": True
                }

                # 增强summary信息
                result["summary"] = (
                    f"✅ 成功获取气象数据，已保存为 {data_id}。"
                    f"记录数: {handle.record_count}。"
                    f"{'风廓线数据使用ERA5压力层（高精度）。' if wind_profile_data.get('era5_data') else '风廓线数据使用经验估算。'}"
                )

                return result

            except Exception as save_error:
                logger.error(
                    "universal_meteorology_data_save_failed",
                    lat=lat,
                    lon=lon,
                    error=str(save_error),
                    exc_info=True
                )
                # 保存失败，返回传统格式（向后兼容）
                comprehensive_data["status"] = "failed"
                comprehensive_data["success"] = False
                comprehensive_data["metadata"] = {
                    "tool_name": "get_universal_meteorology",
                    "error_type": "data_save_failed",
                    "error": str(save_error)
                }
                comprehensive_data["summary"] = f"❌ 数据保存失败: {str(save_error)}"
                return comprehensive_data

        except Exception as e:
            logger.error(
                "universal_meteorology_query_failed",
                lat=lat,
                lon=lon,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "get_universal_meteorology",
                    "error_type": "query_failed",
                    "error": str(e)
                },
                "summary": f"❌ 气象数据获取失败: {str(e)}"
            }

    async def _get_realtime_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        获取实时天气数据（温度、湿度、风、气压等）
        """
        try:
            data = await self.client.fetch_current_weather(lat=lat, lon=lon)

            if not data or "current" not in data:
                return {}

            current = data.get("current", {})

            return {
                "wind_speed_10m": current.get("wind_speed_10m"),
                "wind_direction_10m": current.get("wind_direction_10m"),
                "wind_gusts_10m": current.get("wind_gusts_10m"),
                "temperature_2m": current.get("temperature_2m"),
                "relative_humidity_2m": current.get("relative_humidity_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "surface_pressure": current.get("surface_pressure"),
                "precipitation": current.get("precipitation"),
                "cloud_cover": current.get("cloud_cover"),
                "visibility": current.get("visibility"),
                "time": current.get("time"),
                "data_source": "Open-Meteo Current"
            }

        except Exception as e:
            logger.error("realtime_weather_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {}

    async def _get_boundary_layer_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        获取边界层高度数据 - 返回72小时逐小时序列
        """
        try:
            data = await self.client.fetch_forecast(
                lat=lat,
                lon=lon,
                forecast_days=3,  # 获取3天数据确保72小时
                hourly=True,
                daily=False
            )

            if not data or "hourly" not in data:
                return {}

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            pbl_heights = hourly.get("boundary_layer_height", [])

            if not times or not pbl_heights:
                return {}

            # 构建逐小时边界层高度序列
            pbl_series = []
            now = datetime.utcnow()
            max_hours = 72  # 限制为72小时

            for i, time_str in enumerate(times[:max_hours]):  # 只取前72小时
                try:
                    time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    pbl_height = pbl_heights[i] if i < len(pbl_heights) else None

                    if pbl_height is not None:
                        pbl_series.append({
                            "time": time_str,
                            "boundary_layer_height": pbl_height,
                            "is_past": time < now,
                            "is_future": time >= now
                        })
                except:
                    continue

            if not pbl_series:
                return {}

            # 计算当前/最近时刻的边界层高度
            current_pbl = None
            for entry in pbl_series:
                if entry["is_past"]:
                    current_pbl = entry
                    break
            if not current_pbl and pbl_series:
                current_pbl = pbl_series[0]  # 如果没有过去数据，使用第一个

            return {
                "boundary_layer_series": pbl_series,  # 72小时逐时序列
                "current_height": current_pbl["boundary_layer_height"] if current_pbl else None,
                "current_time": current_pbl["time"] if current_pbl else None,
                "total_hours": len(pbl_series),
                "data_source": "Open-Meteo Forecast"
            }

        except Exception as e:
            logger.error("pbl_data_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {}

    async def _get_wind_profile_data(self, lat: float, lon: float, realtime_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取风廓线数据（多高度层）
        优先使用ERA5压力层数据，失败时回退到经验估算

        Args:
            lat: 纬度
            lon: 经度
            realtime_data: 已获取的实时数据，避免重复网络请求
        """
        try:
            # 首先尝试获取ERA5压力层数据（更精确）
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=6)  # 获取最近6小时数据

            end_date = end_time.strftime("%Y-%m-%d")
            start_date = start_time.strftime("%Y-%m-%d")

            # 压力层到近似高度的映射（标准大气）
            # 使用Barometric formula进行简化估算
            pressure_to_height = {
                1000: 111,   # 1000hPa ≈ 111m
                925: 762,    # 925hPa ≈ 762m
                850: 1457,   # 850hPa ≈ 1457m
                700: 3012,   # 700hPa ≈ 3012m
                500: 5574,   # 500hPa ≈ 5574m
                400: 7183,   # 400hPa ≈ 7183m
                300: 9164,   # 300hPa ≈ 9164m
                250: 10363,  # 250hPa ≈ 10363m
                200: 11784,  # 200hPa ≈ 11784m
                150: 13608,  # 150hPa ≈ 13608m
                100: 16180,  # 100hPa ≈ 16180m
            }

            try:
                # 获取ERA5压力层数据
                pressure_data = await self.client.fetch_era5_pressure_level_data(
                    lat=lat,
                    lon=lon,
                    start_date=start_date,
                    end_date=end_date,
                    pressure_levels=[1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100]
                )

                if pressure_data and "hourly" in pressure_data:
                    hourly = pressure_data.get("hourly", {})
                    times = hourly.get("time", [])

                    if times:
                        # 获取最新时刻的数据
                        latest_index = len(times) - 1
                        if latest_index >= 0:
                            # 构建ERA5风廓线 - 保存所有11个压力层（高空层对光化学分析重要）
                            era5_wind_profile = {}
                            used_era5 = False

                            # 覆盖所有11个压力层：1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100
                            for pressure_level in [1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100]:
                                wind_speed_key = f"wind_speed_{pressure_level}hPa"
                                wind_dir_key = f"wind_direction_{pressure_level}hPa"

                                wind_speed = hourly.get(wind_speed_key, [])
                                wind_direction = hourly.get(wind_dir_key, [])

                                if wind_speed and wind_direction and latest_index < len(wind_speed):
                                    speed = wind_speed[latest_index]
                                    direction = wind_direction[latest_index]

                                    if speed is not None and direction is not None:
                                        height_key = f"{pressure_to_height[pressure_level]:.0f}m"
                                        era5_wind_profile[height_key] = {
                                            "speed": speed,
                                            "direction": direction,
                                            "source": "ERA5压力层数据",
                                            "pressure_level": f"{pressure_level}hPa"
                                        }
                                        used_era5 = True

                            if used_era5:
                                return {
                                    "wind_profile": era5_wind_profile,
                                    "data_source": "ERA5再分析数据（压力层）",
                                    "note": f"使用ERA5再分析数据构建风廓线，覆盖{len(era5_wind_profile)}个高度层",
                                    "time": times[latest_index] if latest_index < len(times) else None,
                                    "era5_data": True,
                                    "total_levels": len(era5_wind_profile)
                                }
            except Exception as e:
                logger.warning(
                    "era5_pressure_level_fetch_failed_fallback_to_estimation",
                    lat=lat,
                    lon=lon,
                    error=str(e)
                )

            # 如果ERA5数据获取失败，回退到经验估算
            logger.info("using_empirical_wind_profile_estimation", lat=lat, lon=lon)

            # 使用透传的实时数据，避免重复网络请求
            wind_speed_10m = realtime_data.get("wind_speed_10m", 0) if realtime_data else 0
            wind_direction_10m = realtime_data.get("wind_direction_10m", 0) if realtime_data else 0

            if not wind_speed_10m:
                return {}

            # 简化风廓线估算（基于Monin-Obukhov相似理论）
            def estimate_wind_speed(height_m, ref_speed):
                """简化风速估算函数"""
                if height_m <= 10:
                    return ref_speed
                # 简化公式：v = v0 * (h/10)^0.25 (中性大气)
                return ref_speed * ((height_m / 10) ** 0.25)

            def estimate_wind_direction(height_m, ref_direction):
                """简化风向估算函数"""
                # 假设每100米风向偏转1度（简化）
                return (ref_direction + height_m / 100.0) % 360

            # 估算典型高度的风廓线
            wind_profile = {
                "10m": {
                    "speed": wind_speed_10m,
                    "direction": wind_direction_10m,
                    "source": "观测/模型"
                },
                "50m": {
                    "speed": estimate_wind_speed(50, wind_speed_10m),
                    "direction": estimate_wind_direction(50, wind_direction_10m),
                    "source": "估算"
                },
                "100m": {
                    "speed": estimate_wind_speed(100, wind_speed_10m),
                    "direction": estimate_wind_direction(100, wind_direction_10m),
                    "source": "估算"
                },
                "200m": {
                    "speed": estimate_wind_speed(200, wind_speed_10m),
                    "direction": estimate_wind_direction(200, wind_direction_10m),
                    "source": "估算"
                },
                "500m": {
                    "speed": estimate_wind_speed(500, wind_speed_10m),
                    "direction": estimate_wind_direction(500, wind_direction_10m),
                    "source": "估算"
                },
                "1000m": {
                    "speed": estimate_wind_speed(1000, wind_speed_10m),
                    "direction": estimate_wind_direction(1000, wind_direction_10m),
                    "source": "估算"
                }
            }

            return {
                "wind_profile": wind_profile,
                "data_source": "经验估算 + 实时观测",
                "note": "基于Monin-Obukhov相似理论的简化估算，ERA5压力层数据不可用",
                "era5_data": False,
                "estimation_method": "简化对数风廓线模型"
            }

        except Exception as e:
            logger.error("wind_profile_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {}

    async def _get_meteorological_forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        获取未来气象预报（完整数据）
        """
        try:
            forecast_data = await self.client.fetch_forecast(
                lat=lat,
                lon=lon,
                forecast_days=3,
                hourly=True,
                daily=True
            )

            if not forecast_data:
                return {}

            # 提取逐小时数据
            hourly = forecast_data.get("hourly", {})
            daily = forecast_data.get("daily", {})

            # 返回完整的原始数据（让Agent自己分析）
            return {
                "hourly": {
                    "time": hourly.get("time", []),
                    "temperature_2m": hourly.get("temperature_2m", []),
                    "relative_humidity_2m": hourly.get("relative_humidity_2m", []),
                    "wind_speed_10m": hourly.get("wind_speed_10m", []),
                    "wind_direction_10m": hourly.get("wind_direction_10m", []),
                    "wind_gusts_10m": hourly.get("wind_gusts_10m", []),
                    "surface_pressure": hourly.get("surface_pressure", []),
                    "precipitation": hourly.get("precipitation", []),
                    "boundary_layer_height": hourly.get("boundary_layer_height", []),
                    "cloud_cover": hourly.get("cloud_cover", [])
                },
                "daily": {
                    "time": daily.get("time", []),
                    "temperature_2m_max": daily.get("temperature_2m_max", []),
                    "temperature_2m_min": daily.get("temperature_2m_min", []),
                    "wind_speed_10m_max": daily.get("wind_speed_10m_max", []),
                    "wind_gusts_10m_max": daily.get("wind_gusts_10m_max", []),
                    "precipitation_sum": daily.get("precipitation_sum", []),
                    "precipitation_probability_max": daily.get("precipitation_probability_max", [])
                },
                "data_source": "Open-Meteo Forecast",
                "timezone": forecast_data.get("timezone", "UTC"),
                "elevation": forecast_data.get("elevation", None)
            }

        except Exception as e:
            logger.error("forecast_data_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {}

    async def _get_historical_reference(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        获取历史参考数据（ERA5）
        """
        try:
            # 获取最近7天的数据作为参考
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)

            # ERA5数据对齐到0.25°网格
            grid_lat = round(lat * 4) / 4
            grid_lon = round(lon * 4) / 4

            historical_data = await self.repo.get_weather_data(
                lat=grid_lat,
                lon=grid_lon,
                start_time=start_time,
                end_time=end_time
            )

            if not historical_data:
                return {}

            # 计算统计指标
            wind_speeds = [d.wind_speed_10m for d in historical_data if d.wind_speed_10m is not None]
            temperatures = [d.temperature_2m for d in historical_data if d.temperature_2m is not None]
            pbl_heights = [d.boundary_layer_height for d in historical_data if d.boundary_layer_height is not None]

            return {
                "record_count": len(historical_data),
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                },
                "grid_location": {
                    "lat": grid_lat,
                    "lon": grid_lon
                },
                "wind_speed_stats": {
                    "mean": sum(wind_speeds) / len(wind_speeds) if wind_speeds else None,
                    "min": min(wind_speeds) if wind_speeds else None,
                    "max": max(wind_speeds) if wind_speeds else None,
                    "count": len(wind_speeds)
                },
                "temperature_stats": {
                    "mean": sum(temperatures) / len(temperatures) if temperatures else None,
                    "min": min(temperatures) if temperatures else None,
                    "max": max(temperatures) if temperatures else None,
                    "count": len(temperatures)
                },
                "boundary_layer_stats": {
                    "mean": sum(pbl_heights) / len(pbl_heights) if pbl_heights else None,
                    "min": min(pbl_heights) if pbl_heights else None,
                    "max": max(pbl_heights) if pbl_heights else None,
                    "count": len(pbl_heights)
                },
                "data_source": "ERA5 Reanalysis"
            }

        except Exception as e:
            logger.error("historical_data_fetch_failed", lat=lat, lon=lon, error=str(e))
            return {}

    def _merge_data(
        self,
        location: Dict[str, Any],
        realtime: Dict[str, Any],
        pbl: Dict[str, Any],
        wind_profile: Optional[Dict[str, Any]],
        forecast: Optional[Dict[str, Any]],
        historical: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        合并多源数据（仅数据合并，无业务分析）
        """
        try:
            # 构建返回数据
            result = {
                "success": True,
                "location": location,
                "query_time": datetime.utcnow().isoformat() + "Z",
                "data_availability": {
                    "realtime": bool(realtime),
                    "boundary_layer": bool(pbl),
                    "wind_profile": bool(wind_profile),
                    "forecast": bool(forecast),
                    "historical": bool(historical)
                }
            }

            # 添加实时天气数据
            if realtime:
                result["realtime_weather"] = realtime

            # 添加边界层数据
            if pbl:
                result["boundary_layer"] = {
                    "height": pbl.get("boundary_layer_height"),
                    "time": pbl.get("time"),
                    "data_source": pbl.get("data_source")
                }

            # 添加风廓线数据
            if wind_profile:
                result["wind_profile"] = wind_profile.get("wind_profile", {})
                # 保留元数据信息
                if "note" in wind_profile:
                    result["wind_profile"]["note"] = wind_profile.get("note", "")
                if "data_source" in wind_profile:
                    result["wind_profile"]["data_source"] = wind_profile.get("data_source")
                if "time" in wind_profile:
                    result["wind_profile"]["time"] = wind_profile.get("time")
                if "era5_data" in wind_profile:
                    result["wind_profile"]["era5_data"] = wind_profile.get("era5_data")

            # 添加预报数据
            if forecast:
                result["forecast"] = forecast

            # 添加历史参考数据
            if historical:
                result["historical_reference"] = historical

            return result

        except Exception as e:
            logger.error("data_merge_failed", error=str(e))
            return {
                "success": False,
                "error": f"数据合并失败: {str(e)}",
                "location": location
            }