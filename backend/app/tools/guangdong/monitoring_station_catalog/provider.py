"""广东监测体系站点地理目录（query / 监测问数子模式专用）。

数据源：监测平台站点地理快照（`station_district_results_with_type_id.json`，
经 `GeoMappingResolver` 加载，与 `query_gd_suncere_*` 取数工具同源）。
返回监测平台唯一编码、站点名称、城市/区县归属、站点类型与经纬度。
与运维体系（`guangdong_station_catalog`，dim_station 台账）和组分体系
（`component_station_catalog`，geo_mappings）是相互独立的三套站点体系。
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.station_directory import (
    STATION_TYPE_NAME_BY_ID,
    StationCategory,
    StationDirectoryProvider,
    StationQuery,
    StationRecord,
    matches_query,
)

logger = structlog.get_logger()

# 行政区划码前 4 位 → 地级市（admin_code 是监测平台快照里最可靠的归属字段，
# 快照的城市字段有少量错误，实测 452 站中 9 站与行政区划码冲突）。
_CITY_BY_ADMIN_PREFIX: dict[str, str] = {
    "4401": "广州市",
    "4402": "韶关市",
    "4403": "深圳市",
    "4404": "珠海市",
    "4405": "汕头市",
    "4406": "佛山市",
    "4407": "江门市",
    "4408": "湛江市",
    "4409": "茂名市",
    "4412": "肇庆市",
    "4413": "惠州市",
    "4414": "梅州市",
    "4415": "汕尾市",
    "4416": "河源市",
    "4417": "阳江市",
    "4418": "清远市",
    "4419": "东莞市",
    "4420": "中山市",
    "4451": "潮州市",
    "4452": "揭阳市",
    "4453": "云浮市",
}

# 快照中既无行政区划码也无城市字段的少量站点（含移动监测车），按台账
# 交叉核对或站名补全城市；流动监测车无固定城市，保持空值。
_CITY_NAME_FALLBACK: dict[str, str] = {
    "新丰": "韶关市",
    "梅华": "珠海市",
    "浈江": "韶关市",
    "乐昌": "韶关市",
    "河源监测车": "河源市",
    "肇庆监测车": "肇庆市",
    "潮南峡山(组分)": "汕头市",
    "鹤山花果山(组分网)": "江门市",
    "440784001R": "江门市",
    "东澳岛": "珠海市",
    "临江": "肇庆市",
    "下埔": "惠州市",
    "东城": "东莞市",
    "中山公园": "汕头市",
    "北中村委": "汕头市",
    "南澳白牛岭": "汕头市",
    "市生态环境局": "茂名市",
    "广宁南东": "肇庆市",
    "梅江北联": "梅州市",
    "莲花山": "深圳市",
}


class MonitoringStationCatalogProvider(StationDirectoryProvider):
    """监测体系（监测平台站点地理快照）站点目录 provider。"""

    name = "monitoring_station_catalog"

    def __init__(self) -> None:
        self._records: list[StationRecord] | None = None

    async def list_stations(self, query: StationQuery | None = None) -> list[StationRecord]:
        return [record for record in self._load() if matches_query(record, query)]

    def _load(self) -> list[StationRecord]:
        if self._records is not None:
            return self._records
        from app.tools.query.query_gd_suncere.tool import GeoMappingResolver

        GeoMappingResolver._load_station_data_from_json()
        codes = GeoMappingResolver._station_code_map_from_json
        meta_map = GeoMappingResolver._station_meta_map
        records: list[StationRecord] = []
        for name, code in codes.items():
            meta: dict[str, Any] = meta_map.get(code) or {}
            admin_code = str(meta.get("admin_code") or "").strip()
            city = _CITY_BY_ADMIN_PREFIX.get(admin_code[:4], "")
            if not city:
                city = str(meta.get("city") or "").strip()
                if city and not city.endswith("市"):
                    city = f"{city}市"
            if not city:
                city = _CITY_NAME_FALLBACK.get(name, "")
            type_id_raw = meta.get("type_id")
            try:
                type_id = int(float(type_id_raw)) if type_id_raw not in (None, "") else None
            except (TypeError, ValueError):
                type_id = None
            station_type = STATION_TYPE_NAME_BY_ID.get(type_id, "") if type_id is not None else ""
            records.append(
                StationRecord(
                    station_code=str(code or "").strip(),
                    station_name=name,
                    city=city,
                    district=str(meta.get("district") or "").strip(),
                    longitude=_to_float(meta.get("lng")),
                    latitude=_to_float(meta.get("lat")),
                    address=str(meta.get("address") or "").strip(),
                    admin_code=admin_code,
                    station_type=station_type,
                    type_id=type_id,
                    station_category=(
                        StationCategory.TOWNSHIP.value
                        if type_id == 5
                        else StationCategory.REGULAR.value
                    ),
                    source="monitoring:station_geo_snapshot",
                )
            )
        records.sort(key=lambda item: (item.city, item.district, item.station_name))
        self._records = records
        logger.info("monitoring_station_catalog_loaded", stations=len(records))
        return records


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
