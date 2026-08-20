from app.tools.jiangsu.result_filter import (
    INLINE_RECORD_LIMIT,
    compact_air_quality_records,
    compact_statistics_records,
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


def test_result_filter_keeps_unknown_metric_fields_and_rejects_admin_columns():
    """Reject-list behaviour: only admin/audit columns are dropped, every other
    field with a real value — including metrics absent from any allow-list such
    as per-pollutant IAQI breakdowns — must survive."""
    records = [
        {
            "name": "江宁区",
            "timePoint": "2026-08-18T00:00:00",
            "aqi": "113",
            "o3_8H_IAQI": "113",
            "pM2_5_IAQI": "32",
            "visibility": "8500",
            "id": "f0f0",
            "createTime": "2026-08-19 06:00:00",
            "modifyTime": "2026-08-19 06:00:00",
            "calAreaType": 2,
            "o3_8H_Mark": "有效",
        }
    ]

    compact, _ = compact_air_quality_records(records)

    assert compact == [
        {
            "name": "江宁区",
            "timePoint": "2026-08-18T00:00:00",
            "aqi": "113",
            "o3_8H_IAQI": "113",
            "pM2_5_IAQI": "32",
            "visibility": "8500",
        }
    ]


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


def test_compact_statistics_records_keeps_per_metric_holder_names():
    records = [
        {
            "dateTimeString": "2026-08-17～2026-08-17",
            "pM2_5_CityName": "南京市",
            "pM2_5_DistrictName": "玄武区",
            "pM2_5": "35",
            "pM2_5_Rank": "3",
            "pM2_5_SameCompare": "—",
            "pM2_5_SameCompare_Rank": "—",
            "pM2_5_SameCompare_CityName": "南京市",
            "pM2_5_SameCompare_DistrictName": "玄武区",
            "o3_8h_CityName": "南京市",
            "o3_8h_DistrictName": "玄武区",
            "o3_8h": "160",
            "o3_8h_Rank": "1",
            "o3_8h_SameCompare": "-5.2",
            "o3_8h_SameCompare_Rank": "2",
            "overDay_CityName": "南京市",
            "overDay_DistrictName": "玄武区",
            "overDay": "—",
            "overDay_Rank": "—",
        },
        {"dateTimeString": "2026-08-17～2026-08-17", "pM2_5_CityName": "南京市", "pM2_5_DistrictName": "秦淮区", "pM2_5": "—", "pM2_5_Rank": "—"},
    ]

    compact, metadata = compact_statistics_records(records)

    assert compact == [
        {
            "time_range": "2026-08-17～2026-08-17",
            "metrics": {
                "pM2_5": {
                    "city_name": "南京市",
                    "district_name": "玄武区",
                    "value": "35",
                    "rank": "3",
                    "same_compare_city_name": "南京市",
                    "same_compare_district_name": "玄武区",
                },
                "o3_8h": {
                    "city_name": "南京市",
                    "district_name": "玄武区",
                    "value": "160",
                    "rank": "1",
                    "same_compare": "-5.2",
                    "same_compare_rank": "2",
                },
            },
        }
    ]
    assert metadata["raw_record_count"] == 2
    assert metadata["compacted_record_count"] == 1
    assert metadata["no_data_names"] == ["秦淮区"]
    assert metadata["removed_empty_field_count"] >= 6


def test_compact_statistics_records_does_not_mix_metric_holders_within_slot():
    """Regression: source rows are rank slots; each metric names its own holder.

    Seen on the live district_rank API: fineRate_DistrictName sorts before
    pM2_5_DistrictName and points at a different district.  Attributing the
    whole row to the first name column swaps PM2.5 values between districts.
    """
    records = [
        {
            "dateTimeString": "2026-08-18～2026-08-18",
            "fineRate_CityName": "南京市",
            "fineRate_DistrictName": "江宁区",
            "fineRate": "0",
            "fineRate_Rank": "1",
            "pM2_5_CityName": "南京市",
            "pM2_5_DistrictName": "溧水区",
            "pM2_5": "17",
            "pM2_5_Rank": "1",
            "pM2_5_SameCompare": "90",
            "pM2_5_SameCompare_Rank": "1",
            "pM2_5_SameCompare_CityName": "南京市",
            "pM2_5_SameCompare_DistrictName": "高淳区",
            "o3_8h_CityName": "南京市",
            "o3_8h_DistrictName": "高淳区",
            "o3_8h": "151",
            "o3_8h_Rank": "1",
        },
        {
            "dateTimeString": "2026-08-18～2026-08-18",
            "fineRate_CityName": "南京市",
            "fineRate_DistrictName": "溧水区",
            "fineRate": "100",
            "fineRate_Rank": "2",
            "pM2_5_CityName": "南京市",
            "pM2_5_DistrictName": "江宁区",
            "pM2_5": "22",
            "pM2_5_Rank": "3",
        },
    ]

    compact, _ = compact_statistics_records(records)

    assert compact[0]["metrics"]["pM2_5"]["district_name"] == "溧水区"
    assert compact[0]["metrics"]["pM2_5"]["value"] == "17"
    assert compact[0]["metrics"]["pM2_5"]["same_compare_district_name"] == "高淳区"
    assert compact[0]["metrics"]["fineRate"]["district_name"] == "江宁区"
    assert compact[0]["metrics"]["o3_8h"]["district_name"] == "高淳区"
    assert compact[1]["metrics"]["pM2_5"]["district_name"] == "江宁区"
    assert compact[1]["metrics"]["pM2_5"]["value"] == "22"
    assert compact[1]["metrics"]["fineRate"]["district_name"] == "溧水区"
    # no row-level district_name may exist: it would imply one holder per row
    assert "district_name" not in compact[0]
    assert "district_name" not in compact[1]


def test_compact_statistics_records_collapses_station_name_blocks():
    records = [
        {
            "dateTimeString": "2026-08-17～2026-08-17",
            "aqi_StationName": "南京站",
            "aqi": "52",
            "aqi_Rank": "5",
        }
    ]

    compact, _ = compact_statistics_records(records)

    assert compact == [
        {
            "time_range": "2026-08-17～2026-08-17",
            "metrics": {"aqi": {"station_name": "南京站", "value": "52", "rank": "5"}},
        }
    ]


def test_compact_statistics_records_keeps_unknown_fields_at_row_level():
    records = [{"transferRate": "98.6", "stationName": "备用站点", "auditFlag": "—"}]

    compact, metadata = compact_statistics_records(records)

    assert compact == [{"transferRate": "98.6", "stationName": "备用站点"}]
    assert metadata["removed_empty_field_count"] == 1
