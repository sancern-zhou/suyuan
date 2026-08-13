"""Add per-project namespace for local knowledge-base metadata."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        if connection.dialect.name != "postgresql":
            raise RuntimeError("add_knowledge_base_local_scope supports PostgreSQL only")
        await connection.execute(
            text("ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS local_scope VARCHAR(128)")
        )
        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_knowledge_bases_local_scope ON knowledge_bases(local_scope)")
        )


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
