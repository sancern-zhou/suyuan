# -*- coding: utf-8 -*-
"""盘点：同步进 jiangsu_ods 的表里，Agent 到底能查哪些、不能查哪些。

不变式（由 dq_check 每日校验）：**同步的数据不允许 Agent 查不到**。
mart/dim 契约覆盖不到的表，必须落在 ods_contract.txt 兜底白名单里。

用法: python audit_ods_coverage.py
输出: GAP(同步但两边都够不到) / ODS-FALLBACK(走兜底通道) / MART(有 mart/dim 契约) 三档。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_ods_fallback_contract as ods_contract  # noqa: E402


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    if not dsn:
        from dotenv import load_dotenv

        load_dotenv(r"E:\suyuan\backend\.env.jiangsu-ops")
        dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    if not dsn:
        raise SystemExit("DATABASE_URL 未配置")
    return dsn


async def main() -> int:
    import asyncpg

    fallback, covered = ods_contract.fallback_tables()
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(
            """SELECT c.relname AS table_name, c.reltuples::bigint AS est_rows
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'jiangsu_ods' AND c.relkind = 'r'"""
        )
    finally:
        await conn.close()
    est = {r["table_name"]: r["est_rows"] for r in rows}

    synced = set(ods_contract.synced_logical_tables())
    fallback_set, covered_set = set(fallback), set(covered)
    gap = sorted(synced - fallback_set - covered_set)

    def show(title: str, tables: list[str]) -> None:
        print(f"== {title} ({len(tables)})")
        for t in tables:
            print(f"   {t:<34} rows~{est.get(t, 'n/a')}")
        print()

    print(f"sync_config 逻辑表: {len(synced)} | mart/dim 覆盖: {len(covered_set)} | "
          f"ODS 兜底: {len(fallback_set)} | GAP: {len(gap)}\n")
    show("GAP: 同步了但 Agent 查不到（必须修）", gap)
    show("ODS-FALLBACK: 走原始层兜底", fallback)
    show("MART: 有 mart/dim 契约", covered)
    return 1 if gap else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
