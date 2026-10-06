# -*- coding: utf-8 -*-
"""Verify bsd_DeviceType structure, join key to bsd_device.devicetype, and name coverage."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pyodbc

from _creds import source_connstr

cn = pyodbc.connect(source_connstr(), timeout=30)
cur = cn.cursor()

print("=== bsd_DeviceType (air_province_bsd) ===")
cur.execute("""select c.name, ty.name, c.max_length from air_province_bsd.sys.columns c
               join air_province_bsd.sys.types ty on c.user_type_id=ty.user_type_id
               where c.object_id=object_id('air_province_bsd.dbo.bsd_DeviceType') order by c.column_id""")
print("cols:", ", ".join("%s:%s(%s)" % (r[0], r[1], r[2]) for r in cur.fetchall()))
cur.execute("select count(*), count(distinct Code) from air_province_bsd.dbo.bsd_DeviceType")
print("rows / distinct Code:", cur.fetchone())
cur.execute("select top 8 Code, Name, status, PollutantCode from air_province_bsd.dbo.bsd_DeviceType order by Code")
for r in cur.fetchall():
    print("  ", r)

print("=== join bsd_device.devicetype -> bsd_DeviceType.Code ===")
cur.execute("""select count(*) from air_province_bsd.dbo.bsd_device d
               join air_province_bsd.dbo.bsd_DeviceType t on d.devicetype = t.Code""")
print("  joined:", cur.fetchone()[0])
cur.execute("""select count(*) from air_province_bsd.dbo.bsd_device d
               left join air_province_bsd.dbo.bsd_DeviceType t on d.devicetype = t.Code
               where t.Code is null""")
print("  devices with unmatched type code:", cur.fetchone()[0])
cur.execute("select top 5 devicetype, count(*) from air_province_bsd.dbo.bsd_device group by devicetype order by 2 desc")
print("  device devicetype dist:", cur.fetchall())

print("=== opa_product_data.dbo.bsd_DeviceType same table? ===")
cur.execute("select count(*) from opa_product_data.dbo.bsd_DeviceType")
print("  rows:", cur.fetchone()[0])

cn.close()
print("DONE")
