"""临时脚本：sup_rf_common 关键表单类型列语义统计推断（二期档案建设辅助）。"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from decimal import Decimal

import psycopg2
import yaml  # noqa: F401  (保持与档案输出格式一致的占位)

URL = [l.strip().split("=", 1)[1] for l in open(".env.guangdong", encoding="utf-8") if l.startswith("OPS_MART_DATABASE_URL=")][0]

PCT_RE = re.compile(r"^-?\d+(?:\.\d+)?\s*%$")


def num(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    text = str(value).strip().replace("%", "").replace("％", "")
    try:
        return float(text)
    except ValueError:
        return None


def pct_cols(row):
    return [c for c in row if c.startswith("string") and PCT_RE.match(str(row[c] or "").strip())]


def infer_error_formula(cur, tag, limit=200):
    """对表单类型抽样，检验 error% ≈ (b-a)/a*100 的列组合。"""
    cur.execute(
        "SELECT * FROM guangdong_mart.sup_rf_common WHERE ruleitemtag=%s "
        "ORDER BY createtime DESC LIMIT %s",
        (tag, limit),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    str_cols = [c for c in cols if re.match(r"^string\d+$", c)]
    hits = defaultdict(int)
    for row in rows:
        for ec in pct_cols(row):
            e = num(row[ec])
            if e is None:
                continue
            for a_col in str_cols:
                a = num(row[a_col])
                if a is None or a == 0:
                    continue
                for b_col in str_cols:
                    if b_col == a_col:
                        continue
                    b = num(row[b_col])
                    if b is None:
                        continue
                    expected = (b - a) / a * 100
                    if abs(expected - e) <= max(0.06, abs(e) * 0.06):
                        hits[(ec, a_col, b_col)] += 1
    return len(rows), dict(hits)


def profile(cur, tag, limit=3):
    cur.execute(
        "SELECT * FROM guangdong_mart.sup_rf_common WHERE ruleitemtag=%s "
        "ORDER BY createtime DESC LIMIT %s",
        (tag, limit),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    print(f"\n##### {tag} ({len(rows)} sampled)")
    for idx, row in enumerate(rows):
        print(f"--- row {idx}: order={row.get('workingordercode')} checkdate={row.get('checkdate')}")
        for c in cols:
            v = row[c]
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            if c.startswith("bool_") and str(v) in {"0", "False", "false"}:
                continue
            print(f"  {c:14s} = {str(v)[:70]}")


if __name__ == "__main__":
    conn = psycopg2.connect(URL, connect_timeout=10)
    cur = conn.cursor()
    tag = os.getenv("INFER_TAG", "Sup_RF_PANsFlowCheck")
    if os.getenv("MODE") == "profile":
        profile(cur, tag)
    else:
        total, hits = infer_error_formula(cur, tag)
        print(f"type={tag} sampled={total}")
        for (ec, a, b), n in sorted(hits.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  {ec} = ({b}-{a})/{a}*100   hits={n}")
