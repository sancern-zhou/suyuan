# -*- coding: utf-8 -*-
"""Inspect failing DQ checks + daily mart watermarks."""
import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import asyncpg

dsn = json.load(open(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json", encoding="utf-8"))["target"]["dsn"]


async def main():
    pg = await asyncpg.connect(dsn)
    rows = await pg.fetch(
        "select check_name, status, detail, to_char(checked_at,'MM-DD HH24:MI') "
        "from jiangsu_sync.dq_results where lower(status)!='ok' and checked_at > now() - interval '2 hours' "
        "order by checked_at desc limit 12"
    )
    print("=== failing dq checks (latest run) ===")
    for r in rows:
        print(r[3], r[1], r[0], "::", str(r[2])[:130])
    wm = await pg.fetch(
        "select table_name, last_mode, last_status, to_char(updated_at,'MM-DD HH24:MI') "
        "from jiangsu_sync.sync_watermark "
        "where table_name in ('mart_station_daily_profile','mart_qc_arrangement_analysis') "
        "or table_name like 'mart_%' order by table_name limit 20"
    )
    print("=== watermark table (mart rows may not exist here; marts are dbt-built) ===")
    for r in wm:
        print(tuple(r))
    await pg.close()


asyncio.run(main())
