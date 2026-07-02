from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.cognition.query_core import (
    default_cognitive_maps_root,
    entity_payload,
    find_start_entities,
    load_extraction,
    relation_payload,
    selected_map_ids,
    traverse_relations,
)


class CognitiveMapGraphTraverseTool(LLMTool):
    def __init__(self, cognitive_maps_root: Path | None = None) -> None:
        self.cognitive_maps_root = cognitive_maps_root or default_cognitive_maps_root()
        super().__init__(
            name="cognitive_map_graph_traverse",
            description="Traverse cognitive map graph relations from an entity with direction, relation type, depth, and target type filters.",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "cognitive_map_graph_traverse",
                "description": "认知地图关系遍历工具。用于从实体出发查关联实体，支持 incoming/outgoing/both、多跳和目标实体类型过滤。例如 广州 <- located_in <- 区县 <- located_in <- Station。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_mode": {"type": "string", "description": "Agent模式，不传 map_ids 时用该模式绑定地图，默认 query。"},
                        "map_ids": {"type": "array", "items": {"type": "string"}, "description": "可选认知地图ID列表。"},
                        "start_entity": {"type": "string", "description": "起点实体名称、别名、ID或属性值。"},
                        "relation_type": {"type": "string", "description": "关系类型，如 located_in。"},
                        "direction": {"type": "string", "enum": ["outgoing", "incoming", "both"], "description": "遍历方向。"},
                        "depth": {"type": "integer", "description": "遍历深度，默认1。"},
                        "target_entity_type": {"type": "string", "description": "只返回指定类型的目标实体，如 Station。"},
                        "limit": {"type": "integer", "description": "最大返回实体数，默认50。"},
                    },
                    "required": ["start_entity"],
                },
            },
            version="0.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        start_entity: str,
        agent_mode: str = "query",
        map_ids: list[str] | str | None = None,
        relation_type: str | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        depth: int = 1,
        target_entity_type: str | None = None,
        limit: int = 50,
        **_: Any,
    ) -> dict[str, Any]:
        selected = selected_map_ids(
            cognitive_maps_root=self.cognitive_maps_root,
            agent_mode=agent_mode,
            map_ids=map_ids,
        )
        all_entities: list[dict[str, Any]] = []
        all_relations: list[dict[str, Any]] = []
        all_paths: list[list[dict[str, Any]]] = []
        start_entities_payload: list[dict[str, Any]] = []
        missing_maps: list[str] = []

        for map_id in selected[:10]:
            extraction = load_extraction(self.cognitive_maps_root, map_id)
            if extraction is None:
                missing_maps.append(map_id)
                continue
            entity_by_id = {entity.entity_id: entity for entity in extraction.candidate_entities}
            starts = find_start_entities(extraction.candidate_entities, start_entity)
            start_entities_payload.extend(entity_payload(entity, map_id) for entity in starts)
            entities, paths = traverse_relations(
                start_entities=starts,
                relations=extraction.candidate_relations,
                entity_by_id=entity_by_id,
                relation_type=relation_type,
                direction=direction,
                depth=depth,
                target_entity_type=target_entity_type,
                limit=limit,
            )
            seen_entity_ids = {item["entity_id"] for item in all_entities}
            for entity in entities:
                if entity.entity_id not in seen_entity_ids:
                    all_entities.append(entity_payload(entity, map_id))
                    seen_entity_ids.add(entity.entity_id)
            seen_relation_ids = {item["relation_id"] for item in all_relations}
            for path in paths:
                path_payload = [relation_payload(relation, entity_by_id, map_id) for relation in path]
                all_paths.append(path_payload)
                for relation_item in path_payload:
                    if relation_item["relation_id"] not in seen_relation_ids:
                        all_relations.append(relation_item)
                        seen_relation_ids.add(relation_item["relation_id"])
            if len(all_entities) >= limit:
                all_entities = all_entities[:limit]
                break

        success = bool(all_entities)
        return {
            "status": "success" if success else "failed",
            "success": success,
            "summary": f"遍历到 {len(all_entities)} 个关联实体。" if success else "未遍历到匹配的关联实体。",
            "data": {
                "count": len(all_entities),
                "entities": all_entities,
                "relations": all_relations,
                "paths": all_paths,
                "start_entities": start_entities_payload,
                "map_ids": selected,
                "missing_maps": missing_maps,
            },
            "metadata": {
                "tool_name": self.name,
                "generator": self.name,
                "start_entity": start_entity,
                "relation_type": relation_type,
                "direction": direction,
                "depth": depth,
                "target_entity_type": target_entity_type,
            },
        }
