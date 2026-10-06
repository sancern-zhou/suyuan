# -*- coding: utf-8 -*-
"""Check dim grain uniqueness + column types for the 4 new tables."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pyodbc

from _creds import source_connstr

cn = pyodbc.connect(source_connstr(), timeout=30)
cur = cn.cursor()

print("=== bsd_moniter_parameter grain ===")
cur.execute("""select count(*), count(distinct cast(devicemodel as nvarchar)+','+cast(parameterid as nvarchar)),
                      count(distinct cast(devicemodel as nvarchar)+','+cast(parameterid as nvarchar)+','+isnull(statusname,''))
               from air_province_bsd.dbo.bsd_moniter_parameter""")
print("  rows / (model,param) / (model,param,name):", cur.fetchone())
cur.execute("""select top 5 cast(devicemodel as nvarchar)+','+cast(parameterid as nvarchar) k, count(*)
               from air_province_bsd.dbo.bsd_moniter_parameter group by cast(devicemodel as nvarchar)+','+cast(parameterid as nvarchar) having count(*)>1""")
print("  dup (model,param):", cur.fetchall())
cur.execute("select status, count(*) from air_province_bsd.dbo.bsd_moniter_parameter group by status")
print("  status dist:", cur.fetchall())
cur.execute("select warntype, count(*) from air_province_bsd.dbo.bsd_moniter_parameter group by warntype")
print("  warntype dist:", cur.fetchall())

print("=== column types for new tables ===")
for db, tab in [
    ("air_province_data", "qc_backorderarrangelog"),
    ("air_province_bsd", "bsd_supply"),
    ("air_province_bsd", "bsd_moniter_parameter"),
    ("opa_product_data", "DEV_SCRAP"),
]:
    cur.execute("""select c.name, ty.name, c.max_length from %s.sys.columns c
                   join %s.sys.types ty on c.user_type_id=ty.user_type_id
                   where c.object_id=object_id('%s.dbo.%s') order by c.column_id""" % (db, db, db, tab))
    print(" ", tab, ":", ", ".join("%s:%s(%s)" % (r[0], r[1], r[2]) for r in cur.fetchall()))

print("=== bsd_supply total rows / id uniqueness ===")
cur.execute("select count(*), count(distinct Id) from air_province_bsd.dbo.bsd_supply")
print("  rows/distinct Id:", cur.fetchone())

cn.close()
print("DONE")
