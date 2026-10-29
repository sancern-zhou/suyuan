"""广东站点目录 provider。

把 `catalog.py` 的目录构建/解析接入共享的 ``StationDirectoryProvider`` 契约，
让 ``guangdong_station_catalog`` 工具与共享层走同一条数据路径
（数据源：guangdong_mart.dim_station + dim_station_user，见 catalog.py）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.services.station_directory import (
    StationDirectoryProvider,
    StationQuery,
    StationRecord,
    matches_query,
)

from .catalog import load_catalog, resolve_stations


class GuangdongStationCatalogProvider(StationDirectoryProvider):
    """广东站点目录 provider（运维 mart 站点维度 + 人员桥表）。"""

    name = "guangdong_station_catalog"

    def __init__(
        self,
        catalog_loader: Callable[[bool], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self._catalog_loader = catalog_loader or load_catalog

    async def load_catalog(self, refresh: bool = False) -> dict[str, Any]:
        return await self._catalog_loader(bool(refresh))

    async def list_stations(self, query: StationQuery | None = None) -> list[StationRecord]:
        catalog = await self.load_catalog()
        records = [self._to_record(item) for item in catalog.get("stations") or ()]
        return [record for record in records if matches_query(record, query)]

    async def resolve_legacy(
        self,
        *,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        cities: list[str] | None = None,
        station_types: list[str] | None = None,
        operation_units: list[str] | None = None,
        managers: list[str] | None = None,
        keyword: str | None = None,
        limit: int | None = None,
        refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """按工具契约解析站点，返回（目录条目, 目录快照）。"""

        catalog = await self.load_catalog(refresh)
        items = resolve_stations(
            catalog,
            station_names=stations,
            station_codes=station_codes,
            cities=cities,
            station_types=station_types,
            operation_units=operation_units,
            managers=managers,
            keyword=keyword,
            limit=limit,
        )
        return items, catalog

    @staticmethod
    def _to_record(item: dict[str, Any]) -> StationRecord:
        return StationRecord.from_mapping(
            item,
            source=str(item.get("data_source") or ""),
            station_category=str(item.get("station_category") or "") or None,
        )
