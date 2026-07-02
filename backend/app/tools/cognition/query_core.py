from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

from app.agent.cognition.models import ExtractionResult
from app.api.cognitive_map_routes import _enabled_binding_map_ids
from app.utils.path_config import get_data_registry


def default_cognitive_maps_root() -> Path:
    return get_data_registry() / "cognitive_maps"


def clean_list(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def selected_map_ids(
    *,
    cognitive_maps_root: Path,
    agent_mode: str,
    map_ids: list[str] | str | None,
) -> list[str]:
    ids = clean_list(map_ids)
    if ids:
        return ids
    if cognitive_maps_root == default_cognitive_maps_root():
        return _enabled_binding_map_ids(agent_mode)
    bindings_path = cognitive_maps_root / "agent_bindings.json"
    if not bindings_path.exists():
        return []
    bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    enabled = [
        item
        for item in bindings
        if item.get("agent_mode") == agent_mode and item.get("enabled", True)
    ]
    enabled.sort(key=lambda item: (item.get("priority", 100), item.get("updated_at", "")))
    return [item["map_id"] for item in enabled if item.get("map_id")]


def load_extraction(cognitive_maps_root: Path, map_id: str) -> ExtractionResult | None:
    path = cognitive_maps_root / map_id / "extraction.json"
    if not path.exists():
        return None
    return ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))


def entity_payload(entity: Any, map_id: str) -> dict[str, Any]:
    return {
        "map_id": map_id,
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "name": entity.name,
        "canonical_name": entity.canonical_name,
        "aliases": list(entity.aliases or []),
        "description": entity.description,
        "attributes": dict(entity.attributes or {}),
        "review_status": entity.review_status,
    }


def relation_payload(relation: Any, entity_by_id: dict[str, Any], map_id: str) -> dict[str, Any]:
    source = entity_by_id.get(relation.source_entity_id)
    target = entity_by_id.get(relation.target_entity_id)
    return {
        "map_id": map_id,
        "relation_id": relation.relation_id,
        "relation_type": relation.relation_type,
        "source_entity_id": relation.source_entity_id,
        "source_name": source.name if source else relation.source_entity_id,
        "source_entity_type": source.entity_type if source else "",
        "target_entity_id": relation.target_entity_id,
        "target_name": target.name if target else relation.target_entity_id,
        "target_entity_type": target.entity_type if target else "",
        "description": relation.description,
        "attributes": dict(relation.attributes or {}),
        "review_status": relation.review_status,
    }


def value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(value_matches(actual, item) for item in expected)
    return str(actual) == str(expected)


def entity_matches(
    entity: Any,
    *,
    entity_type: str | None,
    entity_names: list[str],
    name_contains: str | None,
    attribute_filters: dict[str, Any] | None,
) -> bool:
    if entity_type and entity.entity_type != entity_type:
        return False
    if entity_names:
        names = [entity.name, entity.canonical_name, *(entity.aliases or []), entity.entity_id]
        if not any(any(value_matches(name, hint) for name in names if name) for hint in entity_names):
            return False
    if name_contains:
        haystack = " ".join([entity.name or "", entity.canonical_name or "", *(entity.aliases or [])])
        if name_contains not in haystack:
            return False
    for key, expected in (attribute_filters or {}).items():
        if not value_matches((entity.attributes or {}).get(key), expected):
            return False
    return True


def find_start_entities(
    entities: list[Any],
    start_entity: str,
) -> list[Any]:
    text = str(start_entity or "").strip()
    if not text:
        return []
    matched = []
    for entity in entities:
        names = [entity.entity_id, entity.name, entity.canonical_name, *(entity.aliases or [])]
        if any(str(name or "") == text for name in names):
            matched.append(entity)
    if matched:
        return matched
    for entity in entities:
        attrs = entity.attributes or {}
        attr_values = [str(value) for value in attrs.values() if value is not None]
        if any(value == text for value in attr_values):
            matched.append(entity)
    if matched:
        return matched
    return [
        entity
        for entity in entities
        if text in " ".join(str(value or "") for value in [entity.name, entity.canonical_name, *(entity.aliases or [])])
    ]


def traverse_relations(
    *,
    start_entities: list[Any],
    relations: list[Any],
    entity_by_id: dict[str, Any],
    relation_type: str | None,
    direction: str,
    depth: int,
    target_entity_type: str | None,
    limit: int,
) -> tuple[list[Any], list[list[Any]]]:
    depth = max(1, int(depth or 1))
    limit = max(1, int(limit or 50))
    outgoing: dict[str, list[Any]] = {}
    incoming: dict[str, list[Any]] = {}
    for relation in relations:
        if relation_type and relation.relation_type != relation_type:
            continue
        outgoing.setdefault(relation.source_entity_id, []).append(relation)
        incoming.setdefault(relation.target_entity_id, []).append(relation)

    queue = deque((entity.entity_id, [], 0) for entity in start_entities)
    seen_states: set[tuple[str, int]] = set()
    result_entities: dict[str, Any] = {}
    result_paths: list[list[Any]] = []
    start_ids = {entity.entity_id for entity in start_entities}

    while queue and len(result_entities) < limit:
        entity_id, path, cur_depth = queue.popleft()
        state = (entity_id, cur_depth)
        if state in seen_states:
            continue
        seen_states.add(state)
        if cur_depth >= depth:
            continue

        candidate_relations: list[Any] = []
        if direction in {"outgoing", "both"}:
            candidate_relations.extend(outgoing.get(entity_id, []))
        if direction in {"incoming", "both"}:
            candidate_relations.extend(incoming.get(entity_id, []))

        for relation in candidate_relations:
            if direction == "incoming" and relation.target_entity_id == entity_id:
                next_id = relation.source_entity_id
            elif direction == "outgoing" and relation.source_entity_id == entity_id:
                next_id = relation.target_entity_id
            elif direction == "both":
                next_id = relation.target_entity_id if relation.source_entity_id == entity_id else relation.source_entity_id
            else:
                continue

            next_entity = entity_by_id.get(next_id)
            if not next_entity:
                continue
            next_path = [*path, relation]
            if next_entity.entity_id not in start_ids and (
                not target_entity_type or next_entity.entity_type == target_entity_type
            ):
                result_entities.setdefault(next_entity.entity_id, next_entity)
                result_paths.append(next_path)
                if len(result_entities) >= limit:
                    break
            queue.append((next_entity.entity_id, next_path, cur_depth + 1))

    return list(result_entities.values()), result_paths
