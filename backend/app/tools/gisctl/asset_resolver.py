from __future__ import annotations

from typing import Any

from app.services.data_registry import DataRegistryEntry, data_registry


LONGITUDE_ALIASES = ("longitude", "lon", "lng", "经度")
LATITUDE_ALIASES = ("latitude", "lat", "纬度")
HIDDEN_AGENT_VISIBILITIES = {"hidden", "disabled", "manual_only", "false", "0"}
NON_AUTO_ENVIRONMENTS = {"test", "temp", "debug", "local"}
TEST_ID_MARKERS = ("_test", ":test", "test:", "map_asset_test", "map_layer_test")

SEMANTIC_ASSET_PROFILES: dict[str, dict[str, Any]] = {
    "map_layer_source.station_points": {
        "asset_type": "map_layer_source",
        "business_entity": "air_quality_station",
        "layer_kind": "point",
        "geometry": "point",
        "required_capabilities": ("lon_field", "lat_field"),
        "tool_bindings": ("gisctl.point-layer",),
    },
    "map_layer_source.pollution_sources": {
        "asset_type": "map_layer_source",
        "business_entity": "pollution_source",
        "layer_kind": "point",
        "geometry": "point",
        "required_capabilities": ("lon_field", "lat_field"),
        "tool_bindings": ("spatial_analysis", "gisctl.point-layer"),
    },
}


def _records_from_sample(sample: Any) -> list[dict[str, Any]]:
    if isinstance(sample, list):
        return [record for record in sample if isinstance(record, dict)]
    if isinstance(sample, dict):
        payload = sample.get("sample")
        if isinstance(payload, list):
            return [record for record in payload if isinstance(record, dict)]
        records = sample.get("records") or sample.get("data")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    return []


def _entry_fields(entry: DataRegistryEntry) -> set[str]:
    fields: set[str] = set()
    for stat in entry.field_stats or []:
        if isinstance(stat, dict) and stat.get("name"):
            fields.add(str(stat["name"]))
    if fields:
        return fields

    try:
        sample = data_registry.load_sample(entry.data_id)
    except Exception:
        return fields

    for record in _records_from_sample(sample)[:5]:
        fields.update(str(key) for key in record.keys())
    return fields


def _find_field(fields: set[str], aliases: tuple[str, ...]) -> str | None:
    lowered = {field.lower(): field for field in fields}
    for alias in aliases:
        if alias in fields:
            return alias
        found = lowered.get(alias.lower())
        if found:
            return found
    return None


def _text_score(text: str, terms: list[str]) -> float:
    normalized = text.lower()
    return sum(1.0 for term in terms if term and term.lower() in normalized)


def _metadata_text(entry: DataRegistryEntry) -> str:
    return " ".join(
        str(value)
        for value in [
            entry.data_id,
            entry.schema,
            entry.version,
            entry.metadata.get("description"),
            entry.metadata.get("source"),
            entry.metadata.get("query_type"),
            entry.metadata.get("asset_profile"),
            entry.metadata.get("asset_type"),
            entry.metadata.get("business_entity"),
            entry.metadata.get("domain"),
        ]
        if value is not None
    )


def _infer_asset_profile(intent: str) -> str | None:
    normalized = intent.lower()
    if any(term in normalized for term in ("污染源", "排放源", "企业排放", "pollution source", "emission")):
        return "map_layer_source.pollution_sources"
    if any(term in normalized for term in ("站点", "station")) and any(
        term in normalized for term in ("图层", "地图", "layer", "map")
    ):
        return "map_layer_source.station_points"
    return None


def _is_hidden_or_test_asset(entry: DataRegistryEntry) -> str | None:
    metadata = entry.metadata or {}
    visibility = str(metadata.get("agent_visibility", "auto_selectable")).lower()
    if visibility in HIDDEN_AGENT_VISIBILITIES:
        return f"agent_visibility={visibility}"

    environment = str(metadata.get("environment", "prod")).lower()
    if environment in NON_AUTO_ENVIRONMENTS:
        return f"environment={environment}"

    identity = f"{entry.data_id} {entry.schema}".lower()
    if any(marker in identity for marker in TEST_ID_MARKERS):
        return "test_asset_identifier"

    return None


def _entry_asset_profile(entry: DataRegistryEntry) -> str | None:
    metadata = entry.metadata or {}
    value = metadata.get("asset_profile") or metadata.get("semantic_asset_profile")
    return str(value) if value else None


def _field_from_capabilities(capabilities: dict[str, Any], key: str, fields: set[str]) -> str | None:
    value = capabilities.get(key)
    if isinstance(value, str) and value in fields:
        return value
    return None


def _candidate_for_entry(
    entry: DataRegistryEntry,
    *,
    asset_profile: str | None,
    intent_terms: list[str],
    required_fields: list[str],
    preferred_fields: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    excluded_reason = _is_hidden_or_test_asset(entry)
    if excluded_reason:
        return None, excluded_reason

    entry_profile = _entry_asset_profile(entry)
    if asset_profile and entry_profile != asset_profile:
        return None, "asset_profile_mismatch"

    fields = _entry_fields(entry)
    if not fields:
        return None, "no_fields"

    metadata = entry.metadata or {}
    capabilities = metadata.get("map_capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}

    profile_definition = SEMANTIC_ASSET_PROFILES.get(asset_profile or entry_profile or "")
    if profile_definition:
        expected_geometry = profile_definition.get("geometry")
        geometry = capabilities.get("geometry")
        if expected_geometry and geometry and geometry != expected_geometry:
            return None, "geometry_mismatch"

    longitude_field = _field_from_capabilities(capabilities, "lon_field", fields) or _find_field(fields, LONGITUDE_ALIASES)
    latitude_field = _field_from_capabilities(capabilities, "lat_field", fields) or _find_field(fields, LATITUDE_ALIASES)
    if not longitude_field or not latitude_field:
        return None, "missing_coordinates"

    missing_required = [field for field in required_fields if field not in fields]
    if missing_required:
        return None, "missing_required_fields"

    matched_preferred = [field for field in preferred_fields if field in fields]
    metadata_text = _metadata_text(entry)
    profile_bonus = 20.0 if asset_profile and entry_profile == asset_profile else 0.0
    production_bonus = 5.0 if str(metadata.get("environment", "prod")).lower() == "prod" else 0.0
    capability_bonus = 5.0 if capabilities else 0.0
    score = (
        10.0
        + profile_bonus
        + production_bonus
        + capability_bonus
        + min(entry.record_count, 1000) / 1000.0
        + len(matched_preferred) * 1.5
        + _text_score(metadata_text, intent_terms)
    )

    return {
        "data_id": entry.data_id,
        "asset_profile": entry_profile,
        "asset_type": metadata.get("asset_type"),
        "business_entity": metadata.get("business_entity"),
        "domain": metadata.get("domain"),
        "environment": metadata.get("environment", "prod"),
        "schema": entry.schema,
        "version": entry.version,
        "record_count": entry.record_count,
        "longitude_field": longitude_field,
        "latitude_field": latitude_field,
        "available_fields": sorted(fields),
        "matched_preferred_fields": matched_preferred,
        "score": round(score, 3),
        "reason": "匹配语义资产 profile，且包含地图点图层所需字段" if entry_profile else "包含经纬度字段，可生成地图点图层",
    }, None


def resolve_map_data_asset(
    *,
    intent: str,
    asset_profile: str | None = None,
    required_fields: list[str] | None = None,
    preferred_fields: list[str] | None = None,
    limit: int = 5,
    scan_limit: int = 1000,
) -> dict[str, Any]:
    required_fields = required_fields or []
    preferred_fields = preferred_fields or []
    asset_profile = asset_profile or _infer_asset_profile(intent)
    intent_terms = [term for term in intent.replace("，", " ").replace(",", " ").split() if term]

    candidates: list[dict[str, Any]] = []
    excluded_count = 0
    excluded_reasons: dict[str, int] = {}
    entries = list(data_registry._index.values())
    scanned_count = 0
    for entry in reversed(entries):
        if scanned_count >= scan_limit:
            break
        scanned_count += 1
        candidate, excluded_reason = _candidate_for_entry(
            entry,
            asset_profile=asset_profile,
            intent_terms=intent_terms,
            required_fields=required_fields,
            preferred_fields=preferred_fields,
        )
        if candidate:
            candidates.append(candidate)
        elif excluded_reason:
            excluded_count += 1
            excluded_reasons[excluded_reason] = excluded_reasons.get(excluded_reason, 0) + 1

    candidates.sort(key=lambda item: item["score"], reverse=True)
    candidates = candidates[: max(1, min(limit, 20))]
    selected = candidates[0] if candidates else None
    success = selected is not None

    return {
        "status": "success" if success else "failed",
        "success": success,
        "data": {
            "intent": intent,
            "asset_profile": asset_profile,
            "selected": selected,
            "candidates": candidates,
            "required_fields": required_fields,
            "preferred_fields": preferred_fields,
        },
        "metadata": {
            "schema_version": "map_asset_resolver.v2",
            "tool_name": "resolve_map_data_asset",
            "generator": "resolve_map_data_asset",
            "candidate_count": len(candidates),
            "excluded_count": excluded_count,
            "excluded_reasons": excluded_reasons,
            "scanned_count": scanned_count,
        },
        "summary": (
            f"Resolved map data asset {selected['data_id']}"
            if selected
            else f"No mappable data asset found for {intent}"
        ),
    }
