"""Compile confirmed business language into strict extraction schemas."""

from __future__ import annotations

from app.knowledge_base.graph_extraction.models import GraphExtractionSchema
from app.knowledge_base.scene_schemas import BusinessLogic, SceneDraft


class SchemaCompilationError(ValueError):
    """Raised when a business scene cannot form a consistent graph schema."""


class SceneSchemaCompiler:
    def compile(self, draft: SceneDraft) -> GraphExtractionSchema:
        object_keys = [item.key for item in draft.business_objects]
        self._ensure_unique(object_keys, "business object")
        self._ensure_unique([item.key for item in draft.business_logic], "business logic")

        known_objects = set(object_keys)
        for item in draft.business_logic:
            for endpoint in (item.source_key, item.target_key):
                if endpoint not in known_objects:
                    raise SchemaCompilationError(
                        f"business logic {item.key} references unknown object: {endpoint}"
                    )

        active_logic = [item for item in draft.business_logic if item.policy != "forbidden"]
        forbidden_logic = [item for item in draft.business_logic if item.policy == "forbidden"]
        allowed_triplets = list(dict.fromkeys(self._triplet(item) for item in active_logic))
        forbidden_triplets = list(dict.fromkeys(self._triplet(item) for item in forbidden_logic))

        return GraphExtractionSchema(
            allowed_entity_types=object_keys,
            allowed_relation_types=list(
                dict.fromkeys(item.relation_key for item in active_logic)
            ),
            allowed_relation_triplets=allowed_triplets,
            required_relation_triplets=list(
                dict.fromkeys(
                    self._triplet(item)
                    for item in active_logic
                    if item.policy == "required"
                )
            ),
            forbidden_relation_triplets=forbidden_triplets,
            required_evidence=True,
            build_requirement=draft.scene_goal,
            domain_aliases={
                item.name: list(dict.fromkeys(item.aliases))
                for item in draft.business_objects
                if item.aliases
            },
            entity_type_descriptions={
                item.key: item.description for item in draft.business_objects
            },
            relation_type_descriptions={
                item.relation_key: item.statement for item in active_logic
            },
            ignored_content=list(dict.fromkeys(draft.ignored_content)),
        )

    @staticmethod
    def _triplet(item: BusinessLogic) -> tuple[str, str, str]:
        return item.source_key, item.relation_key, item.target_key

    @staticmethod
    def _ensure_unique(values: list[str], label: str) -> None:
        if len(values) != len(set(values)):
            raise SchemaCompilationError(f"duplicate {label} key")

