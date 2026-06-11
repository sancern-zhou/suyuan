import pytest

from app.tools.query.city_pollutant_rankings.tool import (
    build_city_pollutant_rankings,
    _records_from_data_id,
)


def test_low_pm10_uses_full_tie_break_chain():
    records = [
        {"city": "汕尾", "pM10": 30, "fineRate": "98.0", "pM2_5_Decimal": "19.7", "o3_8h": 137, "nO2": 10},
        {"city": "河源", "pM10": 31, "fineRate": "100", "pM2_5_Decimal": "21.9", "o3_8h": 122, "nO2": 11},
        {"city": "梅州", "pM10": 31, "fineRate": "100", "pM2_5_Decimal": "20.9", "o3_8h": 111, "nO2": 12},
        {"city": "中山", "pM10": 33, "fineRate": "88.7", "pM2_5_Decimal": "21.4", "o3_8h": 156, "nO2": 13},
        {"city": "深圳", "pM10": 34, "fineRate": "95.4", "pM2_5_Decimal": "19.2", "o3_8h": 141, "nO2": 14},
        {"city": "珠海", "pM10": 34, "fineRate": "93.4", "pM2_5_Decimal": "20.5", "o3_8h": 143, "nO2": 15},
    ]

    result = build_city_pollutant_rankings(records, pollutants=["PM10"], top_n=5)

    low_cities = [row["city"] for row in result["rankings"]["PM10"]["low"]]
    assert low_cities == ["汕尾", "梅州", "河源", "中山", "深圳"]
    assert result["rankings"]["PM10"]["low"][1]["tie_break_values"]["PM2.5"] == 20.9


def test_high_o3_reverses_tie_break_direction_and_skips_main_pollutant():
    records = [
        {"city": "甲市", "o3_8h": 170, "fineRate": 90, "pM2_5_Decimal": 20, "nO2": 18, "pM10": 35},
        {"city": "乙市", "o3_8h": 170, "fineRate": 90, "pM2_5_Decimal": 24, "nO2": 15, "pM10": 30},
        {"city": "丙市", "o3_8h": 170, "fineRate": 95, "pM2_5_Decimal": 30, "nO2": 40, "pM10": 60},
        {"city": "丁市", "o3_8h": 160, "fineRate": 50, "pM2_5_Decimal": 99, "nO2": 99, "pM10": 99},
    ]

    result = build_city_pollutant_rankings(records, pollutants=["O3"], top_n=3)

    high = result["rankings"]["O3"]["high"]
    assert [row["city"] for row in high] == ["乙市", "甲市", "丙市"]
    assert [item["field"] for item in result["ranking_keys"]["O3"]] == [
        "O3",
        "AQI达标率",
        "PM2.5",
        "NO2",
        "PM10",
        "城市",
    ]


def test_air_quality_good_and_poor_rankings_use_aqi_rate_with_tie_breaks():
    records = [
        {"city": "梅州", "fineRate": 100, "pM2_5_Decimal": 20.9, "o3_8h": 111, "nO2": 16, "pM10": 31},
        {"city": "河源", "fineRate": 100, "pM2_5_Decimal": 21.9, "o3_8h": 122, "nO2": 15, "pM10": 31},
        {"city": "茂名", "fineRate": 99.3, "pM2_5_Decimal": 21.3, "o3_8h": 120, "nO2": 13, "pM10": 39},
        {"city": "江门", "fineRate": 91.7, "pM2_5_Decimal": 26.5, "o3_8h": 150, "nO2": 24, "pM10": 40},
        {"city": "广州", "fineRate": 91.7, "pM2_5_Decimal": 25.8, "o3_8h": 149, "nO2": 28, "pM10": 39},
        {"city": "肇庆", "fineRate": 91.7, "pM2_5_Decimal": 25.2, "o3_8h": 142, "nO2": 21, "pM10": 38},
        {"city": "中山", "fineRate": 88.7, "pM2_5_Decimal": 21.4, "o3_8h": 156, "nO2": 20, "pM10": 33},
        {"city": "东莞", "fineRate": 85.4, "pM2_5_Decimal": 23.1, "o3_8h": 170, "nO2": 26, "pM10": 41},
    ]

    result = build_city_pollutant_rankings(records, pollutants=["PM10"], top_n=5)

    assert [row["city"] for row in result["air_quality"]["good"]] == ["梅州", "河源", "茂名", "肇庆", "广州"]
    assert [row["city"] for row in result["air_quality"]["poor"]] == ["东莞", "中山", "江门", "广州", "肇庆"]
    assert result["air_quality"]["poor"][2]["tie_break_values"]["PM2.5"] == 26.5
    assert [item["field"] for item in result["air_quality_ranking_keys"]] == [
        "AQI达标率",
        "PM2.5",
        "O3",
        "NO2",
        "城市",
    ]


def test_missing_required_metric_is_reported():
    with pytest.raises(ValueError, match="PM10"):
        build_city_pollutant_rankings(
            [{"city": "广州", "fineRate": 90, "pM2_5_Decimal": 20, "o3_8h": 140, "nO2": 25}],
            pollutants=["PM10"],
        )


def test_region_summary_rows_are_excluded_when_city_rows_exist():
    records = [
        {"city": "湛江", "PM10": 30, "AQI达标率": 98, "pM2_5_Decimal": 20, "O3-8h": 120, "NO2": 18},
        {"city": "珠海", "PM10": 31, "AQI达标率": 95, "pM2_5_Decimal": 21, "O3-8h": 121, "NO2": 19},
        {"city": "粤西", "PM10": 29, "AQI达标率": 99, "pM2_5_Decimal": 19, "O3-8h": 119, "NO2": 17},
    ]

    result = build_city_pollutant_rankings(records, pollutants=["PM10"], top_n=3)

    assert [row["city"] for row in result["rankings"]["PM10"]["low"]] == ["湛江", "珠海"]
    assert result["record_count"] == 2


def test_report_package_pollutant_field_policy_uses_pm25_decimal_and_other_rounded_means():
    records = [
        {
            "city": "广州",
            "fineRate": 90,
            "pM2_5": 1,
            "pM2_5_Decimal": 20.9,
            "pM10": 40,
            "pM10_Decimal": 1.1,
            "o3_8h": 150,
            "o3_8h_Decimal": 1.2,
            "nO2": 30,
            "nO2_Decimal": 1.3,
        },
        {
            "city": "深圳",
            "fineRate": 91,
            "pM2_5": 99,
            "pM2_5_Decimal": 19.2,
            "pM10": 41,
            "pM10_Decimal": 0.1,
            "o3_8h": 151,
            "o3_8h_Decimal": 0.2,
            "nO2": 31,
            "nO2_Decimal": 0.3,
        },
    ]

    result = build_city_pollutant_rankings(records, pollutants=["PM2.5", "PM10", "O3"], top_n=2)

    assert [row["city"] for row in result["rankings"]["PM2.5"]["low"]] == ["深圳", "广州"]
    assert [row["city"] for row in result["rankings"]["PM10"]["low"]] == ["广州", "深圳"]
    assert [row["city"] for row in result["rankings"]["O3"]["low"]] == ["广州", "深圳"]
    assert result["rankings"]["PM10"]["low"][0]["tie_break_values"]["NO2"] == 30.0


def test_ranking_rejects_fallback_fields_for_required_pollutant_policy():
    records = [
        {
            "city": "广州",
            "fineRate": 90,
            "pM2_5": 20,
            "pM10_Decimal": 40.1,
            "o3_8h_Decimal": 150.2,
            "nO2_Decimal": 30.3,
        }
    ]

    with pytest.raises(ValueError, match="PM2.5.*O3.*NO2.*PM10"):
        build_city_pollutant_rankings(records, pollutants=["PM2.5"], top_n=1)


def test_records_from_report_package_data_id_falls_back_to_dataset_file(tmp_path, monkeypatch):
    data_id = "standard_report_package:v1:abc123"
    dataset_path = tmp_path / "standard_report_package_v1_abc123.json"
    dataset_path.write_text(
        """
{
  "views": {
    "cities": [
      {"城市": "广州", "PM10": 30, "AQI达标率": 99, "PM2.5": 20, "O3-8h": 120, "NO2": 18}
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )

    class RegistryStub:
        datasets_dir = tmp_path

        def load_dataset(self, data_id):
            raise KeyError(f"data_id {data_id} not found in registry")

    monkeypatch.setattr("app.tools.query.city_pollutant_rankings.tool.data_registry", RegistryStub())

    records, view = _records_from_data_id(data_id, "cities")

    assert view == "cities"
    assert records[0]["城市"] == "广州"


def test_records_from_report_package_defaults_to_cities_view_for_ranking_fields(monkeypatch):
    data_id = "standard_report_package:v1:view-order"
    payload = {
        "views": {
            "reporting": [
                {"城市": "广州", "PM2.5": 20, "PM10": 30, "O3-8h": 120, "NO2": 18, "AQI达标率": 99}
            ],
            "cities": [
                {
                    "city": "广州",
                    "pM2_5_Decimal": 20.1,
                    "pM10": 30,
                    "o3_8h": 120,
                    "nO2": 18,
                    "fineRate": 99,
                }
            ],
        }
    }

    class RegistryStub:
        def load_dataset(self, data_id):
            return payload

    monkeypatch.setattr("app.tools.query.city_pollutant_rankings.tool.data_registry", RegistryStub())

    records, view = _records_from_data_id(data_id)

    assert view == "cities"
    assert records[0]["pM2_5_Decimal"] == 20.1
