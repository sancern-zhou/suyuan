from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.query_dashboard import (
    DashboardModule,
    DashboardOverviewResponse,
    DashboardSource,
)


DEFAULT_GUANGDONG_CITIES = [
    "广州",
    "深圳",
    "珠海",
    "汕头",
    "佛山",
    "韶关",
    "河源",
    "梅州",
    "惠州",
    "汕尾",
    "东莞",
    "中山",
    "江门",
    "阳江",
    "湛江",
    "茂名",
    "肇庆",
    "清远",
    "潮州",
    "揭阳",
    "云浮",
]
DEFAULT_MODULES = ["realtime", "month_to_date", "year_to_date", "layers"]
TOOL_NAME = "query_gd_suncere"
TZ = ZoneInfo("Asia/Shanghai")


class QueryDashboardProvider(Protocol):
    def city_hour(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def city_day(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def station_hour(self, **kwargs: Any) -> dict[str, Any]:
        ...


def _now() -> datetime:
    return datetime.now(TZ)


def build_default_date_ranges(today: date | None = None) -> dict[str, dict[str, str]]:
    current = today or _now().date()
    current_day = current.isoformat()

    return {
        "realtime": {"start": f"{current_day} 00:00:00", "end": f"{current_day} 23:59:59"},
        "month_to_date": {
            "start": current.replace(day=1).isoformat(),
            "end": current.isoformat(),
        },
        "year_to_date": {
            "start": current.replace(month=1, day=1).isoformat(),
            "end": current.isoformat(),
        },
    }


def _records_from_result(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [record for record in result if isinstance(record, dict)]

    if not isinstance(result, dict):
        return []

    data = result.get("data")
    if isinstance(data, list):
        return [record for record in data if isinstance(record, dict)]

    if isinstance(data, dict):
        for key in ("records", "items", "rows", "data"):
            records = data.get(key)
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]

    for key in ("records", "items", "rows"):
        records = result.get(key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]

    return []


def _metadata(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _first_count(*values: Any) -> int | None:
    for value in values:
        if value is not None:
            return value
    return None


def _error_message(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("error")
        if message:
            return str(message)
    if error:
        return str(error)
    return "查询工具返回失败"


def _ensure_successful_tool_result(result: dict[str, Any]) -> None:
    records = _records_from_result(result)
    status = str(result.get("status", "")).lower()
    has_error_without_data = bool(result.get("error")) and not records

    if result.get("success") is False or status in {"error", "failed"} or has_error_without_data:
        raise RuntimeError(_error_message(result.get("error") or result.get("message")))


def extract_dashboard_source(source_id: str, tool_name: str, result: dict[str, Any]) -> DashboardSource:
    records = _records_from_result(result)
    metadata = _metadata(result)
    query_params = metadata.get("query_params") if isinstance(metadata.get("query_params"), dict) else {}
    data_ids = result.get("data_ids") or metadata.get("data_ids") or []
    if isinstance(data_ids, str):
        data_ids = [data_ids]
    record_count = _first_count(
        result.get("total_count"),
        result.get("record_count"),
        result.get("total_records"),
        metadata.get("total_count"),
        metadata.get("record_count"),
        metadata.get("total_records"),
    )

    return DashboardSource(
        source_id=source_id,
        tool_name=tool_name,
        data_id=result.get("data_id") or metadata.get("data_id"),
        data_ids=[data_id for data_id in data_ids if isinstance(data_id, str)],
        query_params=query_params,
        record_count=record_count if record_count is not None else len(records),
        updated_at=result.get("updated_at") or metadata.get("updated_at"),
        generated_at=result.get("generated_at") or metadata.get("generated_at"),
        sample_records=records[:10],
    )


class GDSuncereDashboardProvider:
    def __init__(self, context: Any | None = None) -> None:
        self.context = context or self._create_context()

    def city_hour(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.query.query_gd_suncere.tool import execute_query_gd_suncere_station_hour

        result = execute_query_gd_suncere_station_hour(
            cities=kwargs["cities"],
            start_time=kwargs["start_time"],
            end_time=kwargs["end_time"],
            context=self.context,
            include_weather=kwargs.get("include_weather", True),
            ns_type=kwargs.get("ns_type", 2),
            skip_count=kwargs.get("skip_count", 0),
            max_result_count=kwargs.get("max_result_count", 1000),
        )
        self._merge_query_params(result, kwargs)
        return result

    def city_day(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.query.query_gd_suncere.tool import execute_query_gd_suncere_city_day

        result = execute_query_gd_suncere_city_day(
            cities=kwargs["cities"],
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            context=self.context,
            data_type=kwargs.get("data_type"),
            sand_type=kwargs.get("sand_type", 1),
            ns_type=kwargs.get("ns_type", 2),
            cal_area_type=kwargs.get("cal_area_type", 0),
            skip_count=kwargs.get("skip_count", 0),
            max_result_count=kwargs.get("max_result_count", 1000),
        )
        self._merge_query_params(result, kwargs)
        return result

    def station_hour(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.query.query_gd_suncere.tool import execute_query_gd_suncere_station_hour_real

        result = execute_query_gd_suncere_station_hour_real(
            start_time=kwargs["start_time"],
            end_time=kwargs["end_time"],
            context=self.context,
            cities=kwargs.get("cities"),
            stations=kwargs.get("stations"),
            station_type=kwargs.get("station_type"),
            include_weather=kwargs.get("include_weather", True),
            data_type=kwargs.get("data_type"),
            ns_type=kwargs.get("ns_type", 2),
            skip_count=kwargs.get("skip_count", 0),
            max_result_count=kwargs.get("max_result_count", 1000),
        )
        self._merge_query_params(result, kwargs)
        return result

    def _create_context(self) -> Any:
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        session_id = f"query_dashboard_{uuid4().hex[:8]}"
        data_manager = DataContextManager(HybridMemoryManager(session_id=session_id))
        return ExecutionContext(session_id=session_id, iteration=0, data_manager=data_manager)

    @staticmethod
    def _merge_query_params(result: dict[str, Any], query_params: dict[str, Any]) -> None:
        metadata = result.setdefault("metadata", {})
        if isinstance(metadata, dict):
            existing = metadata.get("query_params")
            metadata["query_params"] = {
                **(existing if isinstance(existing, dict) else {}),
                **query_params,
            }


class QueryDashboardService:
    def __init__(
        self,
        provider: QueryDashboardProvider | None = None,
        today: date | None = None,
        cities: list[str] | None = None,
        station_index: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.provider = provider or GDSuncereDashboardProvider()
        self.today = today
        self.cities = cities or DEFAULT_GUANGDONG_CITIES
        self.station_index = station_index if station_index is not None else self._load_station_index()

    def build_guangdong_overview(self, include: list[str] | None = None) -> DashboardOverviewResponse:
        requested_modules = include or DEFAULT_MODULES
        ranges = build_default_date_ranges(today=self.today)
        generated_at = _now().isoformat()
        modules: dict[str, DashboardModule] = {}
        sources: list[DashboardSource] = []
        errors: list[dict[str, Any]] = []

        for module_name in requested_modules:
            try:
                module = self._build_module(module_name, ranges)
            except Exception as exc:
                error = {"module": module_name, "message": str(exc)}
                module = DashboardModule(status="error", error={"message": str(exc)})
                errors.append(error)

            modules[module_name] = module
            sources.extend(module.sources)

        return DashboardOverviewResponse(
            success=any(module.status == "success" for module in modules.values()),
            generated_at=generated_at,
            region="广东省",
            modules=modules,
            sources=sources,
            errors=errors,
        )

    def _build_module(self, module_name: str, ranges: dict[str, dict[str, str]]) -> DashboardModule:
        if module_name == "realtime":
            result = self.provider.city_hour(
                label=module_name,
                cities=self.cities,
                start_time=ranges["realtime"]["start"],
                end_time=ranges["realtime"]["end"],
            )
            return self._module_from_result(module_name, result, cities=_records_from_result(result))

        if module_name in {"month_to_date", "year_to_date"}:
            range_ = ranges[module_name]
            result = self.provider.city_day(
                label=module_name,
                cities=self.cities,
                start_date=range_["start"],
                end_date=range_["end"],
            )
            records = _records_from_result(result)
            return self._module_from_result(module_name, result, cities=records, city_metrics=records)

        if module_name == "layers":
            result = self.provider.station_hour(
                label=module_name,
                cities=self.cities,
                start_time=ranges["realtime"]["start"],
                end_time=ranges["realtime"]["end"],
            )
            records = _records_from_result(result)
            stations = self._enrich_station_records(records)
            return self._module_from_result(
                module_name,
                result,
                stations=stations,
                heat_points=self._heat_points_from_stations(stations),
            )

        raise ValueError(f"Unsupported dashboard module: {module_name}")

    def _module_from_result(self, module_name: str, result: dict[str, Any], **payload: Any) -> DashboardModule:
        _ensure_successful_tool_result(result)
        records = _records_from_result(result)
        source = extract_dashboard_source(f"src_{module_name}", TOOL_NAME, result)
        return DashboardModule(
            status="success",
            summary={"record_count": source.record_count or len(records)},
            sources=[source],
            **payload,
        )

    @staticmethod
    def _load_station_index() -> dict[str, dict[str, Any]]:
        try:
            from app.utils.geo_matcher import GeoMatcher

            return GeoMatcher().station_index
        except Exception:
            return {}

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _station_lookup(self, record: dict[str, Any]) -> dict[str, Any]:
        for key in ("station_name", "name", "站点名称", "站点"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                station = self.station_index.get(value.strip())
                if station:
                    return station
        return {}

    def _enrich_station_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched = []
        for record in records:
            station = self._station_lookup(record)
            lng = self._number(
                record.get("lng")
                or record.get("lon")
                or record.get("longitude")
                or record.get("经度")
                or station.get("longitude")
                or station.get("lng")
            )
            lat = self._number(
                record.get("lat")
                or record.get("latitude")
                or record.get("纬度")
                or station.get("latitude")
                or station.get("lat")
            )
            next_record = dict(record)
            if lng is not None:
                next_record["lng"] = lng
                next_record["longitude"] = lng
            if lat is not None:
                next_record["lat"] = lat
                next_record["latitude"] = lat
            if station.get("city") and not next_record.get("city"):
                next_record["city"] = station["city"]
            enriched.append(next_record)
        return enriched

    def _heat_points_from_stations(self, stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points = []
        for station in stations:
            lng = self._number(station.get("lng") or station.get("longitude"))
            lat = self._number(station.get("lat") or station.get("latitude"))
            if lng is None or lat is None:
                continue

            measurements = station.get("measurements") if isinstance(station.get("measurements"), dict) else {}
            value = self._number(station.get("AQI") or station.get("aqi") or measurements.get("AQI"))
            points.append(
                {
                    "lng": lng,
                    "lat": lat,
                    "value": value if value is not None else 0,
                    "name": station.get("station_name") or station.get("name") or station.get("站点名称") or "",
                }
            )
        return points
