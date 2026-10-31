# -*- coding: utf-8 -*-
"""站点实体图谱种子（运行时数据，不入提交的种子 JSON）。

gen_graph_seed.py 的种子只含数据语义资产（域/表/指标/工具），保证跨机器可复现
与 --check 漂移检测；站点台账来自 guangdong_mart.dim_station 运行时数据，
由 graph_seed_sync.py 在同步时经本模块并入图谱。

实体：Station（432 站）/ Region（地市）/ OperationUnit（运维单位）
关系：located_in（站->市）、managed_by（站->运维单位，组分站缺口如实保留）、
      belongs_to（站 -> 站点与组织域，与 gen_graph_seed 的域实体共用）。
"""
from __future__ import annotations

DOMAIN_STATION = "domain_站点与组织"


async def build_station_seed(refresh: bool = False) -> tuple[list[dict], list[dict], dict]:
    """从站点目录构建站点实体与关系，返回（实体, 关系, 统计）。"""
    from app.tools.guangdong.station_catalog.catalog import load_catalog

    catalog = await load_catalog(refresh)
    return build_station_seed_from_catalog(catalog)


def build_station_seed_from_catalog(
    catalog: dict,
) -> tuple[list[dict], list[dict], dict]:
    """纯函数：按目录快照构建站点实体与关系（便于测试）。"""
    stations = catalog.get("stations") or []

    entities: list[dict] = []
    relations: list[dict] = []
    seen_local_ids: set[str] = set()
    city_local_ids: dict[str, str] = {}
    unit_local_ids: dict[str, str] = {}

    def _add(entity: dict) -> None:
        if entity["local_id"] in seen_local_ids:
            return
        seen_local_ids.add(entity["local_id"])
        entities.append(entity)

    for item in stations:
        station_name = str(item.get("station_name") or "").strip()
        station_code = str(item.get("station_code") or "").strip()
        station_id = str(item.get("station_id") or "").strip()
        if not station_name:
            continue
        city_name = str(item.get("city_name") or "").strip()
        station_type = str(item.get("station_type_name") or "").strip()
        operation_unit = str(item.get("operation_unit_name") or "").strip()

        if city_name:
            city_local_id = city_local_ids.get(city_name)
            if city_local_id is None:
                city_local_id = f"city_{city_name}"
                city_local_ids[city_name] = city_local_id
                city_aliases = [city_name]
                short_name = city_name[:-1] if city_name.endswith("市") else ""
                if short_name and short_name not in city_aliases:
                    city_aliases.append(short_name)
                _add({
                    "local_id": city_local_id,
                    "entity_type": "Region",
                    "name": city_name,
                    "aliases": city_aliases,
                    "description": "广东省地市",
                    "attributes": {"city_code": str(item.get("city_code") or "")},
                    "evidence_text": city_name,
                })

        aliases = [alias for alias in (station_code, station_id) if alias]
        attributes = {
            "station_code": station_code,
            "city": city_name,
            "station_type": station_type,
        }
        category = str(item.get("station_category") or "").strip()
        if category:
            attributes["station_category"] = category
        description_parts = [f"{city_name}站点".strip()] if city_name else []
        if station_type:
            description_parts.append(f"类型 {station_type}")
        if operation_unit:
            description_parts.append(f"运维单位 {operation_unit}")
            attributes["operation_unit"] = operation_unit
        elif str(item.get("data_source") or "") == "component":
            description_parts.append("组分站（无运维单位信息，缺口如实声明）")
        _add({
            "local_id": f"station_{station_code or station_id}",
            "entity_type": "Station",
            "name": station_name,
            "aliases": aliases,
            "description": "，".join(part for part in description_parts if part),
            "attributes": attributes,
            "evidence_text": f"{station_name}（{station_code or station_id}）",
        })

        if city_name:
            relations.append({
                "source_local_id": f"station_{station_code or station_id}",
                "target_local_id": city_local_ids[city_name],
                "relation_type": "located_in",
                "description": f"{station_name} 位于 {city_name}",
                "evidence_text": f"{station_name} -> {city_name}",
            })
        if operation_unit:
            unit_local_id = unit_local_ids.get(operation_unit)
            if unit_local_id is None:
                unit_local_id = f"unit_{operation_unit}"
                unit_local_ids[operation_unit] = unit_local_id
                _add({
                    "local_id": unit_local_id,
                    "entity_type": "OperationUnit",
                    "name": operation_unit,
                    "aliases": [],
                    "description": "广东运维单位（dim_station 台账口径）",
                    "attributes": {},
                    "evidence_text": operation_unit,
                })
            relations.append({
                "source_local_id": f"station_{station_code or station_id}",
                "target_local_id": unit_local_id,
                "relation_type": "managed_by",
                "description": f"{station_name} 由 {operation_unit} 运维",
                "evidence_text": f"{station_name} -> {operation_unit}",
            })
        relations.append({
            "source_local_id": f"station_{station_code or station_id}",
            "target_local_id": DOMAIN_STATION,
            "relation_type": "belongs_to",
            "description": f"{station_name} 属于站点与组织数据域",
            "evidence_text": f"{station_name} -> 站点与组织",
        })

    stats = {
        "stations": sum(1 for e in entities if e["entity_type"] == "Station"),
        "cities": len(city_local_ids),
        "operation_units": len(unit_local_ids),
        "relations": len(relations),
    }
    return entities, relations, stats
