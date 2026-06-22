from app.schemas.query_dashboard import (
    DashboardFocus,
    DashboardModule,
    DashboardOverviewResponse,
    DashboardSource,
)
from datetime import date

from app.services.query_dashboard_service import (
    GDSuncereDashboardProvider,
    QueryDashboardService,
    build_default_date_ranges,
    extract_dashboard_source,
)


def test_dashboard_overview_response_accepts_partial_modules():
    response = DashboardOverviewResponse(
        generated_at="2026-06-22T10:00:00+08:00",
        region="广东省",
        modules={
            "realtime": DashboardModule(
                status="success",
                summary={"AQI": 42},
                cities=[{"city": "广州", "AQI": 42}],
                sources=[
                    DashboardSource(
                        source_id="src_001",
                        tool_name="query_gd_suncere",
                        data_id="air_quality_unified:v1:abc",
                        query_params={"cities": ["广州"]},
                        record_count=1,
                        updated_at="2026-06-22T09:55:00+08:00",
                    )
                ],
            ),
            "year_to_date": DashboardModule(
                status="error",
                error={"message": "查询超时", "impact": "全年累计模块暂不可验证"},
            ),
        },
    )

    payload = response.model_dump()
    assert payload["success"] is True
    assert payload["modules"]["realtime"]["status"] == "success"
    assert payload["modules"]["year_to_date"]["status"] == "error"
    assert payload["modules"]["realtime"]["sources"][0]["data_id"] == "air_quality_unified:v1:abc"


def test_dashboard_focus_defaults_to_empty_lists():
    focus = DashboardFocus(scope="province")

    assert focus.scope == "province"
    assert focus.cities == []
    assert focus.stations == []
    assert focus.pollutants == []
    assert focus.source_data_ids == []


def test_build_default_date_ranges_uses_current_month_and_year():
    ranges = build_default_date_ranges(today=date(2026, 6, 22))

    assert ranges["realtime"] == {"start": "2026-06-22 00:00:00", "end": "2026-06-22 23:59:59"}
    assert ranges["month_to_date"] == {"start": "2026-06-01", "end": "2026-06-22"}
    assert ranges["year_to_date"] == {"start": "2026-01-01", "end": "2026-06-22"}


def test_extract_dashboard_source_reads_tool_result_metadata():
    result = {
        "data_id": "air_quality_unified:v1:abc",
        "total_count": 21,
        "metadata": {"query_params": {"cities": ["广州"]}},
        "data": [{"city": "广州", "AQI": 42}],
    }

    source = extract_dashboard_source("src_realtime", "query_gd_suncere", result)

    assert source.source_id == "src_realtime"
    assert source.tool_name == "query_gd_suncere"
    assert source.data_id == "air_quality_unified:v1:abc"
    assert source.record_count == 21
    assert source.query_params == {"cities": ["广州"]}
    assert source.sample_records == [{"city": "广州", "AQI": 42}]


def test_extract_dashboard_source_prefers_metadata_total_records_over_sample_length():
    result = {
        "data_id": "air_quality_unified:v1:externalized",
        "metadata": {
            "query_params": {"cities": ["广州"]},
            "total_records": 128,
        },
        "data": [{"city": "广州", "AQI": 42}],
    }

    source = extract_dashboard_source("src_realtime", "query_gd_suncere", result)

    assert source.record_count == 128


def test_real_provider_preserves_query_params_for_realtime_and_layers(monkeypatch):
    captured = {}

    def fake_city_hour(**kwargs):
        captured["city_hour"] = kwargs
        return {
            "success": True,
            "data_id": "air_quality_5min:v1:realtime",
            "metadata": {},
            "data": [],
        }

    def fake_station_hour_real(**kwargs):
        captured["station_hour"] = kwargs
        return {
            "success": True,
            "data_id": "air_quality_5min:v1:layers",
            "metadata": {},
            "data": [],
        }

    monkeypatch.setattr(
        "app.tools.query.query_gd_suncere.tool.execute_query_gd_suncere_station_hour",
        fake_city_hour,
    )
    monkeypatch.setattr(
        "app.tools.query.query_gd_suncere.tool.execute_query_gd_suncere_station_hour_real",
        fake_station_hour_real,
    )
    provider = GDSuncereDashboardProvider(context=object())

    realtime = provider.city_hour(label="realtime", cities=["广州"], start_time="2026-06-22T00:00:00+08:00", end_time="2026-06-22T23:59:59+08:00")
    layers = provider.station_hour(label="layers", cities=["广州"], start_time="2026-06-22T00:00:00+08:00", end_time="2026-06-22T23:59:59+08:00")

    assert realtime["metadata"]["query_params"]["label"] == "realtime"
    assert realtime["metadata"]["query_params"]["cities"] == ["广州"]
    assert layers["metadata"]["query_params"]["label"] == "layers"
    assert layers["metadata"]["query_params"]["cities"] == ["广州"]
    assert captured["city_hour"]["context"] is provider.context
    assert captured["station_hour"]["context"] is provider.context


class StubProvider:
    def __init__(self):
        self.calls = []

    def city_hour(self, **kwargs):
        self.calls.append(("city_hour", kwargs))
        return {
            "success": True,
            "data_id": "air_quality_5min:v1:realtime",
            "total_count": 1,
            "data": [{"city": "广州", "AQI": 42, "PM2_5": 18}],
            "metadata": {"query_params": kwargs},
        }

    def city_day(self, **kwargs):
        self.calls.append(("city_day", kwargs))
        return {
            "success": True,
            "data_id": f"air_quality_unified:v1:{kwargs['label']}",
            "total_count": 1,
            "data": [{"city": "广州", "PM2_5": 18, "O3_8h": 122}],
            "metadata": {"query_params": kwargs},
        }

    def station_hour(self, **kwargs):
        self.calls.append(("station_hour", kwargs))
        return {
            "success": True,
            "data_id": "air_quality_5min:v1:stations",
            "total_count": 1,
            "data": [{"station_name": "麓湖", "city": "广州", "lng": 113.29, "lat": 23.15, "AQI": 42}],
            "metadata": {"query_params": kwargs},
        }


def test_build_overview_returns_successful_modules_from_existing_tool_provider():
    provider = StubProvider()
    service = QueryDashboardService(provider=provider, today=date(2026, 6, 22))

    response = service.build_guangdong_overview(include=["realtime", "month_to_date", "year_to_date", "layers"])

    assert response.modules["realtime"].status == "success"
    assert response.modules["month_to_date"].status == "success"
    assert response.modules["year_to_date"].status == "success"
    assert response.modules["layers"].status == "success"
    assert response.modules["layers"].stations[0]["station_name"] == "麓湖"
    assert response.sources[0].tool_name == "query_gd_suncere"
    assert ("city_hour", provider.calls[0][1]) in provider.calls


def test_layers_enrich_station_coordinates_and_heat_points():
    class StationWithoutCoordinatesProvider(StubProvider):
        def station_hour(self, **kwargs):
            return {
                "success": True,
                "data_id": "air_quality_5min:v1:stations",
                "total_count": 1,
                "data": [{"station_name": "麓湖", "AQI": 42}],
                "metadata": {"query_params": kwargs},
            }

    service = QueryDashboardService(
        provider=StationWithoutCoordinatesProvider(),
        today=date(2026, 6, 22),
        station_index={"麓湖": {"longitude": 113.292, "latitude": 23.151}},
    )

    response = service.build_guangdong_overview(include=["layers"])

    station = response.modules["layers"].stations[0]
    assert station["lng"] == 113.292
    assert station["lat"] == 23.151
    assert response.modules["layers"].heat_points == [
        {"lng": 113.292, "lat": 23.151, "value": 42, "name": "麓湖"}
    ]


def test_build_overview_keeps_partial_success_when_module_fails():
    class FailingProvider(StubProvider):
        def city_day(self, **kwargs):
            if kwargs["label"] == "year_to_date":
                raise RuntimeError("统计接口超时")
            return super().city_day(**kwargs)

    service = QueryDashboardService(provider=FailingProvider(), today=date(2026, 6, 22))

    response = service.build_guangdong_overview(include=["realtime", "month_to_date", "year_to_date"])

    assert response.success is True
    assert response.modules["realtime"].status == "success"
    assert response.modules["month_to_date"].status == "success"
    assert response.modules["year_to_date"].status == "error"
    assert response.modules["year_to_date"].error["message"] == "统计接口超时"
    assert response.errors[0]["module"] == "year_to_date"


def test_build_overview_treats_returned_failure_payload_as_module_error():
    class FailurePayloadProvider(StubProvider):
        def city_day(self, **kwargs):
            if kwargs["label"] == "month_to_date":
                return {
                    "success": False,
                    "status": "failed",
                    "error": {"message": "接口返回失败"},
                    "data": [],
                    "metadata": {"query_params": kwargs},
                }
            return super().city_day(**kwargs)

    service = QueryDashboardService(provider=FailurePayloadProvider(), today=date(2026, 6, 22))

    response = service.build_guangdong_overview(include=["realtime", "month_to_date", "year_to_date"])

    assert response.success is True
    assert response.modules["realtime"].status == "success"
    assert response.modules["month_to_date"].status == "error"
    assert response.modules["month_to_date"].error["message"] == "接口返回失败"
    assert response.modules["year_to_date"].status == "success"
    assert response.errors[0]["module"] == "month_to_date"
