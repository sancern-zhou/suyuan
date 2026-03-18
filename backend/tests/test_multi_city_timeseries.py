"""
Test multi-city timeseries chart generation

This test verifies that when data contains multiple cities with a single pollutant,
the chart generator produces separate series for each city instead of averaging them.

Test scenario: 4 cities x 24 hours x 1 pollutant (O3) = 96 records
Expected: 4 series (one per city), not 1 averaged series
"""

import pytest
from datetime import datetime, timedelta
from app.utils.chart_data_converter import ChartDataConverter, convert_chart_data


def generate_multi_city_o3_data():
    """
    Generate test data: 4 cities x 24 hours x O3

    Cities: foshan, zhuhai, jiangmen, zhaoqing
    Time range: 24 hours
    Pollutant: O3 only
    """
    cities = ["foshan", "zhuhai", "jiangmen", "zhaoqing"]
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    records = []
    for city in cities:
        # Each city has different O3 pattern
        base_o3 = {
            "foshan": 80,
            "zhuhai": 60,
            "jiangmen": 70,
            "zhaoqing": 50
        }[city]

        for hour in range(24):
            timestamp = (base_time + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S")
            # Simulate daily O3 pattern (higher in afternoon)
            o3_value = base_o3 + (10 if 12 <= hour <= 16 else 0)

            records.append({
                "station_name": city,
                "timestamp": timestamp,
                "measurements": {
                    "O3": o3_value
                }
            })

    return records


def test_multi_city_timeseries_detection():
    """Test that multi-city + single pollutant scenario is correctly detected"""
    data = generate_multi_city_o3_data()

    # Count unique stations
    station_count = ChartDataConverter._count_unique_stations(data)
    assert station_count == 4, f"Expected 4 stations, got {station_count}"

    # Detect pollutants
    pollutants = ChartDataConverter._detect_pollutants(data)
    assert len(pollutants) == 1, f"Expected 1 pollutant, got {len(pollutants)}"
    assert "O3" in pollutants, f"Expected O3 in pollutants, got {pollutants}"


def test_multi_city_timeseries_generation():
    """Test that 4 cities generate 4 series (one per city)"""
    data = generate_multi_city_o3_data()

    # Convert using guangdong_stations data type with timeseries chart type
    result = convert_chart_data(
        data=data,
        data_type="guangdong_stations",
        chart_type="timeseries"
    )

    # Check no error
    assert "error" not in result, f"Unexpected error: {result.get('error')}"

    # Check chart type
    assert result["type"] == "timeseries", f"Expected timeseries, got {result['type']}"

    # Check series count - should be 4 (one per city)
    series = result["data"]["data"]["series"]
    assert len(series) == 4, f"Expected 4 series (one per city), got {len(series)}"

    # Check series names match city names
    series_names = {s["name"] for s in series}
    expected_names = {"foshan", "zhuhai", "jiangmen", "zhaoqing"}
    assert series_names == expected_names, f"Expected {expected_names}, got {series_names}"

    # Check meta indicates city-grouped
    assert result["meta"]["chart_type"] == "city_grouped_timeseries"
    assert set(result["meta"]["stations"]) == expected_names


def test_multi_city_timeseries_data_integrity():
    """Test that each city's data is correctly separated (not averaged)"""
    data = generate_multi_city_o3_data()

    result = convert_chart_data(
        data=data,
        data_type="guangdong_stations",
        chart_type="timeseries"
    )

    series = result["data"]["data"]["series"]

    # Find foshan series (base O3 = 80)
    foshan_series = next(s for s in series if s["name"] == "foshan")
    # Non-peak hours should be around 80
    assert foshan_series["data"][0] == 80, f"Foshan hour 0 should be 80, got {foshan_series['data'][0]}"

    # Find zhaoqing series (base O3 = 50)
    zhaoqing_series = next(s for s in series if s["name"] == "zhaoqing")
    # Non-peak hours should be around 50
    assert zhaoqing_series["data"][0] == 50, f"Zhaoqing hour 0 should be 50, got {zhaoqing_series['data'][0]}"


def test_selected_stations_filter():
    """Test that selected_stations parameter correctly filters cities"""
    data = generate_multi_city_o3_data()

    # Only request 2 cities
    result = convert_chart_data(
        data=data,
        data_type="guangdong_stations",
        chart_type="timeseries",
        selected_stations=["foshan", "zhuhai"]
    )

    # Check no error
    assert "error" not in result, f"Unexpected error: {result.get('error')}"

    # Check series count - should be 2
    series = result["data"]["data"]["series"]
    assert len(series) == 2, f"Expected 2 series, got {len(series)}"

    # Check series names
    series_names = {s["name"] for s in series}
    expected_names = {"foshan", "zhuhai"}
    assert series_names == expected_names, f"Expected {expected_names}, got {series_names}"


def test_single_city_multi_pollutant_fallback():
    """Test that single city with multiple pollutants uses pollutant-grouped mode"""
    # Create data with 1 city and multiple pollutants
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    records = []

    for hour in range(24):
        timestamp = (base_time + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S")
        records.append({
            "station_name": "guangzhou",
            "timestamp": timestamp,
            "measurements": {
                "O3": 80 + hour,
                "PM2.5": 30 + hour,
                "NO2": 20 + hour
            }
        })

    result = convert_chart_data(
        data=records,
        data_type="guangdong_stations",
        chart_type="timeseries"
    )

    # Check no error
    assert "error" not in result, f"Unexpected error: {result.get('error')}"

    # Should use pollutant-grouped mode (3 series for 3 pollutants)
    series = result["data"]["data"]["series"]
    assert len(series) == 3, f"Expected 3 series (one per pollutant), got {len(series)}"

    # Series names should be pollutant names
    series_names = {s["name"] for s in series}
    expected_pollutants = {"O3", "PM2.5", "NO2"}
    assert series_names == expected_pollutants, f"Expected {expected_pollutants}, got {series_names}"


def test_time_points_consistency():
    """Test that all series have the same time points"""
    data = generate_multi_city_o3_data()

    result = convert_chart_data(
        data=data,
        data_type="guangdong_stations",
        chart_type="timeseries"
    )

    x_data = result["data"]["data"]["x"]
    series = result["data"]["data"]["series"]

    # Should have 24 time points
    assert len(x_data) == 24, f"Expected 24 time points, got {len(x_data)}"

    # Each series should have 24 values
    for s in series:
        assert len(s["data"]) == 24, f"Series {s['name']} has {len(s['data'])} values, expected 24"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
