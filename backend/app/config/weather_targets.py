"""Shared weather query targets used by fetchers and query tools.

Add or update a city here once.  ERA5/observed fetchers and
``get_weather_data`` resolve the same target definition.

当前目录只维护广东省 21 个地级市：每个城市挂一个 NMC 城市观测站
（逐小时实况，写入 observed_weather_data）和一个 ERA5 历史代表点
（city_weather_history 写入 era5_reanalysis_data）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# 广东省城市历史（ERA5 再分析）由 project manifest 的 weather_history 驱动，
# 此标签仅用于把城市目录中的 era5 代表点归属到该 fetcher。
ERA5_CITY_HISTORY_FETCHER = "city_weather_history"


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
    """Build a Guangdong city target backed by an NMC observed station.

    ``station_id`` 是中央气象台城市页
    ``/publish/forecast/AGD/<url_slug>.html`` 末尾隐藏域中的站点 ID
    （2026-10-29 逐站勘探并经 rest/weather passedchart 验证）。
    """
    return WeatherCityTarget(
        city,
        "广东省",
        lat,
        lon,
        ERA5_CITY_HISTORY_FETCHER,
        observed_stations=(
            _nmc_station(
                key=key,
                station_id=station_id,
                station_name=station_name,
                province="广东省",
                city=city,
                lat=lat,
                lon=lon,
                url=f"/publish/forecast/AGD/{url_slug}.html",
            ),
        ),
    )


# This mapping is the single source of truth for explicitly fetched city targets.
WEATHER_CITY_TARGETS: dict[str, WeatherCityTarget] = {
    "广州市": _nmc_city_target(
        city="广州市",
        key="guangzhou",
        station_id="DwzZf",
        station_name="广州",
        lat=23.13,
        lon=113.26,
        url_slug="guangzhou",
    ),
    "韶关市": _nmc_city_target(
        city="韶关市",
        key="shaoguan",
        station_id="fXufo",
        station_name="韶关",
        lat=24.81,
        lon=113.60,
        url_slug="shaoguan",
    ),
    "深圳市": _nmc_city_target(
        city="深圳市",
        key="shenzhen",
        station_id="AhpEU",
        station_name="深圳",
        lat=22.54,
        lon=114.06,
        url_slug="shenzuo",
    ),
    "珠海市": _nmc_city_target(
        city="珠海市",
        key="zhuhai",
        station_id="sdnjf",
        station_name="珠海",
        lat=22.27,
        lon=113.58,
        url_slug="zhuhai",
    ),
    "汕头市": _nmc_city_target(
        city="汕头市",
        key="shantou",
        station_id="KYhpn",
        station_name="汕头",
        lat=23.35,
        lon=116.68,
        url_slug="shantou",
    ),
    "佛山市": _nmc_city_target(
        city="佛山市",
        key="foshan",
        station_id="YOyIv",
        station_name="佛山",
        lat=23.02,
        lon=113.12,
        url_slug="foshan",
    ),
    "江门市": _nmc_city_target(
        city="江门市",
        key="jiangmen",
        station_id="YtTxj",
        station_name="江门",
        lat=22.58,
        lon=113.08,
        url_slug="jiangmen",
    ),
    "湛江市": _nmc_city_target(
        city="湛江市",
        key="zhanjiang",
        station_id="OKhmr",
        station_name="湛江",
        lat=21.27,
        lon=110.36,
        url_slug="zhanjiang",
    ),
    "茂名市": _nmc_city_target(
        city="茂名市",
        key="maoming",
        station_id="aELXI",
        station_name="茂名",
        lat=21.66,
        lon=110.93,
        url_slug="maoming",
    ),
    "肇庆市": _nmc_city_target(
        city="肇庆市",
        key="zhaoqing",
        station_id="SwPNZ",
        station_name="肇庆",
        lat=23.05,
        lon=112.47,
        url_slug="zhaoqing",
    ),
    "惠州市": _nmc_city_target(
        city="惠州市",
        key="huizhou",
        station_id="VDZzQ",
        station_name="惠州",
        lat=23.11,
        lon=114.42,
        url_slug="huizhou",
    ),
    "梅州市": _nmc_city_target(
        city="梅州市",
        key="meizhou",
        station_id="lWavY",
        station_name="梅州",
        lat=24.29,
        lon=116.12,
        url_slug="meizhou",
    ),
    "汕尾市": _nmc_city_target(
        city="汕尾市",
        key="shanwei",
        station_id="hlwPp",
        station_name="汕尾",
        lat=22.79,
        lon=115.38,
        url_slug="shanwei",
    ),
    "河源市": _nmc_city_target(
        city="河源市",
        key="heyuan",
        station_id="Fkjlf",
        station_name="河源",
        lat=23.75,
        lon=114.70,
        url_slug="heyuan",
    ),
    "阳江市": _nmc_city_target(
        city="阳江市",
        key="yangjiang",
        station_id="dCezB",
        station_name="阳江",
        lat=21.86,
        lon=111.98,
        url_slug="yangjiang",
    ),
    "清远市": _nmc_city_target(
        city="清远市",
        key="qingyuan",
        station_id="WYryQ",
        station_name="清远",
        lat=23.68,
        lon=113.05,
        url_slug="qingyuan",
    ),
    "东莞市": _nmc_city_target(
        city="东莞市",
        key="dongguan",
        station_id="cqsJg",
        station_name="东莞",
        lat=23.02,
        lon=113.75,
        url_slug="dongzuo",
    ),
    "中山市": _nmc_city_target(
        city="中山市",
        key="zhongshan",
        station_id="YIWau",
        station_name="中山",
        lat=22.52,
        lon=113.39,
        url_slug="zhongshan",
    ),
    "潮州市": _nmc_city_target(
        city="潮州市",
        key="chaozhou",
        station_id="CSTxF",
        station_name="潮州",
        lat=23.66,
        lon=116.62,
        url_slug="chaozhou",
    ),
    "揭阳市": _nmc_city_target(
        city="揭阳市",
        key="jieyang",
        station_id="rUWdQ",
        station_name="揭阳",
        lat=22.55,
        lon=116.37,
        url_slug="jieyang",
    ),
    "云浮市": _nmc_city_target(
        city="云浮市",
        key="yunfu",
        station_id="JMZwt",
        station_name="云浮",
        lat=22.92,
        lon=112.04,
        url_slug="yunfu",
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
