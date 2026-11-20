"""Nightly sentinel: fail loudly when dbt tag:daily marts did not actually refresh.

Guards against the silent-skip failure class seen 2026-11-17..19: the dbt
stage of sync-daily.cmd never ran (shared-log redirect race) while the rest
of the chain completed and the scheduled task still reported success.

Runs a few minutes after the nightly build, so a successful build leaves
max(synced_at) minutes old. A tight 2h bound therefore catches even the
FIRST skipped night (DQ's 26h SLA only surfaces the problem one day later).
Tables are deliberately small dictionaries/low-row marts so max() stays cheap.
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

MAX_AGE_MIN = 120

CHECKS = [
    "jiangsu_mart.dim_person",
    "jiangsu_mart.dim_device",
    "jiangsu_mart.mart_station_door_access",
]


async def main() -> int:
    load_dotenv(r"E:\suyuan\backend\.env.jiangsu-ops")
    dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    pg = await asyncpg.connect(dsn)
    failures = []
    try:
        now = await pg.fetchval("select localtimestamp")
        for table in CHECKS:
            ts = await pg.fetchval(f"select max(synced_at) from {table}")
            if ts is None:
                failures.append(f"{table}: empty")
                continue
            age_min = (now - ts).total_seconds() / 60
            ok = age_min <= MAX_AGE_MIN
            print(f"[{'OK' if ok else 'STALE'}] {table}: max(synced_at)={ts} "
                  f"age={age_min:.0f}min bound={MAX_AGE_MIN}min")
            if not ok:
                failures.append(f"{table}: age={age_min:.0f}min")
    finally:
        await pg.close()
    if failures:
        print(f"SENTINEL FAIL ({len(failures)}): " + "; ".join(failures))
        return 1
    print("SENTINEL OK: daily marts refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
