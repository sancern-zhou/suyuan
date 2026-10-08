from datetime import datetime

from app.tools.analysis.xuchang_upwind_permit_sources.engine import (
    WeatherStation,
    circular_difference_deg,
    classify_stability,
    dynamic_sector_half_angle_deg,
    dispersion_sigmas,
    dispersion_weight,
    industry_factor,
    nearest_station,
    pollutant_relevance,
    pollutant_relevance_factor,
    strict_hour_weather,
)


def test_nearest_station_is_deterministic():
    stations = (
        WeatherStation("a", "A", 34.0, 113.0),
        WeatherStation("b", "B", 34.0, 114.0),
    )

    assert nearest_station(34.01, 113.05, stations).station_id == "a"


def test_strict_hour_rejects_missing_representative_without_fallback():
    representative = WeatherStation("primary", "Primary", 34.0, 113.0)
    result = strict_hour_weather(
        timestamp=datetime(2026, 8, 5, 10),
        representative=representative,
        station_records={
            "validator": {"wind_direction_10m": 315, "wind_speed_10m": 2},
        },
    )

    assert result["usable"] is False
    assert result["reason"] == "representative_station_wind_unavailable_or_calm"


def test_strict_hour_requires_a_consistent_validator():
    representative = WeatherStation("primary", "Primary", 34.0, 113.0)
    result = strict_hour_weather(
        timestamp=datetime(2026, 8, 5, 10),
        representative=representative,
        station_records={
            "primary": {"wind_direction_10m": 315, "wind_speed_10m": 2},
            "validator": {"wind_direction_10m": 45, "wind_speed_10m": 3},
        },
    )

    assert result["usable"] is False
    assert result["reason"] == "no_validating_station_with_consistent_wind_direction"


def test_strict_hour_distinguishes_missing_validator_wind():
    representative = WeatherStation("primary", "Primary", 34.0, 113.0)
    result = strict_hour_weather(
        timestamp=datetime(2026, 8, 5, 10),
        representative=representative,
        station_records={
            "primary": {"wind_direction_10m": 315, "wind_speed_10m": 2},
        },
    )

    assert result["usable"] is False
    assert result["reason"] == "no_validating_station_wind_available"
    assert result["validator_direction_differences_deg"] == {}


def test_strict_hour_accepts_circularly_close_winds():
    representative = WeatherStation("primary", "Primary", 34.0, 113.0)
    result = strict_hour_weather(
        timestamp=datetime(2026, 8, 5, 10),
        representative=representative,
        station_records={
            "primary": {"wind_direction_10m": 350, "wind_speed_10m": 2},
            "validator": {"wind_direction_10m": 10, "wind_speed_10m": 3},
        },
    )

    assert circular_difference_deg(350, 10) == 20
    assert result["usable"] is True
    assert result["validation_direction_difference_deg"] == 20
    assert result["sector_half_angle_deg"] == 45


def test_documented_dispersion_and_industry_factors_are_available():
    sigma_y, sigma_z = dispersion_sigmas(1000, "E")

    assert sigma_y > 0
    assert sigma_z == 100
    assert industry_factor("精细化工") == 1.5
    assert industry_factor("食品加工") == 0.8
    assert dispersion_weight(
        distance_km=1,
        angle_difference_deg=0,
        wind_speed_ms=2,
        historical_wind_speed_ms=2,
        stability="D",
    ) > 0


def test_dynamic_sector_reflects_wind_uncertainty():
    assert dynamic_sector_half_angle_deg(wind_speed_ms=2, validation_direction_difference_deg=10) == 30
    assert dynamic_sector_half_angle_deg(wind_speed_ms=2, validation_direction_difference_deg=25) == 45
    assert dynamic_sector_half_angle_deg(wind_speed_ms=0.8, validation_direction_difference_deg=10) == 60


def test_stability_supports_daytime_a_and_nighttime_f():
    daytime = classify_stability(
        boundary_layer_height_m=None,
        cloud_cover_pct=20,
        timestamp=datetime(2026, 8, 5, 12),
        latitude_deg=34.0,
        wind_speed_ms=1.5,
    )
    nighttime = classify_stability(
        boundary_layer_height_m=None,
        cloud_cover_pct=20,
        timestamp=datetime(2026, 8, 5, 23),
        latitude_deg=34.0,
        wind_speed_ms=1.5,
    )

    assert daytime["stability_class"] == "A"
    assert nighttime["stability_class"] == "F"


def test_pollutant_relevance_is_category_specific():
    assert pollutant_relevance("PM2.5", "颗粒物") == "exact_match"
    assert pollutant_relevance("O3", "挥发性有机物") == "precursor_match"
    assert pollutant_relevance("NOX", "氮氧化物") == "exact_match"
    assert pollutant_relevance_factor("PM2.5", "no_recorded_match", True) == 0.1


def test_dispersion_does_not_apply_an_extra_inverse_distance_square():
    near = dispersion_weight(
        distance_km=1,
        angle_difference_deg=0,
        wind_speed_ms=2,
        historical_wind_speed_ms=2,
        stability="D",
    )
    far = dispersion_weight(
        distance_km=2,
        angle_difference_deg=0,
        wind_speed_ms=2,
        historical_wind_speed_ms=2,
        stability="D",
    )

    assert 1 < near / far < 10
