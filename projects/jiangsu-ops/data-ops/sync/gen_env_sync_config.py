# -*- coding: utf-8 -*-
"""生成/刷新 sync_config.json 中的站房动环小时表条目(integrated_h_2026_<站>)。

用法(在 runtime 目录运行, 需要真实凭据):
    E:\Tools\Python311\python.exe gen_env_sync_config.py            # 增改 101 条目(备份后写入)
    E:\Tools\Python311\python.exe gen_env_sync_config.py --check    # 只校验, 不写

规则:
- 站名录 = PostgreSQL jiangsu_mart.dim_station 中 is_active_provincial = true 的 101 站;
- 源表   = SQL Server air_province_data.dbo.integrated_h_2026_<站小写>(按年分片, 每年 1 月需换年份);
- 范围   = where timepoint >= CUTOFF(当前 2026-06-01; 2026-10-19 用户决策从 10 月窗口前推到 6 月, 此谓词每次拉取都生效);
- 增量   = id 整型严格递增(平台不回写旧行, mark 变更极少, 如需修正走 --full 重拉)。

每年 1 月: 修改本文件 YEAR/CUTOFF 常量后重跑即可切换到 integrated_h_2027_*。
"""
import asyncio
import datetime as dt
import io
import json
import re
import shutil
import sys
from pathlib import Path

import pyodbc

SYNC_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SYNC_DIR / "sync_config.json"

YEAR = "2026"
CUTOFF = "2026-10-01"
SOURCE_DB = "air_province_data"
PREFIX = f"integrated_h_{YEAR}_"

ENV_SYS_PATH = r"E:\suyuan\backend\.env.jiangsu-ops"


def _pg_dsn() -> str:
    for line in io.open(ENV_SYS_PATH, "r", encoding="utf-8-sig"):
        m = re.match(r"^\s*DATABASE_URL=(.*)$", line)
        if m:
            return m.group(1).strip().replace("+asyncpg", "")
    raise RuntimeError("DATABASE_URL not found in .env.jiangsu-ops")


async def provincial_codes() -> list[str]:
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn())
    try:
        rows = await conn.fetch(
            "SELECT station_code FROM jiangsu_mart.dim_station "
            "WHERE is_active_provincial = true ORDER BY station_code")
        return [r["station_code"] for r in rows]
    finally:
        await conn.close()


def existing_shards(cfg: dict) -> set[str]:
    src = cfg["source"]
    conn = pyodbc.connect(
        f"DRIVER={{{src['driver']}}};Server={src['server']};Database=master;"
        f"UID={src['user']};PWD={src['password']};", timeout=30)
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT name FROM [%s].sys.tables WHERE name LIKE ?" % SOURCE_DB,
            PREFIX + "%").fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def build_entry(station_code: str) -> dict:
    return {
        "source_db": SOURCE_DB,
        "source_table": f"dbo.{PREFIX}{station_code.lower()}",
        "mode": "incremental",
        "incremental_column": "id",
        "incremental_type": "int",
        "pk": ["id"],
        "where": f"timepoint >= '{CUTOFF}'",
        "columns": ["id", "stationcode", "timepoint", "pollutantcode",
                    "monvalue", "mark", "modifytime", "createtime"],
        "column_types": {
            "id": "int",
            "timepoint": "timestamp",
            "modifytime": "timestamp",
            "createtime": "timestamp",
        },
        "_comment": f"站房动环小时数据 {station_code}(回填 {CUTOFF} 起, 按年分片, "
                    f"每年1月换表名: gen_env_sync_config.py)",
    }


def main() -> int:
    check_only = "--check" in sys.argv
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    codes = asyncio.run(provincial_codes())
    shards = existing_shards(cfg)

    added, missing = [], []
    for code in codes:
        table = PREFIX + code.lower()
        if table not in shards:
            missing.append(code)
            continue
        entry = build_entry(code)
        if table not in cfg["tables"]:
            added.append(table)
        cfg["tables"][table] = entry

    stale = sorted(t for t in cfg["tables"]
                   if t.startswith(PREFIX) and t[len(PREFIX):].upper() not in set(codes))
    print(f"provincial stations: {len(codes)}")
    print(f"entries written: {len(codes) - len(missing)} (new: {len(added)})")
    if missing:
        print(f"MISSING source shards ({len(missing)}): {','.join(missing)}")
    if stale:
        print(f"stale env entries not in current list ({len(stale)}): {','.join(stale)}")
    if check_only:
        return 0

    backup = CONFIG_PATH.with_suffix(".json.bak_env_" + dt.date.today().strftime("%Y%m%d"))
    if not backup.exists():
        shutil.copyfile(CONFIG_PATH, backup)
        print(f"backup written: {backup.name}")
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"config updated: {CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
