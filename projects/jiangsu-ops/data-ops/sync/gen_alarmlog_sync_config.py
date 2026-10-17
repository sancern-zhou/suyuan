# -*- coding: utf-8 -*-
"""生成/刷新 sync_config.json 中的告警分片与质控三件套条目(工具链本地化替换的数据底座)。

用法(在 runtime 目录运行):
    E:\Tools\Python311\python.exe gen_alarmlog_sync_config.py            # 增改(备份后写入)
    E:\Tools\Python311\python.exe gen_alarmlog_sync_config.py --check    # 只校验

四组条目:
- alarmlog_2026_<站小写> × 101(站房/仪器告警, 与 101 省控名录全交集; 窗口 lauchtime >= 2026-07-01);
- qc_his_task_status_result_2026 / qc_his_run_log_result_2026 / qc_his_air_data_result_2026
  (质控状态/运行日志/监测曲线, 按年单表, 省控过滤, 初始窗口 createtime >= 2026-07-01)。
每年 1 月: 改 YEAR 后重跑(质控三件套表名带年份, alarmlog 分片表名带年份)。
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
SINCE = "2026-07-01T00:00:00"
SOURCE_DB = "air_province_data"
ALARM_PREFIX = f"alarmlog_{YEAR}_"
QC_TABLES = [
    f"qc_his_task_status_result_{YEAR}",
    f"qc_his_run_log_result_{YEAR}",
    f"qc_his_air_data_result_{YEAR}",
]
QC_STATION_FILTER = ("[uniquecode] IN (SELECT [uniquecode] FROM air_province_bsd.dbo.bsd_station "
                     "WITH (NOLOCK) WHERE [stationtypeid] = 2 AND [status] = 1)")

ENV_SYS_PATH = r"E:\suyuan\backend\.env.jiangsu-ops"


def _pg_dsn() -> str:
    for line in io.open(ENV_SYS_PATH, "r", encoding="utf-8-sig"):
        m = re.match(r"^\s*DATABASE_URL=(.*)$", line)
        if m:
            return m.group(1).strip().replace("+asyncpg", "")
    raise RuntimeError("DATABASE_URL not found")


async def provincial_codes() -> list[str]:
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn())
    try:
        rows = await conn.fetch(
            "SELECT station_code FROM jiangsu_mart.dim_station WHERE is_active_provincial = true")
        return sorted(r["station_code"] for r in rows)
    finally:
        await conn.close()


def alarm_entry(station_code: str, columns: list[str], column_types: dict[str, str]) -> dict:
    table = f"{ALARM_PREFIX}{station_code.lower()}"
    return {
        "source_db": SOURCE_DB,
        "source_table": f"dbo.{table}",
        "mode": "incremental",
        "incremental_column": "id",
        "incremental_type": "int",
        "pk": ["id"],
        "apply_window": True,
        "initial_where_tpl": f"[id] >= (SELECT MIN([id]) FROM dbo.{table} WITH (NOLOCK) WHERE [lauchtime] >= '{{since}}')",
        "columns": columns,
        "column_types": column_types,
        "_comment": f"站房/仪器告警 {station_code}(窗口 {SINCE[:10]} 起; 2026-10-16 工具链本地化)",
    }


def qc_entry(table: str, columns: list[str], column_types: dict[str, str]) -> dict:
    return {
        "source_db": SOURCE_DB,
        "source_table": f"dbo.{table}",
        "mode": "incremental",
        "incremental_column": "id",
        "incremental_type": "int",
        "pk": ["id"],
        "apply_window": True,
        "initial_where_tpl": f"[id] >= (SELECT MIN([id]) FROM dbo.{table} WITH (NOLOCK) WHERE [createtime] >= '{{since}}')",
        "where": QC_STATION_FILTER,
        "columns": columns,
        "column_types": column_types,
        "_comment": f"质控{'状态' if 'task_status' in table else '运行日志' if 'run_log' in table else '监测曲线'}(按年表, 省控过滤, 窗口 {SINCE[:10]} 起; 2026-10-16 工具链本地化)",
    }


def table_columns(cfg: dict, table: str) -> list[str]:
    src = cfg["source"]
    conn = pyodbc.connect(
        f"DRIVER={{{src['driver']}}};Server={src['server']};Database=master;"
        f"UID={src['user']};PWD={src['password']};", timeout=30)
    try:
        rows = conn.execute(
            "SELECT c.name, t.name AS dtype FROM [%s].sys.columns c "
            "JOIN [%s].sys.types t ON c.user_type_id = t.user_type_id "
            "WHERE c.object_id=OBJECT_ID('[%s].dbo.[%s]') "
            "ORDER BY c.column_id" % (SOURCE_DB, SOURCE_DB, SOURCE_DB, table)).fetchall()
        return rows
    finally:
        conn.close()


_PG_TYPE = {
    "int": "integer", "bigint": "integer", "smallint": "integer", "tinyint": "integer",
    "datetime": "timestamp", "datetime2": "timestamp", "smalldatetime": "timestamp",
    "date": "timestamp", "bit": "boolean",
    "float": "double precision", "real": "double precision",
    "numeric": "numeric", "decimal": "numeric", "money": "numeric",
}


def typed_columns(cfg: dict, table: str) -> tuple[list[str], dict[str, str]]:
    """读取源表列名与实际类型, 自动映射 PG 类型(不靠手写, 杜绝 text 截断原生 int/datetime)。"""
    cols = table_columns(cfg, table)
    columns = [name for name, _ in cols]
    column_types = {}
    for name, dtype in cols:
        pg = _PG_TYPE.get((dtype or "").lower())
        if pg:
            column_types[name] = pg
    return columns, column_types


def main() -> int:
    check_only = "--check" in sys.argv
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    codes = asyncio.run(provincial_codes())

    shards = set()
    src = cfg["source"]
    conn = pyodbc.connect(
        f"DRIVER={{{src['driver']}}};Server={src['server']};Database=master;"
        f"UID={src['user']};PWD={src['password']};", timeout=30)
    try:
        shards = {r[0] for r in conn.execute(
            "SELECT name FROM [%s].sys.tables WHERE name LIKE ?" % SOURCE_DB,
            ALARM_PREFIX + "%").fetchall()}
    finally:
        conn.close()

    added = 0
    missing = [c for c in codes if f"{ALARM_PREFIX}{c.lower()}" not in shards]
    sample_cols = None
    for code in codes:
        table = f"{ALARM_PREFIX}{code.lower()}"
        if table not in shards:
            continue
        if sample_cols is None:
            sample_cols = typed_columns(cfg, table)
        columns, column_types = sample_cols  # 101 张分片表同构, 取一列即可
        if table not in cfg["tables"]:
            added += 1
        cfg["tables"][table] = alarm_entry(code, columns, column_types)

    for table in QC_TABLES:
        columns, column_types = typed_columns(cfg, table)
        if table not in cfg["tables"]:
            added += 1
        cfg["tables"][table] = qc_entry(table, columns, column_types)

    print(f"alarmlog entries: {len(codes) - len(missing)} (new {added}); missing shards: {missing or '无'}")
    print(f"qc yearly entries: {len(QC_TABLES)}")
    if check_only:
        return 0

    backup = CONFIG_PATH.with_suffix(".json.bak_alarm_" + dt.date.today().strftime("%Y%m%d"))
    if not backup.exists():
        shutil.copyfile(CONFIG_PATH, backup)
        print("backup:", backup.name)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config updated:", CONFIG_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
