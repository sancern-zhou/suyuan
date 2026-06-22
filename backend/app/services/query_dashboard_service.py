from __future__ import annotations

from datetime import date, datetime, time
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
    realtime_start = datetime.combine(current, time.min, tzinfo=TZ).isoformat()
    realtime_end = datetime.combine(current, time.max, tzinfo=TZ).replace(microsecond=0).isoformat()

    return {
        "realtime": {"start": realtime_start, "end": realtime_end},
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
    ) -> None:
        self.provider = provider or GDSuncereDashboardProvider()
        self.today = today
        self.cities = cities or DEFAULT_GUANGDONG_CITIES

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
            return self._module_from_result(
                module_name,
                result,
                stations=records,
                heat_points=[record for record in records if record.get("lng") is not None and record.get("lat") is not None],
            )

        raise ValueError(f"Unsupported dashboard module: {module_name}")

    def _module_from_result(self, module_name: str, result: dict[str, Any], **payload: Any) -> DashboardModule:
        records = _records_from_result(result)
        source = extract_dashboard_source(f"src_{module_name}", TOOL_NAME, result)
        return DashboardModule(
            status="success",
            summary={"record_count": source.record_count or len(records)},
            sources=[source],
            **payload,
        )
