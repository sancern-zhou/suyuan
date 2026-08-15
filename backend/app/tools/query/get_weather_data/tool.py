"""
Get Weather Data Tool

LLM可调用的气象数据查询工具

功能：
- 查询指定位置和时间范围的历史气象数据
- 支持ERA5再分析数据
- 支持观测站数据
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.config.weather_targets import normalize_city_name, resolve_weather_city_target
from app.db.repositories.jiangsu_nmc_weather_repo import JiangsuNMCWeatherRepository
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
            "description": """查询历史气象数据（ERA5再分析数据或地面观测站数据）。

【调用规则 - 严格遵守】

1. data_type="era5"（推荐使用）：
   - 城市查询：提供 city 或 cities，工具内部解析城市代表点并查询ERA5网格
   - 精确查询：提供 lat, lon
   - 无需提供 station_id

2. data_type="observed"：
   - 城市查询：提供 city 或 cities，工具内部查询该市及下辖区县观测站
   - 江苏区县查询：提供 district 或 districts，工具内部解析对应观测站
   - 精确查询：提供 station_id
   - 不能用 lat/lon 替代观测站或城市

【禁止的调用方式】
- data_type="observed" 但只提供 lat/lon ❌
- data_type="era5" 但只提供 station_id ❌

【返回格式】
{
    "success": bool,              # 查询是否成功
    "file_path": string,            # 数据ID（下游工具通过 context.get_data() 获取）
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
                        "description": (
                            "数据类型：era5=ERA5再分析数据(城市或lat/lon) | "
                            "observed=观测站数据(城市、江苏区县或station_id)"
                        )
                    },
                    "lat": {
                        "type": "number",
                        "description": "纬度（ERA5精确查询使用，与lon配套）"
                    },
                    "lon": {
                        "type": "number",
                        "description": "经度（ERA5精确查询使用，与lat配套）"
                    },
                    "station_id": {
                        "type": "string",
                        "description": "气象站ID（观测数据精确查询使用，如'54511'）"
                    },
                    "city": {
                        "type": "string",
                        "description": (
                            "单个城市名称。工具内部解析ERA5代表点或观测站，"
                            "无需提供站点ID，如'南京市'"
                        )
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表；observed查询时工具内部批量解析各城市站点"
                    },
                    "district": {
                        "type": "string",
                        "description": "江苏区县名称，仅用于observed观测数据查询，如'江宁区'"
                    },
                    "districts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "江苏区县名称列表，仅用于observed观测数据批量查询"
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
            version="1.2.0"
        )

        # Context-Aware V2: 设置需要 context 参数
        self.requires_context = True

        self.repo = WeatherRepository()
        self.jiangsu_nmc_repo = JiangsuNMCWeatherRepository()

    async def execute(
        self,
        context,  # Context-Aware V2: ExecutionContext 对象
        data_type: str,
        start_time: str,
        end_time: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        station_id: Optional[str] = None,
        city: Optional[str] = None,
        cities: Optional[List[str]] = None,
        district: Optional[str] = None,
        districts: Optional[List[str]] = None,
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
            city: 单个城市名称，由工具内部解析查询目标
            cities: 城市名称列表，由工具内部批量解析查询目标
            district: 单个江苏区县名称，由工具内部解析查询目标
            districts: 江苏区县名称列表，由工具内部批量解析查询目标

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

            requested_cities = self._clean_cities(city=city, cities=cities)
            requested_districts = self._clean_districts(
                district=district,
                districts=districts,
            )
            if requested_districts:
                if data_type != "observed":
                    return self._area_query_failure(
                        data_type=data_type,
                        cities=requested_cities,
                        districts=requested_districts,
                        error="区县名称仅支持 observed 观测站数据查询",
                    )
                return await self._query_jiangsu_observed_areas(
                    context=context,
                    cities=requested_cities,
                    districts=requested_districts,
                    start_time=start_dt,
                    end_time=end_dt,
                )
            if requested_cities:
                if data_type == "observed" and self._is_jiangsu_project():
                    return await self._query_jiangsu_observed_areas(
                        context=context,
                        cities=requested_cities,
                        districts=[],
                        start_time=start_dt,
                        end_time=end_dt,
                    )
                return await self._query_by_cities(
                    context=context,
                    data_type=data_type,
                    cities=requested_cities,
                    start_time=start_dt,
                    end_time=end_dt,
                )

            if data_type == "era5":
                return await self._query_era5(context, lat, lon, start_dt, end_dt)
            elif data_type == "observed":
                return await self._query_observed(context, station_id, start_dt, end_dt)
            else:
                from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
                return UnifiedData(
                    status=DataStatus.FAILED,
                    success=False,
                    error=f"不支持的数据类型: {data_type}",
                    data=[],
                    metadata=DataMetadata(
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

    @staticmethod
    def _clean_districts(
        *,
        district: Optional[str],
        districts: Optional[List[str]],
    ) -> List[str]:
        values: List[str] = []
        if district:
            values.append(district)
        if isinstance(districts, str):
            values.append(districts)
        else:
            values.extend(districts or [])

        result: List[str] = []
        for value in values:
            normalized = str(value or "").strip().replace(" ", "")
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _is_jiangsu_project() -> bool:
        from config.settings import settings

        return settings.project_id == "jiangsu-ops"

    async def _query_by_cities(
        self,
        *,
        context,
        data_type: str,
        cities: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        if data_type == "era5":
            return await self._query_era5_cities(
                context, cities, start_time, end_time
            )
        if data_type == "observed":
            return await self._query_observed_cities(
                context, cities, start_time, end_time
            )
        return self._city_query_failure(
            data_type=data_type,
            cities=cities,
            error=f"不支持的数据类型: {data_type}",
        )

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
            data_type="era5",
            requested_cities=cities,
            results=results,
            unresolved_cities=unresolved,
            targets=targets,
            start_time=start_time,
            end_time=end_time,
        )

    async def _query_observed_cities(
        self,
        context,
        cities: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        db_stations = await self.repo.get_active_stations_by_cities(cities)
        results: List[Dict[str, Any]] = []
        unresolved: List[str] = []
        targets: List[Dict[str, Any]] = []

        for requested_city in cities:
            target = resolve_weather_city_target(requested_city)
            canonical_city = target.city if target else normalize_city_name(requested_city)
            stations: Dict[str, Dict[str, Any]] = {}

            if target:
                for station in target.observed_stations:
                    stations[station.station_id] = {
                        "station_id": station.station_id,
                        "station_name": station.station_name,
                        "lat": station.lat,
                        "lon": station.lon,
                        "provider": station.provider,
                    }

            for station in db_stations.get(normalize_city_name(requested_city), []):
                stations.setdefault(
                    station.station_id,
                    {
                        "station_id": station.station_id,
                        "station_name": station.station_name,
                        "lat": station.lat,
                        "lon": station.lon,
                        "provider": station.data_provider,
                    },
                )

            if not stations:
                unresolved.append(requested_city)
                continue

            city_results: List[Dict[str, Any]] = []
            for station in stations.values():
                result = await self._query_observed(
                    None,
                    station["station_id"],
                    start_time,
                    end_time,
                    city=canonical_city,
                )
                city_results.append(result)
                targets.append({"city": canonical_city, **station})

            results.append(
                {
                    "city": canonical_city,
                    "result": {
                        "data": [
                            record
                            for station_result in city_results
                            for record in station_result.get("data", [])
                        ]
                    },
                }
            )

        return self._combine_city_results(
            context=context,
            data_type="observed",
            requested_cities=cities,
            results=results,
            unresolved_cities=unresolved,
            targets=targets,
            start_time=start_time,
            end_time=end_time,
        )

    @staticmethod
    def _normalize_admin_name(value: Any) -> str:
        return str(value or "").strip().replace(" ", "").rstrip("省市区县")

    async def _query_jiangsu_observed_areas(
        self,
        *,
        context,
        cities: List[str],
        districts: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Query Jiangsu NMC observations using administrative names only."""
        targets = await self.jiangsu_nmc_repo.get_area_targets(
            city_names=cities,
            district_names=districts,
        )
        data = await self.jiangsu_nmc_repo.get_area_observed_data(
            city_names=cities,
            district_names=districts,
            start_time=start_time,
            end_time=end_time,
        )

        resolved_cities: List[str] = []
        unresolved_cities: List[str] = []
        for requested in cities:
            matching_names = [
                str(target["city_name"])
                for target in targets
                if self._normalize_admin_name(target.get("city_name"))
                == self._normalize_admin_name(requested)
            ]
            if matching_names:
                canonical = matching_names[0]
                if canonical not in resolved_cities:
                    resolved_cities.append(canonical)
            else:
                unresolved_cities.append(requested)

        resolved_districts: List[str] = []
        unresolved_districts: List[str] = []
        for requested in districts:
            matching_names = [
                str(target["district_name"])
                for target in targets
                if target.get("district_name")
                and self._normalize_admin_name(target.get("district_name"))
                == self._normalize_admin_name(requested)
            ]
            if matching_names:
                canonical = matching_names[0]
                if canonical not in resolved_districts:
                    resolved_districts.append(canonical)
            else:
                unresolved_districts.append(requested)

        raw_records = [
            {
                "timestamp": record.time,
                "station_name": record.nmc_location_name,
                "station_code": record.station_id,
                "province": record.province_name,
                "city": record.city_name,
                "city_code": record.city_code,
                "district": record.district_name,
                "district_code": record.district_code,
                "location_level": record.location_level,
                "temperature_2m": record.temperature_2m,
                "relative_humidity_2m": record.relative_humidity_2m,
                "wind_speed_10m": record.wind_speed_10m,
                "wind_direction_10m": record.wind_direction_10m,
                "surface_pressure": record.surface_pressure,
                "precipitation": record.precipitation,
                "data_source": record.data_source,
                "data_quality": record.data_quality,
            }
            for record in data
        ]
        standardized_records = get_data_standardizer().standardize(raw_records)

        station_ids = {str(target["station_id"]) for target in targets}
        city_station_ids = {
            str(target["station_id"])
            for target in targets
            if target.get("location_level") == "city"
        }
        district_station_ids = station_ids - city_station_ids

        no_data_cities = [
            city
            for city in resolved_cities
            if not any(
                self._normalize_admin_name(record.city_name)
                == self._normalize_admin_name(city)
                for record in data
            )
        ]
        no_data_districts = [
            district
            for district in resolved_districts
            if not any(
                self._normalize_admin_name(record.district_name)
                == self._normalize_admin_name(district)
                for record in data
            )
        ]

        saved_file_path = None
        if standardized_records and context is not None:
            try:
                saved_file_path = context.save_data(
                    data=standardized_records,
                    schema="weather",
                )
            except Exception as exc:
                logger.warning(
                    "jiangsu_observed_weather_data_save_failed",
                    error=str(exc),
                )

        record_count = len(standardized_records)
        inline_records = standardized_records
        sample_strategy = "all"
        if saved_file_path and record_count > 24:
            inline_records = [*standardized_records[:12], *standardized_records[-12:]]
            sample_strategy = "first_12_last_12"

        unresolved = unresolved_cities or unresolved_districts
        no_data = no_data_cities or no_data_districts
        if record_count:
            status = "partial" if unresolved or no_data else "success"
            summary = (
                f"[OK] 按行政区查询到 {len(station_ids)} 个 NMC 气象站的 "
                f"{record_count} 条观测数据"
            )
        elif targets:
            status = "empty"
            summary = "[WARN] 已解析行政区及气象站，但指定时段没有观测数据"
        else:
            status = "failed"
            summary = "[ERROR] 未找到所请求城市或区县的 NMC 气象站"
        if unresolved_cities:
            summary += f"；未解析城市：{', '.join(unresolved_cities)}"
        if unresolved_districts:
            summary += f"；未解析区县：{', '.join(unresolved_districts)}"
        if no_data_cities:
            summary += f"；无数据城市：{', '.join(no_data_cities)}"
        if no_data_districts:
            summary += f"；无数据区县：{', '.join(no_data_districts)}"

        return {
            "status": status,
            "success": bool(record_count),
            "data": inline_records,
            "file_path": saved_file_path,
            "data_complete": len(inline_records) == record_count,
            "record_count": record_count,
            "returned_records": len(inline_records),
            "sample_strategy": sample_strategy,
            "metadata": {
                "schema_version": "v2.0",
                "schema_type": "weather",
                "generator": "get_weather_data",
                "scenario": "weather_analysis",
                "weather_data_type": "observed",
                "source": "NMC",
                "requested_cities": cities,
                "requested_districts": districts,
                "resolved_cities": resolved_cities,
                "resolved_districts": resolved_districts,
                "unresolved_cities": unresolved_cities,
                "unresolved_districts": unresolved_districts,
                "no_data_cities": no_data_cities,
                "no_data_districts": no_data_districts,
                "station_count": len(station_ids),
                "city_station_count": len(city_station_ids),
                "district_station_count": len(district_station_ids),
                "record_count": record_count,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
            },
            "summary": summary,
        }

    def _combine_city_results(
        self,
        *,
        context,
        data_type: str,
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
                f"{data_type}气象数据"
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
                "weather_data_type": data_type,
                "record_count": len(combined),
                "source": "era5_reanalysis" if data_type == "era5" else "observed_station",
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

    @staticmethod
    def _city_query_failure(
        *, data_type: str, cities: List[str], error: str
    ) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": error,
            "data": [],
            "file_path": None,
            "metadata": {
                "schema_version": "v2.0",
                "schema_type": "weather",
                "generator": "get_weather_data",
                "weather_data_type": data_type,
                "requested_cities": cities,
            },
            "summary": f"[ERROR] {error}",
        }

    @staticmethod
    def _area_query_failure(
        *,
        data_type: str,
        cities: List[str],
        districts: List[str],
        error: str,
    ) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": error,
            "data": [],
            "file_path": None,
            "metadata": {
                "schema_version": "v2.0",
                "schema_type": "weather",
                "generator": "get_weather_data",
                "weather_data_type": data_type,
                "requested_cities": cities,
                "requested_districts": districts,
            },
            "summary": f"[ERROR] {error}",
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
            # 提取气象测量值，处理None值。
            # 缺失值必须保留为 None：NaN 不是合法 JSON，无法写入
            # PostgreSQL 的 json/jsonb transcript 字段。
            measurements = {
                "temperature_2m": record.temperature_2m,
                "relative_humidity_2m": record.relative_humidity_2m,
                "dew_point_2m": record.dew_point_2m,
                "wind_speed_10m": record.wind_speed_10m,
                "wind_direction_10m": record.wind_direction_10m,
                "wind_gusts_10m": record.wind_gusts_10m,
                "surface_pressure": record.surface_pressure,
                "precipitation": record.precipitation,
                "cloud_cover": record.cloud_cover,
                "shortwave_radiation": record.shortwave_radiation,
                "visibility": record.visibility,
                "boundary_layer_height": record.boundary_layer_height,
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

    async def _query_observed(
        self,
        context,
        station_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
        city: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询观测数据（统一格式）"""
        from app.schemas.unified import (
            UnifiedData, DataType, DataStatus, DataMetadata, UnifiedDataRecord
        )

        if not station_id:
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error="观测数据查询需要提供 city/cities 或 station_id 参数",
                data=[],
                metadata=DataMetadata(
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
            # 提取气象测量值，处理None值。保留 None，确保结果可安全
            # 序列化为标准 JSON 并写入 transcript。
            measurements = {
                "temperature_2m": record.temperature_2m,
                "relative_humidity_2m": record.relative_humidity_2m,
                "dew_point_2m": record.dew_point_2m,
                "wind_speed_10m": record.wind_speed_10m,
                "wind_direction_10m": record.wind_direction_10m,
                "surface_pressure": record.surface_pressure,
                "precipitation": record.precipitation,
                "cloud_cover": record.cloud_cover,
                "visibility": record.visibility,
            }

            records.append(UnifiedDataRecord(
                timestamp=record.time,
                station_name=record.station_name or station_id,
                lat=record.lat,
                lon=record.lon,
                measurements=measurements,
                dimensions={"city": city, "station_id": station_id},
            ))

        logger.info("observed_query_successful", records=len(records))

        # 【UDF v2.0】使用data_standardizer标准化数据
        # 将UnifiedDataRecord转换为字典进行标准化
        records_dict_list = []
        for record in records:
            record_dict = {
                "timestamp": record.timestamp,
                "station_name": record.station_name,
                "station_id": station_id,
                "city": city,
                "lat": record.lat,
                "lon": record.lon,
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

        # 构建元数据
        metadata = DataMetadata(
            data_type=DataType.WEATHER,
            record_count=len(standardized_records),
            station_name=station_id,
            city=city,
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
                    "observed_data_saved_to_context",
                    file_path=saved_file_path,
                    record_count=len(standardized_records)
                )
            except Exception as e:
                logger.warning(
                    "observed_data_save_failed",
                    error=str(e),
                    message="将继续使用本地file_path，但下游工具可能无法通过context获取数据"
                )

        final_file_path = saved_file_path

        if final_file_path:
            summary = f"{summary}，文件路径: {final_file_path}。"

        # 更新 metadata 中的 file_path
        metadata = DataMetadata(
            file_path=final_file_path,
            data_type=DataType.WEATHER,
            record_count=len(standardized_records),
            station_name=station_id,
            city=city,
            source="observed_station",
            time_range={
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            quality_score=0.9 if standardized_records else 0.0
        )

        sample_record = standardized_records[0] if standardized_records else None

        # 【UDF v2.0】返回标准化数据
        return {
            "status": "success",
            "success": len(standardized_records) > 0,
            "data": standardized_records,
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
