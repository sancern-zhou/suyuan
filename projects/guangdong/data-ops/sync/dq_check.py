"""Daily data-quality checks for guangdong_ods / guangdong_mart.

Checks:
  1. mart freshness  - max(refreshed_at) within SLA (hourly tables: 2h; daily: 26h)
  2. key null rates  - required columns must be non-null
  3. sync heartbeat  - every ODS watermark updated within 24h with status ok
  4. unique keys     - dedup-sensitive tables must have no duplicate keys
  5. contract drift  - contract.txt 必须与 sync/datasets/*.yaml 一致
     (gen_tool_contract.py --check)

Results appended to guangdong_sync.dq_results; exit 1 if any check fails so the
scheduled task log shows it clearly. guangdong_query_metrics 读取本表生成
quality_status（blocked/degraded/ok）。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys

import asyncpg

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_config.json")

FRESHNESS_SLA_MIN = {
    # table: (sla_minutes, refresh_ts_column)
    "mart_work_order_analysis": (120, "refreshed_at"),
    "mart_alarm_notify_analysis": (120, "refreshed_at"),
    "mart_device_lifecycle_analysis": (120, "refreshed_at"),
    "mart_inspection_task_analysis": (26 * 60, "refreshed_at"),
    "mart_station_alarm_status": (26 * 60, "refreshed_at"),
    "working_orders": (120, "refreshed_at"),
    "working_order_details": (26 * 60, "refreshed_at"),
    "wo_commonfile_links": (120, "refreshed_at"),
    "dim_station": (26 * 60, "refreshed_at"),
    "dim_device": (26 * 60, "refreshed_at"),
    "dim_user": (26 * 60, "refreshed_at"),
    "alm_alarm": (120, "refreshed_at"),
    "log_device": (120, "refreshed_at"),
    "sup_rf_common": (120, "refreshed_at"),
}

NULL_CHECKS = {
    # table: (columns, allowed_null_rows)
    # station_code 容忍少量 null: CAL* 等系统生成工单无站点(源库同现状)
    "mart_work_order_analysis": (
        ["id", "working_order_code", "create_time"], {"station_code": 10},
    ),
    "mart_alarm_notify_analysis": (["alarm_id", "notify_time"], {"station_id": 2000}),
    "mart_device_lifecycle_analysis": (["event_id", "event_time"], {"station_code": 500, "device_code": 500}),
    "mart_inspection_task_analysis": (["task_item_id"], {"station_code": 500}),
    "mart_station_alarm_status": (["station_id"], {}),
    "working_orders": (["id", "working_order_code", "create_time"], {}),
    "dim_station": (["station_id", "station_code"], {"city_name": 5}),
    "dim_user": (["user_id", "user_name"], {"department_name": 100}),
    "dim_device": (["device_id"], {"station_id": 10}),
}

UNIQUE_CHECKS = {
    "mart_work_order_analysis": ["id"],
    "mart_alarm_notify_analysis": ["alarm_id"],
    "mart_device_lifecycle_analysis": ["event_id"],
    "mart_inspection_task_analysis": ["task_item_id"],
    "mart_station_alarm_status": ["station_id"],
    "working_orders": ["id"],
    "working_order_details": ["id"],
    "wo_commonfile_links": ["id"],
    "dim_station": ["station_id"],
    "dim_user": ["user_id"],
    "dim_device": ["device_id"],
    "alm_alarm": ["alarmid"],
    "log_device": ["devicelogid"],
    "pw_taskitem": ["pwtaskitemid"],
}

# 高频增量表（心跳检查范围；daily_full 表由 freshness 覆盖）
HEARTBEAT_TABLES = ["working_orders", "working_order_details", "wo_commonfile_links",
                    "ALM_ALARM", "LOG_DEVICE", "Sup_RF_Common"]

DDL_DQ_RESULTS = """
CREATE TABLE IF NOT EXISTS guangdong_sync.dq_results (
    check_name  text,
    table_name  text,
    status      text,
    detail      text,
    checked_at  timestamp default now()
);
"""


async def record(pg, results, check, table, status, detail):
    results.append({"check": check, "table": table, "status": status, "detail": detail})
    await pg.execute(
        """INSERT INTO guangdong_sync.dq_results (check_name, table_name, status, detail)
           VALUES ($1,$2,$3,$4)""",
        check, table, status, detail,
    )


async def check_freshness(pg, results):
    for table, (sla_min, col) in FRESHNESS_SLA_MIN.items():
        try:
            max_ts = await pg.fetchval(
                f"SELECT max({col}) FROM guangdong_mart.{table}")
        except Exception as exc:  # noqa: BLE001
            await record(pg, results, "freshness", table, "FAIL", f"query error: {exc}")
            continue
        if max_ts is None:
            await record(pg, results, "freshness", table, "FAIL", "no rows / no refresh timestamp")
            continue
        age_min = (dt.datetime.now() - max_ts).total_seconds() / 60.0
        if age_min > sla_min:
            await record(pg, results, "freshness", table, "FAIL",
                         f"age {age_min:.0f}min > SLA {sla_min}min (max {max_ts})")
        elif age_min > sla_min / 2:
            await record(pg, results, "freshness", table, "WARN",
                         f"age {age_min:.0f}min approaching SLA {sla_min}min")
        else:
            await record(pg, results, "freshness", table, "OK",
                         f"age {age_min:.0f}min <= SLA {sla_min}min")


async def check_nulls(pg, results):
    for table, (cols, allowed) in NULL_CHECKS.items():
        for col in cols:
            nulls = await pg.fetchval(f"SELECT count(*) FROM guangdong_mart.{table} WHERE {col} IS NULL")
            quota = allowed.get(col, 0)
            if nulls > quota:
                await record(pg, results, "null_rate", f"{table}.{col}", "FAIL",
                             f"{nulls} nulls > allowed {quota}")
            elif nulls:
                await record(pg, results, "null_rate", f"{table}.{col}", "WARN",
                             f"{nulls} nulls (allowed {quota})")


async def check_unique(pg, results):
    for table, keys in UNIQUE_CHECKS.items():
        key_sql = ", ".join(keys)
        dupes = await pg.fetchval(
            f"""SELECT count(*) FROM (
                SELECT {key_sql} FROM guangdong_mart.{table}
                GROUP BY {key_sql} HAVING count(*) > 1) d""")
        if dupes:
            await record(pg, results, "unique_key", table, "FAIL", f"{dupes} duplicate keys on ({key_sql})")
        else:
            await record(pg, results, "unique_key", table, "OK", f"no duplicates on ({key_sql})")


async def check_heartbeat(pg, results):
    for table in HEARTBEAT_TABLES:
        row = await pg.fetchrow(
            """SELECT watermark, last_status, updated_at
               FROM guangdong_sync.ods_sync_watermark WHERE table_name=$1""", table)
        if row is None:
            await record(pg, results, "heartbeat", table, "FAIL", "no watermark row (never synced)")
            continue
        age_h = (dt.datetime.now() - row["updated_at"]).total_seconds() / 3600.0
        if row["last_status"] != "ok":
            await record(pg, results, "heartbeat", table, "FAIL",
                         f"last_status={row['last_status']}")
        elif age_h > 24:
            await record(pg, results, "heartbeat", table, "FAIL",
                         f"watermark stale {age_h:.0f}h")
        else:
            await record(pg, results, "heartbeat", table, "OK",
                         f"watermark={row['watermark']} age {age_h:.1f}h")


async def check_contract_drift(pg, results):
    """契约防漂移: datasets/*.yaml 必须与工具加载的 contract.txt 生成物一致。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen_tool_contract.py")
    if not os.path.exists(script):
        await record(pg, results, "contract", "execute_guangdong_mart_sql", "SKIP",
                     "gen_tool_contract.py not deployed to runtime; skip")
        return
    # 仓库内运行：sync 目录向上四级为仓库根；独立运行时目录（gitignore 的部署副本）：
    # 在 sync_config.json 配 backend_root 绝对路径。
    cfg_backend_root = None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg_backend_root = json.load(fh).get("backend_root")
    except Exception:  # noqa: BLE001
        pass
    backend_root = cfg_backend_root or os.path.abspath(
        os.path.join(os.path.dirname(script), "..", "..", "..", "..", "backend"))
    env = dict(os.environ)
    env["PYTHONPATH"] = backend_root + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                sys.executable, script, "--check",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                cwd=backend_root, env=env,
            ),
            timeout=60,
        )
        out, _ = await proc.communicate()
        lines = (out or b"").decode("utf-8", "replace").strip().splitlines()
        detail = lines[-1] if lines else f"exit={proc.returncode}"
        status = "OK" if proc.returncode == 0 else "FAIL"
    except Exception as exc:  # noqa: BLE001
        status, detail = "FAIL", f"check error: {exc}"
    await record(pg, results, "contract", "execute_guangdong_mart_sql", status, detail)


async def main() -> int:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        dsn = json.load(fh)["target"]["dsn"]
    pg = await asyncpg.connect(dsn)
    results = []
    try:
        await pg.execute(DDL_DQ_RESULTS)
        await check_freshness(pg, results)
        await check_nulls(pg, results)
        await check_unique(pg, results)
        await check_heartbeat(pg, results)
        await check_contract_drift(pg, results)
    finally:
        await pg.close()
    failed = [r for r in results if r["status"] == "FAIL"]
    warned = [r for r in results if r["status"] == "WARN"]
    print(json.dumps({
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total": len(results), "failed": len(failed), "warned": len(warned),
        "failures": failed,
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
