"""Single-process database preparation entry point for server launch scripts."""

import asyncio
import os

from app.db.database import close_db, init_db


async def main() -> None:
    if not os.getenv("DATABASE_URL"):
        return
    try:
        await init_db()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
