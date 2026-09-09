import pytest

from app.tools.jiangsu.review_station_selection import select_district_stations


def row(code, district="D1", lon=120, lat=32, city="C1"):
    return {"stationCode": code, "districtCode": district, "districtName": "同名区",
            "cityCode": city, "cityName": city, "longitude": lon, "latitude": lat}


def test_same_district_excludes_closer_outside_stations_and_sorts_all_neighbors():
    rows = [row("target"), row("outside", "D2", 120.001)]
    rows += [row(str(i), lon=120 + i / 100) for i in range(8, 0, -1)]
    rows += [row("1", lon=120.01), row("other-city", "D3", 120.002, city="C2")]
    selected = select_district_stations({"station_code": "target"}, rows)
    assert selected["station_codes"] == [str(i) for i in range(1, 9)] + ["target"]
    assert selected["nearest_station_code"] == "1"
    assert selected["comparison_stations"][0]["distance_km"] == pytest.approx(0.943, abs=0.002)
    assert selected["distance_ranking_complete"] is True


def test_unknown_coordinates_do_not_claim_absolute_nearest():
    selected = select_district_stations({"station_code": "target"}, [
        row("target"), row("known", lon=120.1), row("unknown", lon="NaN"), row("zero", lon=0, lat=0),
    ])
    assert selected["nearest_station_code"] == "known"
    assert selected["distance_ranking_complete"] is False
    assert selected["comparison_stations"][1]["distance_km"] is None
    assert "仅指" in selected["selection_note"]
    no_origin = select_district_stations({"station_code": "target"}, [row("target", lon=""), row("known")])
    assert no_origin["nearest_station_code"] is None


def test_missing_district_never_expands_to_city():
    with pytest.raises(ValueError, match="区县"):
        select_district_stations({"station_code": "absent", "city_name": "南京市"}, [])
    selected = select_district_stations({"station_code": "target"}, [row("target")])
    assert selected["comparison_stations"] == []


def test_name_fallback_requires_both_city_and_district():
    selected = select_district_stations({"station_code": "absent", "city_name": "C1", "district_name": "同名区"}, [
        row("same"), row("other", city="C2"),
    ])
    assert selected["station_codes"] == ["same", "absent"]
