"""Pure calculations for strict, station-representative upwind matching."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import asin, atan2, cos, exp, pi, radians, sin, sqrt
from typing import Any

EARTH_RADIUS_KM = 6371.0088
MIN_WIND_SPEED_MS = 0.5
MAX_WIND_DIRECTION_DIFFERENCE_DEG = 60.0
DEFAULT_SECTOR_HALF_ANGLE_DEG = 45.0

INDUSTRY_FACTORS = (
    (("石油化工", "精细化工", "化工"), 1.5),
    (("燃煤电厂", "火电", "电力"), 1.4),
    (("陶瓷", "建材"), 1.3),
    (("冶炼", "电镀", "金属"), 1.3),
    (("印染", "纺织", "造纸", "制浆", "橡胶", "塑料"), 1.2),
    (("印刷", "家具", "涂装"), 1.1),
    (("食品"), 0.8),
)


@dataclass(frozen=True)
class WeatherStation:
    station_id: str
    station_name: str
    lat: float
    lon: float


XUCHANG_WEATHER_STATIONS = (
    WeatherStation("ZzMTA", "许昌", 34.07, 113.92),
    WeatherStation("HFqwM", "禹州", 34.16, 113.49),
    WeatherStation("sHlBF", "长葛", 34.22, 113.77),
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def bearing_deg(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> float:
    dlon = radians(to_lon - from_lon)
    lat1 = radians(from_lat)
    lat2 = radians(to_lat)
    bearing = atan2(
        sin(dlon) * cos(lat2),
        cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon),
    )
    return (bearing * 180 / 3.141592653589793 + 360) % 360


def circular_difference_deg(first: float, second: float) -> float:
    return abs((first - second + 180) % 360 - 180)


def nearest_station(receptor_lat: float, receptor_lon: float, stations: Iterable[WeatherStation] = XUCHANG_WEATHER_STATIONS) -> WeatherStation:
    return min(
        stations,
        key=lambda station: haversine_km(receptor_lat, receptor_lon, station.lat, station.lon),
    )


def valid_wind(record: dict[str, Any] | None, min_wind_speed_ms: float = MIN_WIND_SPEED_MS) -> bool:
    if not record:
        return False
    try:
        direction = float(record["wind_direction_10m"])
        speed = float(record["wind_speed_10m"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= direction <= 360 and speed >= min_wind_speed_ms


def strict_hour_weather(
    *,
    timestamp: datetime,
    representative: WeatherStation,
    station_records: dict[str, dict[str, Any]],
    min_wind_speed_ms: float = MIN_WIND_SPEED_MS,
    max_direction_difference_deg: float = MAX_WIND_DIRECTION_DIFFERENCE_DEG,
) -> dict[str, Any]:
    """Return one usable strict-weather hour or an explicit exclusion reason.

    The representative station is fixed by geometry. Another station must validate
    its direction; a missing representative record never falls back to another one.
    """
    primary = station_records.get(representative.station_id)
    if not valid_wind(primary, min_wind_speed_ms):
        return {
            "time": timestamp.isoformat(),
            "usable": False,
            "reason": "representative_station_wind_unavailable_or_calm",
            "representative_station": representative.station_name,
        }

    primary_direction = float(primary["wind_direction_10m"])
    validators = []
    for station_id, record in station_records.items():
        if station_id == representative.station_id or not valid_wind(record, min_wind_speed_ms):
            continue
        difference = circular_difference_deg(primary_direction, float(record["wind_direction_10m"]))
        validators.append((station_id, difference))

    accepted = [item for item in validators if item[1] <= max_direction_difference_deg]
    if not accepted:
        reason = (
            "no_validating_station_wind_available"
            if not validators
            else "no_validating_station_with_consistent_wind_direction"
        )
        return {
            "time": timestamp.isoformat(),
            "usable": False,
            "reason": reason,
            "representative_station": representative.station_name,
            "validator_direction_differences_deg": {station_id: round(diff, 1) for station_id, diff in validators},
        }

    validator_id, validator_difference = min(accepted, key=lambda item: item[1])
    return {
        "time": timestamp.isoformat(),
        "usable": True,
        "representative_station": representative.station_name,
        "representative_station_id": representative.station_id,
        "wind_from_deg": primary_direction,
        "wind_speed_ms": float(primary["wind_speed_10m"]),
        "validation_station_id": validator_id,
        "validation_direction_difference_deg": round(validator_difference, 1),
        "sector_half_angle_deg": dynamic_sector_half_angle_deg(
            wind_speed_ms=float(primary["wind_speed_10m"]),
            validation_direction_difference_deg=validator_difference,
        ),
    }


def dynamic_sector_half_angle_deg(*, wind_speed_ms: float, validation_direction_difference_deg: float) -> float:
    if wind_speed_ms < 1.0 or validation_direction_difference_deg > 35:
        return 60.0
    if wind_speed_ms >= 1.5 and validation_direction_difference_deg <= 15:
        return 30.0
    return DEFAULT_SECTOR_HALF_ANGLE_DEG


def solar_altitude_deg(timestamp: datetime, latitude_deg: float) -> float:
    day_of_year = timestamp.timetuple().tm_yday
    declination = 23.45 * sin(radians(360 / 365 * (day_of_year - 81)))
    hour = timestamp.hour + timestamp.minute / 60
    hour_angle = 15 * (hour - 12)
    sin_altitude = (
        sin(radians(latitude_deg)) * sin(radians(declination))
        + cos(radians(latitude_deg)) * cos(radians(declination)) * cos(radians(hour_angle))
    )
    return asin(max(-1.0, min(1.0, sin_altitude))) * 180 / pi


def classify_stability(
    *,
    boundary_layer_height_m: float | None,
    cloud_cover_pct: float | None,
    timestamp: datetime,
    latitude_deg: float,
    wind_speed_ms: float,
) -> dict[str, Any]:
    """Classify A-F stability from daylight, cloud, wind and optional BLH."""
    if boundary_layer_height_m is None and cloud_cover_pct is None:
        return {"status": "unavailable", "stability_class": None, "dispersion_condition": None}

    altitude = solar_altitude_deg(timestamp, latitude_deg)
    cloud = cloud_cover_pct
    if cloud is None:
        if boundary_layer_height_m is not None and boundary_layer_height_m < 400:
            stability = "E" if altitude <= 0 else "D"
        elif boundary_layer_height_m is not None and boundary_layer_height_m >= 1200 and altitude > 0:
            stability = "C"
        else:
            stability = "D"
    elif altitude > 0:
        if cloud <= 40:
            stability = "A" if wind_speed_ms <= 2 else "B" if wind_speed_ms <= 3 else "C" if wind_speed_ms <= 5 else "D"
        elif cloud <= 70:
            stability = "B" if wind_speed_ms <= 2 else "C" if wind_speed_ms <= 3 else "D"
        else:
            stability = "C" if wind_speed_ms <= 2 else "D"
    else:
        stability = "D" if cloud >= 80 else "F" if wind_speed_ms <= 2 else "E" if wind_speed_ms <= 3 else "D"

    dispersion = {
        "A": "very_well_mixed",
        "B": "well_mixed",
        "C": "slightly_unstable",
        "D": "neutral",
        "E": "restricted",
        "F": "strongly_restricted",
    }[stability]

    return {
        "status": "available",
        "stability_class": stability,
        "dispersion_condition": dispersion,
        "boundary_layer_height_m": boundary_layer_height_m,
        "cloud_cover_pct": cloud_cover_pct,
        "solar_altitude_deg": round(altitude, 1),
    }


def pollutant_relevance(pollutant: str, permit_pollutants: str | None) -> str:
    text = (permit_pollutants or "").lower().replace(" ", "")
    mappings = {
        "PM2.5": (("颗粒物", "烟尘"), ("二氧化硫", "so2", "氮氧化物", "nox", "挥发性有机物", "vocs")),
        # Ozone is not emitted directly; VOCs and NOx are both precursor evidence.
        "O3": ((), ("vocs", "挥发性有机物", "非甲烷总烃", "氮氧化物", "nox", "no2")),
        "NOX": (("二氧化氮", "氮氧化物", "nox", "no2"), ()),
    }
    direct, precursor = mappings.get(pollutant, ((), ()))
    if any(token in text for token in direct):
        return "exact_match"
    if any(token in text for token in precursor):
        return "precursor_match"
    return "no_recorded_match"


def pollutant_relevance_factor(pollutant: str, relevance: str, permit_text_available: bool) -> float:
    if not permit_text_available:
        return 0.3
    if relevance == "exact_match":
        return 1.0
    if relevance == "precursor_match":
        return 1.0 if pollutant == "O3" else 0.6
    return 0.1


def candidate_hour_score(*, distance_km: float, angle_difference_deg: float, sector_half_angle_deg: float) -> float:
    direction_score = exp(-0.5 * (angle_difference_deg / sector_half_angle_deg) ** 2)
    distance_score = exp(-distance_km / 15.0)
    return direction_score * distance_score


def industry_factor(industry: str | None) -> float:
    text = industry or ""
    for labels, factor in INDUSTRY_FACTORS:
        if any(label in text for label in labels):
            return factor
    return 1.0


def dispersion_sigmas(distance_m: float, stability: str | None) -> tuple[float, float]:
    """Return the documented simplified Briggs sigma_y/sigma_z values in metres."""
    distance_m = max(distance_m, 1.0)
    stability = stability or "D"
    if stability == "A":
        return 0.22 * distance_m, 0.20 * distance_m
    if stability == "B":
        return 0.22 * distance_m / sqrt(1 + 0.0001 * distance_m), 0.20 * distance_m
    if stability in {"C", "D"}:
        return 0.32 * distance_m / sqrt(1 + 0.0004 * distance_m), 0.22 * distance_m
    if stability == "E":
        return 0.32 * distance_m / sqrt(1 + 0.001 * distance_m), 0.10 * distance_m
    return 0.32 * distance_m / sqrt(1 + 0.001 * distance_m), 0.06 * distance_m


def dispersion_weight(
    *,
    distance_km: float,
    angle_difference_deg: float,
    wind_speed_ms: float,
    historical_wind_speed_ms: float,
    stability: str | None,
) -> float:
    """Gaussian dispersion diagnostic without emissions or effective source height."""
    distance_m = max(distance_km * 1000, 1.0)
    sigma_y, sigma_z = dispersion_sigmas(distance_m, stability)
    lateral_offset_m = distance_m * sin(radians(angle_difference_deg))
    # Distance already enters through sigma_y and sigma_z. An additional 1/d^2
    # term would double-count distance and overwhelm every other evidence item.
    _ = historical_wind_speed_ms
    return (
        1 / (max(wind_speed_ms, 0.5) * sigma_y * sigma_z)
        * exp(-(lateral_offset_m**2) / (2 * sigma_y**2))
    )
