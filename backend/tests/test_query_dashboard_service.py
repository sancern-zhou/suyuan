from app.schemas.query_dashboard import (
    DashboardFocus,
    DashboardModule,
    DashboardOverviewResponse,
    DashboardSource,
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
