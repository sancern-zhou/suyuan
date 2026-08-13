"""Add shared/local vector-store scope to knowledge bases.

Run from ``backend`` with::

    python -m app.alembic.versions.add_knowledge_base_vector_store_scope
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.database import engine


STATEMENTS = (
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS vector_store_scope VARCHAR(16) NOT NULL DEFAULT 'shared'",
    "ALTER TABLE knowledge_bases DROP CONSTRAINT IF EXISTS ck_knowledge_bases_vector_store_scope",
    "ALTER TABLE knowledge_bases ADD CONSTRAINT ck_knowledge_bases_vector_store_scope CHECK (vector_store_scope IN ('shared', 'local'))",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_bases_vector_store_scope ON knowledge_bases(vector_store_scope)",
)


async def upgrade() -> None:
    async with engine.begin() as connection:
        if connection.dialect.name != "postgresql":
            raise RuntimeError("add_knowledge_base_vector_store_scope supports PostgreSQL only")
        for statement in STATEMENTS:
            await connection.execute(text(statement))


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
