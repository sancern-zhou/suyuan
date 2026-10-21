"""Provider contract for the shared station directory layer.

A provider owns exactly one data source (air data platform, provincial API,
checked-in table, ...) and converts it into canonical :class:`StationRecord`
values.  Tools and services talk to the provider through this interface only,
so a project can swap its directory backend without changing any tool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .geo import compass_direction_8, haversine_km
from .models import StationRecord


def _clean(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return tuple(cleaned)


@dataclass(frozen=True)
class StationQuery:
    """Declarative filter passed to a provider."""

    station_names: tuple[str, ...] = ()
    station_codes: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    districts: tuple[str, ...] = ()
    station_types: tuple[str, ...] = ()
    station_categories: tuple[str, ...] = ()
    limit: int | None = None

    @classmethod
    def create(
        cls,
        *,
        station_names: Iterable[Any] | None = None,
        station_codes: Iterable[Any] | None = None,
        cities: Iterable[Any] | None = None,
        districts: Iterable[Any] | None = None,
        station_types: Iterable[Any] | None = None,
        station_categories: Iterable[Any] | None = None,
        limit: int | None = None,
    ) -> StationQuery:
        return cls(
            station_names=_clean(station_names),
            station_codes=_clean(station_codes),
            cities=_clean(cities),
            districts=_clean(districts),
            station_types=_clean(station_types),
            station_categories=_clean(station_categories),
            limit=limit,
        )

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.station_names,
                self.station_codes,
                self.cities,
                self.districts,
                self.station_types,
                self.station_categories,
            )
        )


@dataclass(frozen=True)
class NearbyStation:
    """A station together with its distance and direction from a reference."""

    station: StationRecord
    distance_km: float
    direction: str


@dataclass
class StationResolution:
    """Result of resolving user-supplied names and codes against a provider."""

    stations: list[StationRecord] = field(default_factory=list)
    unresolved_names: list[str] = field(default_factory=list)
    unresolved_codes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return bool(self.stations) and not self.unresolved_names and not self.unresolved_codes


def _location_match(value: str, wanted: Sequence[str]) -> bool:
    if not wanted:
        return True
    text = str(value or "").strip()
    if not text:
        return False
    return any(
        text == item or text.startswith(item) or item.startswith(text) for item in wanted if item
    )


def matches_query(station: StationRecord, query: StationQuery | None) -> bool:
    """Return whether ``station`` satisfies every field group in ``query``."""

    if query is None or query.is_empty:
        return True

    if query.station_codes or query.station_names:
        code_hit = bool(query.station_codes) and (
            station.station_code in query.station_codes
            or station.unique_code in query.station_codes
        )
        name_hit = bool(query.station_names) and any(
            item == station.station_name
            or item in station.station_name
            or station.station_name.endswith(item)
            for item in query.station_names
        )
        if not (code_hit or name_hit):
            return False

    if not _location_match(station.city, query.cities):
        return False
    if not _location_match(station.district, query.districts):
        return False
    if query.station_types and station.station_type not in query.station_types:
        return False
    if query.station_categories and station.station_category not in query.station_categories:
        return False
    return True


class StationDirectoryProvider(ABC):
    """Base class every project station directory provider must implement."""

    name: str = "station_directory"

    @abstractmethod
    async def list_stations(self, query: StationQuery | None = None) -> list[StationRecord]:
        """Return every station matching ``query`` (all stations when ``None``)."""

    async def get_station(self, station_code: str) -> StationRecord | None:
        code = str(station_code or "").strip()
        if not code:
            return None
        for station in await self.list_stations(StationQuery(station_codes=(code,))):
            if station.station_code == code or station.unique_code == code:
                return station
        return None

    async def resolve(self, query: StationQuery | None = None) -> StationResolution:
        query = query or StationQuery()
        stations = await self.list_stations(query)

        resolved_codes: set[str] = set()
        for station in stations:
            resolved_codes.add(station.station_code)
            if station.unique_code:
                resolved_codes.add(station.unique_code)
        unresolved_codes = [code for code in query.station_codes if code not in resolved_codes]

        unresolved_names: list[str] = []
        for name in query.station_names:
            if not any(
                name == station.station_name
                or name in station.station_name
                or station.station_name.endswith(name)
                for station in stations
            ):
                unresolved_names.append(name)

        return StationResolution(
            stations=stations,
            unresolved_names=unresolved_names,
            unresolved_codes=unresolved_codes,
            metadata={
                "provider": self.name,
                "station_count": len(stations),
            },
        )

    async def nearby(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        query: StationQuery | None = None,
    ) -> list[NearbyStation]:
        stations = await self.list_stations(query or StationQuery())
        results: list[NearbyStation] = []
        for station in stations:
            if station.longitude is None or station.latitude is None:
                continue
            distance = haversine_km(latitude, longitude, station.latitude, station.longitude)
            if distance <= radius_km:
                results.append(
                    NearbyStation(
                        station=station,
                        distance_km=round(distance, 3),
                        direction=compass_direction_8(
                            latitude, longitude, station.latitude, station.longitude
                        ),
                    )
                )
        results.sort(key=lambda item: item.distance_km)
        return results
