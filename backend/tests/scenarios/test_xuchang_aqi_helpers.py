"""HJ 633 小时 AQI 计算辅助函数（中大源站点小时行补首要污染物/等级）。"""

from app.scenarios.xuchang_city_exceedance.aqi import (
    aqi_level,
    hourly_aqi_and_primary,
    iaqi,
)


def test_iaqi_piecewise_linear_pm25():
    assert iaqi("pm25", 35) == 50
    assert iaqi("pm25", 75) == 100
    assert iaqi("pm25", 82) == 108.8
    assert iaqi("pm25", -99) is None
    assert iaqi("pm25", None) is None


def test_hourly_primary_and_aqi_from_zhongda_row():
    row = {"pm25": 82, "pm10": 100, "o3": 50, "no2": 20, "so2": 5, "co": 0.7}
    aqi, primary = hourly_aqi_and_primary(row)
    assert primary == "PM2.5"
    assert aqi == 108.8


def test_low_pollution_has_no_primary():
    row = {"pm25": 10, "pm10": 20, "o3": 40, "no2": 10, "so2": 5, "co": 0.4}
    aqi, primary = hourly_aqi_and_primary(row)
    assert aqi is not None and aqi <= 50
    assert primary is None


def test_aqi_level_bands():
    assert aqi_level(45) == 1
    assert aqi_level(101) == 3
    assert aqi_level(320) == 6
    assert aqi_level(None) is None
    assert aqi_level(-99) is None
