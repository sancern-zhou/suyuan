"""
临时数据库迁移脚本：为 PostgreSQL 枚举类型 chunkingstrategy 添加 LLM 取值。

使用说明：
- 依赖 .env 中的 DATABASE_URL（例如 postgresql+asyncpg://user:pass@host:5432/dbname）
- 只需执行一次，重复执行不会报错。
"""

import asyncio
import os
from pathlib import Path

import asyncpg  # type: ignore
from dotenv import load_dotenv  # type: ignore


async def main() -> None:
    # 定位项目根目录和 .env
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[2]  # d:\\溯源
    backend_env = project_root / "backend" / ".env"

    if backend_env.exists():
        load_dotenv(backend_env)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("环境变量 DATABASE_URL 未配置，无法连接数据库。")

    # 将 SQLAlchemy 风格 URL 转为 asyncpg 可用的 URL
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    print(f"[INFO] Connecting to database: {db_url}")

    conn = await asyncpg.connect(db_url)
    try:
        # 使用 IF NOT EXISTS，避免重复执行时报错
        sql = "ALTER TYPE chunkingstrategy ADD VALUE IF NOT EXISTS 'LLM';"
        print("[INFO] Running migration:", sql)
        await conn.execute(sql)
        print("[INFO] Migration completed successfully.")
    finally:
        await conn.close()
        print("[INFO] Connection closed.")


if __name__ == "__main__":
    asyncio.run(main())


