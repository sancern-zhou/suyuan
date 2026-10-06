# -*- coding: utf-8 -*-
"""jiangsu_query_metrics 直调验证（成功/拒绝路径）。"""
import asyncio
import os
import sys

sys.path.insert(0, r"E:\suyuan\backend")
os.environ.setdefault("CUBE_API_URL", "http://127.0.0.1:4610/cubejs-api/v1")
os.environ.setdefault("CUBE_API_SECRET", "fa947a6ee8160312416316176aeac34f9613bdb04373df0c79ca60aa89d3cd5f")

from app.tools.query.jiangsu_cube_metrics.tool import JiangsuQueryMetricsTool  # noqa: E402


async def main() -> None:
    tool = JiangsuQueryMetricsTool()
    cases = [
        ("T1 按市超期率",
         dict(measures=["WorkOrder.count", "WorkOrder.overdueRate"],
              dimensions=["WorkOrder.cityName"], order={"WorkOrder.count": "desc"}, limit=5)),
        ("T2 近7日趋势",
         dict(measures=["WorkOrder.count"], time_dimension="WorkOrder.createTime",
              date_range="last 7 days", granularity="day")),
        ("T3 告警过滤(紧急)",
         dict(measures=["AlarmEvent.count", "AlarmEvent.unresolvedRate"],
              filters=[{"member": "AlarmEvent.alarmLevel", "operator": "equals",
                        "values": ["紧急"]}])),
        ("T4 拒绝:未知成员",
         dict(measures=["WorkOrder.notExist"])),
        ("T5 拒绝:跨Cube",
         dict(measures=["WorkOrder.count", "AlarmEvent.count"])),
        ("T6 拒绝:空measures",
         dict(measures=[], dimensions=["WorkOrder.cityName"])),
    ]
    failures = 0
    for name, kwargs in cases:
        result = await tool.execute(context=None, **kwargs)
        ok = result.get("success")
        print(f"[{name}] success={ok}")
        if ok:
            rows = result.get("data") or []
            print(f"    rows={result.get('count')} as_of={result.get('data_as_of')}")
            for row in rows[:3]:
                print(f"    {row}")
        else:
            print(f"    summary={result.get('summary')}")
        expect_fail = name.startswith("T4") or name.startswith("T5") or name.startswith("T6")
        if expect_fail and ok:
            failures += 1
            print("    !!! 应拒绝却成功了")
        if (not expect_fail) and (not ok):
            failures += 1
            print("    !!! 应成功却失败了")
    print(f"\nRESULT: {'ALL PASS' if failures == 0 else f'{failures} FAILURES'}")


asyncio.run(main())
