# -*- coding: utf-8 -*-
"""Append the 2026-10-04 addendum to the survey report (idempotent)."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPORT = r"E:\Tools\suyuan-jiangsu\源库表单勘察报告.md"
ADDENDUM = r"E:\Tools\suyuan-jiangsu\sync\report_addendum.md"

t = open(REPORT, encoding="utf-8").read()
if "2026-10-04 全库活跃表复盘" in t:
    print("addendum already present, skip")
else:
    add = open(ADDENDUM, encoding="utf-8").read()
    with open(REPORT, "a", encoding="utf-8", newline="\n") as f:
        f.write(add)
    print("appended; report lines now:", len(open(REPORT, encoding="utf-8").read().splitlines()))
