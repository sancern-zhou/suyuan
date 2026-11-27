"""Shared Xuchang station and regional-city identifiers.

Constants live in the scenario layer because both the hourly-process and the
station-daily exceedance fetchers need them, and fetchers must not import
each other (circular import risk).
"""

from __future__ import annotations

# 国控站统一使用中大平台站码（station_code）；站名与经纬度为固定台站属性。
# 中大表不含坐标列，读取小时/日值后用 NATIONAL_STATION_META 补全坐标与展示名。
NATIONAL_STATION_CODES = ("1003A", "1005A", "1008A", "1009A", "1011A", "1012A")

NATIONAL_STATION_META = {
    "1003A": {"name": "开发区", "lon": 113.7906, "lat": 33.9953},
    "1005A": {"name": "市一中", "lon": 113.8172, "lat": 34.0339},
    "1008A": {"name": "许昌学院", "lon": 113.8611, "lat": 34.0443},
    "1009A": {"name": "芙蓉广场", "lon": 113.8428, "lat": 34.0825},
    "1011A": {"name": "新元大道996号", "lon": 113.8157285, "lat": 34.126705},
    "1012A": {"name": "望田路111号", "lon": 113.835877, "lat": 34.0155267},
}

REGIONAL_CITIES = ("郑州市", "开封市", "平顶山市", "漯河市", "周口市", "商丘市", "驻马店市")
