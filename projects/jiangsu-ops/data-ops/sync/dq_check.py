"""Daily data-quality checks for jiangsu_ods / jiangsu_mart (design doc section 7).

Checks:
  1. mart freshness  - max(refreshed_at) within SLA (5min tables: 30min; daily: 26h)
  2. key null rates  - required columns must be non-null
  3. sync heartbeat  - every incremental watermark updated within 24h with status ok
  4. unique keys     - dedup-sensitive tables must have no duplicate keys
  5. generated-artifact drift - contract.txt 与 dbt sources/schema/snapshots
     必须与 datasets/*.yaml 一致（gen_tool_contract.py / gen_dbt_artifacts.py --check）

Results appended to jiangsu_sync.dq_results; exit 1 if any check fails so the
scheduled task log shows it clearly.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys

import asyncpg

FRESHNESS_SLA_MIN = {
    # table: (sla_minutes, refresh_ts_column)
    "mart_work_order_analysis": (30, "refreshed_at"),
    "mart_alarm_event_analysis": (30, "refreshed_at"),
    "mart_station_device_health": (30, "refreshed_at"),
    "mart_station_daily_profile": (26 * 60, "refreshed_at"),
    "mart_qc_execution_analysis": (30, "synced_at"),
    "mart_qc_arrangement_analysis": (26 * 60, "synced_at"),
    "mart_inspection_analysis": (30, "synced_at"),
    "mart_performance_analysis": (26 * 60, "synced_at"),
    "mart_blackout_analysis": (26 * 60, "synced_at"),
    "mart_qc_backorder_analysis": (26 * 60, "synced_at"),
    "mart_device_lifecycle_analysis": (26 * 60, "synced_at"),
    "dim_station": (30, "synced_at"),
    "dim_device": (26 * 60, "synced_at"),
    "dim_device_parameter": (26 * 60, "synced_at"),
    "mart_station_alarm_log": (26 * 60, "synced_at"),
    "mart_station_env_power": (26 * 60, "synced_at"),
    "mart_qc_task_status_result": (26 * 60, "synced_at"),
    "mart_qc_air_data_result": (26 * 60, "synced_at"),
    "mart_qc_run_log_result": (26 * 60, "synced_at"),
}

NULL_CHECKS = {
    # table: (columns, allowed_null_rows)
    # station_code 容忍少量 null: CAL* 校准类工单系统生成、无站点(源库同现状)
    "mart_work_order_analysis": (
        ["id", "station_code", "create_time"], {"station_code": 10},
    ),
    "mart_alarm_event_analysis": (["id", "station_code", "alarm_time"], {}),
    "mart_station_device_health": (["station_code"], {}),
    "mart_station_daily_profile": (["profile_date", "station_code"], {}),
    # 质控窗口内 100% 可关联站点(dim_station via uniquecode);city_name 容忍少量外省对照站
    "mart_qc_execution_analysis": (
        ["id", "station_code", "qc_date"], {"city_name": 100},
    ),
    "mart_qc_arrangement_analysis": (["id", "station_code", "status_cn"], {"city_name": 100}),
    "mart_inspection_analysis": (["id", "station_code", "task_date"], {}),
    "mart_performance_analysis": (["station_code", "perf_month"], {}),
    "mart_blackout_analysis": (["id", "station_code"], {}),
    "mart_qc_backorder_analysis": (["id", "station_code", "start_time"], {"city_name": 100}),
    "mart_device_lifecycle_analysis": (["event_id", "event_time"], {"station_code": 50, "city_name": 100}),
    "dim_station": (["station_code"], {}),
    "dim_device": (["device_code"], {"station_code": 400}),
    "dim_device_parameter": (["devicemodel", "parameterid", "parameter_name"], {}),
    "mart_station_alarm_log": (["station_code", "alarm_time"], {}),
    "mart_station_env_power": (["station_code", "timepoint", "pollutant_code"], {}),
    "mart_qc_task_status_result": (["rid"], {"station_code": 100}),
    "mart_qc_air_data_result": (["station_code", "timepoint"], {}),
    "mart_qc_run_log_result": (["rid"], {}),
}

UNIQUE_CHECKS = {
    "mart_station_alarm_log": ["station_code", "id"],
    "mart_station_env_power": ["station_code", "id"],
    "mart_qc_task_status_result": ["rid"],
    "mart_qc_air_data_result": ["id"],
    "mart_qc_run_log_result": ["id"],
}


async def _run_generator_check(script_name: str):
    """Run a sync/*.py --check drift detector; return (status, detail).

    脚本未部署到运行时副本时 SKIP(不阻塞, 等下一次 deploy-to-runtime)。
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    if not os.path.exists(script):
        return "SKIP", f"{script_name} not deployed to runtime sync dir; skip"
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                sys.executable, script, "--check",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            ),
            timeout=60,
        )
        out, _ = await proc.communicate()
        lines = (out or b"").decode("utf-8", "replace").strip().splitlines()
        detail = lines[-1] if lines else f"exit={proc.returncode}"
        status = "OK" if proc.returncode == 0 else "FAIL"
    except Exception as exc:  # noqa: BLE001
        status, detail = "FAIL", f"check error: {exc}"
    return status, detail


async def check_contract_drift(pg, results):
    """契约防漂移: datasets/*.yaml 必须与工具加载的 contract.txt 生成物一致。"""
    status, detail = await _run_generator_check("gen_tool_contract.py")
    await record(pg, results, "contract", "execute_jiangsu_mart_sql", status, detail)


async def check_dbt_artifacts(pg, results):
    """dbt 生成物(sources/schema/snapshots)防漂移: 必须与 datasets/*.yaml 一致。"""
    status, detail = await _run_generator_check("gen_dbt_artifacts.py")
    await record(pg, results, "dbt_artifacts", "schema.yml", status, detail)


async def record(pg, results, name, table, status, detail):
    results.append((name, table, status, detail))
    print(f"[{status}] {name}/{table}: {detail}")
    await pg.execute(
        "INSERT INTO jiangsu_sync.dq_results (check_name, table_name, status, detail) "
        "VALUES ($1,$2,$3,$4)",
        name, table, status, detail,
    )


async def check_freshness(pg, results):
    for table, (sla, col) in FRESHNESS_SLA_MIN.items():
        ts = await pg.fetchval(f"SELECT max({col}) FROM jiangsu_mart.{table}")
        if ts is None:
            await record(pg, results, "freshness", table, "FAIL", "table empty")
            continue
        if ts.tzinfo is not None:  # timestamptz 列(如历史版本 synced_at)归一为本地 naive
            ts = ts.astimezone().replace(tzinfo=None)
        age = (dt.datetime.now() - ts).total_seconds() / 60
        if age <= sla:
            await record(pg, results, "freshness", table, "OK", f"age={age:.0f}min")
        else:
            await record(pg, results, "freshness", table, "FAIL",
                         f"age={age:.0f}min > sla={sla}min")


async def check_nulls(pg, results):
    for table, (cols, allowed) in NULL_CHECKS.items():
        exprs = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL) AS {c}" for c in cols)
        row = await pg.fetchrow(
            f"SELECT count(*) AS total, {exprs} FROM jiangsu_mart.{table}"
        )
        total = row["total"]
        if total == 0:
            await record(pg, results, "nulls", table, "FAIL", "table empty")
            continue
        status = "OK"
        details = []
        for c in cols:
            n = row[c]
            cap = allowed.get(c, 0)
            if n > cap:
                status = "FAIL"
                details.append(f"{c}={n}>cap{cap}")
            elif n > 0:
                if status == "OK":
                    status = "WARN"
                details.append(f"{c}={n}<=cap{cap}(known)")
        if status == "OK":
            details = [f"{total} rows, key columns complete"]
        await record(pg, results, "nulls", table, status, "; ".join(details))


async def check_heartbeat(pg, results):
    rows = await pg.fetch(
        "SELECT table_name, last_status, updated_at FROM jiangsu_sync.sync_watermark"
    )
    for r in rows:
        age_h = (dt.datetime.now() - r["updated_at"]).total_seconds() / 3600
        if r["last_status"] != "ok":
            await record(pg, results, "heartbeat", r["table_name"], "FAIL",
                         f"last_status={r['last_status']}")
        elif age_h > 24:
            await record(pg, results, "heartbeat", r["table_name"], "FAIL",
                         f"watermark stale {age_h:.0f}h")
        else:
            await record(pg, results, "heartbeat", r["table_name"], "OK",
                         f"updated {age_h:.1f}h ago")


async def check_uniques(pg, results):
    for table, columns in UNIQUE_CHECKS.items():
        keys = ", ".join(columns)
        duplicate_count = await pg.fetchval(
            f"SELECT count(*) FROM (SELECT {keys} FROM jiangsu_mart.{table} "
            f"GROUP BY {keys} HAVING count(*) > 1) duplicates"
        )
        if duplicate_count:
            await record(pg, results, "uniques", table, "FAIL",
                         f"duplicate_groups={duplicate_count} on ({keys})")
        else:
            await record(pg, results, "uniques", table, "OK",
                         f"unique on ({keys})")


async def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(r"E:\suyuan\backend\.env.jiangsu-ops")
    dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    pg = await asyncpg.connect(dsn)
    results: list = []
    try:
        await pg.execute(
            """CREATE TABLE IF NOT EXISTS jiangsu_sync.dq_results (
                   checked_at  timestamp DEFAULT now(),
                   check_name  text,
                   table_name  text,
                   status      text,
                   detail      text
               )"""
        )
        await check_freshness(pg, results)
        await check_nulls(pg, results)
        await check_heartbeat(pg, results)
        await check_uniques(pg, results)
        await check_contract_drift(pg, results)
        await check_dbt_artifacts(pg, results)
    finally:
        await pg.close()
    failures = sum(1 for r in results if r[2] == "FAIL")
    print(f"DQ_SUMMARY total={len(results)} fail={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
