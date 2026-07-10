import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.models import KnowledgeBase
from scripts.migrate_cognitive_maps_to_knowledge_bases import CognitiveMapMigrator


@pytest.mark.asyncio
async def test_cognitive_map_migration_preserves_status_schema_and_is_idempotent(tmp_path):
    source = tmp_path / "maps"
    map_dir = source / "map1"
    map_dir.mkdir(parents=True)
    (map_dir / "map.json").write_text(json.dumps({"id": "map1", "name": "旧图谱"}))
    (map_dir / "schema.json").write_text(json.dumps({
        "allowed_entity_types": ["Pollutant"],
        "allowed_relation_types": ["affects"],
        "allowed_relation_triplets": []
    }))
    (map_dir / "extraction.json").write_text(json.dumps({
        "map_id": "map1",
        "candidate_entities": [
            {"entity_id": "e1", "map_id": "map1", "entity_type": "Pollutant", "name": "臭氧", "review_status": "published"},
            {"entity_id": "e2", "map_id": "map1", "entity_type": "Pollutant", "name": "前体物", "review_status": "candidate"}
        ],
        "candidate_relations": [
            {"relation_id": "r1", "map_id": "map1", "source_entity_id": "e2", "target_entity_id": "e1", "relation_type": "affects", "review_status": "confirmed"}
        ],
        "evidence": [],
        "diagnostics": {"provider_name": "fixture"}
    }))
    (source / "agent_bindings.json").write_text(json.dumps([
        {"map_id": "map1", "agent_mode": "ops", "enabled": True}
    ]))

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    migrator = CognitiveMapMigrator(factory, source)

    await migrator.migrate(apply=True)
    await migrator.migrate(apply=True)

    async with factory() as session:
        kb = await session.scalar(select(KnowledgeBase))
        assert kb.name == "旧图谱"
        assert kb.is_default is True
        assert kb.graph_schema["allowed_entity_types"] == ["Pollutant"]
        assert await session.scalar(select(func.count()).select_from(KnowledgeGraphEntity)) == 2
        assert await session.scalar(select(func.count()).select_from(KnowledgeGraphRelation)) == 1
        statuses = set((await session.execute(select(KnowledgeGraphEntity.review_status))).scalars())
        assert statuses == {"published", "candidate"}
    await engine.dispose()
