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
from app.knowledge_base.graph_build_models import KnowledgeGraphBuildTask

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
    KnowledgeGraphBuildTask.__table__,
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
        # Keep this explicit and idempotent for deployments where the table
        # was created outside SQLAlchemy metadata.
        await connection.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_graph_build_tasks (
                id VARCHAR(36) PRIMARY KEY,
                kb_id VARCHAR(36) NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','partial','failed','cancelled')),
                mode VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (mode IN ('pending','reset_and_build')),
                created_by VARCHAR(36) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP, completed_at TIMESTAMP,
                total_chunks INTEGER NOT NULL DEFAULT 0,
                processed_chunks INTEGER NOT NULL DEFAULT 0,
                failed_chunks INTEGER NOT NULL DEFAULT 0,
                remaining_chunks INTEGER NOT NULL DEFAULT 0,
                failed_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                last_error TEXT, cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
                lease_until TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_kg_build_task_status ON knowledge_graph_build_tasks(status)"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_graph_build_tasks_kb_id ON knowledge_graph_build_tasks(kb_id)"))
        await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_build_active_kb ON knowledge_graph_build_tasks(kb_id) WHERE status IN ('queued', 'running')"))


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
