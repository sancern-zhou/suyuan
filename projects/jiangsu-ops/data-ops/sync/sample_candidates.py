# -*- coding: utf-8 -*-
"""Sample key candidate tables to characterize them."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pyodbc

from _creds import source_connstr

cn = pyodbc.connect(source_connstr(), timeout=30)

def brief(db, tab, datecol, n=3):
    print("\n### %s.dbo.%s" % (db, tab))
    cur = cn.cursor()
    cur.execute(
        "select c.name, ty.name from [%s].sys.columns c "
        "join [%s].sys.types ty on c.user_type_id=ty.user_type_id "
        "where c.object_id=object_id('[%s].dbo.[%s]') order by c.column_id" % (db, db, db, tab)
    )
    cols = cur.fetchall()
    print("cols(%d):" % len(cols), ", ".join(r[0] for r in cols)[:400])
    try:
        cur.execute("select count(*) from [%s].dbo.[%s] where [%s] >= '2026-07-01'" % (db, tab, datecol))
        print("rows in window >=2026-07-01:", cur.fetchone()[0])
    except Exception as e:
        print("window count err:", e)
    top = ", ".join("cast([%s] as nvarchar(60))" % r[0] for r in cols[:10])
    try:
        cur.execute("select top %d %s from [%s].dbo.[%s] order by [%s] desc" % (n, top, db, tab, datecol))
        for row in cur.fetchall():
            print("  |", " | ".join(str(v)[:28] if v is not None else "-" for v in row))
    except Exception as e:
        print("sample err:", e)

brief("air_province_data", "dat_station_day", "modifytime")
brief("air_province_data", "aud_stationstate", "modifytime")
brief("air_province_data", "aud_audit_hourinvaliddata", "modifytime")
brief("air_province_data", "aud_audit_outlierdata", "modifytime")
brief("air_province_data", "qc_backorderarrangelog", "create_time")
brief("air_province_data", "air_livedata", "timepoint")
brief("air_province_bsd", "bsd_supply", "createdate")
brief("air_province_bsd", "bsd_moniter_parameter", "modifytime")
cn.close()
print("\nDONE")
