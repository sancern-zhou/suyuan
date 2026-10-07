# -*- coding: utf-8 -*-
"""Full audit trail of the lifecycle test run (all entries today)."""
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
        """select audit_id, to_char(queried_at,'HH24:MI:SS') t, tool, rows_returned, duration_ms,
                  left(coalesce(params::text,''),240) p, left(coalesce(error,''),120) e
           from jiangsu_sync.query_audit
           where queried_at >= '2026-10-04' order by audit_id"""
    )
    print("today audit entries:", len(rows))
    for r in rows:
        print("%s %s %-28s rows=%-4s %sms err=%s" % (r[0], r[1], r[2], r[3], r[4], (r[6] or "-")[:60]))
        print("      ", (r[5] or "").replace("\n", " ")[:220])
    await pg.close()


asyncio.run(main())
