"""同步河南省城市空气质量大数据综合应用系统年度对比三表到 DataCrawler。

首次（或 --full）全量复制；日常按源表 fetched_at 水位增量同步，并重取最新
MTD/YTD 快照。三张表在同一事务中幂等 upsert，全部成功后才推进水位。

宿主机运行：
  cd /root/suyuan/backend
  /opt/miniconda3/envs/backend_py311/bin/python \
    ../projects/xuchang/data-ops/sync_henan_platform_aq/sync.py [--full]

生产调度由 XuchangHenanPlatformAqSyncFetcher 每日 04:00 调用本模块。
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import aiomysql
import pyodbc

TABLES = {
    "HenanPlatformAqYearStat": (
        "standard", "data_type", "is_deduct", "region_id", "stat_year",
    ),
    "HenanPlatformAqMonthStat": (
        "standard", "data_type", "is_deduct", "region_id", "stat_year", "stat_month",
    ),
    "HenanPlatformAqAccumulateStat": (
        "standard", "data_type", "is_deduct", "region_id",
        "period_type", "period_start", "period_end",
    ),
}
DIMENSIONS = [
    "standard", "data_type", "is_deduct", "region_level", "region_id", "admin_code",
    "region_name", "stat_year", "stat_month", "period_type", "period_start", "period_end",
]
METRICS = [
    "pm25", "pm10", "so2", "no2", "co", "o3_8h_90", "total_index", "good_rate",
    "good_days", "bad_days", "bad_rate", "o3_over_days", "lost_fine_days", "dust_days",
]
YOY = ["yoy_base_year"] + [
    f"yoy_{name}" for name in (
        "pm25", "pm10", "so2", "no2", "co", "o3_8h_90", "total_index", "good_rate",
        "good_days", "bad_days", "bad_rate", "o3_over_days", "lost_fine_days", "dust_days",
    )
]
COLUMNS = DIMENSIONS + METRICS + YOY + ["fetched_at", "raw_json", "created_at"]
NUMERIC = METRICS + YOY[1:]


def ddl(table: str, unique_keys: tuple[str, ...]) -> str:
    numeric = "\n".join(f"  `{name}` DECIMAL(12,4) NULL," for name in NUMERIC)
    return f"""CREATE TABLE IF NOT EXISTS `{table}` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `standard` VARCHAR(10) NOT NULL COMMENT 'new新标准/old老标准',
  `data_type` VARCHAR(10) NOT NULL COMMENT 'SK实况',
  `is_deduct` TINYINT NOT NULL COMMENT '1扣沙',
  `region_level` VARCHAR(10) NOT NULL,
  `region_id` VARCHAR(20) NOT NULL,
  `admin_code` VARCHAR(20) NULL,
  `region_name` VARCHAR(50) NOT NULL,
  `stat_year` INT NOT NULL,
  `stat_month` INT NULL,
  `period_type` VARCHAR(10) NOT NULL COMMENT 'year/month/mtd/ytd',
  `period_start` DATE NOT NULL,
  `period_end` DATE NOT NULL,
{numeric}
  `yoy_base_year` INT NULL,
  `fetched_at` DATETIME(6) NOT NULL COMMENT '上游省平台抓取时间',
  `raw_json` LONGTEXT NULL COMMENT '上游原始响应',
  `created_at` DATETIME(6) NOT NULL COMMENT '上游入库时间',
  `synced_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `UK_{table}` ({', '.join(f'`{key}`' for key in unique_keys)}),
  KEY `IDX_{table}_fetched` (`fetched_at`),
  KEY `IDX_{table}_period` (`period_end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='河南省城市空气质量大数据综合应用系统年度对比本地副本(每日04:00增量同步)'"""


STATE_DDL = """CREATE TABLE IF NOT EXISTS HenanPlatformAqSyncState (
  table_name VARCHAR(64) PRIMARY KEY,
  last_fetched_at DATETIME NULL,
  last_synced_at DATETIME NOT NULL,
  last_source_rows INT NOT NULL,
  last_run_status VARCHAR(16) NOT NULL,
  last_error TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""


def mysql_config() -> dict[str, Any]:
    from config.settings import settings

    return {
        "host": settings.crawler_mysql_host,
        "port": settings.crawler_mysql_port,
        "user": settings.crawler_mysql_user,
        "password": settings.crawler_mysql_password,
        "db": settings.crawler_mysql_database,
        "charset": "utf8mb4",
        "autocommit": False,
    }


def read_source(full: bool = False, watermarks: dict[str, datetime | None] | None = None) -> dict[str, list[dict[str, Any]]]:
    from config.settings import settings

    connection = pyodbc.connect(settings.sqlserver_connection_string, timeout=30)
    try:
        cursor = connection.cursor()
        result = {}
        for table in TABLES:
            watermark = None if full else (watermarks or {}).get(table)
            query = f"SELECT {', '.join(COLUMNS)} FROM dbo.{table}"
            parameters: list[Any] = []
            if watermark:
                if table == "HenanPlatformAqAccumulateStat":
                    # 每天重取最新 MTD/YTD，防止上游同时间戳修订或回补造成漏数。
                    query += " WHERE fetched_at > ? OR period_end = (SELECT MAX(period_end) FROM dbo.HenanPlatformAqAccumulateStat)"
                else:
                    query += " WHERE fetched_at > ?"
                parameters.append(watermark)
            query += " ORDER BY fetched_at, id"
            cursor.execute(query, parameters)
            names = [column[0] for column in cursor.description]
            result[table] = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        return result
    finally:
        connection.close()


async def _sync_async(full: bool = False) -> dict[str, Any]:
    connection = await aiomysql.connect(**mysql_config())
    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(STATE_DDL)
            for table, keys in TABLES.items():
                await cursor.execute(ddl(table, keys))
                await cursor.execute(
                    f"ALTER TABLE `{table}` MODIFY fetched_at DATETIME(6) NOT NULL, "
                    "MODIFY created_at DATETIME(6) NOT NULL"
                )
            await cursor.execute("SELECT table_name, last_fetched_at FROM HenanPlatformAqSyncState")
            watermarks = {row["table_name"]: row["last_fetched_at"] for row in await cursor.fetchall()}
        await connection.commit()
        source = await asyncio.to_thread(read_source, full, watermarks)
        max_fetched: dict[str, datetime | None] = {}
        async with connection.cursor() as cursor:
            for table, rows in source.items():
                keys = TABLES[table]
                assignments = ", ".join(
                    f"`{column}`=VALUES(`{column}`)" for column in COLUMNS if column not in keys
                )
                upsert = (
                    f"INSERT INTO `{table}` ({', '.join(f'`{column}`' for column in COLUMNS)}) "
                    f"VALUES ({', '.join(['%s'] * len(COLUMNS))}) ON DUPLICATE KEY UPDATE {assignments}"
                )
                if rows:
                    await cursor.executemany(upsert, [tuple(row[column] for column in COLUMNS) for row in rows])
                    max_fetched[table] = max(watermarks.get(table) or rows[0]["fetched_at"], *(row["fetched_at"] for row in rows))
                else:
                    max_fetched[table] = watermarks.get(table)
                await cursor.execute(
                    """INSERT INTO HenanPlatformAqSyncState
                    (table_name,last_fetched_at,last_synced_at,last_source_rows,last_run_status,last_error)
                    VALUES (%s,%s,NOW(),%s,'success',NULL)
                    ON DUPLICATE KEY UPDATE last_fetched_at=VALUES(last_fetched_at),
                    last_synced_at=VALUES(last_synced_at),last_source_rows=VALUES(last_source_rows),
                    last_run_status='success',last_error=NULL""",
                    (table, max_fetched[table], len(rows)),
                )
                await cursor.execute(f"SELECT COUNT(*) AS n FROM `{table}`")
                count = (await cursor.fetchone())[0]
                source[table] = {"source_rows": len(rows), "local_rows": count, "last_fetched_at": max_fetched[table]}
        # 写后按业务键和全部原始字段与上游比对，提交前发现缺行/错值即整批回滚。
        async with connection.cursor() as cursor:
            for table, keys in TABLES.items():
                query = f"SELECT {', '.join(COLUMNS)} FROM `{table}`"
                await cursor.execute(query)
                names = [column[0] for column in cursor.description]
                local_rows = [dict(zip(names, row, strict=True)) for row in await cursor.fetchall()]
                local_index = {tuple(row[key] for key in keys): row for row in local_rows}
                fresh = await asyncio.to_thread(read_source, True, None)
                for source_row in fresh[table]:
                    key = tuple(source_row[column] for column in keys)
                    local_row = local_index.get(key)
                    if local_row is None:
                        raise RuntimeError(f"{table} 同步缺行: {key}")
                    for column in COLUMNS:
                        if local_row[column] != source_row[column]:
                            if column in {"fetched_at", "created_at"}:
                                # SQL Server datetime2 可含微秒，本地 DATETIME 明确保留秒。
                                if local_row[column].replace(microsecond=0) == source_row[column].replace(microsecond=0):
                                    continue
                            raise RuntimeError(f"{table} 字段不一致: {key} {column}")
        await connection.commit()
        return {"full": full, "tables": source}
    except Exception:
        await connection.rollback()
        raise
    finally:
        connection.close()


def sync(full: bool = False) -> dict[str, Any]:
    return asyncio.run(_sync_async(full))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="忽略水位，全量幂等刷新三表")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[4] / "backend"
    from dotenv import load_dotenv

    load_dotenv(backend / ".env", override=False)
    import json
    import sys

    sys.path.insert(0, str(backend))
    print(json.dumps(sync(args.full), ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
