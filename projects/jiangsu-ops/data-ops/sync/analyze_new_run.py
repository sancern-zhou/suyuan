# -*- coding: utf-8 -*-
"""Analyze the latest re-test run: meta + preview, then tool sequence from backend.log."""
import io
import json
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RUN = r"E:\suyuan\backend\logs\agent_runs\run_20261004_194527_695005.json"
d = json.load(open(RUN, encoding="utf-8"))
sid = d.get("session_id", "")
print("query:", d.get("query"))
print("status:", d.get("status"), "| iterations:", d.get("metadata", {}).get("iterations"),
      "| duration_ms:", d.get("stats", {}).get("duration_ms"))
print("session:", sid)
print("\n=== response_preview ===")
print(str(d.get("response_preview"))[:1500])

# tool executions for this session from UTF-16 backend.log
ANSI = re.compile(r"\x1b\[[0-9;]*m")
pat_start = re.compile(r"streaming_tool_started.*?tool_name=(\S+)")
pat_exec = re.compile(r"executing_tool_v2.*?tool_name=(\S+)")
calls = []
with open(r"E:\Tools\suyuan-jiangsu\logs\backend.log", encoding="utf-16", errors="replace") as f:
    for raw in f:
        if sid not in raw:
            continue
        l = ANSI.sub("", raw.rstrip("\r\n"))
        m = pat_exec.search(l) or pat_start.search(l)
        if m and "executing_tool_v2" in l:
            calls.append((m.group(1), l[:200]))

print("\n=== tool executions (%d) ===" % len(calls))
for i, (n, l) in enumerate(calls, 1):
    t = re.search(r"2026-10-04T([\d:.]+)", l)
    print("%2d. %s %s" % (i, t.group(1)[3:8] if t else "--", n))
