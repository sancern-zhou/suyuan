# -*- coding: utf-8 -*-
"""Verify join fanout and state/time features for qc_backorderarrangelog."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pyodbc

from _creds import source_connstr

cn = pyodbc.connect(source_connstr(), timeout=30)
cur = cn.cursor()

print("=== qc_arrangeresult uniquecode duplication ===")
cur.execute("select count(*), count(distinct uniquecode) from air_province_data.dbo.qc_arrangeresult")
print("  rows / distinct uniquecode:", cur.fetchone())
cur.execute("select top 3 uniquecode, count(*) c from air_province_data.dbo.qc_arrangeresult group by uniquecode order by c desc")
for r in cur.fetchall():
    print("   top dup:", r)

print("=== backorder uniquecode in arrangeresult? ===")
cur.execute("select count(*) from (select distinct uniquecode from air_province_data.dbo.qc_backorderarrangelog where create_time >= '2026-07-01') b left join (select distinct uniquecode from air_province_data.dbo.qc_arrangeresult) a on b.uniquecode=a.uniquecode where a.uniquecode is null")
print("  backorder uniquecodes NOT in arrangeresult:", cur.fetchone()[0])
cur.execute("select count(*) from (select distinct uniquecode from air_province_data.dbo.qc_backorderarrangelog where create_time >= '2026-07-01') b join (select distinct uniquecode from air_province_data.dbo.qc_historyresult) h on b.uniquecode=h.uniquecode")
print("  backorder uniquecodes IN qc_historyresult:", cur.fetchone()[0])

print("=== state vs recency (is state a progression?) ===")
cur.execute("""select state, count(*), min(convert(date,create_time)), max(convert(date,create_time))
              from air_province_data.dbo.qc_backorderarrangelog where create_time >= '2026-07-01' group by state""")
for r in cur.fetchall():
    print("   state=%s x %s  dates %s..%s" % (r[0], r[1], r[2], r[3]))

print("=== state by month (does 1 flow into 2?) ===")
cur.execute("""select convert(char(7), create_time, 120) ym, state, count(*) from air_province_data.dbo.qc_backorderarrangelog
              where create_time >= '2026-07-01' group by convert(char(7), create_time, 120), state order by 1, 2""")
for r in cur.fetchall():
    print("   %s state=%s x %s" % (r[0], r[1], r[2]))

print("=== per-station backorder volume (top 8, window) ===")
cur.execute("""select top 8 stationcode, count(*) c, count(distinct convert(date, start_time)) days
              from air_province_data.dbo.qc_backorderarrangelog where create_time >= '2026-07-01'
              group by stationcode order by c desc""")
for r in cur.fetchall():
    print("   %s x %s (days %s)" % (r[0], r[1], r[2]))

print("=== rows per uniquecode+datatype (pairing pattern) ===")
cur.execute("""select top 5 uniquecode, start_time, datatype, state, pollutantname
              from air_province_data.dbo.qc_backorderarrangelog
              where create_time >= '2026-09-25' order by create_time desc""")
for r in cur.fetchall():
    print("   ", r)

cn.close()
print("\nDONE")
