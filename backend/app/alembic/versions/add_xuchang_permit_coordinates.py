"""Add geocoding columns required by Xuchang permit-source analysis.

Run from ``backend`` with::

    python -m app.alembic.versions.add_xuchang_permit_coordinates
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE permit_licenses "
                "ADD COLUMN IF NOT EXISTS longitude NUMERIC(10, 6), "
                "ADD COLUMN IF NOT EXISTS latitude NUMERIC(9, 6), "
                "ADD COLUMN IF NOT EXISTS coordinate_source VARCHAR(64), "
                "ADD COLUMN IF NOT EXISTS coordinate_fetched_at TIMESTAMP, "
                "ADD COLUMN IF NOT EXISTS coordinate_crs VARCHAR(32), "
                "ADD COLUMN IF NOT EXISTS permit_original_path TEXT"
            )
        )


async def main() -> None:
    try:
        await upgrade()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
