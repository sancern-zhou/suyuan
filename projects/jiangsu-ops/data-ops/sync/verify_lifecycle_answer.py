# -*- coding: utf-8 -*-
"""Final E2E: answer '最近一周设备生命周期' in ONE SQL as agent_reader (what the agent can now do)."""
import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import asyncpg

dsn = "postgresql://agent_reader:AgentRead%23Js2026@127.0.0.1:5432/suyuan_jiangsu"


async def main():
    pg = await asyncpg.connect(dsn)
    await pg.execute("SET search_path TO jiangsu_mart")

    print("== 一条 SQL 回答'最近一周设备生命周期'(agent 现在的能力) ==")
    rows = await pg.fetch("""
        select event_time, station_code, station_name, device_code, device_type_name,
               state_after, event_type, working_order_code
        from mart_device_lifecycle_analysis
        where event_time >= now() - interval '7 days'
        order by event_time desc limit 12""")
    for r in rows:
        print("  %s | %s %s | %s [%s] | %s/%s | %s" % (
            str(r[0])[:16], r[1], (r[2] or "")[:10], r[3], r[4] or "-",
            r[5] or ("" if r[6] else "报废"), r[6] or "", r[7] or "-"))

    print("\n== 近一周事件统计 ==")
    rows = await pg.fetch("""
        select event_type, count(*) from mart_device_lifecycle_analysis
        where event_time >= now() - interval '7 days' group by 1 order by 2 desc""")
    print("  ", [(r[0], r[1]) for r in rows])

    print("\n== 备机更换及时性示例: DeviceSpare 事件(近90天) ==")
    rows = await pg.fetch("""
        select event_time, station_code, station_name, device_code, remarks
        from mart_device_lifecycle_analysis
        where state_after = 'DeviceSpare' and event_time >= now() - interval '90 days'
        order by event_time desc limit 5""")
    for r in rows:
        print("  %s | %s %s | %s" % (str(r[0])[:16], r[1], (r[2] or "")[:12], r[3]))

    print("\n== dim_device.device_type_name 抽查 ==")
    rows = await pg.fetch("""
        select device_type, device_type_name, count(*) from dim_device
        group by 1,2 order by 3 desc limit 6""")
    for r in rows:
        print("  %s = %s x %s" % (r[0], r[1], r[2]))

    await pg.close()


asyncio.run(main())
