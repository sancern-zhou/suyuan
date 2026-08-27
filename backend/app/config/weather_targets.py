"""Shared weather query targets used by fetchers and query tools.

Add or update a city here once.  ERA5/observed fetchers and
``get_weather_data`` resolve the same target definition.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

ERA5_MAIN_FETCHER = "era5_fetcher"
ERA5_JINING_FETCHER = "jining_era5_fetcher"


@dataclass(frozen=True)
class ObservedWeatherStationTarget:
    """An observed-weather station attached to a city target."""

    key: str
    station_id: str
    station_name: str
    province: str
    city: str
    lat: float
    lon: float
    provider: str
    url: str | None = None


@dataclass(frozen=True)
class WeatherCityTarget:
    """One city and its source-specific weather query targets."""

    city: str
    province: str
    era5_lat: float | None = None
    era5_lon: float | None = None
    era5_fetcher: str | None = None
    aliases: tuple[str, ...] = ()
    observed_stations: tuple[ObservedWeatherStationTarget, ...] = ()

    @property
    def era5_point(self) -> dict[str, float] | None:
        if self.era5_lat is None or self.era5_lon is None:
            return None
        return {"lat": self.era5_lat, "lon": self.era5_lon}


def _nmc_station(
    *,
    key: str,
    station_id: str,
    station_name: str,
    province: str,
    city: str,
    lat: float,
    lon: float,
    url: str,
) -> ObservedWeatherStationTarget:
    return ObservedWeatherStationTarget(
        key=key,
        station_id=station_id,
        station_name=station_name,
        province=province,
        city=city,
        lat=lat,
        lon=lon,
        provider="NMC",
        url=url,
    )


def _nmc_city_target(
    *,
    city: str,
    key: str,
    station_id: str,
    station_name: str,
    lat: float,
    lon: float,
    url_slug: str,
) -> WeatherCityTarget:
    """Build a city target backed only by an NMC observed station."""
    return WeatherCityTarget(
        city,
        "河南省",
        observed_stations=(
            _nmc_station(
                key=key,
                station_id=station_id,
                station_name=station_name,
                province="河南省",
                city=city,
                lat=lat,
                lon=lon,
                url=f"/publish/forecast/AHA/{url_slug}.html",
            ),
        ),
    )


# This mapping is the single source of truth for explicitly fetched city targets.
WEATHER_CITY_TARGETS: dict[str, WeatherCityTarget] = {
    "南京市": WeatherCityTarget("南京市", "江苏省", 32.0603, 118.7969, ERA5_MAIN_FETCHER),
    "无锡市": WeatherCityTarget("无锡市", "江苏省", 31.4912, 120.3119, ERA5_MAIN_FETCHER),
    "徐州市": WeatherCityTarget("徐州市", "江苏省", 34.2044, 117.2857, ERA5_MAIN_FETCHER),
    "常州市": WeatherCityTarget("常州市", "江苏省", 31.8107, 119.9741, ERA5_MAIN_FETCHER),
    "苏州市": WeatherCityTarget("苏州市", "江苏省", 31.2989, 120.5853, ERA5_MAIN_FETCHER),
    "南通市": WeatherCityTarget("南通市", "江苏省", 31.9802, 120.8943, ERA5_MAIN_FETCHER),
    "连云港市": WeatherCityTarget("连云港市", "江苏省", 34.5967, 119.2229, ERA5_MAIN_FETCHER),
    "淮安市": WeatherCityTarget("淮安市", "江苏省", 33.6104, 119.0153, ERA5_MAIN_FETCHER),
    "盐城市": WeatherCityTarget("盐城市", "江苏省", 33.3495, 120.1633, ERA5_MAIN_FETCHER),
    "扬州市": WeatherCityTarget("扬州市", "江苏省", 32.3936, 119.4127, ERA5_MAIN_FETCHER),
    "镇江市": WeatherCityTarget("镇江市", "江苏省", 32.1878, 119.4250, ERA5_MAIN_FETCHER),
    "泰州市": WeatherCityTarget("泰州市", "江苏省", 32.4558, 119.9230, ERA5_MAIN_FETCHER),
    "宿迁市": WeatherCityTarget("宿迁市", "江苏省", 33.9630, 118.2750, ERA5_MAIN_FETCHER),
    "郑州市": _nmc_city_target(
        city="郑州市",
        key="zhengzhou",
        station_id="YVItN",
        station_name="郑州",
        lat=34.72,
        lon=113.65,
        url_slug="zhengzhou",
    ),
    "开封市": _nmc_city_target(
        city="开封市",
        key="kaifeng",
        station_id="swtij",
        station_name="开封",
        lat=34.78,
        lon=114.30,
        url_slug="kaifeng",
    ),
    "洛阳市": _nmc_city_target(
        city="洛阳市",
        key="luoyang",
        station_id="rYaxY",
        station_name="洛阳",
        lat=34.82,
        lon=112.43,
        url_slug="luoyang2",
    ),
    "平顶山市": _nmc_city_target(
        city="平顶山市",
        key="pingdingshan",
        station_id="nRecJ",
        station_name="平顶山",
        lat=33.74,
        lon=113.30,
        url_slug="pingdingshan",
    ),
    "安阳市": _nmc_city_target(
        city="安阳市",
        key="anyang",
        station_id="hNkdK",
        station_name="安阳",
        lat=36.05,
        lon=114.13,
        url_slug="anyang",
    ),
    "鹤壁市": _nmc_city_target(
        city="鹤壁市",
        key="hebi",
        station_id="NYclC",
        station_name="鹤壁",
        lat=35.75,
        lon=114.30,
        url_slug="hebi",
    ),
    "新乡市": _nmc_city_target(
        city="新乡市",
        key="xinxiang",
        station_id="VLpOH",
        station_name="新乡",
        lat=35.32,
        lon=113.88,
        url_slug="xinxiang",
    ),
    "焦作市": _nmc_city_target(
        city="焦作市",
        key="jiaozuo",
        station_id="ubXHV",
        station_name="焦作",
        lat=35.23,
        lon=113.25,
        url_slug="jiaozuo",
    ),
    "濮阳市": _nmc_city_target(
        city="濮阳市",
        key="puyang",
        station_id="XbbBI",
        station_name="濮阳",
        lat=35.76,
        lon=115.03,
        url_slug="zuoyang1",
    ),
    "运城市": WeatherCityTarget(
        "运城市",
        "山西省",
        35.0264,
        111.0076,
        ERA5_MAIN_FETCHER,
        observed_stations=(
            _nmc_station(
                key="yuncheng",
                station_id="AupnI",
                station_name="运城",
                province="山西省",
                city="运城市",
                lat=35.11,
                lon=111.06,
                url="/publish/forecast/ASX/yuncheng.html",
            ),
        ),
    ),
    "许昌市": WeatherCityTarget(
        "许昌市",
        "河南省",
        34.036,
        113.852,
        ERA5_MAIN_FETCHER,
        observed_stations=(
            _nmc_station(
                key="xuchang",
                station_id="ZzMTA",
                station_name="许昌",
                province="河南省",
                city="许昌市",
                lat=34.07,
                lon=113.92,
                url="/publish/forecast/AHA/xuchang.html",
            ),
            _nmc_station(
                key="yuzhou",
                station_id="HFqwM",
                station_name="禹州",
                province="河南省",
                city="许昌市",
                lat=34.16,
                lon=113.49,
                url="/publish/forecast/AHA/yuzhou.html",
            ),
            _nmc_station(
                key="changge",
                station_id="sHlBF",
                station_name="长葛",
                province="河南省",
                city="许昌市",
                lat=34.22,
                lon=113.77,
                url="/publish/forecast/AHA/changge.html",
            ),
        ),
    ),
    "漯河市": _nmc_city_target(
        city="漯河市",
        key="luohe",
        station_id="lncFZ",
        station_name="漯河",
        lat=33.58,
        lon=114.02,
        url_slug="zuohe",
    ),
    "三门峡市": _nmc_city_target(
        city="三门峡市",
        key="sanmenxia",
        station_id="TjcXC",
        station_name="三门峡",
        lat=34.80,
        lon=111.20,
        url_slug="sanmenxia",
    ),
    "南阳市": _nmc_city_target(
        city="南阳市",
        key="nanyang",
        station_id="vRweN",
        station_name="南阳",
        lat=33.10,
        lon=112.48,
        url_slug="nanyang",
    ),
    "商丘市": _nmc_city_target(
        city="商丘市",
        key="shangqiu",
        station_id="aMsMR",
        station_name="商丘",
        lat=34.45,
        lon=115.65,
        url_slug="shangqiu",
    ),
    "信阳市": _nmc_city_target(
        city="信阳市",
        key="xinyang",
        station_id="hdKHW",
        station_name="信阳",
        lat=32.13,
        lon=114.05,
        url_slug="xinyang",
    ),
    "周口市": _nmc_city_target(
        city="周口市",
        key="zhoukou",
        station_id="URskB",
        station_name="周口",
        lat=33.63,
        lon=114.70,
        url_slug="zhoukou",
    ),
    "驻马店市": _nmc_city_target(
        city="驻马店市",
        key="zhumadian",
        station_id="ZmGSj",
        station_name="驻马店",
        lat=32.93,
        lon=113.92,
        url_slug="zhumadian",
    ),
    "济源市": _nmc_city_target(
        city="济源市",
        key="jiyuan",
        station_id="TJdvk",
        station_name="济源",
        lat=35.08,
        lon=112.58,
        url_slug="jiyuan",
    ),
    "济宁市": WeatherCityTarget(
        "济宁市",
        "山东省",
        35.4143,
        116.5871,
        ERA5_JINING_FETCHER,
    ),
}


def normalize_city_name(value: str) -> str:
    """Normalize common city spellings for catalog and DB matching."""
    normalized = str(value or "").strip().replace(" ", "")
    if normalized and not normalized.endswith("市"):
        normalized += "市"
    return normalized


def resolve_weather_city_target(city: str) -> WeatherCityTarget | None:
    normalized = normalize_city_name(city)
    target = WEATHER_CITY_TARGETS.get(normalized)
    if target is not None:
        return target

    raw = str(city or "").strip()
    for candidate in WEATHER_CITY_TARGETS.values():
        aliases = {normalize_city_name(alias) for alias in candidate.aliases}
        if normalized in aliases or raw in candidate.aliases:
            return candidate
    return None


def iter_era5_city_targets(fetcher: str) -> Iterable[WeatherCityTarget]:
    return (
        target
        for target in WEATHER_CITY_TARGETS.values()
        if target.era5_fetcher == fetcher and target.era5_point is not None
    )


def get_observed_station_targets(
    *, provider: str | None = None
) -> dict[str, ObservedWeatherStationTarget]:
    stations: dict[str, ObservedWeatherStationTarget] = {}
    for target in WEATHER_CITY_TARGETS.values():
        for station in target.observed_stations:
            if provider and station.provider.casefold() != provider.casefold():
                continue
            stations[station.key] = station
    return stations
