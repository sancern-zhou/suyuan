# -*- coding: utf-8 -*-
"""Ground truth for the retest: query_audit entries + tool exec events in the time window."""
import asyncio
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import asyncpg

app_dsn = json.load(open(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json", encoding="utf-8"))["target"]["dsn"]


async def audit():
    pg = await asyncpg.connect(app_dsn)
    rows = await pg.fetch(
        """select audit_id, to_char(queried_at,'HH24:MI:SS') t, tool, rows_returned, duration_ms,
                  left(params::text, 300) p
           from jiangsu_sync.query_audit where queried_at >= '2026-10-04 19:40' order by audit_id"""
    )
    print("=== query_audit since 19:40 (%d) ===" % len(rows))
    for r in rows:
        sql = re.search(r'"sql":\s*"(.{0,180})', r[5] or "")
        print(r[0], r[1], r[2], "rows=%s %sms" % (r[3], r[4]))
        print("      ", (sql.group(1).replace("\\n", " ") if sql else (r[5] or "")[:180]))
    await pg.close()


ANSI = re.compile(r"\x1b\[[0-9;]*m")

def tools_in_window():
    execs = []
    with open(r"E:\Tools\suyuan-jiangsu\logs\backend.log", encoding="utf-16", errors="replace") as f:
        for raw in f:
            if "2026-10-04T11:4" not in raw:
                continue
            l = ANSI.sub("", raw.rstrip("\r\n"))
            if "executing_tool_v2" in l or "streaming_tool_started" in l:
                if "streaming_tool_started" in l:
                    m = re.search(r"tool_name=(\S+)", l)
                    t = re.search(r"2026-10-04T([\d:.]+)", l)
                    execs.append((t.group(1)[3:11] if t else "--", m.group(1) if m else "?"))
    print("\n=== tool starts in 11:4x window (%d) ===" % len(execs))
    for i, (t, n) in enumerate(execs, 1):
        print("%2d. %s %s" % (i, t, n))


asyncio.run(audit())
tools_in_window()
