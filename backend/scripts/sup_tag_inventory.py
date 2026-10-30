"""组分站表单 tag 盘点：扫描全部 sup_rf% 分表，输出 tag 分布、列填充率与样本行。

用法（backend 目录）：
    python scripts/sup_tag_inventory.py [--out <markdown 路径>]

输出默认写入 projects/guangdong/docs/sup-instrument-rules/tag-inventory.md，
供 sup_form_profiles.yaml 建档（阶段 T2/T3）作唯一清单依据。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import psycopg2
import yaml

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.guangdong"
DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "projects/guangdong/docs/sup-instrument-rules/tag-inventory.md"

# 业务空值：这些取值视同未填写，不计入填充率。
BLANK_TEXTS = {"", "/", "-", "—", "无", "nan", "none", "null"}
# 技术列：不参与填充率展示。
TECH_COLUMNS = {
    "id", "workingordercode", "stationid", "stationcode", "uniquecode",
    "operationunitid", "deviceid", "prepareuserid", "preparetime",
    "reviewuserid", "reviewtime", "audituserid", "audittime", "processtype",
    "createuserid", "createtime", "updateuserid", "updatetime", "detailid",
    "refreshed_at", "ruleitemtag", "pollutanttype", "checkdate",
}
SAMPLE_VALUE_MAX = 36
SAMPLE_COLUMNS_MAX = 24
FILL_COLUMNS_MAX = 40
FILL_MIN_RATE = 0.15


def mart_url() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPS_MART_DATABASE_URL="):
            return line.strip().split("=", 1)[1]
    raise RuntimeError(f"{ENV_FILE} 未配置 OPS_MART_DATABASE_URL")


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def business_filled_sql(column: str) -> str:
    col = quote_ident(column)
    blanks = ", ".join(f"'{t}'" for t in sorted(BLANK_TEXTS))
    return f"sum(CASE WHEN {col} IS NOT NULL AND btrim({col}::text) NOT IN ({blanks}) THEN 1 ELSE 0 END)"


def table_columns(cur, schema: str, table: str) -> list[dict]:
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, table),
    )
    return [{"name": r[0], "type": r[1]} for r in cur.fetchall()]


def sup_tables(cur, schema: str) -> list[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name LIKE %s ORDER BY table_name",
        (schema, "sup_rf%"),
    )
    return [r[0] for r in cur.fetchall()]


def tag_stats(cur, schema: str, table: str) -> list[dict]:
    cur.execute(
        f"SELECT ruleitemtag, count(*) AS total, "
        f"count(*) FILTER (WHERE createtime >= now() - interval '90 days') AS recent, "
        f"to_char(min(checkdate),'YYYY-MM-DD') AS first_check, "
        f"to_char(max(checkdate),'YYYY-MM-DD') AS last_check "
        f"FROM {quote_ident(schema)}.{quote_ident(table)} GROUP BY ruleitemtag "
        f"ORDER BY total DESC"
    )
    return [
        {"tag": r[0] or "(空)", "total": r[1], "recent": r[2],
         "first_check": r[3], "last_check": r[4]}
        for r in cur.fetchall()
    ]


def pollutant_stats(cur, schema: str, table: str, tag: str, limit: int = 5) -> list[str]:
    if not column_exists(cur, schema, table, "pollutanttype"):
        return []
    cur.execute(
        f"SELECT pollutanttype, count(*) FROM {quote_ident(schema)}.{quote_ident(table)} "
        f"WHERE ruleitemtag = %s GROUP BY pollutanttype ORDER BY count(*) DESC LIMIT %s",
        (tag, limit),
    )
    return [f"{r[0] or '(空)'}×{r[1]}" for r in cur.fetchall()]


def column_exists(cur, schema: str, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema=%s "
        "AND table_name=%s AND column_name=%s",
        (schema, table, column),
    )
    return cur.fetchone() is not None


def fill_stats(cur, schema: str, table: str, tag: str) -> tuple[int, list[tuple[str, float]]]:
    columns = [c for c in table_columns(cur, schema, table)
               if c["name"] not in TECH_COLUMNS]
    if not columns:
        return 0, []
    sums = ", ".join(f"{business_filled_sql(c['name'])} AS {quote_ident('f_' + c['name'])}" for c in columns)
    cur.execute(
        f"SELECT count(*) AS total, {sums} FROM {quote_ident(schema)}.{quote_ident(table)} "
        f"WHERE ruleitemtag = %s",
        (tag,),
    )
    row = cur.fetchone()
    total = row[0]
    filled = []
    for index, column in enumerate(columns, start=1):
        if total and row[index]:
            rate = row[index] / total
            if rate >= FILL_MIN_RATE:
                filled.append((column["name"], rate))
    filled.sort(key=lambda item: (-item[1], item[0]))
    return total, filled[:FILL_COLUMNS_MAX]


def sample_rows(cur, schema: str, table: str, tag: str, limit: int = 1) -> list[str]:
    keep = ["workingordercode", "checkdate", "pollutanttype", "devicebrand",
            "devicemodel", "remark"] + [
        c["name"] for c in table_columns(cur, schema, table)
        if c["name"] not in TECH_COLUMNS][:60]
    keep = [c for c in dict.fromkeys(keep) if column_exists(cur, schema, table, c)]
    select = ", ".join(quote_ident(c) for c in keep)
    cur.execute(
        f"SELECT {select} FROM {quote_ident(schema)}.{quote_ident(table)} "
        f"WHERE ruleitemtag = %s AND createtime >= now() - interval '90 days' "
        f"ORDER BY createtime DESC LIMIT %s",
        (tag, limit),
    )
    names = [d[0] for d in cur.description]
    lines = []
    for row in cur.fetchall():
        parts = []
        for name, value in zip(names, row):
            if value is None:
                continue
            text = str(value).strip()
            if text.lower() in BLANK_TEXTS or name in {"workingordercode", "checkdate"}:
                continue
            parts.append(f"{name}={text[:SAMPLE_VALUE_MAX]}")
            if len(parts) >= SAMPLE_COLUMNS_MAX:
                break
        lines.append(f"  - 样本 {row[names.index('workingordercode')]} ({row[names.index('checkdate')]}): " + "；".join(parts))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--schema", default="guangdong_mart")
    parser.add_argument("--samples", action="store_true", help="附 90 天内样本行")
    args = parser.parse_args()

    yaml.safe_load("{}")  # 依赖自检（与档案配置同源依赖）
    conn = psycopg2.connect(mart_url(), connect_timeout=15)
    cur = conn.cursor()
    schema = args.schema
    lines = [
        "# 组分站表单 tag 盘点（自动生成）",
        "",
        f"- 生成脚本：`backend/scripts/sup_tag_inventory.py`；扫描 {schema} 全部 sup_rf% 分表。",
        "- 填充率=非空且非业务占位（/、-、无等）的行占比；仅列出 ≥15% 的列，每 tag 最多 40 列。",
        "- 用途：sup_form_profiles.yaml 建档清单依据；对照表单标题见同目录各转录分册。",
        "",
    ]
    for table in sup_tables(cur, schema):
        if not column_exists(cur, schema, table, "ruleitemtag"):
            lines += [f"## {table}", "", "- 无 ruleitemtag 列，跳过。", ""]
            continue
        stats = tag_stats(cur, schema, table)
        cur.execute(f"SELECT count(*) FROM {quote_ident(schema)}.{quote_ident(table)}")
        total_rows = cur.fetchone()[0]
        lines += [f"## {table}（总行数 {total_rows}，tag 数 {len(stats)}）", "",
                  "| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |",
                  "| --- | ---: | ---: | --- | --- |"]
        for item in stats:
            pollutants = "、".join(pollutant_stats(cur, schema, table, item["tag"])) or "-"
            lines.append(
                f"| {item['tag']} | {item['total']} | {item['recent']} "
                f"| {item['first_check']} ~ {item['last_check']} | {pollutants} |"
            )
        lines.append("")
        for item in stats:
            if item["tag"] == "(空)":
                continue
            total, filled = fill_stats(cur, schema, table, item["tag"])
            if not total:
                continue
            cols_text = "，".join(f"{name}({rate:.0%})" for name, rate in filled) or "（无 ≥15% 填充列）"
            lines += [f"### {table} / {item['tag']}", "", f"填充列：{cols_text}", ""]
            if args.samples and item["recent"]:
                lines += sample_rows(cur, schema, table, item["tag"]) + [""]
    conn.close()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {out_path}")


if __name__ == "__main__":
    main()
