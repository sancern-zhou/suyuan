from app.fetchers.consultation import monthly_pollution_events_components as module


class FakeRegistry:
    def load_dataset(self, data_id):
        assert data_id == "air_quality_unified:v1:full"
        return [
            {"name": "广州", "timestamp": "2026-05-01 00:00:00", "measurements": {"AQI": 80}},
            {"name": "江门", "timestamp": "2026-05-30 00:00:00", "measurements": {"AQI": 137}},
        ]


def test_extract_records_prefers_full_registry_dataset_over_preview(monkeypatch):
    monkeypatch.setattr(module, "data_registry", FakeRegistry())
    generator = module.MonthlyPollutionEventsComponents.__new__(
        module.MonthlyPollutionEventsComponents
    )

    records = generator._extract_records(
        {
            "data_id": "air_quality_unified:v1:full",
            "data": [
                {
                    "name": "广州",
                    "timestamp": "2026-05-01 00:00:00",
                    "measurements": {"AQI": 80},
                }
            ],
            "metadata": {"total_records": 2, "returned_records": 1},
        }
    )

    assert len(records) == 2
    assert records[1]["name"] == "江门"


class FakeAsyncComponentTool:
    async def execute(self, **kwargs):
        return {"success": True, "data": [{"timestamp": kwargs["start_time"], "value": 1}]}


async def test_fetch_component_dataset_runs_inside_existing_event_loop():
    generator = module.MonthlyPollutionEventsComponents.__new__(
        module.MonthlyPollutionEventsComponents
    )
    generator.context = object()
    generator.vocs_tool = FakeAsyncComponentTool()

    rows = generator.fetch_component_dataset(
        {"city": "广州", "station": "广州", "date": "2026-05-01"},
        "vocs",
    )

    assert rows == [{"timestamp": "2026-05-01 00:00:00", "value": 1}]
