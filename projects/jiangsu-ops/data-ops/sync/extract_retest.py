# -*- coding: utf-8 -*-
"""Dump all session lines for the retest to see what events exist."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SID = "ops_session_1791114326107"

lines = []
with open(r"E:\Tools\suyuan-jiangsu\logs\backend.log", encoding="utf-16", errors="replace") as f:
    for l in f:
        if SID in l:
            lines.append(ANSI.sub("", l.rstrip("\r\n")))

print("session lines:", len(lines))
for l in lines:
    # skip the repetitive memory-projection noise
    if "fresh_tool_result_projection" in l or "add_streaming_tool_results" in l:
        continue
    print(l[:260])
