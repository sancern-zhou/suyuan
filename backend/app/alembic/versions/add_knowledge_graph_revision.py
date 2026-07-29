"""Add a monotonic graph revision to every knowledge base."""

import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.execute(text(
            "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS graph_revision BIGINT"
        ))
        await connection.execute(text(
            "UPDATE knowledge_bases SET graph_revision = 0 WHERE graph_revision IS NULL"
        ))
        await connection.execute(text(
            "ALTER TABLE knowledge_bases ALTER COLUMN graph_revision SET DEFAULT 0"
        ))
        await connection.execute(text(
            "ALTER TABLE knowledge_bases ALTER COLUMN graph_revision SET NOT NULL"
        ))


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
