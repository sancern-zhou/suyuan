# -*- coding: utf-8 -*-
"""Survey all 3 source DBs for actively-updating tables outside our sync scope.

Method:
1. Row counts per table via dm_db_partition_stats (cheap, one query per DB).
2. For candidate tables (rows>0), pick datetime-ish columns from sys.columns and
   take MAX() of the best update-candidate column (UpdateTime > CreateTime > any).
3. Report tables whose max is recent (>= 2026-09-01) and NOT in sync scope.
4. air_province_data (13k tables): filter out partition shells by name pattern first.
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pyodbc

cfg = json.load(open(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json", encoding="utf-8"))
src = cfg["source"]
cs = (
    f"Driver={{ {src['driver']} }};" if False else
    "Driver={%s};Server=%s;UID=%s;PWD=%s;MARS_Connection=yes;" % (src["driver"], src["server"], src["user"], src["password"])
)
cn = pyodbc.connect(cs, timeout=30)

synced = set(k.lower() for k in cfg["tables"])
# known deliberately-excluded / non-business patterns
EXCLUDE_PAT = [
    r"^vdo_equipment_\d{8}$", r"^cache_db", r"^bak", r"_bak$", r"_error\d+$", r"_error$",
    r"^\d", r"^tmp", r"_tmp$", r"^test", r"^copy", r"20\d{6}$", r"_20\d{2}$",
]

# ---------- step 1: row counts
def table_rows(db):
    q = (
        "select t.name, sum(p.rows) "
        "from [%s].sys.tables t "
        "join [%s].sys.partitions p on t.object_id=p.object_id and p.index_id in (0,1) "
        "group by t.name" % (db, db)
    )
    cur = cn.cursor()
    cur.execute(q)
    return {n: rc for n, rc in cur.fetchall()}

# ---------- step 2: datetime columns per table
def date_cols(db):
    q = (
        "select t.name, c.name "
        "from [%s].sys.columns c "
        "join [%s].sys.types ty on c.user_type_id=ty.user_type_id "
        "join [%s].sys.tables t on c.object_id=t.object_id "
        "where ty.name in ('datetime','datetime2','smalldatetime','date')"
        % (db, db, db)
    )
    cur = cn.cursor()
    cur.execute(q)
    m = {}
    for t, c in cur.fetchall():
        m.setdefault(t, []).append(c)
    return m

def rank_cols(cols):
    """Prefer UpdateTime-ish over CreateTime-ish over the rest."""
    upd = [c for c in cols if re.search(r"update|modify|last|changetime|operatetime|timepoint|finishtime|applytime|approvetime", c, re.I)]
    cre = [c for c in cols if re.search(r"create|regist|input|add", c, re.I)]
    rest = [c for c in cols if c not in upd and c not in cre]
    return (upd + cre + rest)[:3]

RECENT_CUTOFF = "2026-09-01"

report = []
for db in ["opa_product_data", "air_province_bsd", "air_province_data"]:
    rows = table_rows(db)
    cols = date_cols(db)
    names = sorted(rows)
    if db == "air_province_data":
        # partition shells: integrated_30s_2024_3033a / Moniter_5m_xxx_yyyymm etc.
        names = [
            n for n in names
            if rows.get(n, 0) > 0
            and not re.search(r"_20\d{2}(_|$)", n)          # year-partitioned
            and not re.search(r"^\w+_(30s|1m|5m|10m|1h|60s)\b", n, re.I)
            and not re.search(r"^(integrated|moniter|monitor|minuter)", n, re.I)
        ]
    else:
        names = [n for n in names if rows.get(n, 0) > 0]
    print("[%s] tables with rows>0 after filter: %d" % (db, len(names)), flush=True)
    for n in names:
        nl = n.lower()
        if nl in synced:
            continue
        if any(re.search(p, nl) for p in EXCLUDE_PAT):
            continue
        cand = rank_cols(cols.get(n, []))
        best = None
        for c in cand:
            try:
                cur = cn.cursor()
                cur.execute("select max([%s]) from [%s].dbo.[%s]" % (c, db, n))
                v = cur.fetchone()[0]
                if v and (best is None or str(v) > str(best[1])):
                    best = (c, v)
            except Exception:
                continue
        if best and str(best[1]) >= RECENT_CUTOFF:
            report.append((db, n, rows.get(n, 0), best[0], best[1]))

print("\n=== ACTIVELY UPDATING (max >= 2026-09-01), NOT in sync scope ===")
for db, n, rc, c, v in sorted(report):
    print("%-20s %-42s rows=%-9s max(%s)=%s" % (db, n, rc, c, v))
print("\ntotal:", len(report))
