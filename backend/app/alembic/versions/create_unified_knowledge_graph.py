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
        await connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_graph_build_tasks (
            id VARCHAR(36) PRIMARY KEY, kb_id VARCHAR(36) NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','partial','failed','cancelled')), mode VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (mode IN ('pending','reset_and_build')),
            created_by VARCHAR(36) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP, completed_at TIMESTAMP, total_chunks INTEGER NOT NULL DEFAULT 0,
            processed_chunks INTEGER NOT NULL DEFAULT 0, failed_chunks INTEGER NOT NULL DEFAULT 0,
            remaining_chunks INTEGER NOT NULL DEFAULT 0, failed_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            last_error TEXT, cancel_requested BOOLEAN NOT NULL DEFAULT FALSE, lease_until TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'pending'"))
        await connection.execute(text("UPDATE knowledge_graph_build_tasks SET mode='pending' WHERE mode IS NULL OR mode NOT IN ('pending','reset_and_build')"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks ALTER COLUMN mode SET NOT NULL"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks ALTER COLUMN mode SET DEFAULT 'pending'"))
        await connection.execute(text("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='knowledge_graph_build_tasks' AND column_name='failed_chunk_ids' AND udt_name='json') THEN
                ALTER TABLE knowledge_graph_build_tasks ALTER COLUMN failed_chunk_ids TYPE JSONB USING failed_chunk_ids::jsonb;
            END IF;
        END $$;"""))
        await connection.execute(text("""DO $$ DECLARE c record; BEGIN
            FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='knowledge_graph_build_tasks'::regclass AND (pg_get_constraintdef(oid) ILIKE '%status%' OR pg_get_constraintdef(oid) ILIKE '%mode%') LOOP
                EXECUTE format('ALTER TABLE knowledge_graph_build_tasks DROP CONSTRAINT %I', c.conname);
            END LOOP;
        END $$;"""))
        await connection.execute(text("""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_graph_build_tasks_kb_id_fkey') THEN
                ALTER TABLE knowledge_graph_build_tasks ADD CONSTRAINT knowledge_graph_build_tasks_kb_id_fkey FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE;
            END IF;
        END $$;"""))
        await connection.execute(text("UPDATE knowledge_graph_build_tasks SET status = CASE WHEN status IN ('queued','running','completed','partial','failed','cancelled') THEN status ELSE 'failed' END"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks ALTER COLUMN status SET DEFAULT 'queued'"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks DROP CONSTRAINT IF EXISTS ck_kg_build_status"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks ADD CONSTRAINT ck_kg_build_status CHECK (status IN ('queued','running','completed','partial','failed','cancelled'))"))
        await connection.execute(text("UPDATE knowledge_graph_build_tasks SET mode = 'pending' WHERE mode IS NULL OR mode = 'full' OR mode NOT IN ('pending','reset_and_build')"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks DROP CONSTRAINT IF EXISTS ck_kg_build_mode"))
        await connection.execute(text("ALTER TABLE knowledge_graph_build_tasks ADD CONSTRAINT ck_kg_build_mode CHECK (mode IN ('pending','reset_and_build'))"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_kg_build_task_status ON knowledge_graph_build_tasks(status)"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_graph_build_tasks_kb_id ON knowledge_graph_build_tasks(kb_id)"))
        await connection.execute(text("DROP INDEX IF EXISTS uq_kg_build_active_kb"))
        await connection.execute(text("CREATE UNIQUE INDEX uq_kg_build_active_kb ON knowledge_graph_build_tasks(kb_id) WHERE status IN ('queued', 'running')"))


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
