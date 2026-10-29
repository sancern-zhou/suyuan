"""Create weather tables in the local weather database (weather_engine).

用法（宿主机，conda backend_py311）：

    cd backend
    python scripts/init_weather_tables.py --env-file .env.guangdong

2026-10-29 广东气象抓取改造：气象链路（NMC 观测/ERA5 历史/逐日聚合/Agent SQL
查询）统一走 weather_engine（WEATHER_DATABASE_URL 优先），本脚本在目标库中
幂等创建启用链路所需的天气表。本机 PostgreSQL 无 TimescaleDB 时降级为普通表。

观测逐日表 observed_weather_daily 由 observed_weather_daily_fetcher 自建
（CREATE TABLE IF NOT EXISTS），此处一并提供以便查询工具提前可用。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 只创建广东启用链路涉及的天气表，避免把 Base 里的无关业务表建进本地库。
WEATHER_TABLES = (
    "era5_reanalysis_data",
    "observed_weather_data",
    "observed_weather_daily",
    "weather_stations",
)


def _load_env_file(env_file: Path) -> None:
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=".env.guangdong",
        help="backend 目录下的环境文件（默认 .env.guangdong）",
    )
    args = parser.parse_args()

    _load_env_file(BACKEND_DIR / args.env_file)

    # 导入 weather 模块即完成模型注册；weather_engine 按
    # WEATHER_DATABASE_URL > DATABASE_URL 解析目标库。
    from sqlalchemy import text

    import app.db.models  # noqa: F401
    from app.db.database import Base
    from app.db.models import weather_models  # noqa: F401
    from app.db.weather_database import weather_engine, close_weather_db

    target = weather_engine.url.render_as_string(hide_password=True)
    print(f"target database: {target}")

    tables = [Base.metadata.tables[name] for name in WEATHER_TABLES]
    async with weather_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    print(f"tables created: {', '.join(WEATHER_TABLES)}")

    # TimescaleDB 仅是增强（hypertable/压缩），缺失时普通表即可运行；
    # 必须与建表分开成独立事务，扩展失败不能回滚已建的表。
    try:
        async with weather_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    except Exception as exc:
        print(f"timescaledb unavailable, using plain tables: {exc}")

    await close_weather_db()


if __name__ == "__main__":
    asyncio.run(main())
