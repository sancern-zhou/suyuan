"""In-memory station directory provider.

Serves as the reference implementation of :class:`StationDirectoryProvider`
and as a test double.  Project providers should mirror its shape while
replacing :meth:`list_stations` with their real data source.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import StationRecord
from .provider import StationDirectoryProvider, StationQuery, matches_query


class StaticStationDirectoryProvider(StationDirectoryProvider):
    """Provider backed by a fixed list of stations held in memory."""

    def __init__(
        self,
        stations: Iterable[StationRecord | Mapping[str, object]],
        *,
        name: str = "static",
        source: str = "",
    ) -> None:
        self.name = name
        self._stations: list[StationRecord] = [
            station
            if isinstance(station, StationRecord)
            else StationRecord.from_mapping(station, source=source)
            for station in stations
        ]

    async def list_stations(self, query: StationQuery | None = None) -> list[StationRecord]:
        selected = [station for station in self._stations if matches_query(station, query)]
        if query is not None and query.limit is not None:
            return selected[: query.limit]
        return selected
