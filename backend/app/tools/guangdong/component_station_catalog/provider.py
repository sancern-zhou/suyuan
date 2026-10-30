"""广东组分体系站点地理目录（query_component 专用）。

数据源：`geo_mappings.json`（超站组分站点编码，格式如 1004b）及其
`station_geo` 城市/区县归属、`station_capabilities` 每站组分监测能力标注
（`vocs`=VOCs 组分、`pm25`=PM2.5 组分，按接口原始数据实测维护）。
站点编码此前只用于组分接口取数，城市归属在此补齐后，组分问数才能按城市
展开站点；能力标注用于回答"某城市有无 VOCs/颗粒物组分站"——两者不是
同一批站（VOCs 监测网仅覆盖少数珠三角站点）。
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.station_directory import (
    StationDirectoryProvider,
    StationQuery,
    StationRecord,
    matches_query,
)
from app.utils.particulate_geo_matcher import _get_geo_mappings_path, load_capability_map

logger = structlog.get_logger()


class ComponentStationCatalogProvider(StationDirectoryProvider):
    """组分体系（geo_mappings）站点目录 provider。"""

    name = "component_station_catalog"

    def __init__(self) -> None:
        self._records: list[StationRecord] | None = None

    async def list_stations(self, query: StationQuery | None = None) -> list[StationRecord]:
        return [record for record in self._load() if matches_query(record, query)]

    def _load(self) -> list[StationRecord]:
        if self._records is not None:
            return self._records
        path = _get_geo_mappings_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        stations: dict[str, str] = data.get("stations") or {}
        geo: dict[str, dict[str, Any]] = data.get("station_geo") or {}
        capabilities = load_capability_map()
        records: list[StationRecord] = []
        for name, code in stations.items():
            city_info = geo.get(name) or {}
            records.append(
                StationRecord(
                    station_code=str(code or "").strip(),
                    station_name=name,
                    city=str(city_info.get("city") or "").strip(),
                    district=str(city_info.get("district") or "").strip(),
                    station_category="component",
                    data_domains=capabilities.get(name, ()),
                    source="component:geo_mappings",
                )
            )
        records.sort(key=lambda item: (item.city, item.district, item.station_name))
        self._records = records
        logger.info("component_station_catalog_loaded", path=str(path), stations=len(records))
        return records

    def cities(self) -> list[str]:
        seen: list[str] = []
        for record in self._load():
            if record.city and record.city not in seen:
                seen.append(record.city)
        return seen
