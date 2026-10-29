"""Daily data-quality checks for guangdong_ods / guangdong_mart.

Checks:
  1. mart freshness  - max(refreshed_at) within SLA (hourly tables: 2h; daily: 26h)
  2. key null rates  - required columns must be non-null
  3. sync heartbeat  - every ODS watermark updated within 24h with status ok
  4. unique keys     - dedup-sensitive tables must have no duplicate keys
  5. contract drift  - contract.txt 必须与 sync/datasets/*.yaml 一致
     (gen_tool_contract.py --check)
  6. ods fallback    - ods_contract.txt 与同步范围一致，且 agent_reader 对兜底表
     有 SELECT 授权（同步进 guangdong_ods 的表不允许 Agent 查不到；
     gen_ods_fallback_contract.py --check + role_table_grants）
  7. mart coverage   - guangdong_mart 里的每张表都必须出现在 agent 白名单
     （contract.txt 主契约 或 ods_contract.txt 兜底），否则 Agent 查不到；
     仅查 guangdong_ods 的 check 6 覆盖不到 mart-only 表（2026-10-28 复盘补的盲区）
  8. sup profiles    - 组分站语义档案（sup_form_profiles.yaml）里每个 ruleitemtag
     的承载表都必须可被 Agent 查询（档案有、数据查不到即 FAIL）

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
    "mart_performance_analysis": (26 * 60, "refreshed_at"),
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
    "mart_performance_analysis": (["ospsid", "performance_month"], {"city_name": 50}),
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
    "mart_performance_analysis": ["ospsid"],
    "opa_performance": ["id"],
    "opa_stationperformancescore": ["ospsid"],
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


async def _run_generator_check(script_name):
    """在仓库根 PYTHONPATH 下运行 sync 生成器的 --check，返回 (status, detail)。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    if not os.path.exists(script):
        return "SKIP", f"{script_name} not deployed to runtime; skip"
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
        return ("OK" if proc.returncode == 0 else "FAIL"), detail
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"check error: {exc}"


async def check_contract_drift(pg, results):
    """契约防漂移: datasets/*.yaml 必须与工具加载的 contract.txt 生成物一致。"""
    status, detail = await _run_generator_check("gen_tool_contract.py")
    await record(pg, results, "contract", "execute_guangdong_mart_sql", status, detail)


async def check_ods_fallback(pg, results):
    """ODS 兜底通道: 生成物防漂移 + agent_reader 授权完整性。

    不变式: 同步进 guangdong_ods 的表不得出现"Agent 查不到"——没被主契约
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
           WHERE grantee='agent_reader' AND table_schema='guangdong_ods'"""
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


TOOL_DIR_PARTS = ("app", "tools", "query", "guangdong_ops_sql_query")


def _contract_table_paths() -> tuple[str, str]:
    """定位 agent 工具加载的两份白名单（主契约 + ODS 兜底）。

    运行时目录可能在仓库外（sync_config.json 的 backend_root），优先用它；
    未配置或路径不存在时按仓库标准布局（本文件上溯 4 级到仓库根）回退。
    """
    backend_root = ""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            backend_root = str(json.load(fh).get("backend_root") or "")
    except (OSError, ValueError):
        backend_root = ""
    if not backend_root or not os.path.isdir(backend_root):
        here = os.path.dirname(os.path.abspath(__file__))
        backend_root = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "backend"))
    tool_dir = os.path.join(backend_root, *TOOL_DIR_PARTS)
    return (os.path.join(tool_dir, "contract.txt"),
            os.path.join(tool_dir, "ods_contract.txt"))


def _read_contract_tables(path: str) -> set[str]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("TABLES:"):
                return {t.strip().lower() for t in line.split(":", 1)[1].split(",") if t.strip()}
    return set()


async def check_mart_contract_coverage(pg, results):
    """mart 表必须被 agent 白名单覆盖（主契约或 ODS 兜底）。

    check_ods_fallback 只校验 guangdong_ods 的同步表；只存在于 guangdong_mart
    的表（如组分网分表先在 mart 落地）是盲区：库里有数、审计读得到，但
    execute_guangdong_mart_sql 会因白名单缺失拒绝查询。
    """
    try:
        rows = await pg.fetch(
            """SELECT c.relname AS table_name
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'guangdong_mart' AND c.relkind = 'r'"""
        )
        mart_tables = {r["table_name"].lower() for r in rows}
        contract_path, ods_path = _contract_table_paths()
        allowed = _read_contract_tables(contract_path) | _read_contract_tables(ods_path)
    except Exception as exc:  # noqa: BLE001
        await record(pg, results, "contract", "guangdong_mart", "FAIL",
                     f"coverage check error: {exc}")
        return
    missing = sorted(mart_tables - allowed)
    if missing:
        await record(
            pg, results, "contract", "guangdong_mart", "FAIL",
            f"{len(missing)} mart table(s) not in agent whitelist: "
            + ", ".join(missing[:8])
            + (" ..." if len(missing) > 8 else "")
            + " (add to sources.yml/datasets then regenerate contracts)",
        )
    else:
        await record(pg, results, "contract", "guangdong_mart", "OK",
                     f"{len(mart_tables)} mart tables all covered by agent whitelist")


async def check_sup_profile_coverage(pg, results):
    """组分站语义档案与 Agent 白名单一致性（sup_form_profiles.yaml -> 承载表可查）。

    档案按 ruleitemtag 建档但不声明承载表：若某 tag 的数据只落在未进白名单的表，
    就会出现"规则有档案、Agent 查不到数据"。复用 check_sup_profile_coverage.py
    的扫描与比对逻辑，避免两份实现漂移。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import check_sup_profile_coverage as cov

        profile_tags = cov.load_profile_tags()
        whitelist = cov.load_whitelist()
        carriers = await cov.scan_tag_carriers(pg)
    except Exception as exc:  # noqa: BLE001
        await record(pg, results, "contract", "sup_form_profiles", "FAIL",
                     f"check error: {exc}")
        return

    lower_map = {k.lower(): v for k, v in carriers.items()}
    unreachable, no_data = [], []
    for tag in sorted(profile_tags):
        tables = carriers.get(tag) or lower_map.get(tag.lower()) or set()
        if not tables:
            no_data.append(tag)
            continue
        bad = sorted(t for t in tables if t not in whitelist)
        if bad:
            unreachable.append("%s -> %s" % (tag, ",".join(bad)))
    if unreachable:
        await record(
            pg, results, "contract", "sup_form_profiles", "FAIL",
            "%d profile tag(s) carry data only in non-whitelisted tables: " % len(unreachable)
            + "; ".join(unreachable[:6])
            + (" ..." if len(unreachable) > 6 else "")
            + " (sync + whitelist the carrier table, then regenerate contracts)",
        )
    elif no_data:
        await record(
            pg, results, "contract", "sup_form_profiles", "WARN",
            "%d profile tag(s) have no carrier rows in synced tables: " % len(no_data)
            + ", ".join(no_data[:8]),
        )
    else:
        await record(pg, results, "contract", "sup_form_profiles", "OK",
                     f"{len(profile_tags)} profile tags all backed by whitelisted tables")

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
        await check_ods_fallback(pg, results)
        await check_mart_contract_coverage(pg, results)
        await check_sup_profile_coverage(pg, results)
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
