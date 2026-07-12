"""Add scene-driven knowledge-graph workflow resources.

Run from ``backend`` with::

    python -m app.alembic.versions.add_scenario_driven_knowledge_graph
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.database import engine
from app.knowledge_base.scene_models import (
    KnowledgeBusinessRule,
    KnowledgeGraphExtractionRun,
    KnowledgeSceneProfile,
    KnowledgeSchemaSuggestion,
    KnowledgeUserFact,
)

KNOWLEDGE_BASE_ALTERS = [
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS scene_status VARCHAR(32) NOT NULL DEFAULT 'awaiting_documents'",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS scene_profile_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS rule_version INTEGER NOT NULL DEFAULT 0",
]

GRAPH_FACT_ALTERS = [
    *[
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source_type VARCHAR(24) NOT NULL DEFAULT 'document_fact'"
        for table in ("knowledge_graph_entities", "knowledge_graph_relations")
    ],
    *[
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} INTEGER NOT NULL DEFAULT 0"
        for table in ("knowledge_graph_entities", "knowledge_graph_relations")
        for column in ("scene_profile_version", "schema_version", "rule_version")
    ],
]

SCENE_TABLES = [
    KnowledgeSceneProfile.__table__,
    KnowledgeBusinessRule.__table__,
    KnowledgeUserFact.__table__,
    KnowledgeSchemaSuggestion.__table__,
    KnowledgeGraphExtractionRun.__table__,
]


def _create_scene_tables(sync_connection) -> None:
    for table in SCENE_TABLES:
        table.create(sync_connection, checkfirst=True)


async def upgrade() -> None:
    async with engine.begin() as connection:
        if connection.dialect.name != "postgresql":
            raise RuntimeError(
                "add_scenario_driven_knowledge_graph supports PostgreSQL deployments only"
            )
        for statement in [*KNOWLEDGE_BASE_ALTERS, *GRAPH_FACT_ALTERS]:
            await connection.execute(text(statement))
        await connection.run_sync(_create_scene_tables)
        await connection.execute(
            text(
                """
                UPDATE knowledge_bases kb
                SET scene_status = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM documents d WHERE d.knowledge_base_id = kb.id
                    ) THEN 'awaiting_confirmation'
                    ELSE 'awaiting_documents'
                END
                WHERE scene_profile_version = 0
                """
            )
        )


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
