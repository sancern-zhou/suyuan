"""
Get Weather Data Tool
LLM可调用的气象数据查询工具

功能：
- 查询指定位置和时间范围的历史气象数据
- 仅支持ERA5再分析数据；地面观测站小时数据请使用 execute_postgres_sql_query 查询 observed_weather_data 表
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.config.weather_targets import normalize_city_name, resolve_weather_city_target
from app.db.repositories.weather_repo import WeatherRepository
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.data_features_extractor import DataFeaturesExtractor  # 数据特征提取
from app.utils.data_standardizer import get_data_standardizer  # UDF v2.0 集成
from app.utils.weather_time import (
    WEATHER_UNITS, WEATHER_QUERY_GUIDANCE, normalize_weather_record,
    weather_data_structure, weather_output_metadata, weather_output_time, weather_query_time,
)

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
            "description": """查询已入库的历史气象网格数据（历史兼容参数data_type="era5"）。

【工具选择】
1. 历史网格气象、历史边界层高度或短波辐射：用本工具。配置城市历史采集的项目优先读库，边界层缺失时小范围在线补采，大范围提交后台；检查history_backfill中的进度和警告，排队不代表已获取数据。
2. 今天（含已过小时）、未来、或历史库未覆盖的近5天边界层高度/短波辐射：直接调用get_weather_forecast。不要向本工具传未来时段试探；纯ERA5有发布延迟，无法提供当天数据。
3. 跨历史与未来的请求：历史段用本工具，当天及未来段用get_weather_forecast；根据actual_time_range核对缺口，按带时区的timestamp去重，每条保留data_source，不混称为ERA5或实测。
4. 站点实测（温湿度、风等）：查询observed_weather_data观测表（工具可用时用execute_postgres_sql_query）；站点实测不能替代模式边界层高度/短波辐射，不得从气温风速自行估算缺失字段。
5. 仅当用户明确要求纯ERA5时，核对data_source；本工具不能保证纯ERA5。不能因工具名或请求坐标按0.25°对齐，就声称数据来自ERA5网格。

【时间与覆盖】
输入支持Z或+08:00，无时区按北京时间。输出timestamp已带+08:00，不得再次加减8小时，也不得用日变化拟合时差。
缺失值必须保留为缺失，不补0、不用短波辐射日累计(MJ/m²)替代小时平均(W/m²)。请求范围不等于实际覆盖范围；有缺口时，仅对近5天调用get_weather_forecast补充，仍缺失则明确说明。

data_type="era5" 是历史兼容名称，不保证纯ERA5模型；数据来源以返回的data_source为准。
历史网格查询的无时区输入按北京时间解释；输出timestamp带+08:00，禁止再次加8小时。
网格数据输出风速和阵风统一为m/s，边界层高度为m。实际覆盖范围见actual_time_range，不能将请求范围当作实际范围。

【调用规则 - 严格遵守】

1. data_type="era5"（推荐使用）：
   - 城市查询：提供 city 或 cities，工具内部解析城市代表点并查询历史网格
   - 精确查询：提供 lat, lon
   - 无需提供 station_id

【本工具仅支持历史网格数据】
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
                        "description": "era5=历史网格库（兼容名称，实际模型见data_source）；当天/未来用get_weather_forecast；站点实测用execute_postgres_sql_query"
                    },
                    "lat": {
                        "type": "number",
                        "description": "历史网格查询纬度，与lon配套；有城市名称时优先传city"
                    },
                    "lon": {
                        "type": "number",
                        "description": "历史网格查询经度，与lat配套；请求坐标不保证上游实际模型网格"
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
                        "description": "开始时间，ISO 8601格式；无时区按北京时间。例如2025-01-01T00:00:00+08:00"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间（包含），ISO 8601格式；无时区按北京时间。支持Z或+08:00"
                    }
                },
                "required": ["data_type", "start_time", "end_time"]
            }
        }

        function_schema["description"] += WEATHER_QUERY_GUIDANCE
        super().__init__(
            name="get_weather_data",
            description="Query stored historical weather; use get_weather_forecast for today, future and recent gaps",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.2.0"
        )

        # Context-Aware V2: 设置需要 context 参数
        self.requires_context = True

        self.repo = WeatherRepository()
        from app.services.weather_history import configured_history_service
        self.history = configured_history_service()

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
            if data_type == "era5":
                start_dt = weather_query_time(start_dt)
                end_dt = weather_query_time(end_dt)
                if end_dt < start_dt:
                    raise ValueError("end_time must not precede start_time")

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
            backfill = await self._prepare_history(requested_cities, lat, lon, start_dt, end_dt)
            if requested_cities:
                result = await self._query_era5_cities(
                    context, requested_cities, start_dt, end_dt
                )
                return self._finish_history(result, backfill, requested_cities, start_dt, end_dt)

            result = await self._query_era5(context, lat, lon, start_dt, end_dt)
            return self._finish_history(result, backfill, [], start_dt, end_dt)

        except Exception as e:
            logger.error(
                "weather_query_failed",
                error=str(e),
                exc_info=True
            )
            from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
            result = UnifiedData(
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
            result["error_code"] = "WEATHER_QUERY_FAILED"
            return result

    def _resolve_city(self, city):
        point = self.history.resolve(city) if self.history else None
        if point is not None:
            from app.config.weather_targets import WeatherCityTarget
            return WeatherCityTarget(point.city, point.province, point.lat, point.lon)
        return resolve_weather_city_target(city)

    async def _prepare_history(self, cities, lat, lon, start, end):
        if self.history is None or not self.history.config.online_enabled:
            return None
        from app.services.weather_history import grid_point, coverage
        points = []
        for city in cities:
            target = self._resolve_city(city)
            if target is not None and target.era5_point is not None:
                points.append({"city": target.city, "lat": target.era5_lat, "lon": target.era5_lon})
        if not cities and lat is not None and lon is not None:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Invalid weather coordinates")
            points.append({"city": "coordinate", "lat": lat, "lon": lon})
        report = {"jobs": [], "warnings": []}
        from app.utils.weather_time import BEIJING
        last = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=1)
        last = min(last, datetime.now(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=1))
        end = min(end, last)
        if end < start:
            return report
        if len(points) > 100 or (end.date() - start.date()).days >= 366:
            report["warnings"].append({"code": "HISTORY_RANGE_LIMIT", "message": "自动补采最多100个点、366天，请分段查询。"})
            return report
        deadline = asyncio.get_running_loop().time() + 20
        small = len(points) <= 3 and (end.date() - start.date()).days < 7
        for point in points:
            grid_lat, grid_lon = grid_point(point["lat"], point["lon"])
            rows = await self.repo.get_weather_data(grid_lat, grid_lon, start, end)
            if not coverage(rows, start, end)["missing_hours"]:
                continue
            if small and asyncio.get_running_loop().time() < deadline:
                try:
                    async with asyncio.timeout_at(deadline):
                        result = await self.history.repair(grid_lat, grid_lon, start, end)
                    if not result["missing_hours"]:
                        continue
                except Exception as exc:
                    logger.warning("online_weather_repair_failed", city=point["city"], error=str(exc))
                    report["warnings"].append({"code": "ONLINE_HISTORY_INCOMPLETE", "message": f'{point["city"]}在线补采未完成，已转后台重试。'})
            job = self.history.submit([point], start, end)
            if job:
                report["jobs"].append({"city": point["city"], **job})
                report["warnings"].append({"code": "HISTORY_BACKFILL_PENDING" if job["state"] in {"pending", "running"} else "HISTORY_BACKFILL_INCOMPLETE",
                    "message": f'{point["city"]}边界层高度仍有缺口；补采状态：{job["state"]}。'})
        return report

    @staticmethod
    def _finish_history(result, backfill, cities, start, end):
        if backfill is None:
            return result
        from app.services.weather_history import expected_hours, valid_height
        result.setdefault("metadata", {})["history_backfill"] = backfill
        result.setdefault("warnings", []).extend(backfill["warnings"])
        if backfill["jobs"]:
            result["summary"] += "；补采进度见metadata.history_backfill.jobs，再次查询可检查结果"
        expected = set(expected_hours(start, end))
        valid_by_city = {city: {} for city in (cities or ["coordinate"])}
        for row in result.get("data", []):
            value = row.get("measurements", {}).get("boundary_layer_height", row.get("boundary_layer_height"))
            source = row.get("data_source", "legacy_unverified")
            if valid_height(value) and source != "legacy_unverified":
                hour = weather_query_time(row["timestamp"])
                if hour in expected:
                    key = row.get("city") if cities else "coordinate"
                    if key in valid_by_city:
                        valid_by_city[key][hour] = source
        common = set.intersection(*(set(hours) for hours in valid_by_city.values())) if valid_by_city else set()
        common = {hour for hour in common if len({hours[hour] for hours in valid_by_city.values()}) == 1}
        result["metadata"]["comparison_coverage"] = {
            "variable": "boundary_layer_height", "unit": "m", "spatial_scope": "city_representative_point" if cities else "grid_point",
            "expected_hours": len(expected), "common_valid_hours": len(common),
            "common_timestamps": [weather_output_time(hour) for hour in sorted(common)],
            "cities": {city: {"valid_hours": len(hours), "missing_hours": len(expected) - len(hours),
                       "missing_rate": (len(expected) - len(hours)) / len(expected) if expected else 0}
                       for city, hours in valid_by_city.items()},
        }
        if len(common) < len(expected):
            result["warnings"].append({"code": "BOUNDARY_LAYER_COVERAGE_PARTIAL", "message": "边界层对比存在缺失或来源不一致，请使用comparison_coverage中的共同有效小时；城市代表点不等于全市平均。"})
        if result["warnings"] and result.get("success"):
            result["status"] = "partial"
        return result

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
            target = self._resolve_city(requested_city)
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

        warnings = []
        saved_file_path = None
        if combined and context is not None:
            try:
                saved_file_path = context.save_data(data=combined, schema="weather")
            except Exception as exc:
                warnings.append({"code": "DATA_SAVE_FAILED", "message": "保存失败，完整数据已内联返回；不得声称已保存文件。"})
                logger.warning("city_weather_data_save_failed", error=str(exc))

        if combined:
            status = "partial" if unresolved_cities or no_data_cities else "success"
            summary = (
                f"[OK] 查询到 {len(resolved_cities)} 个城市的 {len(combined)} 条"
                "历史网格气象数据"
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

        summary += "；时间已为北京时间（+08:00），勿再加8小时；风速m/s；来源见data_source"

        return {
            "status": "partial" if warnings and combined else status,
            "success": bool(combined),
            "warnings": warnings,
            "data_complete": True,
            "record_count": len(combined),
            "returned_records": len(combined),
            "data_structure": weather_data_structure(len(combined), len(combined), False),
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
                    "start": weather_output_time(start_time),
                    "end": weather_output_time(end_time),
                },
                **weather_output_metadata(combined),
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
                "wind_speed_10m": record.wind_speed_10m / 3.6 if record.wind_speed_10m is not None else math.nan,
                "wind_direction_10m": record.wind_direction_10m if record.wind_direction_10m is not None else math.nan,
                "wind_gusts_10m": record.wind_gusts_10m / 3.6 if record.wind_gusts_10m is not None else math.nan,
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
                "timestamp": weather_output_time(record.timestamp),
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
        for output, stored in zip(standardized_records, data, strict=True):
            output["data_source"] = getattr(stored, "data_source", None) or "legacy_unverified"
            output["timezone"] = "Asia/Shanghai"
            output["units"] = WEATHER_UNITS.copy()
        standardized_records = [normalize_weather_record(record) for record in standardized_records]

        logger.info(
            "era5_data_standardized",
            original_count=len(records),
            standardized_count=len(standardized_records)
        )

        summary = f"[OK] 查询到 {len(standardized_records)} 条历史网格气象数据"
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
        summary += "；时间已为北京时间（+08:00），勿再加8小时；风速m/s；来源见data_source"

        # 【Context-Aware V2】使用 context.save_data() 保存数据
        warnings = []
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
                warnings.append({"code": "DATA_SAVE_FAILED", "message": "保存失败，完整数据已内联返回；不得声称已保存文件。"})
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
                "start": weather_output_time(start_time),
                "end": weather_output_time(end_time)
            },
            quality_score=0.9 if standardized_records else 0.0
        )

        # 【UDF v2.0】返回标准化数据
        return {
            "status": ("partial" if warnings else "success") if standardized_records else "empty",
            "success": len(standardized_records) > 0,
            "warnings": warnings,
            "error_code": None if standardized_records else "NO_DATA",
            "data_complete": True,
            "record_count": len(standardized_records),
            "returned_records": len(standardized_records),
            "data_structure": weather_data_structure(len(standardized_records), len(standardized_records), False),
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
                "sample_record": sample_record,  # ✅ 数据样本
                **weather_output_metadata(standardized_records),
            },
            "summary": summary
        }
