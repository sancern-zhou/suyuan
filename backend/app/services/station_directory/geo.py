"""Small geographic helpers shared by station directory providers."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088

COMPASS_DIRECTIONS_8: tuple[str, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

COMPASS_DIRECTIONS_16: tuple[str, ...] = (
    "北",
    "北东北",
    "东北",
    "东东北",
    "东",
    "东东南",
    "东南",
    "南东南",
    "南",
    "南西南",
    "西南",
    "西西南",
    "西",
    "西西北",
    "西北",
    "北西北",
)


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance between two coordinates in kilometres."""

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def initial_bearing_degrees(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Initial bearing from point 1 to point 2 in degrees (0-360)."""

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_direction_8(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> str:
    """Eight-point compass direction from point 1 to point 2."""

    bearing = initial_bearing_degrees(lat1, lon1, lat2, lon2)
    return COMPASS_DIRECTIONS_8[int((bearing + 22.5) // 45) % 8]


def compass_direction_16(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> str:
    """Sixteen-point compass direction from point 1 to point 2."""

    bearing = initial_bearing_degrees(lat1, lon1, lat2, lon2)
    return COMPASS_DIRECTIONS_16[int((bearing + 11.25) // 22.5) % 16]
