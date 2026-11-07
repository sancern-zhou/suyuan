"""一次性回补 TownStationData 乡镇站小时/日断档（旧云平台替代源）。

用法（宿主机，conda 环境 backend_py311，cwd=backend）：

    TOWN_HOUR_LOOKBACK_HOURS=320 \
    TOWN_DAY_LOOKBACK_DAYS=16 \
    /opt/miniconda3/envs/backend_py311/bin/python \
      ../projects/xuchang/data-ops/backfill_town_hour_day/backfill.py

- 小时窗口默认 320 小时（覆盖 2026-10-17 起的原始/审核断档），日值窗口
  16 天（覆盖 2026-10-13 起缺口）；幂等 upsert，可重复执行；
- 日常增量由 xuchang_town_hour_fetcher / xuchang_town_day_fetcher 调度接管。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.fetchers.xuchang_town_hour_day import XuchangTownAirDataFetcher


async def main() -> None:
    for kind in ("day", "hour"):
        fetcher = XuchangTownAirDataFetcher(data_kind=kind)
        result = await fetcher.fetch_and_store()
        print(kind, result)


asyncio.run(main())
