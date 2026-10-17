# -*- coding: utf-8 -*-
"""站房动环小时表批量同步驱动(每日 02:30, sync-daily.cmd 调用)。

顺序同步 sync_config.json 中全部 integrated_h_<年>_<站> 条目:
- 首次运行(无水位)自动全量, 受 where 谓词限制只拉 timepoint >= 2026-10-01(回填);
- 之后每次增量只拉新 id; 单表失败不影响其余表(逐表记录, 退出码汇总)。
每年 1 月切换年份后, 用 gen_env_sync_config.py 重新生成条目。

用法:
    E:\Tools\Python311\python.exe sync_env_hourly.py            # 增量(首次自动全量)
    E:\Tools\Python311\python.exe sync_env_hourly.py --full     # 强制全量重拉(修正数据用)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_table  # noqa: E402

PREFIX = "integrated_h_"


async def main_async(full: bool) -> int:
    cfg = sync_table.load_config()
    tables = sorted(t for t in cfg["tables"] if t.startswith(PREFIX))
    if not tables:
        print("no %s* entries in sync_config.json" % PREFIX, flush=True)
        return 1
    print("env hourly sync: %d tables (full=%s)" % (len(tables), full), flush=True)
    failed = []
    for i, table in enumerate(tables, 1):
        try:
            await sync_table.run_sync(table, full)
        except Exception as exc:  # noqa: BLE001 - 单表失败不阻断其余表
            failed.append(table)
            print("[%d/%d] %s FAILED: %s" % (i, len(tables), table, exc), flush=True)
    print("env hourly sync done: %d ok, %d failed" % (len(tables) - len(failed), len(failed)), flush=True)
    return 1 if failed else 0


def main() -> int:
    return asyncio.run(main_async("--full" in sys.argv))


if __name__ == "__main__":
    sys.exit(main())
