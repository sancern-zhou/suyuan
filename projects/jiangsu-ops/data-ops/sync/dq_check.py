"""Daily data-quality checks for jiangsu_ods / jiangsu_mart (design doc section 7).

Checks:
  1. mart freshness  - max(refreshed_at) within SLA (5min tables: 30min; daily: 26h)
  2. key null rates  - required columns must be non-null
  3. sync heartbeat  - every incremental watermark updated within 24h with status ok
  4. unique keys     - dedup-sensitive tables must have no duplicate keys
  5. generated-artifact drift - contract.txt 与 dbt sources/schema/snapshots
     必须与 datasets/*.yaml 一致（gen_tool_contract.py / gen_dbt_artifacts.py --check）
  6. ODS fallback coverage - 同步进 ODS 但无 mart/dim 覆盖的表必须落在
     ods_contract.txt 且 agent_reader 已授权（gen_ods_fallback_contract.py --check）

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
    "mart_routine_order_analysis": (30, "refreshed_at"),
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
    "dim_person": (26 * 60, "synced_at"),
    "mart_station_alarm_log": (26 * 60, "synced_at"),
    "mart_station_door_access": (26 * 60, "synced_at"),
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
    "mart_routine_order_analysis": (
        # ~44张CAL校准单系统生成无站点码(源库同现状, 2026-11-04 全历史回补后实测)
        ["id", "station_code", "create_time"], {"station_code": 60},
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
    "dim_person": (["user_id", "user_name"], {"user_name": 2}),  # user_id=550 上游姓名被清空(2026-10-26), 容2行留可见性
    "mart_station_alarm_log": (["station_code", "alarm_time"], {}),
    "mart_station_door_access": (["event_id", "event_time"], {"station_code": 200}),
    "mart_station_env_power": (["station_code", "timepoint", "pollutant_code"], {}),
    "mart_qc_task_status_result": (["rid"], {"station_code": 100}),
    "mart_qc_air_data_result": (["station_code", "timepoint"], {}),
    "mart_qc_run_log_result": (["rid"], {}),
}

UNIQUE_CHECKS = {
    "dim_person": ["user_id"],
    "mart_station_alarm_log": ["station_code", "id"],
    "mart_station_door_access": ["event_id"],
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


async def check_ods_fallback(pg, results):
    """ODS 兜底通道: 生成物防漂移 + agent_reader 授权完整性。

    不变式: 同步进 jiangsu_ods 的表不得出现"Agent 查不到"——没被 mart/dim 契约
    覆盖的表必须落在 ods_contract.txt 里, 且 agent_reader 有 SELECT 权限。
    """
    status, detail = await _run_generator_check("gen_ods_fallback_contract.py")
    await record(pg, results, "contract", "ods_fallback", status, detail)

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gen_ods_fallback_contract as ods_contract

        tables, _covered = ods_contract.fallback_tables()
    except Exception as exc:  # noqa: BLE001
        await record(pg, results, "grant", "ods_fallback", "FAIL",
                     f"cannot compute fallback list: {exc}")
        return

    rows = await pg.fetch(
        """SELECT table_name FROM information_schema.role_table_grants
           WHERE grantee='agent_reader' AND table_schema='jiangsu_ods'"""
    )
    granted = {r["table_name"] for r in rows}
    missing = sorted(set(tables) - granted)
    if missing:
        await record(
            pg, results, "grant", "ods_fallback", "FAIL",
            f"agent_reader missing SELECT on {len(missing)} table(s): "
            + ", ".join(missing[:8])
            + " (run gen_ods_fallback_contract.py --grant)",
        )
    else:
        await record(pg, results, "grant", "ods_fallback", "OK",
                     f"{len(tables)} fallback tables granted")


async def check_routine_order_semantics(pg, results):
    """例行单口径差对账（2026-11-03 如东芳泉路假阴性事故的长效观测）。

    巡检任务台账(mart_inspection_analysis, pw_taskitem 完成回写口径)说"无关联工单"的
    站点数, 与工单主表真实存在例行单的站点数的差, 就是"台账无单号 ≠ 未建单"的口径差。
    该差是已知口径事实而非错误 —— 记录数值供判定, 只有查询本身失败才 WARN(不 FAIL,
    避免夜间链路被信息型检查阻塞)。
    """
    try:
        row = await pg.fetchrow(
            """
            with ledger as (
                select station_code
                from jiangsu_mart.mart_inspection_analysis
                where plan_start_date >= date_trunc('week', current_date) - interval '7 days'
                  and rule_type_cn = '周巡检'
                group by station_code
                having sum(case when coalesce(workingordercode, '') <> '' then 1 else 0 end) = 0
            ),
            reality as (
                select t.stationcode as station_code
                from jiangsu_ods.mtc_taskitem t
                join jiangsu_ods.mtc_working_order o
                     on o.workingordercode = t.workingordercode
                where t.planfinishtime >= date_trunc('week', current_date) - interval '7 days'
                  and t.planfinishtime < date_trunc('week', current_date)
                  and t.ruleitemtag like 'RF_W%'
                group by t.stationcode
            )
            select
                (select count(*) from ledger) as ledger_no_code,
                (select count(*) from reality) as reality_has_order,
                (select count(*) from ledger l where not exists (
                    select 1 from reality r where r.station_code = l.station_code)) as truly_missing
            """
        )
        await record(
            pg, results, "semantics", "routine_order_ledger_gap", "OK",
            f"上周周巡检: 台账无回写单号={row['ledger_no_code']}站, "
            f"工单主表实际建单={row['reality_has_order']}站, "
            f"其中确实未建单={row['truly_missing']}站 "
            "(口径差=回写口径滞后, 判定工单存在性须用工单主表)",
        )
    except Exception as exc:  # noqa: BLE001
        await record(pg, results, "semantics", "routine_order_ledger_gap", "WARN",
                     f"reconcile query failed: {exc}")


async def check_form_sync_drift(pg, results):
    """表单仅关单/同步滞后哨兵（2026-11-04 rf_common 原地更新漏同步事故长效观测）。

    双信号(任务项状态 OR rf_common.preparetime)都空白的已闭环单, 关单超 3 天仍在
    疑点单列的, 要么是运维真没填表就关单, 要么是同步链路再次漏拉原地更新(含平台
    不盖章的静默写入, 如归档后作废)。count>0 报 WARN(不阻塞夜间链路), 供人工判定。
    """
    try:
        row = await pg.fetchrow(
            """
            select count(*) as total
            from jiangsu_mart.mart_routine_order_analysis
            where is_form_only_close
              and finish_time < current_date - interval '3 days'
              and create_time >= '2026-06-01'
            """
        )
        total = row["total"]
        if total == 0:
            await record(pg, results, "semantics", "form_only_close_drift", "OK",
                         "闭环超3天且无任何填报证据的单=0 (双信号同步健康)")
        else:
            samples = await pg.fetch(
                """
                select working_order_code, station_code, finish_time
                from jiangsu_mart.mart_routine_order_analysis
                where is_form_only_close
                  and finish_time < current_date - interval '3 days'
                  and create_time >= '2026-06-01'
                order by finish_time desc limit 5
                """
            )
            codes = ", ".join(
                f"{r['working_order_code']}({r['station_code']})" for r in samples)
            await record(pg, results, "semantics", "form_only_close_drift", "WARN",
                         f"闭环超3天无填报证据={total}张, 疑似真疑点单或同步漏拉原地更新; "
                         f"样本: {codes}; 判定须直连源库核 rf_common")
    except Exception as exc:  # noqa: BLE001
        await record(pg, results, "semantics", "form_only_close_drift", "WARN",
                     f"drift query failed: {exc}")


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
        await check_ods_fallback(pg, results)
        await check_routine_order_semantics(pg, results)
        await check_form_sync_drift(pg, results)
    finally:
        await pg.close()
    failures = sum(1 for r in results if r[2] == "FAIL")
    print(f"DQ_SUMMARY total={len(results)} fail={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
