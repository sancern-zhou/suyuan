# -*- coding: utf-8 -*-
"""Count real tool executions in the test window + inspect the later runs."""
import io
import json
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# 1) backend.log tool executions between 06:46:40Z and 06:48:20Z (the 14:46 run)
hits = []
with open(r"E:\Tools\suyuan-jiangsu\logs\backend.log", encoding="utf-16", errors="replace") as f:
    for raw in f:
        if "2026-10-04T06:4" not in raw:
            continue
        m = re.search(r"2026-10-04T06:(4[6-8]):(\d\d)", raw)
        if not m:
            continue
        if raw.startswith("2026-10-04T06:46:") and raw.split("T")[1][:8] < "06:46:40":
            continue
        l = ANSI.sub("", raw.rstrip("\r\n"))
        low = l.lower()
        if any(k in low for k in ["tool", "fetch", "execute_jiangsu", "jiangsu_"]):
            hits.append(l)

print("window lines w/ tool-ish content:", len(hits))
execs = [l for l in hits if re.search(r"(tool_(execut|complet|finish|start)\w*|tool_call\w*|executing[_ ]tool|tool\s+execution)", l, re.I)]
print("\n=== explicit tool execution events (%d) ===" % len(execs))
for l in execs[:40]:
    print(l[:250])

# tool-name-ish tokens
names = Counter()
for l in hits:
    for n in re.findall(r"\b(jiangsu_[a-z_]+|execute_jiangsu_mart_sql|query_statistics)\b", l):
        names[n] += 1
print("\n=== tool-name token counts in window ===")
for n, c in names.most_common(15):
    print("  %-36s %d" % (n, c))

# 2) later runs: what were they?
for p in [r"E:\suyuan\backend\logs\agent_runs\run_20261004_153935_521391.json",
          r"E:\suyuan\backend\logs\agent_runs\run_20261004_154113_785283.json"]:
    d = json.load(open(p, encoding="utf-8"))
    print("\n", p.split("\\")[-1])
    print("  query:", str(d.get("query"))[:120])
    print("  status:", d.get("status"), "| duration_ms:", d.get("stats", {}).get("duration_ms"))
    print("  meta:", json.dumps(d.get("metadata", {}), ensure_ascii=False)[:220])
    print("  preview:", str(d.get("response_preview"))[:200])
