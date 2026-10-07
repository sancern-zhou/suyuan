# -*- coding: utf-8 -*-
"""Final verification as agent_reader: new marts + diagnosis join path."""
import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import asyncpg

cfg = json.load(open(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json", encoding="utf-8"))
dsn = "postgresql://agent_reader:AgentRead%23Js2026@127.0.0.1:5432/suyuan_jiangsu"


async def main():
    pg = await asyncpg.connect(dsn)
    await pg.execute("SET ROLE agent_reader")
    await pg.execute("SET search_path TO jiangsu_mart")

    n1 = await pg.fetchval("select count(*) from mart_qc_backorder_analysis")
    n2 = await pg.fetchval("select count(*) from dim_device_parameter")
    print("agent_reader: mart_qc_backorder_analysis rows =", n1, "| dim_device_parameter rows =", n2)

    print("\n-- 补测风暴 top5 (站点×日聚合, 近7天) --")
    rows = await pg.fetch("""
        select station_code, station_name, city_name, count(*) c,
               count(distinct date_trunc('day', start_time)) d
        from mart_qc_backorder_analysis
        where start_time >= now() - interval '7 days'
        group by 1,2,3 order by c desc limit 5""")
    for r in rows:
        print("  %s %s(%s) x %s 条 / %s 天" % (r[0], r[1], r[2], r[3], r[4]))

    print("\n-- 诊断路径: 3079A 的设备型号 → 参数清单(前8) --")
    rows = await pg.fetch("""
        select p.parameter_name, p.toplimit, p.lowlimit, p.unit, p.warntype, p.model_device_count
        from dim_device d
        join dim_device_parameter p on p.devicemodel_id = d.device_model_id
        where d.station_code = '3079A'
        order by p.parameter_name limit 8""")
    for r in rows:
        print("  %-14s [%s, %s] %s (%s, 该型号全省 %s 台)" % (r[0], r[2], r[1], r[3] or "-", r[4], r[5]))

    n3 = await pg.fetchval("""
        select count(*) from dim_device d
        join dim_device_parameter p on p.devicemodel_id = d.device_model_id""")
    print("\n  dim_device×dim_device_parameter 可关联行数:", n3)

    await pg.close()


asyncio.run(main())
