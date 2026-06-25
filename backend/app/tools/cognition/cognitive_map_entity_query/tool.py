from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.cognition.query_core import (
    clean_list,
    default_cognitive_maps_root,
    entity_matches,
    entity_payload,
    load_extraction,
    selected_map_ids,
)


class CognitiveMapEntityQueryTool(LLMTool):
    def __init__(self, cognitive_maps_root: Path | None = None) -> None:
        self.cognitive_maps_root = cognitive_maps_root or default_cognitive_maps_root()
        super().__init__(
            name="cognitive_map_entity_query",
            description="Query cognitive map entities by type, name, aliases, and exact attribute filters.",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "cognitive_map_entity_query",
                "description": "认知地图实体查询工具。用于精确查询实体及其属性，例如 Station where city=广州。适合资产发现、站点目录查询、地图上图前获取经纬度。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_mode": {"type": "string", "description": "Agent模式，不传 map_ids 时用该模式绑定地图，默认 query。"},
                        "map_ids": {"type": "array", "items": {"type": "string"}, "description": "可选认知地图ID列表。"},
                        "entity_type": {"type": "string", "description": "实体类型，如 Station、Region、Pollutant。"},
                        "entity_names": {"type": "array", "items": {"type": "string"}, "description": "实体名、别名或ID精确匹配。"},
                        "name_contains": {"type": "string", "description": "实体名/别名包含匹配。"},
                        "attribute_filters": {"type": "object", "description": "实体属性等值过滤，如 {\"city\":\"广州\"}。"},
                        "limit": {"type": "integer", "description": "最大返回实体数，默认50。"},
                    },
                },
            },
            version="0.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        agent_mode: str = "query",
        map_ids: list[str] | str | None = None,
        entity_type: str | None = None,
        entity_names: list[str] | str | None = None,
        name_contains: str | None = None,
        attribute_filters: dict[str, Any] | None = None,
        limit: int = 50,
        **_: Any,
    ) -> dict[str, Any]:
        selected = selected_map_ids(
            cognitive_maps_root=self.cognitive_maps_root,
            agent_mode=agent_mode,
            map_ids=map_ids,
        )
        limit = max(1, min(int(limit or 50), 500))
        names = clean_list(entity_names)
        entities: list[dict[str, Any]] = []
        missing_maps: list[str] = []

        for map_id in selected[:10]:
            extraction = load_extraction(self.cognitive_maps_root, map_id)
            if extraction is None:
                missing_maps.append(map_id)
                continue
            for entity in extraction.candidate_entities:
                if entity_matches(
                    entity,
                    entity_type=entity_type,
                    entity_names=names,
                    name_contains=name_contains,
                    attribute_filters=attribute_filters,
                ):
                    entities.append(entity_payload(entity, map_id))
                    if len(entities) >= limit:
                        break
            if len(entities) >= limit:
                break

        success = bool(entities)
        return {
            "status": "success" if success else "failed",
            "success": success,
            "summary": f"查询到 {len(entities)} 个认知地图实体。" if success else "未查询到匹配的认知地图实体。",
            "data": {
                "count": len(entities),
                "entities": entities,
                "map_ids": selected,
                "missing_maps": missing_maps,
            },
            "metadata": {
                "tool_name": self.name,
                "generator": self.name,
                "entity_type": entity_type,
                "attribute_filters": attribute_filters or {},
            },
        }
