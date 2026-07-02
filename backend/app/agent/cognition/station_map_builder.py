from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agent.cognition.models import (
    CandidateEntity,
    CandidateRelation,
    CognitiveSchema,
    Evidence,
    ExtractionDiagnostic,
    ExtractionResult,
    lightweight_extraction,
    lightweight_extraction_payload,
)
from app.utils.path_config import get_data_registry


STATION_MAP_ID = "cm_guangdong_monitoring_stations"
STATION_MAP_NAME = "广东省环境空气监测站点"
STATION_SOURCE_FILE_ID = "file_guangdong_station_registry"

POLLUTANTS = ("PM2.5", "PM10", "O3", "NO2", "SO2", "CO")


def _default_cognitive_maps_root() -> Path:
    return get_data_registry() / "cognitive_maps"


def _default_station_file() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "config" / "station_district_results_with_type_id.json"
        if candidate.exists():
            return candidate
        candidate = parent / "backend" / "config" / "station_district_results_with_type_id.json"
        if candidate.exists():
            return candidate
    return Path("backend/config/station_district_results_with_type_id.json")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_station_records(station_file: Path) -> list[dict[str, Any]]:
    payload = json.loads(station_file.read_text(encoding="utf-8"))
    records = payload.get("data") if isinstance(payload, dict) else payload
    return [record for record in records or [] if isinstance(record, dict)]


def _type_name(type_id: Any) -> str:
    names = {
        1.0: "国控",
        2.0: "省控",
        3.0: "市控",
        4.0: "区县控",
        5.0: "乡镇控",
        6.0: "其他",
        7.0: "背景站",
        8.0: "区域站",
        9.0: "交通站",
        15.0: "专项站",
    }
    try:
        key = float(type_id)
    except (TypeError, ValueError):
        return "未知"
    return names.get(key, f"类型{key:g}")


def _entity_id(prefix: str, value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value).strip("_")
    if not safe:
        safe = "unknown"
    return f"{prefix}_{safe}"


def _schema() -> CognitiveSchema:
    schema = CognitiveSchema.default_air_quality_schema()
    triplets = set(schema.allowed_relation_triplets)
    for triplet in [
        ("Station", "located_in", "Region"),
        ("Region", "located_in", "Region"),
        ("Station", "measures", "Pollutant"),
        ("Station", "belongs_to_category", "Metric"),
        ("Station", "uses_method", "Tool"),
        ("Tool", "requires_data", "Station"),
        ("Tool", "produces", "Dataset"),
    ]:
        triplets.add(triplet)
    schema.allowed_relation_triplets = sorted(triplets)
    schema.domain_aliases.setdefault("PM2.5", ["PM25", "细颗粒物"])
    schema.domain_aliases.setdefault("站点地理属性", ["站点经纬度", "站点坐标", "站点位置"])
    return schema


def _build_extraction(map_id: str, station_file: Path) -> ExtractionResult:
    records = _load_station_records(station_file)
    entities: dict[str, CandidateEntity] = {}
    relations: list[CandidateRelation] = []
    evidence: list[Evidence] = []

    def add_entity(entity: CandidateEntity) -> None:
        entities.setdefault(entity.entity_id, entity)

    source_evidence_id = "ev_station_registry"
    evidence.append(
        Evidence(
            evidence_id=source_evidence_id,
            map_id=map_id,
            source_file_id=STATION_SOURCE_FILE_ID,
            chunk_id="chunk_station_registry",
            location=str(station_file),
            text_span="广东省环境空气监测站点基础属性表，包含站点名称、编码、城市、区县、经纬度、地址和站点类型。",
            normalized_summary="站点基础属性表提供可用于问数地图定位和图层渲染的确定性站点地理属性。",
            quote="站点名称、唯一编码、城市名称、区县、经度、纬度、详细地址、站点类型ID",
            support_type="source_registry",
            evidence_quality="deterministic_structured_source",
        )
    )

    for pollutant in POLLUTANTS:
        add_entity(
            CandidateEntity(
                entity_id=_entity_id("pollutant", pollutant),
                map_id=map_id,
                entity_type="Pollutant",
                name=pollutant,
                canonical_name=pollutant,
                aliases=[pollutant.replace(".", "_")] if "." in pollutant else [],
                review_status="published",
            )
        )

    resolve_tool_id = "tool_resolve_station_geo"
    dataset_id = "dataset_guangdong_station_registry"
    add_entity(
        CandidateEntity(
            entity_id=resolve_tool_id,
            map_id=map_id,
            entity_type="Tool",
            name="resolve_station_geo",
            canonical_name="resolve_station_geo",
            description="按站点名称或编码解析站点经纬度、城市、区县和类型。",
            review_status="published",
        )
    )
    add_entity(
        CandidateEntity(
            entity_id=dataset_id,
            map_id=map_id,
            entity_type="Dataset",
            name="广东省站点地理属性表",
            canonical_name="广东省站点地理属性表",
            attributes={"source_file": str(station_file), "station_count": len(records)},
            review_status="published",
        )
    )

    seen_relation_keys: set[tuple[str, str, str]] = set()
    seen_station_ids: set[str] = set()

    def add_relation(source_id: str, relation_type: str, target_id: str, description: str) -> None:
        key = (source_id, relation_type, target_id)
        if key in seen_relation_keys:
            return
        seen_relation_keys.add(key)
        relations.append(
            CandidateRelation(
                relation_id=f"rel_{len(relations) + 1:06d}",
                map_id=map_id,
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation_type,
                description=description,
                review_status="published",
            )
        )

    add_relation(resolve_tool_id, "requires_data", dataset_id, "站点地理解析工具依赖广东省站点地理属性表。")

    province_id = _entity_id("region_province", "广东省")
    add_entity(
        CandidateEntity(
            entity_id=province_id,
            map_id=map_id,
            entity_type="Region",
            name="广东省",
            canonical_name="广东省",
            aliases=["广东"],
            attributes={"region_kind": "province"},
            review_status="published",
        )
    )

    for record in records:
        station_name = str(record.get("站点名称") or "").strip()
        station_code = str(record.get("唯一编码") or "").strip()
        if not station_name or not station_code:
            continue
        city = str(record.get("城市名称") or "").strip()
        district_raw = record.get("区县")
        district = district_raw.strip() if isinstance(district_raw, str) else ""
        type_id = record.get("站点类型ID")
        station_id = _entity_id("station", station_code)
        if station_id in seen_station_ids:
            continue
        seen_station_ids.add(station_id)
        station_entity = CandidateEntity(
            entity_id=station_id,
            map_id=map_id,
            entity_type="Station",
            name=station_name,
            canonical_name=station_name,
            aliases=[station_code],
            attributes={
                "station_code": station_code,
                "city": city,
                "district": district,
                "longitude": record.get("经度"),
                "latitude": record.get("纬度"),
                "address": record.get("详细地址", ""),
                "admin_code": record.get("行政区划代码", ""),
                "type_id": type_id,
                "type_name": _type_name(type_id),
            },
            review_status="published",
        )
        add_entity(station_entity)
        add_relation(resolve_tool_id, "produces", station_id, "站点地理解析工具返回站点空间实体属性。")

        city_id = ""
        district_id = ""
        if city:
            city_id = _entity_id("region_city", city)
            add_entity(
                CandidateEntity(
                    entity_id=city_id,
                    map_id=map_id,
                    entity_type="Region",
                    name=city,
                    canonical_name=city,
                    attributes={"region_kind": "city"},
                    review_status="published",
                )
            )
            add_relation(city_id, "located_in", province_id, f"{city} 位于广东省。")

        if district:
            district_key = f"{city}_{district}" if city else district
            district_id = _entity_id("region_district", district_key)
            add_entity(
                CandidateEntity(
                    entity_id=district_id,
                    map_id=map_id,
                    entity_type="Region",
                    name=district,
                    canonical_name=f"{city}{district}" if city else district,
                    attributes={"region_kind": "district", "city": city},
                    review_status="published",
                )
            )
            if city_id:
                add_relation(district_id, "located_in", city_id, f"{district} 位于 {city}。")

        location_target_id = district_id or city_id or province_id
        location_name = district or city or "广东省"
        add_relation(station_id, "located_in", location_target_id, f"{station_name} 位于 {location_name}。")

        for pollutant in POLLUTANTS:
            add_relation(station_id, "measures", _entity_id("pollutant", pollutant), f"{station_name} 可用于 {pollutant} 站点指标分析。")

    return ExtractionResult(
        map_id=map_id,
        candidate_entities=list(entities.values()),
        candidate_relations=relations,
        evidence=evidence,
        diagnostics=ExtractionDiagnostic(
            provider_name="station_registry_builder",
            provider_version="0.1",
            status="success",
            messages=[f"Loaded {len(records)} station records from {station_file}"],
        ),
    )


def ensure_station_cognitive_map(
    *,
    root: Path | None = None,
    station_file: Path | None = None,
    agent_mode: str = "query",
) -> dict[str, Any]:
    root = root or _default_cognitive_maps_root()
    station_file = station_file or _default_station_file()
    map_dir = root / STATION_MAP_ID
    now = datetime.utcnow().isoformat()
    extraction = _build_extraction(STATION_MAP_ID, station_file)

    meta = {
        "id": STATION_MAP_ID,
        "name": STATION_MAP_NAME,
        "description": "广东省环境空气监测站点空间实体、行政归属、监测污染物与站点地理属性解析工具关系。",
        "status": "published",
        "created_at": now,
        "updated_at": now,
        "parser_provider": "structured_station_registry",
        "requested_extractor_provider": "deterministic",
        "extractor_provider": "station_registry_builder",
        "llm_provider": None,
        "build_requirement": "用于问数模式站点空间分析、站点地图定位、最高污染物站点上图和周边溯源分析。",
        "build_error": None,
    }
    files = [
        {
            "file_id": STATION_SOURCE_FILE_ID,
            "map_id": STATION_MAP_ID,
            "filename": station_file.name,
            "content_type": "application/json",
            "storage_path": str(station_file),
            "metadata": {"source": "station_registry", "station_count": len(_load_station_records(station_file))},
            "created_at": now,
        }
    ]
    persisted_extraction = lightweight_extraction(extraction)
    evaluation = {
        "map_id": STATION_MAP_ID,
        "entity_count": len(persisted_extraction.candidate_entities),
        "relation_count": len(persisted_extraction.candidate_relations),
        "confirmed_entity_count": len(persisted_extraction.candidate_entities),
        "confirmed_relation_count": len(persisted_extraction.candidate_relations),
        "usable_for_agent": True,
        "property_graph_persisted": False,
        "generated_at": now,
        "diagnostic": persisted_extraction.diagnostics.model_dump(mode="json"),
    }
    binding = {
        "binding_id": "cmb_guangdong_monitoring_stations_query",
        "map_id": STATION_MAP_ID,
        "agent_mode": agent_mode,
        "enabled": True,
        "priority": 1,
        "description": "问数模式站点空间实体认知地图绑定",
        "created_at": now,
        "updated_at": now,
    }

    map_dir.mkdir(parents=True, exist_ok=True)
    _write_json(map_dir / "map.json", meta)
    _write_json(map_dir / "files.json", files)
    _write_json(map_dir / "schema.json", _schema().model_dump(mode="json"))
    _write_json(map_dir / "extraction.json", lightweight_extraction_payload(extraction))
    _write_json(map_dir / "evaluation.json", evaluation)
    _write_json(map_dir / "build_runs.json", [{
        "run_id": "run_guangdong_monitoring_stations",
        "status": "completed",
        "parser_provider": "structured_station_registry",
        "extractor_provider": "station_registry_builder",
        "file_count": 1,
        "entity_count": len(persisted_extraction.candidate_entities),
        "relation_count": len(persisted_extraction.candidate_relations),
        "started_at": now,
        "finished_at": now,
        "duration_ms": 0,
    }])

    bindings_path = root / "agent_bindings.json"
    existing = json.loads(bindings_path.read_text(encoding="utf-8")) if bindings_path.exists() else []
    existing = [
        item for item in existing
        if not (item.get("map_id") == STATION_MAP_ID and item.get("agent_mode") == agent_mode)
    ]
    existing.append(binding)
    existing.sort(key=lambda item: (item.get("agent_mode", ""), item.get("priority", 100), item.get("map_id", "")))
    _write_json(bindings_path, existing)

    return {
        "map_id": STATION_MAP_ID,
        "map_dir": str(map_dir),
        "entity_count": len(extraction.candidate_entities),
        "relation_count": len(extraction.candidate_relations),
        "binding": binding,
    }


if __name__ == "__main__":
    print(json.dumps(ensure_station_cognitive_map(), ensure_ascii=False, indent=2))
