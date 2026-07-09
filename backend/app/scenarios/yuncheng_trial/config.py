from dataclasses import dataclass


@dataclass(frozen=True)
class YunchengTrialConfig:
    city: str
    nearby_cities: list[str]
    lat: float
    lon: float
    weather_city_code: str
    default_lookback_hours: int
    fetch_station_data_first_version: bool
    o3_rise_3h_threshold: float
    pm25_rise_3h_threshold: float
    pm10_rise_3h_threshold: float
    pm25_co_supporting_rise_threshold: float
    co_supporting_rise_threshold: float
    no2_supporting_rise_threshold: float
    o3_watch_level: float
    pm25_watch_level: float
    pm10_watch_level: float
    no2_watch_level: float
    co_watch_level: float
    aqi_watch_level: float


YUNCHENG_TRIAL_CONFIG = YunchengTrialConfig(
    city="运城市",
    nearby_cities=["临汾市", "渭南市", "三门峡市", "洛阳市", "晋城市"],
    lat=35.0228,
    lon=111.0075,
    weather_city_code="101100801",
    default_lookback_hours=6,
    fetch_station_data_first_version=False,
    o3_rise_3h_threshold=40.0,
    pm25_rise_3h_threshold=25.0,
    pm10_rise_3h_threshold=40.0,
    pm25_co_supporting_rise_threshold=15.0,
    co_supporting_rise_threshold=0.2,
    no2_supporting_rise_threshold=20.0,
    o3_watch_level=160.0,
    pm25_watch_level=75.0,
    pm10_watch_level=150.0,
    no2_watch_level=100.0,
    co_watch_level=2.0,
    aqi_watch_level=100.0,
)
