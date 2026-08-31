"""
Get Weather Data Tool
LLM可调用的气象数据查询工具

功能：
- 查询指定位置和时间范围的历史气象数据
- 仅支持ERA5再分析数据；地面观测站小时数据请使用 execute_postgres_sql_query 查询 observed_weather_data 表
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.config.weather_targets import normalize_city_name, resolve_weather_city_target
from app.db.repositories.weather_repo import WeatherRepository
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.data_features_extractor import DataFeaturesExtractor  # 数据特征提取
from app.utils.data_standardizer import get_data_standardizer  # UDF v2.0 集成

logger = structlog.get_logger()


class GetWeatherDataTool(LLMTool):
    """
    气象数据查询工具

    给LLM提供查询历史气象数据的能力

    Context-Aware V2 架构：
    - 使用 context.save_data() 保存数据
    - 返回 file_path 供下游工具引用
    """

    def __init__(self):
        function_schema = {
            "name": "get_weather_data",
            "description": """查询历史气象数据（ERA5再分析数据）。

【调用规则 - 严格遵守】

1. 城市查询：提供 city 或 cities，工具内部解析城市代表点并查询ERA5网格
2. 精确查询：提供 lat, lon（无需 station_id）

【本工具仅支持ERA5再分析数据】
- 地面观测站逐小时数据（如许昌站小时观测）请使用 execute_postgres_sql_query 查询 observed_weather_data 表

【返回格式】
{
    "success": bool,              # 查询是否成功
    "file_path": string,            # 数据ID（下游工具通过 context.get_data() 获取）
    "has_data": bool,             # 是否有实际数据
    "data_type": "era5",          # 查询的数据类型
    "count": int,                 # 记录数量
    "summary": str                # 结果摘要（含数据质量信息）
}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_type": {
                        "type": "string",
                        "enum": ["era5"],
                        "description": "数据类型：era5=ERA5再分析数据(城市或lat/lon)，本工具唯一支持类型"
                    },
                    "lat": {
                        "type": "number",
                        "description": "纬度（ERA5精确查询使用，与lon配套）"
                    },
                    "lon": {
                        "type": "number",
                        "description": "经度（ERA5精确查询使用，与lat配套）"
                    },
                    "city": {
                        "type": "string",
                        "description": "单个城市名称。工具内部解析ERA5代表点，如'南京市'"
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，适合多城市批量查询"
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
            description="Query historical ERA5 reanalysis weather data",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.2.0"
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
        city: Optional[str] = None,
        cities: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行气象数据查询（统一数据格式）

        Args:
            data_type: 数据类型（仅支持 era5）
            start_time: 开始时间（ISO 8601格式）
            end_time: 结束时间（ISO 8601格式）
            lat: 纬度（ERA5精确查询必需）
            lon: 经度（ERA5精确查询必需）
            city: 单个城市名称，由工具内部解析查询目标
            cities: 城市名称列表，由工具内部批量解析查询目标

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
                end=end_dt.isoformat(),
                city=city,
                cities=cities,
            )

            if data_type != "era5":
                from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
                return UnifiedData(
                    status=DataStatus.FAILED,
                    success=False,
                    error=(
                        f"不支持的数据类型: {data_type}。本工具仅支持ERA5再分析数据；"
                        "地面观测站小时数据请使用 execute_postgres_sql_query 查询 observed_weather_data 表"
                    ),
                    data=[],
                    metadata=DataMetadata(
                        data_type=DataType.WEATHER,
                        source="weather_repo"
                    ),
                    summary=(
                        f"[ERROR] 不支持的数据类型: {data_type}。"
                        "观测站数据请改用 execute_postgres_sql_query(observed_weather_data)"
                    )
                ).dict()

            requested_cities = self._clean_cities(city=city, cities=cities)
            if requested_cities:
                return await self._query_era5_cities(
                    context, requested_cities, start_dt, end_dt
                )

            return await self._query_era5(context, lat, lon, start_dt, end_dt)

        except Exception as e:
            logger.error(
                "weather_query_failed",
                error=str(e),
                exc_info=True
            )
            from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                data=[],
                metadata=DataMetadata(
                    data_type=DataType.WEATHER,
                    source="weather_repo"
                ),
                summary=f"[ERROR] 气象数据查询失败: {str(e)[:50]}"
            ).dict()

    @staticmethod
    def _clean_cities(
        *,
        city: Optional[str],
        cities: Optional[List[str]],
    ) -> List[str]:
        values: List[str] = []
        if city:
            values.append(city)
        if isinstance(cities, str):
            values.append(cities)
        else:
            values.extend(cities or [])

        result: List[str] = []
        for value in values:
            normalized = normalize_city_name(value)
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    async def _query_era5_cities(
        self,
        context,
        cities: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        unresolved: List[str] = []
        targets: List[Dict[str, Any]] = []

        for requested_city in cities:
            target = resolve_weather_city_target(requested_city)
            if target is None or target.era5_point is None:
                unresolved.append(requested_city)
                continue

            result = await self._query_era5(
                None,
                target.era5_lat,
                target.era5_lon,
                start_time,
                end_time,
                city=target.city,
            )
            results.append({"city": target.city, "result": result})
            metadata = result.get("metadata") or {}
            targets.append(
                {
                    "city": target.city,
                    "province": target.province,
                    "lat": target.era5_lat,
                    "lon": target.era5_lon,
                    "grid_lat": metadata.get("lat"),
                    "grid_lon": metadata.get("lon"),
                }
            )

        return self._combine_city_results(
            context=context,
            requested_cities=cities,
            results=results,
            unresolved_cities=unresolved,
            targets=targets,
            start_time=start_time,
            end_time=end_time,
        )

    def _combine_city_results(
        self,
        *,
        context,
        requested_cities: List[str],
        results: List[Dict[str, Any]],
        unresolved_cities: List[str],
        targets: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        combined: List[Dict[str, Any]] = []
        resolved_cities: List[str] = []
        no_data_cities: List[str] = []

        for item in results:
            city = item["city"]
            resolved_cities.append(city)
            records = item["result"].get("data") or []
            if not records:
                no_data_cities.append(city)
                continue
            for record in records:
                enriched = dict(record)
                enriched["city"] = city
                combined.append(enriched)

        saved_file_path = None
        if combined and context is not None:
            try:
                saved_file_path = context.save_data(data=combined, schema="weather")
            except Exception as exc:
                logger.warning("city_weather_data_save_failed", error=str(exc))

        if combined:
            status = "partial" if unresolved_cities or no_data_cities else "success"
            summary = (
                f"[OK] 查询到 {len(resolved_cities)} 个城市的 {len(combined)} 条"
                "ERA5气象数据"
            )
        elif resolved_cities:
            status = "empty"
            summary = "[WARN] 已解析城市查询目标，但指定时段没有气象数据"
        else:
            status = "failed"
            summary = "[ERROR] 未找到所请求城市的气象查询目标"

        if unresolved_cities:
            summary += f"；未解析城市：{', '.join(unresolved_cities)}"
        if no_data_cities:
            summary += f"；无数据城市：{', '.join(no_data_cities)}"

        return {
            "status": status,
            "success": bool(combined),
            "data": combined,
            "file_path": saved_file_path,
            "metadata": {
                "schema_version": "v2.0",
                "schema_type": "weather",
                "generator": "get_weather_data",
                "scenario": "weather_analysis",
                "data_type": "weather",
                "weather_data_type": "era5",
                "record_count": len(combined),
                "source": "era5_reanalysis",
                "requested_cities": requested_cities,
                "resolved_cities": resolved_cities,
                "unresolved_cities": unresolved_cities,
                "no_data_cities": no_data_cities,
                "targets": targets,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
            },
            "summary": summary,
        }

    async def _query_era5(
        self,
        context,
        lat: Optional[float],
        lon: Optional[float],
        start_time: datetime,
        end_time: datetime,
        city: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询ERA5数据（统一格式）"""
        from app.schemas.unified import (
            UnifiedData, DataType, DataStatus, DataMetadata, UnifiedDataRecord
        )

        if lat is None or lon is None:
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error="ERA5查询需要提供 city/cities 或 lat 和 lon 参数",
                data=[],
                metadata=DataMetadata(
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
                "city": city,
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
        saved_file_path = None  # 初始化变量
        if standardized_records and context is not None:
            try:
                # save_data() 返回字符串 ID
                saved_file_path = context.save_data(
                    data=standardized_records,
                    schema="weather"
                )
                logger.info(
                    "era5_data_saved_to_context",
                    file_path=saved_file_path,
                    record_count=len(standardized_records)
                )
            except Exception as e:
                logger.warning(
                    "era5_data_save_failed",
                    error=str(e),
                    message="将继续使用本地file_path，但下游工具可能无法通过context获取数据"
                )

        final_file_path = saved_file_path

        # 添加 file_path 到 summary（修复：确保 final_file_path 已定义）
        if final_file_path:
            summary = f"{summary}，已保存为 {final_file_path}。"

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
            file_path=final_file_path,
            data_type=DataType.WEATHER,
            record_count=len(standardized_records),
            lat=grid_lat,
            lon=grid_lon,
            city=city,
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
            "file_path": final_file_path,
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
            "summary": summary
        }
