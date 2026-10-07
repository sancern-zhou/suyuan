# -*- coding: utf-8 -*-
"""Extract tool-call sequence for the test session from UTF-16 backend.log."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SID = "ops_session_1791096405582"

lines = []
with open(r"E:\Tools\suyuan-jiangsu\logs\backend.log", encoding="utf-16", errors="replace") as f:
    for raw in f:
        if SID in raw:
            lines.append(ANSI.sub("", raw.rstrip("\r\n")))

print("session lines:", len(lines))

# classify interesting events
pat_tool = re.compile(r"(tool_call\w*|execute[_-]?tool|tool[_-]?name|calling[_-]?tool|tool_result|tool[_-]?dispatch\w*|agent_tool\w*|mcp\w*)", re.I)
for l in lines:
    if pat_tool.search(l):
        print(l[:300])
