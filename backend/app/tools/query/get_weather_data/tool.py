"""
Get Weather Data Tool

LLM可调用的气象数据查询工具

功能：
- 查询指定位置和时间范围的历史气象数据
- 支持ERA5再分析数据
- 支持观测站数据
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import uuid4
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.db.repositories.weather_repo import WeatherRepository
from app.utils.data_standardizer import get_data_standardizer  # UDF v2.0 集成
from app.utils.data_features_extractor import DataFeaturesExtractor  # 数据特征提取

logger = structlog.get_logger()


class GetWeatherDataTool(LLMTool):
    """
    气象数据查询工具

    给LLM提供查询历史气象数据的能力

    Context-Aware V2 架构：
    - 使用 context.save_data() 保存数据
    - 返回 data_id 供下游工具引用
    """

    def __init__(self):
        function_schema = {
            "name": "get_weather_data",
            "description": """查询历史气象数据（ERA5再分析数据或地面观测站数据）。

【调用规则 - 严格遵守】

1. data_type="era5"（推荐使用）：
   - 必填参数：lat, lon, start_time, end_time
   - 根据经纬度自动查询ERA5网格数据
   - 无需提供 station_id

2. data_type="observed"：
   - 必填参数：station_id, start_time, end_time
   - 必须提供具体的气象站ID（如 "54511"）
   - 不能用 lat/lon 替代 station_id

【禁止的调用方式】
- data_type="observed" 但只提供 lat/lon 而无 station_id ❌
- data_type="era5" 但只提供 station_id 而无 lat/lon ❌

【返回格式】
{
    "success": bool,              # 查询是否成功
    "data_id": string,            # 数据ID（下游工具通过 context.get_data() 获取）
    "has_data": bool,             # 是否有实际数据
    "data_type": "era5|observed", # 查询的数据类型
    "count": int,                 # 记录数量
    "summary": str                # 结果摘要（含数据质量信息）
}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_type": {
                        "type": "string",
                        "enum": ["era5", "observed"],
                        "description": "数据类型：era5=ERA5再分析数据(需lat/lon) | observed=观测站数据(需station_id)"
                    },
                    "lat": {
                        "type": "number",
                        "description": "纬度（ERA5查询必填，与lon配套使用）"
                    },
                    "lon": {
                        "type": "number",
                        "description": "经度（ERA5查询必填，与lat配套使用）"
                    },
                    "station_id": {
                        "type": "string",
                        "description": "气象站ID（观测数据查询必填，如'54511'，不能用lat/lon替代）"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，ISO 8601格式，例如：2025-01-01T00:00:00"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，ISO 8601格式，例如：2025-01-02T00:00:00"
                    }
                },
                "required": ["data_type", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="get_weather_data",
            description="Query historical weather data (ERA5 reanalysis or observed station data)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        # Context-Aware V2: 设置需要 context 参数
        self.requires_context = True

        self.repo = WeatherRepository()

    async def execute(
        self,
        context,  # Context-Aware V2: ExecutionContext 对象
        data_type: str,
        start_time: str,
        end_time: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        station_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行气象数据查询（统一数据格式）

        Args:
            data_type: 数据类型（era5 或 observed）
            start_time: 开始时间（ISO 8601格式）
            end_time: 结束时间（ISO 8601格式）
            lat: 纬度（ERA5查询必需）
            lon: 经度（ERA5查询必需）
            station_id: 气象站ID（observed查询必需）

        Returns:
            Dict: 统一数据格式的查询结果 (UnifiedData.dict())
        """
        try:
            # 解析时间
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            logger.info(
                "weather_query_started",
                data_type=data_type,
                start=start_dt.isoformat(),
                end=end_dt.isoformat()
            )

            if data_type == "era5":
                return await self._query_era5(context, lat, lon, start_dt, end_dt)
            elif data_type == "observed":
                return await self._query_observed(context, station_id, start_dt, end_dt)
            else:
                from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
                # 生成标准的长格式data_id用于错误情况
                error_data_id = f"weather_error:v1:{uuid4().hex}"
                return UnifiedData(
                    status=DataStatus.FAILED,
                    success=False,
                    error=f"不支持的数据类型: {data_type}",
                    data=[],
                    metadata=DataMetadata(
                        data_id=error_data_id,
                        data_type=DataType.WEATHER,
                        source="weather_repo"
                    ),
                    summary=f"[ERROR] 不支持的数据类型: {data_type}"
                ).dict()

        except Exception as e:
            logger.error(
                "weather_query_failed",
                error=str(e),
                exc_info=True
            )
            from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
            # 生成标准的长格式data_id用于异常情况
            exception_data_id = f"weather_error:v1:{uuid4().hex}"
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                data=[],
                metadata=DataMetadata(
                    data_id=exception_data_id,
                    data_type=DataType.WEATHER,
                    source="weather_repo"
                ),
                summary=f"[ERROR] 气象数据查询失败: {str(e)[:50]}"
            ).dict()

    async def _query_era5(
        self,
        context,
        lat: Optional[float],
        lon: Optional[float],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """查询ERA5数据（统一格式）"""
        from app.schemas.unified import (
            UnifiedData, DataType, DataStatus, DataMetadata, UnifiedDataRecord
        )

        if lat is None or lon is None:
            # 生成标准的长格式data_id用于错误情况
            error_data_id = f"weather_error:v1:{uuid4().hex}"
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error="ERA5查询需要提供 lat 和 lon 参数",
                data=[],
                metadata=DataMetadata(
                    data_id=error_data_id,
                    data_type=DataType.WEATHER,
                    source="weather_repo"
                ),
                summary="[ERROR] ERA5查询参数错误"
            ).dict()

        # ERA5 网格对齐（0.25° 分辨率）
        # 原始坐标 (23.13, 113.26) → 对齐到 (23.25, 113.25)
        original_lat, original_lon = lat, lon
        grid_lat = round(lat * 4) / 4
        grid_lon = round(lon * 4) / 4

        if (grid_lat != original_lat) or (grid_lon != original_lon):
            logger.info(
                "era5_grid_alignment",
                original=f"({original_lat:.2f}, {original_lon:.2f})",
                aligned=f"({grid_lat:.2f}, {grid_lon:.2f})",
                message="坐标已对齐到ERA5 0.25°网格"
            )

        # 查询数据库（使用对齐后的坐标）
        data = await self.repo.get_weather_data(grid_lat, grid_lon, start_time, end_time)

        # 转换为UnifiedDataRecord格式
        records = []
        for record in data:
            # 提取气象测量值，处理None值
            # 对于None值，使用NaN表示缺失数据
            import math

            measurements = {
                "temperature_2m": record.temperature_2m if record.temperature_2m is not None else math.nan,
                "relative_humidity_2m": record.relative_humidity_2m if record.relative_humidity_2m is not None else math.nan,
                "dew_point_2m": record.dew_point_2m if record.dew_point_2m is not None else math.nan,
                "wind_speed_10m": record.wind_speed_10m if record.wind_speed_10m is not None else math.nan,
                "wind_direction_10m": record.wind_direction_10m if record.wind_direction_10m is not None else math.nan,
                "wind_gusts_10m": record.wind_gusts_10m if record.wind_gusts_10m is not None else math.nan,
                "surface_pressure": record.surface_pressure if record.surface_pressure is not None else math.nan,
                "precipitation": record.precipitation if record.precipitation is not None else math.nan,
                "cloud_cover": record.cloud_cover if record.cloud_cover is not None else math.nan,
                "shortwave_radiation": record.shortwave_radiation if record.shortwave_radiation is not None else math.nan,
                "visibility": record.visibility if record.visibility is not None else math.nan,
                "boundary_layer_height": record.boundary_layer_height if record.boundary_layer_height is not None else math.nan,
            }

            records.append(UnifiedDataRecord(
                timestamp=record.time,
                lat=grid_lat,
                lon=grid_lon,
                measurements=measurements
            ))

        logger.info("era5_query_successful", records=len(records), grid_point=f"({grid_lat}, {grid_lon})")

        # 【优化3】数据质量验证
        from app.utils.data_quality_validator import get_data_quality_validator
        quality_validator = get_data_quality_validator()

        # 【UDF v2.0】使用data_standardizer标准化数据
        # 将UnifiedDataRecord转换为字典进行标准化
        records_dict_list = []
        for record in records:
            record_dict = {
                "timestamp": record.timestamp,
                "lat": record.lat,
                "lon": record.lon,
                "temperature_2m": record.measurements.get("temperature_2m"),
                "relative_humidity_2m": record.measurements.get("relative_humidity_2m"),
                "dew_point_2m": record.measurements.get("dew_point_2m"),
                "wind_speed_10m": record.measurements.get("wind_speed_10m"),
                "wind_direction_10m": record.measurements.get("wind_direction_10m"),
                "wind_gusts_10m": record.measurements.get("wind_gusts_10m"),
                "surface_pressure": record.measurements.get("surface_pressure"),
                "precipitation": record.measurements.get("precipitation"),
                "cloud_cover": record.measurements.get("cloud_cover"),
                "shortwave_radiation": record.measurements.get("shortwave_radiation"),
                "visibility": record.measurements.get("visibility"),
                "boundary_layer_height": record.measurements.get("boundary_layer_height")
            }
            records_dict_list.append(record_dict)

        # 使用全局数据标准化器标准化数据
        data_standardizer = get_data_standardizer()
        standardized_records = data_standardizer.standardize(records_dict_list)

        logger.info(
            "era5_data_standardized",
            original_count=len(records),
            standardized_count=len(standardized_records)
        )

        # 生成标准的长格式data_id（schema:v1:hash）
        data_id_hash = uuid4().hex
        standard_data_id = f"weather:v1:{data_id_hash}"

        summary = f"[OK] 查询到 {len(standardized_records)} 条ERA5气象数据"
        if standardized_records:
            summary += f"（网格点 {grid_lat:.2f}, {grid_lon:.2f}，{start_time.date()} 至 {end_time.date()}）"
        else:
            summary = f"[WARN] 数据库中没有网格点 ({grid_lat}, {grid_lon}) 在 {start_time.date()} 至 {end_time.date()} 期间的ERA5气象数据"

        # 【UDF v2.0】提取数据特征用于Agent推荐图表
        data_features = DataFeaturesExtractor.extract_features(
            standardized_records,
            schema_type="weather"
        )

        # 【优化3】数据质量验证（在返回前验证数据质量）
        quality_report = quality_validator.validate_data(
            data=standardized_records,
            schema_type="weather",
            required_fields=["timestamp"],  # ERA5数据至少需要时间戳
            min_records=1
        )

        logger.info(
            "era5_data_quality_validation",
            quality_level=quality_report.quality_level.value,
            is_valid=quality_report.is_valid,
            issues=quality_report.issues
        )

        # 根据质量报告更新summary
        quality_suffix = ""
        if quality_report.quality_level.value == "EXCELLENT":
            quality_suffix = " (数据质量: 优秀)"
        elif quality_report.quality_level.value == "GOOD":
            quality_suffix = " (数据质量: 良好)"
        elif quality_report.quality_level.value == "ACCEPTABLE":
            quality_suffix = f" (数据质量: 可接受，{quality_report.issues[0] if quality_report.issues else ''})"
        elif quality_report.quality_level.value == "POOR":
            quality_suffix = f" (数据质量: 较差，{quality_report.issues[0] if quality_report.issues else ''})"

        summary = summary + quality_suffix

        # 【Context-Aware V2】使用 context.save_data() 保存数据
        saved_data_id = None  # 初始化变量
        file_path = None
        if standardized_records and context is not None:
            try:
                # save_data() 返回字符串 ID
                saved_data_id = await context.save_data(
                    data=standardized_records,
                    schema="weather"
                )
                logger.info(
                    "era5_data_saved_to_context",
                    data_id=saved_data_id,
                    record_count=len(standardized_records)
                )
            except Exception as e:
                logger.warning(
                    "era5_data_save_failed",
                    error=str(e),
                    message="将继续使用本地data_id，但下游工具可能无法通过context获取数据"
                )

        # 使用保存的 data_id 或本地生成的 ID
        final_data_id = saved_data_id if saved_data_id else standard_data_id

        # 添加 data_id 到 summary（修复：确保 final_data_id 已定义）
        if final_data_id:
            summary = f"{summary}，已保存为 {final_data_id}。"

        # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
        sample_record = None
        if standardized_records:
            first = standardized_records[0]
            sample_record = {
                "timestamp": first.get("timestamp"),
                "station_name": first.get("station_name"),
                "lat": first.get("lat"),
                "lon": first.get("lon"),
                "measurements": first.get("measurements", {})
            }

        # 构建元数据（使用对齐后的网格坐标）
        metadata = DataMetadata(
            data_id=final_data_id,
            data_type=DataType.WEATHER,
            record_count=len(standardized_records),
            lat=grid_lat,
            lon=grid_lon,
            source="era5_reanalysis",
            time_range={
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            quality_score=0.9 if standardized_records else 0.0
        )

        # 【UDF v2.0】返回标准化数据
        return {
            "status": "success",
            "success": len(standardized_records) > 0,
            "data": standardized_records,  # 保留 data 字段供直接访问
            "data_id": final_data_id,       # Context-Aware V2: 返回 data_id
            "file_path": file_path,         # 添加文件路径
            "metadata": {
                **metadata.dict(),
                "schema_version": "v2.0",  # UDF v2.0 标记
                "schema_type": "weather",  # ✅ Agent推荐图表的关键字段
                "generator": "get_weather_data",  # ✅ 工具名称
                "scenario": "weather_analysis",  # ✅ 场景标识
                "field_mapping_applied": True,
                "field_mapping_info": data_standardizer.get_field_mapping_info(),
                "data_features": data_features,  # ✅ 数据特征摘要（帮助Agent推荐图表）
                "quality_report": quality_report.dict(),  # ✅ 【优化3】数据质量报告
                "sample_record": sample_record  # ✅ 数据样本
            },
            "summary": summary,
            "legacy_fields": {
                "data_type": "era5",
                "location": {"lat": grid_lat, "lon": grid_lon},
                "original_query": {"lat": original_lat, "lon": original_lon},
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            }
        }

    async def _query_observed(
        self,
        context,
        station_id: Optional[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """查询观测数据（统一格式）"""
        from app.schemas.unified import (
            UnifiedData, DataType, DataStatus, DataMetadata, UnifiedDataRecord
        )

        if not station_id:
            # 生成标准的长格式data_id用于错误情况
            error_data_id = f"weather_error:v1:{uuid4().hex}"
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error="观测数据查询需要提供 station_id 参数",
                data=[],
                metadata=DataMetadata(
                    data_id=error_data_id,
                    data_type=DataType.WEATHER,
                    source="weather_repo"
                ),
                summary="[ERROR] 观测数据查询参数错误"
            ).dict()

        # 查询数据库
        data = await self.repo.get_observed_data(station_id, start_time, end_time)

        # 转换为UnifiedDataRecord格式
        records = []
        for record in data:
            # 提取气象测量值，处理None值
            # 对于None值，使用NaN表示缺失数据
            import math

            measurements = {
                "temperature_2m": record.temperature_2m if record.temperature_2m is not None else math.nan,
                "relative_humidity_2m": record.relative_humidity_2m if record.relative_humidity_2m is not None else math.nan,
                "dew_point_2m": record.dew_point_2m if record.dew_point_2m is not None else math.nan,
                "wind_speed_10m": record.wind_speed_10m if record.wind_speed_10m is not None else math.nan,
                "wind_direction_10m": record.wind_direction_10m if record.wind_direction_10m is not None else math.nan,
                "surface_pressure": record.surface_pressure if record.surface_pressure is not None else math.nan,
                "precipitation": record.precipitation if record.precipitation is not None else math.nan,
                "cloud_cover": record.cloud_cover if record.cloud_cover is not None else math.nan,
                "visibility": record.visibility if record.visibility is not None else math.nan,
            }

            records.append(UnifiedDataRecord(
                timestamp=record.time,
                station_name=station_id,
                measurements=measurements
            ))

        logger.info("observed_query_successful", records=len(records))

        # 【UDF v2.0】使用data_standardizer标准化数据
        # 将UnifiedDataRecord转换为字典进行标准化
        records_dict_list = []
        for record in records:
            record_dict = {
                "timestamp": record.timestamp,
                "station_name": record.station_name,
                "temperature_2m": record.measurements.get("temperature_2m"),
                "relative_humidity_2m": record.measurements.get("relative_humidity_2m"),
                "dew_point_2m": record.measurements.get("dew_point_2m"),
                "wind_speed_10m": record.measurements.get("wind_speed_10m"),
                "wind_direction_10m": record.measurements.get("wind_direction_10m"),
                "surface_pressure": record.measurements.get("surface_pressure"),
                "precipitation": record.measurements.get("precipitation"),
                "cloud_cover": record.measurements.get("cloud_cover"),
                "visibility": record.measurements.get("visibility")
            }
            records_dict_list.append(record_dict)

        # 使用全局数据标准化器标准化数据
        data_standardizer = get_data_standardizer()
        standardized_records = data_standardizer.standardize(records_dict_list)

        logger.info(
            "observed_data_standardized",
            original_count=len(records),
            standardized_count=len(standardized_records)
        )

        # 生成标准的长格式data_id（schema:v1:hash）
        data_id_hash = uuid4().hex
        standard_data_id = f"weather:v1:{data_id_hash}"

        # 构建元数据
        metadata = DataMetadata(
            data_id=standard_data_id,  # ✅ 使用标准长格式ID
            data_type=DataType.WEATHER,
            record_count=len(standardized_records),
            station_name=station_id,
            source="observed_station",
            time_range={
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            quality_score=0.9 if standardized_records else 0.0
        )

        summary = f"[OK] 查询到站点 {station_id} 的 {len(standardized_records)} 条观测气象数据"
        if standardized_records:
            summary += f"（{start_time.date()} 至 {end_time.date()}）"
        else:
            summary = f"[WARN] 数据库中没有站点 {station_id} 在 {start_time.date()} 至 {end_time.date()} 期间的观测气象数据"

        # 【UDF v2.0】提取数据特征用于Agent推荐图表
        data_features = DataFeaturesExtractor.extract_features(
            standardized_records,
            schema_type="weather"
        )

        # 【优化3】数据质量验证（在返回前验证数据质量）
        from app.utils.data_quality_validator import get_data_quality_validator
        quality_validator = get_data_quality_validator()

        quality_report = quality_validator.validate_data(
            data=standardized_records,
            schema_type="weather",
            required_fields=["timestamp", "station_name"],  # 观测数据需要时间戳和站点名
            min_records=1
        )

        logger.info(
            "observed_data_quality_validation",
            quality_level=quality_report.quality_level.value,
            is_valid=quality_report.is_valid,
            issues=quality_report.issues
        )

        # 根据质量报告更新summary
        quality_suffix = ""
        if quality_report.quality_level.value == "EXCELLENT":
            quality_suffix = " (数据质量: 优秀)"
        elif quality_report.quality_level.value == "GOOD":
            quality_suffix = " (数据质量: 良好)"
        elif quality_report.quality_level.value == "ACCEPTABLE":
            quality_suffix = f" (数据质量: 可接受，{quality_report.issues[0] if quality_report.issues else ''})"
        elif quality_report.quality_level.value == "POOR":
            quality_suffix = f" (数据质量: 较差，{quality_report.issues[0] if quality_report.issues else ''})"

        summary = summary + quality_suffix

        # 添加 data_id 到 summary
        if final_data_id:
            summary = f"{summary}，已保存为 {final_data_id}。"

        # 【Context-Aware V2】使用 context.save_data() 保存数据
        saved_data_id = None  # 初始化变量
        file_path = None
        if standardized_records and context is not None:
            try:
                # save_data() 返回字符串 ID
                saved_data_id = await context.save_data(
                    data=standardized_records,
                    schema="weather"
                )
                logger.info(
                    "observed_data_saved_to_context",
                    data_id=saved_data_id,
                    record_count=len(standardized_records)
                )
            except Exception as e:
                logger.warning(
                    "observed_data_save_failed",
                    error=str(e),
                    message="将继续使用本地data_id，但下游工具可能无法通过context获取数据"
                )

        # 使用保存的 data_id 或本地生成的 ID
        final_data_id = saved_data_id if saved_data_id else standard_data_id

        # 更新 metadata 中的 data_id
        metadata = DataMetadata(
            data_id=final_data_id,
            data_type=DataType.WEATHER,
            record_count=len(standardized_records),
            station_name=station_id,
            source="observed_station",
            time_range={
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            quality_score=0.9 if standardized_records else 0.0
        )

        # 【UDF v2.0】返回标准化数据
        return {
            "status": "success",
            "success": len(standardized_records) > 0,
            "data": standardized_records,
            "data_id": final_data_id,       # Context-Aware V2: 返回 data_id
            "file_path": file_path,         # 添加文件路径
            "metadata": {
                **metadata.dict(),
                "schema_version": "v2.0",  # UDF v2.0 标记
                "schema_type": "weather",  # ✅ Agent推荐图表的关键字段
                "generator": "get_weather_data",  # ✅ 工具名称
                "scenario": "weather_analysis",  # ✅ 场景标识
                "field_mapping_applied": True,
                "field_mapping_info": data_standardizer.get_field_mapping_info(),
                "data_features": data_features,  # ✅ 数据特征摘要（帮助Agent推荐图表）
                "quality_report": quality_report.dict(),  # ✅ 【优化3】数据质量报告
                "sample_record": sample_record  # ✅ 数据样本
            },
            "summary": summary,
            "legacy_fields": {
                "data_type": "observed",
                "station_id": station_id,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            }
        }
