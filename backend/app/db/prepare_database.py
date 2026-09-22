"""Single-process database preparation entry point for server launch scripts."""

import asyncio
import os

from app.db.database import close_db, init_db


async def main() -> None:
    if not os.getenv("DATABASE_URL"):
        return
    try:
        await init_db()
        # 会话历史/任务执行记录可能落在独立实例（SESSION_DATABASE_URL），
        # 主库 schema 就绪后同步确保该库的表存在。
        if os.getenv("SESSION_DATABASE_URL"):
            from app.db.init_session_db import init_session_tables

            await init_session_tables()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
