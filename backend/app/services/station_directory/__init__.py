"""Shared station directory layer.

Single source of truth for station metadata, station-type normalisation and
project-based directory providers.  Project-specific providers live on their
own branches and register into :func:`get_station_directory_registry`.
"""

from __future__ import annotations

from .cache import DEFAULT_CACHE_TTL_SECONDS, StationDirectoryCache
from .errors import StationDirectoryError, StationDirectoryNotFound
from .geo import (
    COMPASS_DIRECTIONS_8,
    COMPASS_DIRECTIONS_16,
    compass_direction_8,
    compass_direction_16,
    haversine_km,
    initial_bearing_degrees,
)
from .models import (
    ALL_STATION_TYPES,
    STATION_CATEGORY_VALUES,
    STATION_TYPE_BY_ID,
    STATION_TYPE_NAME_BY_ID,
    StationCategory,
    StationRecord,
    StationType,
    normalize_station_category,
    normalize_station_type,
    station_type_from_row,
)
from .provider import (
    NearbyStation,
    StationDirectoryProvider,
    StationQuery,
    StationResolution,
    matches_query,
)
from .registry import (
    StationDirectoryRegistry,
    get_station_directory_provider,
    get_station_directory_registry,
)
from .static import StaticStationDirectoryProvider

__all__ = [
    "ALL_STATION_TYPES",
    "COMPASS_DIRECTIONS_8",
    "COMPASS_DIRECTIONS_16",
    "DEFAULT_CACHE_TTL_SECONDS",
    "NearbyStation",
    "STATION_CATEGORY_VALUES",
    "STATION_TYPE_BY_ID",
    "STATION_TYPE_NAME_BY_ID",
    "StationCategory",
    "StationDirectoryCache",
    "StationDirectoryError",
    "StationDirectoryNotFound",
    "StationDirectoryProvider",
    "StationDirectoryRegistry",
    "StationQuery",
    "StationRecord",
    "StationResolution",
    "StationType",
    "StaticStationDirectoryProvider",
    "compass_direction_8",
    "compass_direction_16",
    "get_station_directory_provider",
    "get_station_directory_registry",
    "haversine_km",
    "initial_bearing_degrees",
    "matches_query",
    "normalize_station_category",
    "normalize_station_type",
    "station_type_from_row",
]
