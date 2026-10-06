# -*- coding: utf-8 -*-
"""Check local ods bsd_device columns vs source."""
import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import asyncpg

cfg = json.load(open(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json", encoding="utf-8"))
dsn = cfg["target"]["dsn"]

async def main():
    pg = await asyncpg.connect(dsn)
    cols = await pg.fetch(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='jiangsu_ods' and table_name='bsd_device' order by ordinal_position"
    )
    print("local jiangsu_ods.bsd_device cols (%d):" % len(cols))
    print("  " + ", ".join(r[0] for r in cols))
    n = await pg.fetchval("select count(*) from jiangsu_ods.bsd_device")
    print("rows:", n)
    if any(r[0] == "devicestats" for r in cols):
        dist = await pg.fetch("select devicestats, count(*) from jiangsu_ods.bsd_device group by 1 order by 2 desc")
        print("devicestats distribution:", [(r[0], r[1]) for r in dist])
    if any(r[0] == "masterslavenum" for r in cols):
        dist = await pg.fetch(
            "select masterslavenum, count(*) from jiangsu_ods.bsd_device group by 1 order by 2 desc limit 10"
        )
        print("masterslavenum distribution:", [(r[0], r[1]) for r in dist])
    await pg.close()

asyncio.run(main())
