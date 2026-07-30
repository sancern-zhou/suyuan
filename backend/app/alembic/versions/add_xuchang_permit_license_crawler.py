"""Create storage tables for the one-off Xuchang permit crawler.

Run from ``backend`` with::

    python -m app.alembic.versions.add_xuchang_permit_license_crawler
"""

from __future__ import annotations

import asyncio

from app.db.database import engine
from app.fetchers.emission.permit_license_crawler.models import PERMIT_TABLES


def _create_tables(sync_connection) -> None:
    for table in PERMIT_TABLES:
        table.create(sync_connection, checkfirst=True)


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(_create_tables)


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
