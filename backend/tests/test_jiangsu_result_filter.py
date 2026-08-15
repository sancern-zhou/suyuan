from app.tools.jiangsu.result_filter import (
    INLINE_RECORD_LIMIT,
    compact_air_quality_records,
    externalize_compact_records,
)


def test_result_filter_removes_empty_fields_and_exact_duplicates_but_keeps_time_series():
    records = [
        {"name": "南京市", "code": "320100", "timePoint": "2026-08-12T01:00:00", "aqi": "20", "humidity": "—", "visibility": "-99.000", "id": 1},
        {"name": "南京市", "code": "320100", "timePoint": "2026-08-12T01:00:00", "aqi": "20", "humidity": "—", "visibility": "-99.000", "id": 2},
        {"name": "南京市", "code": "320100", "timePoint": "2026-08-12T02:00:00", "aqi": "25", "primaryPollutant": "", "pM2_5": "8"},
        {"name": "无锡市", "code": "320200", "timePoint": "2026-08-12T02:00:00", "aqi": "16", "qualityType": "优"},
    ]

    compact, metadata = compact_air_quality_records(records)

    assert compact == [
        {"name": "南京市", "code": "320100", "timePoint": "2026-08-12T01:00:00", "aqi": "20"},
        {"name": "南京市", "code": "320100", "timePoint": "2026-08-12T02:00:00", "aqi": "25", "pM2_5": "8"},
        {"name": "无锡市", "code": "320200", "timePoint": "2026-08-12T02:00:00", "aqi": "16", "qualityType": "优"},
    ]
    assert metadata["raw_record_count"] == 4
    assert metadata["duplicate_record_count"] == 1
    assert metadata["removed_empty_field_count"] >= 3


def test_result_filter_does_not_collapse_one_city_hour_series_to_latest_record():
    records = [
        {
            "name": "南京市",
            "code": "320100",
            "timePoint": f"2026-08-12T{hour:02d}:00:00",
            "aqi": str(20 + hour),
        }
        for hour in range(24)
    ]

    compact, metadata = compact_air_quality_records(records)

    assert compact == records
    assert metadata["raw_record_count"] == 24
    assert metadata["deduplicated_record_count"] == 24
    assert metadata["duplicate_record_count"] == 0


class _FakeContext:
    def __init__(self):
        self.saved = []

    def save_data(self, *, data, schema, metadata):
        self.saved.append({"data": data, "schema": schema, "metadata": metadata})
        return f"backend/backend_data_registry/sessions/test/data/{schema}.json"


def test_externalizes_filtered_result_over_inline_limit():
    records = [{"name": f"站点{index}", "stationCode": str(index), "aqi": str(index)} for index in range(25)]
    context = _FakeContext()

    preview, file_path, state = externalize_compact_records(
        records, context=context, schema="jiangsu_station_hour_latest", metadata={"source_tool": "test"}
    )

    assert len(preview) == INLINE_RECORD_LIMIT
    assert file_path and file_path.endswith("jiangsu_station_hour_latest.json")
    assert state["externalized"] is True
    assert state["data_complete"] is False
    assert state["record_count"] == 25
    assert state["returned_records"] == INLINE_RECORD_LIMIT
    assert state["sample_strategy"] == "head_tail"
    assert len(context.saved) == 1
    assert len(context.saved[0]["data"]) == 25
