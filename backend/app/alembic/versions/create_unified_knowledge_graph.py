"""Create the unified knowledge-base chunk and graph fact model.

Run from ``backend`` with::

    python -m app.alembic.versions.create_unified_knowledge_graph

The project does not currently expose a complete Alembic environment, so this
migration follows the existing executable migration-module convention.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.database import engine
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphEntityMention,
    KnowledgeGraphRelation,
    KnowledgeGraphRelationMention,
    KnowledgeIndexOutbox,
)

_POSTGRES_COLUMN_STATEMENTS = (
    "ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'DELETING'",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS graph_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS graph_schema JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS graph_extractor_config JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS graph_updated_at TIMESTAMP",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_generation INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS ingestion_status VARCHAR(20) NOT NULL DEFAULT 'pending'",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS graph_status VARCHAR(20) NOT NULL DEFAULT 'pending'",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_error TEXT",
)

_GRAPH_TABLES = (
    KnowledgeChunk.__table__,
    KnowledgeGraphEntity.__table__,
    KnowledgeGraphRelation.__table__,
    KnowledgeGraphEntityMention.__table__,
    KnowledgeGraphRelationMention.__table__,
    KnowledgeIndexOutbox.__table__,
)


def _create_graph_tables(sync_connection) -> None:
    for table in _GRAPH_TABLES:
        table.create(sync_connection, checkfirst=True)


async def upgrade() -> None:
    async with engine.begin() as connection:
        if connection.dialect.name != "postgresql":
            raise RuntimeError(
                "create_unified_knowledge_graph supports PostgreSQL deployments only"
            )
        for statement in _POSTGRES_COLUMN_STATEMENTS:
            await connection.execute(text(statement))
        await connection.run_sync(_create_graph_tables)


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
