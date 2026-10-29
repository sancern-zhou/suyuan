# -*- coding: utf-8 -*-
"""题目项列语义普查：组分站分表列语义 × 档案标签 + 主网表单题目项字典。

产物：projects/guangdong/docs/sup-instrument-rules/column-semantics.md

数据来源：
  1. guangdong_mart 全部 sup_rf% 表（列填充率，按 ruleitemtag 分组）——复用
     sup_tag_inventory.py 的填充率算法；
  2. sup_form_profiles.yaml（按 tag 建档的列语义：range/formula/date/enum/abnormal）；
  3. 源库 dbo.RF_ITEM（主网表单题目项字典：tag -> 题目序号/题目名称）。

标注约定：
  - "档案" = 语义来自 sup_form_profiles.yaml（confirmed: true/false 原样标注）；
  - "未确认" = 档案未覆盖，当前按列名/占位规则推断，需业务确认后补档。

用法（backend 目录）：
    python scripts/form_semantics_census.py [--out <path>] [--schema guangdong_mart]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import psycopg2
import yaml

import sup_tag_inventory as inv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env.guangdong"
PROFILES_PATH = BACKEND_DIR / "app" / "services" / "ops_audit" / "configs" / "sup_form_profiles.yaml"
DEFAULT_OUT = BACKEND_DIR.parent / "projects" / "guangdong" / "docs" / "sup-instrument-rules" / "column-semantics.md"

PLACEHOLDER_RE = re.compile(r"^(string\d+|bool_\d+|time\d+|remark\d*)$", re.I)


def env_value(key: str) -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


def load_global_labels() -> dict[str, str]:
    """全局列名字典（仅语义标注，不参与规则）。"""
    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
    return {str(k).lower(): str(v) for k, v in (data.get("column_labels") or {}).items()}


def load_profile_labels() -> dict[str, dict[str, tuple[str, str]]]:
    """tag -> {column: (label, 确认状态)}。"""
    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
    profiles = data.get("form_profiles") or {}
    result: dict[str, dict[str, tuple[str, str]]] = {}
    for tag, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        labels: dict[str, tuple[str, str]] = {}
        confirmed = "confirmed=true" if profile.get("confirmed") else ""
        for group in ("range_columns", "enum_columns", "date_columns", "abnormal_columns",
                      "required_columns", "formula_columns"):
            for item in profile.get(group) or []:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("business") or "").strip()
                state = "confirmed=true" if item.get("confirmed") else (
                    "confirmed=false" if "confirmed" in item else (confirmed or "档案未标确认"))
                target = item.get("column") or item.get("target")
                if target and label:
                    labels[str(target).lower()] = (label, state)
                for key in ("start", "end"):
                    if item.get(key) and label:
                        labels[str(item[key]).lower()] = (label, state)
                for name in item.get("inputs") or []:
                    if label:
                        labels.setdefault(str(name).lower(), ("参与计算：" + label, state))
        result[str(tag)] = labels
    return result


def source_item_dictionary() -> dict[str, list[str]]:
    """源库 RF_ITEM：tag -> [题目序号.题目名称]（主网表单题目项字典）。"""
    import pyodbc

    conn_str = (
        "Driver={%s};Server=%s,%s;Database=%s;UID=%s;PWD=%s;"
        % (env_value("OPS_SQLSERVER_DRIVER") or "ODBC Driver 17 for SQL Server",
           env_value("OPS_SQLSERVER_HOST"), env_value("OPS_SQLSERVER_PORT") or "1433",
           env_value("OPS_SQLSERVER_DATABASE"), env_value("OPS_SQLSERVER_USER"),
           env_value("OPS_SQLSERVER_PASSWORD"))
    )
    conn = pyodbc.connect(conn_str, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT RULEITEMTAG, ITEMNUM, ITEMNAME FROM dbo.RF_ITEM "
            "WHERE RULEITEMTAG IS NOT NULL AND RULEITEMTAG NOT LIKE 'jcx%' "
            "GROUP BY RULEITEMTAG, ITEMNUM, ITEMNAME ORDER BY RULEITEMTAG, ITEMNUM"
        )
        result: dict[str, list[str]] = {}
        for tag, num, name in cur.fetchall():
            if not name:
                continue
            seq = str(int(num)) if num is not None else "-"
            result.setdefault(str(tag).strip(), []).append("%s. %s" % (seq, str(name).strip()))
        return result
    finally:
        conn.close()


def tag_stats_safe(cur, schema: str, table: str) -> list[dict]:
    """tag 行数/近 90 天/日期范围；缺时间列的 ODS 表按 0/NULL 降级。"""
    has_ct = inv.column_exists(cur, schema, table, "createtime")
    has_cd = inv.column_exists(cur, schema, table, "checkdate")
    recent = ("count(*) FILTER (WHERE createtime >= now() - interval '90 days')"
              if has_ct else "0")
    first = "to_char(min(checkdate),'YYYY-MM-DD')" if has_cd else "NULL"
    last = "to_char(max(checkdate),'YYYY-MM-DD')" if has_cd else "NULL"
    cur.execute(
        'SELECT ruleitemtag, count(*) AS total, %s AS recent, %s AS first_check, %s AS last_check '
        'FROM %s.%s GROUP BY ruleitemtag ORDER BY total DESC'
        % (recent, first, last, inv.quote_ident(schema), inv.quote_ident(table))
    )
    return [{"tag": r[0] or "(空)", "total": r[1], "recent": r[2],
             "first_check": r[3], "last_check": r[4]} for r in cur.fetchall()]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--schema", default="guangdong_mart")
    parser.add_argument("--samples", action="store_true")
    args = parser.parse_args()

    labels = load_profile_labels()
    conn = psycopg2.connect(inv.mart_url(), connect_timeout=15)
    cur = conn.cursor()
    schemas = [s for s in (args.schema, "guangdong_ods") if s]
    table_schemas: dict[str, str] = {}
    for schema in schemas:
        for table in inv.sup_tables(cur, schema):
            table_schemas.setdefault(table, schema)

    lines = [
        "# 题目项列语义普查（自动生成）",
        "",
        "- 生成脚本：`backend/scripts/form_semantics_census.py`（%s）。" % dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "- 来源：`guangdong_mart`/`guangdong_ods` 全部 sup_rf% 表填充率 × `sup_form_profiles.yaml` 档案标签 × 源库 `dbo.RF_ITEM` 题目项字典。",
        "- 标注：**档案**=已有语义档案（附 confirmed 状态）；**未确认**=按列名/占位规则推断，待业务确认。",
        "- 未列入的列：填充率 <15% 或技术列（工单号/站点/设备/流程等）。",
        "",
    ]

    global_labels = load_global_labels()
    table_count = tag_count = col_count = unconfirmed = labeled = placeholder = 0
    unprofiled_tags: list[str] = []
    for table, schema in sorted(table_schemas.items()):
        if not inv.column_exists(cur, schema, table, "ruleitemtag"):
            continue
        stats = tag_stats_safe(cur, schema, table)
        if not stats:
            continue
        table_count += 1
        lines += ["## %s（%s）" % (table, schema), ""]
        for item in stats:
            tag = item["tag"]
            if tag == "(空)":
                continue
            total, filled = inv.fill_stats(cur, schema, table, tag)
            if not total:
                continue
            tag_count += 1
            tag_labels = labels.get(tag) or {}
            if not tag_labels:
                unprofiled_tags.append("%s/%s" % (table, tag))
            lines += [
                "### %s / %s（%d 行，近 90 天 %d）" % (table, tag, item["total"], item["recent"]),
                "",
                "| 列 | 填充率 | 语义 | 来源 |",
                "| --- | ---: | --- | --- |",
            ]
            for column, rate in filled:
                if column.startswith("_"):
                    continue
                col_count += 1
                lower = column.lower()
                hit = tag_labels.get(lower)
                if hit:
                    meaning, source = hit
                    labeled += 1
                elif lower in global_labels:
                    meaning, source = global_labels[lower], "全局字典"
                    labeled += 1
                elif PLACEHOLDER_RE.match(lower):
                    meaning, source = "题目项占位列（序号列，需结合表单模板确认）", "占位"
                    placeholder += 1
                elif re.match(r"^result_\d+$", lower):
                    meaning = "检查结果%d（命名约定）" % int(lower.split("_")[1])
                    source = "命名约定"
                    labeled += 1
                elif lower.endswith("isitnormal") and len(lower) > len("isitnormal"):
                    meaning = "%s 检查是否正常（命名约定）" % lower[:-len("isitnormal")]
                    source = "命名约定"
                    labeled += 1
                else:
                    meaning = "未确认（按列名推断）"
                    source = "未确认"
                    unconfirmed += 1
                lines.append("| `%s` | %.0f%% | %s | %s |" % (column, rate * 100, meaning, source))
            lines.append("")

    # 主网 RF_ITEM 题目项字典
    lines += ["## 主网表单题目项字典（源库 dbo.RF_ITEM）", ""]
    try:
        item_dict = source_item_dictionary()
        lines += [
            "- 用途：主网 RF/SEC 表单的题目项名称清单（区县口径的题目文本）；列级映射仍以代码中的",
            "  `rf_field_profiles.yaml` / `RF_TABLES` 列别名为准。",
            "",
            "| ruleitemtag | 题目数 | 题目项（序号. 名称，最多 30 项） |",
            "| --- | ---: | --- |",
        ]
        for tag in sorted(item_dict):
            names = item_dict[tag]
            lines.append("| %s | %d | %s |" % (tag, len(names), "；".join(names[:30])))
        lines.append("")
    except Exception as exc:  # noqa: BLE001
        lines += ["- 源库读取失败：%s" % exc, ""]

    conn.close()

    lines += [
        "## 缺口统计",
        "",
        "- 扫描表：%d；有数据 tag：%d；参与普查列：%d。" % (table_count, tag_count, col_count),
        "- 已标注列：%d（档案/全局字典/命名约定；占 %.0f%%）。" % (
            labeled, (labeled / col_count * 100) if col_count else 0),
        "- 题目项占位列：%d（stringN/bool_N，需表单模板确认）。" % placeholder,
        "- 未确认列：%d（占 %.0f%%）。" % (unconfirmed, (unconfirmed / col_count * 100) if col_count else 0),
        "- 无档案的 tag：%d%s" % (
            len(unprofiled_tags),
            ("（示例：" + "、".join(unprofiled_tags[:10]) + "…）") if unprofiled_tags else ""),
        "",
        "## 下一步",
        "",
        "1. 剩余未确认列以仪器专有命名为主（fullscale*/mcl*/lingdian*/bz* 等），需对照",
        "   `projects/guangdong/docs/sup-instrument-rules/` 的 22 类仪器转录分册逐族确认后，",
        "   补 `sup_form_profiles.yaml` 的 `column_labels`（仅语义，不触发规则）。",
        "2. 占位列（stringN/bool_N）需结合表单模板/题目项确定序号语义，确定前保持占位标注。",
        "3. 若业务确认某表单族的阈值判据，再为该 tag 建档案规则组（会启用及时性/区间规则，需单独评审）。",
        "",
    ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("written: %s | tables=%d tags=%d cols=%d unconfirmed=%d" % (
        out_path, table_count, tag_count, col_count, unconfirmed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
