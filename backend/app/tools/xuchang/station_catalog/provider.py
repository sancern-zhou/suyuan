"""许昌站点目录 provider

把 `catalog.py` 的目录构建/解析接入共享的 ``StationDirectoryProvider`` 契约，
让 ``xuchang_station_catalog`` 工具与共享层走同一条数据路径。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.services.station_directory import (
    StationDirectoryProvider,
    StationQuery,
    StationRecord,
    matches_query,
)

from .catalog import iter_stations, load_catalog, resolve_stations


class XuchangStationCatalogProvider(StationDirectoryProvider):
    """许昌站点目录 provider（中台目录 + SQL Server 坐标补全）。"""

    name = "xuchang_station_catalog"

    def __init__(
        self,
        catalog_loader: Callable[[bool], dict[str, Any]] = load_catalog,
    ) -> None:
        self._catalog_loader = catalog_loader

    async def load_catalog(self, refresh: bool = False) -> dict[str, Any]:
        return await asyncio.to_thread(self._catalog_loader, bool(refresh))

    async def list_stations(self, query: StationQuery | None = None) -> list[StationRecord]:
        catalog = await self.load_catalog()
        records = [self._to_record(item) for item in iter_stations(catalog, "all")]
        return [record for record in records if matches_query(record, query)]

    async def resolve_legacy(
        self,
        *,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        districts: list[str] | None = None,
        station_type: str = "all",
        refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """按工具既有契约解析站点，返回（目录条目, 目录快照）。"""
        catalog = await self.load_catalog(refresh)
        items = resolve_stations(
            catalog,
            station_names=stations,
            station_codes=station_codes,
            districts=districts,
            station_type=station_type,
        )
        return items, catalog

    @staticmethod
    def _to_record(item: dict[str, Any]) -> StationRecord:
        return StationRecord.from_mapping(item, source=str(item.get("data_source") or ""))
