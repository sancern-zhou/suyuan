# -*- coding: utf-8 -*-
"""Generate the execute_jiangsu_mart_sql tool contract from sync/datasets/*.yaml.

单一来源约定：datasets/*.yaml 是契约的唯一人工维护源；工具描述中的契约文本块
（backend/app/tools/query/jiangsu_ops_sql_query/contract.txt）是本脚本的生成物。

用法:
  PYTHONPATH=backend python projects/jiangsu-ops/data-ops/sync/gen_tool_contract.py            # 生成并写入 contract.txt
  PYTHONPATH=backend python projects/jiangsu-ops/data-ops/sync/gen_tool_contract.py --check    # 校验 contract.txt 是否与 yaml 一致（漂移检测）
  PYTHONPATH=backend python projects/jiangsu-ops/data-ops/sync/gen_tool_contract.py --print    # 仅打印生成结果，不写文件

退出码: --check 不一致时返回 1（供 dq_check / 调度日志判别）。
"""
from __future__ import annotations

import io
import os
import sys

try:
    import yaml  # PyYAML, backend venv 自带
except ImportError:  # pragma: no cover
    yaml = None

from app.utils.path_config import resolve_agent_path, format_agent_path

YAML_DIR = resolve_agent_path("projects/jiangsu-ops/data-ops/sync/datasets")
TARGET_PATH = resolve_agent_path("backend/app/tools/query/jiangsu_ops_sql_query/contract.txt")

# 表在契约文本与白名单中的显示顺序（新表按语义插入到合适位置）
TABLE_ORDER = [
    "mart_work_order_analysis",
    "mart_alarm_event_analysis",
    "mart_station_device_health",
    "mart_station_daily_profile",
    "mart_qc_execution_analysis",
    "mart_qc_arrangement_analysis",
    "mart_inspection_analysis",
    "mart_performance_analysis",
    "mart_blackout_analysis",
    "mart_qc_backorder_analysis",
    "dim_station",
    "dim_device",
    "dim_device_parameter",
    "mart_device_lifecycle_analysis",
]

HEADER = (
    "\n\n【江苏运维主题数据集契约（PostgreSQL，仅下列{n}张表）】\n"
    "数据自2026-07-01起；不支持同比/年度；实时状态请走平台API工具，不在本数据集。\n"
    "生成SQL前先读契约，直接生成SQL，不要先describe_table；仅当契约未列字段时才describe_table。"
)

FOOTER = (
    "\n【SQL方言】PostgreSQL：用 LIMIT 不用 TOP；日期截断用 date_trunc('day', col)；"
    "布尔列直接用 IS TRUE / = TRUE；时间比较用 '2026-09-01' 字面量。"
    "查询务必带 LIMIT（上限1000）；聚合统计优先 GROUP BY 城市或站点返回小结果集。"
)

FILE_HEADER = (
    "# generated from sync/datasets/*.yaml by gen_tool_contract.py — DO NOT EDIT BY HAND\n"
    "# 单一来源: projects/jiangsu-ops/data-ops/sync/datasets/*.yaml；漂移检测见 dq_check.py\n"
)


def load_yaml(path):
    text = io.open(path, encoding="utf-8").read()
    if yaml is not None:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    # 兜底：无 PyYAML 时提取顶层标量字段（dataset/guide）
    data = {}
    key = None
    buf = []
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.startswith(" ") or line.startswith("\t"):
            if key:
                buf.append(line.strip())
            continue
        if ":" in line:
            if key:
                data[key] = " ".join(buf)
            k, _, v = line.partition(":")
            key, buf = k.strip(), ([v.strip()] if v.strip() else [])
    if key:
        data[key] = " ".join(buf)
    return data


def build_contract():
    docs = {}
    for fn in os.listdir(YAML_DIR):
        if fn.endswith(".yaml"):
            docs[fn[:-5]] = load_yaml(os.path.join(YAML_DIR, fn))
    order = [t for t in TABLE_ORDER if t in docs]
    extra = sorted(set(docs) - set(order))
    order += extra
    missing_guide = [t for t in order if not docs[t].get("guide")]
    if missing_guide:
        raise SystemExit("datasets missing guide field: " + ", ".join(missing_guide))
    tables_line = ",".join(order)
    segments = []
    for t in order:
        segments.append("\n- {d}（{g}）：{guide}".format(
            d=t, g=docs[t].get("grain", "").strip(), guide=docs[t]["guide"].strip(),
        ))
    body = HEADER.format(n=len(order)) + "".join(segments) + FOOTER
    content = FILE_HEADER + "TABLES: " + tables_line + "\nGUIDE_START" + body + "\nGUIDE_END\n"
    return content


def main() -> int:
    content = build_contract()
    if "--print" in sys.argv:
        print(content)
        return 0
    if "--check" in sys.argv:
        try:
            deployed = io.open(TARGET_PATH, encoding="utf-8").read()
        except OSError:
            print("CONTRACT DRIFT: contract.txt missing at", TARGET_PATH)
            return 1
        if deployed == content:
            print("CONTRACT OK: contract.txt matches datasets/*.yaml")
            return 0
        print("CONTRACT DRIFT: contract.txt differs from datasets/*.yaml — run gen_tool_contract.py")
        return 1
    io.open(TARGET_PATH, "w", encoding="utf-8", newline="\n").write(content)
    print("written:", format_agent_path(TARGET_PATH), "bytes:", len(content.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
