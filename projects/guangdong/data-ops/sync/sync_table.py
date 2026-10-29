"""Guangdong ops ODS sync engine.

Pulls rows from the ops source SQL Server (Operation_SC_GD, 172.20.105.179,
read-only compatible views dbo.working_orders etc.) into local PostgreSQL
guangdong_ods.<table>, with watermark tracking in guangdong_sync.

架构对齐江苏 data-ops（sync -> dbt -> cube 三层）；本引擎替代原
backend/app/fetchers/guangdong_work_order 的 fetcher 同步方式（2026-10-24 改造）。
元数据表使用 ods_sync_watermark / ods_sync_log，与 fetcher 时代的
guangdong_sync.sync_watermark（dataset/watermark/highwater 结构）不兼容，
二者并存互不干扰；fetcher 下线后旧表自然停更。

Incremental modes per table (sync_config.json):
  - incremental_column + incremental_type=datetime  -> watermark - 1s overlap
  - incremental_column + incremental_type=int       -> strict > watermark
  - mode "daily_full"                               -> no watermark; --full reload
      (master data without a reliable update column)
  - refresh_window_days=N (with explicit --full)    -> rolling-window refresh:
      re-pull rows with [incremental_column] >= now-N days and upsert. For
      forms whose rows are edited IN PLACE during review (reject -> modify ->
      resubmit never changes the create-time column, so the watermark can
      never re-see them). Applies to explicit --full runs only; a first run
      (no watermark yet) still backfills full history. To re-backfill full
      history later, delete the watermark row or drop the option.
  - where (static SQL predicate)                    -> row scope filter applied on
      EVERY pull (full and incremental); watermark only advances over fetched
      (filtered) rows.
  - source_db 省缺时使用 cfg["source"]["database"]（广东运维源为单库）。

Usage:
  python sync_table.py <table>              # incremental (auto-full if no watermark)
  python sync_table.py <table> --full       # force full reload (window applies)
  python sync_table.py <table> --check      # row-count + max-timestamp reconciliation
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import traceback
import uuid
from pathlib import Path

import asyncpg
import pyodbc

CONFIG_PATH = Path(__file__).with_name("sync_config.json")
DATETIME_OVERLAP = dt.timedelta(seconds=1)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    # 同步量控制（2026-10-24 业务约定）：大数据量、定期更新的工单表只回填今年窗口，
    # 偏静态维表全量。窗口支持 {year_start} 占位符，运行时解析为当前年份，
    # 每年 1 月自动滚动，无需改配置；仅影响首拉与 --full 重拉，增量按水位持续推进。
    since = cfg.get("full_load_since")
    if isinstance(since, str) and "{year_start}" in since:
        cfg["full_load_since"] = since.replace("{year_start}", str(dt.date.today().year))
    return cfg


def source_conn(cfg: dict, db: str | None) -> pyodbc.Connection:
    src = cfg["source"]
    database = db or src.get("database")
    if not database:
        raise ValueError(
            f"source_db 未指定且 source.database 未配置（表级 source_db 或 source.database 二选一）"
        )
    conn_str = (
        f"Driver={{{src['driver']}}};"
        f"Server={src['server']};Database={database};"
        f"UID={src['user']};PWD={src['password']};"
    )
    return pyodbc.connect(conn_str, timeout=30)


def q(name: str) -> str:
    return '"' + name.lower() + '"'


TARGET_SCHEMA = "guangdong_ods"
META_SCHEMA = "guangdong_sync"

DDL_WATERMARK = """
CREATE TABLE IF NOT EXISTS guangdong_sync.ods_sync_watermark (
    table_name   text PRIMARY KEY,
    watermark    text,
    rows_total   bigint,
    last_batch   uuid,
    last_mode    text,
    last_status  text,
    updated_at   timestamp default now()
);
"""

DDL_SYNCLOG = """
CREATE TABLE IF NOT EXISTS guangdong_sync.ods_sync_log (
    batch_id     uuid,
    table_name   text,
    mode         text,
    started_at   timestamp,
    finished_at  timestamp,
    rows_fetched bigint,
    watermark_before text,
    watermark_after  text,
    status       text,
    error        text,
    PRIMARY KEY (batch_id, table_name)
);
"""

INCR_COL = "__incr"


async def ensure_meta(pg: asyncpg.Connection) -> None:
    # guangdong_ods 由本引擎自建（fetcher 时代只建了 guangdong_mart/guangdong_sync）。
    await pg.execute(f"CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA}")
    await pg.execute(DDL_WATERMARK)
    await pg.execute(DDL_SYNCLOG)


async def ensure_ods_table(pg: asyncpg.Connection, table: str, spec: dict) -> None:
    # 表名按 ODS 实际存储形式（q() 小写）比对；配置键可为任意大小写。
    exists = await pg.fetchval(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=$1 AND table_name=$2",
        TARGET_SCHEMA, table.lower(),
    )
    if not exists:
        types = spec.get("column_types", {})
        # 大小写无关匹配：源列名常为大写（base_station 等），column_types 键为小写。
        cols = ",\n  ".join(
            f"{q(c)} {types.get(c) or types.get(c.lower()) or 'text'}" for c in spec["columns"]
        )
        ddl = (
            f"CREATE TABLE {TARGET_SCHEMA}.{q(table)} (\n  {cols},\n"
            f"  _src_incremental text,\n  _sync_batch uuid,\n"
            f"  _synced_at timestamp default now(),\n"
            f"  PRIMARY KEY ({', '.join(q(p) for p in spec['pk'])})\n)"
        )
        await pg.execute(ddl)


async def get_watermark(pg, table: str) -> str | None:
    row = await pg.fetchrow(
        "SELECT watermark FROM guangdong_sync.ods_sync_watermark WHERE table_name=$1", table
    )
    return row["watermark"] if row else None


async def log_batch(pg, entry: dict) -> None:
    await pg.execute(
        """INSERT INTO guangdong_sync.ods_sync_log
           (batch_id, table_name, mode, started_at, finished_at, rows_fetched,
            watermark_before, watermark_after, status, error)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
           ON CONFLICT (batch_id, table_name) DO UPDATE SET
             finished_at=EXCLUDED.finished_at, rows_fetched=EXCLUDED.rows_fetched,
             watermark_after=EXCLUDED.watermark_after, status=EXCLUDED.status,
             error=EXCLUDED.error""",
        entry["batch_id"], entry["table_name"], entry["mode"], entry["started_at"],
        entry.get("finished_at"), entry.get("rows_fetched"),
        str(entry.get("watermark_before")), str(entry.get("watermark_after")),
        entry["status"], entry.get("error"),
    )


def build_source_sql(spec: dict, watermark, full: bool, since: str | None,
                     refresh_days: int | None = None) -> str:
    cols = spec["columns"]
    col_sql = ", ".join(f"[{c}]" for c in cols)
    incr = spec.get("incremental_column")
    clauses = []
    if full:
        if refresh_days and incr:
            # 滚动窗口全量：表单在送审流程中是原行修改（打回重报不换行，
            # 创建时间列不变），创建时间水位永远看不见这类修改；业务约定
            # 例行工单超 N 天自动送审、之后不再改，故只重拉近 N 天并整行
            # upsert（config.json 的 refresh_window_days）。
            window_start = (
                dt.datetime.now() - dt.timedelta(days=int(refresh_days))
            ).strftime("%Y-%m-%d %H:%M:%S.000")
            clauses.append(f"[{incr}] >= '{window_start}'")
        elif spec.get("apply_window") and since:
            if spec.get("initial_where_tpl"):
                clauses.append(spec["initial_where_tpl"].format(since=since))
            elif incr:
                clauses.append(f"[{incr}] >= '{since}'")
    elif watermark is not None and incr:
        if spec.get("incremental_type") == "datetime":
            low = dt.datetime.fromisoformat(watermark) - DATETIME_OVERLAP
            since_str = low.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        else:
            since_str = str(watermark)
        clauses.append(f"[{incr}] > '{since_str}'")
    where = (" WHERE " + " AND ".join(f"({c})" for c in clauses)) if clauses else ""
    fixed_where = spec.get("where")
    if fixed_where:
        where = (where + " AND " if where else " WHERE ") + f"({fixed_where})"
    order = f" ORDER BY [{incr}] ASC" if incr else ""
    return f"SELECT {col_sql} FROM {spec['source_table']}{where}{order}"


def fetch_source_rows(spec: dict, cfg: dict, watermark, full: bool,
                      refresh_days: int | None = None):
    since = cfg.get("full_load_since")
    sql = build_source_sql(spec, watermark, full, since, refresh_days)
    conn = source_conn(cfg, spec.get("source_db"))
    try:
        cur = conn.cursor()
        cur.execute(sql)
        while True:
            rows = cur.fetchmany(cfg["sync"]["batch_rows"])
            if not rows:
                break
            yield rows
    finally:
        conn.close()


async def upsert_rows(pg, table: str, spec: dict, rows: list[tuple], batch_id) -> None:
    src_cols = spec["columns"]
    incr_idx = src_cols.index(spec["incremental_column"]) if spec.get("incremental_column") else None
    cols = [c.lower() for c in src_cols] + ["_src_incremental", "_sync_batch"]
    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
    col_sql = ", ".join(q(c) for c in cols)
    update_cols = [c for c in cols if c not in spec["pk"] and c != "_synced_at"]
    update_sql = ", ".join(f"{q(c)}=EXCLUDED.{q(c)}" for c in update_cols)
    sql = (
        f"INSERT INTO {TARGET_SCHEMA}.{q(table)} ({col_sql}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT ({', '.join(q(p) for p in spec['pk'])}) DO UPDATE SET {update_sql}"
    )
    data = []
    for r in rows:
        vals = list(r)
        # SQL Server nchar/nvarchar can carry NUL chars; PostgreSQL text rejects 0x00.
        for i, v in enumerate(vals):
            if isinstance(v, str) and "\x00" in v:
                vals[i] = v.replace("\x00", "")
        if incr_idx is not None:
            incr_val = str(vals[incr_idx]) if vals[incr_idx] is not None else None
        else:
            incr_val = None
        vals.append(incr_val)
        vals.append(batch_id)
        data.append(vals)
    await pg.executemany(sql, data)


def batch_watermark(spec: dict, rows: list[tuple], current):
    col = spec.get("incremental_column")
    if not col:
        return current
    idx = spec["columns"].index(col)
    candidates = [r[idx] for r in rows if r[idx] is not None]
    if not candidates:
        return current
    best = str(max(candidates))
    if spec.get("incremental_type") == "int":
        best_key, cur_key = int(best), (int(current) if current is not None else -1)
    else:
        best_key, cur_key = best, (str(current) if current is not None else "")
    return best if best_key > cur_key else current


async def run_sync(table: str, full: bool) -> int:
    cfg = load_config()
    spec = cfg["tables"][table]
    batch_id = uuid.uuid4()
    started = dt.datetime.now()
    mode = "full" if full else "incremental"
    entry = {"batch_id": batch_id, "table_name": table, "mode": mode,
             "started_at": started, "status": "running", "rows_fetched": 0}
    pg = await asyncpg.connect(cfg["target"]["dsn"])
    try:
        await ensure_meta(pg)
        await ensure_ods_table(pg, table, spec)
        stored_wm = await get_watermark(pg, table)
        wm = None if full else stored_wm
        if wm is None and spec.get("mode") == "daily_full":
            full = True
            entry["mode"] = mode = "full"
        # First run of an incremental table (no watermark yet) must honour the
        # full-load window instead of silently pulling all history.
        query_full = full or wm is None
        entry["watermark_before"] = stored_wm
        # Seed from the stored watermark: a --full run that fetches zero rows
        # (rolling-window refresh on a quiet day) must not rewind or null it.
        new_wm = stored_wm
        # Rolling window applies to explicit --full runs only; a first run
        # (no watermark) must still backfill full history.
        refresh_days = spec.get("refresh_window_days") if full else None
        total = 0
        for rows in fetch_source_rows(spec, cfg, None if query_full else wm,
                                      query_full, refresh_days):
            new_wm = batch_watermark(spec, rows, new_wm)
            await upsert_rows(pg, table, spec, rows, batch_id)
            total += len(rows)
            print(f"[{table}] fetched {total}", flush=True)
        await pg.execute(
            """INSERT INTO guangdong_sync.ods_sync_watermark
               (table_name, watermark, rows_total, last_batch, last_mode, last_status, updated_at)
               VALUES ($1,$2,$3,$4,$5,'ok',now())
               ON CONFLICT (table_name) DO UPDATE SET
                 watermark=EXCLUDED.watermark, rows_total=EXCLUDED.rows_total,
                 last_batch=EXCLUDED.last_batch, last_mode=EXCLUDED.last_mode,
                 last_status='ok', updated_at=now()""",
            table, str(new_wm) if new_wm is not None else None, total, batch_id, mode,
        )
        entry.update(finished_at=dt.datetime.now(), rows_fetched=total,
                     watermark_after=new_wm, status="ok")
        await log_batch(pg, entry)
        print(f"[{table}] DONE rows={total} watermark={new_wm}", flush=True)
        return 0
    except Exception as exc:
        entry.update(finished_at=dt.datetime.now(), status="failed",
                     error=f"{type(exc).__name__}: {exc}")
        try:
            await log_batch(pg, entry)
        except Exception:
            traceback.print_exc()
        print(f"[{table}] FAILED: {entry['error']}", file=sys.stderr, flush=True)
        raise
    finally:
        await pg.close()


async def run_check(table: str) -> int:
    cfg = load_config()
    spec = cfg["tables"][table]
    incr = spec.get("incremental_column")
    conn = source_conn(cfg, spec.get("source_db"))
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {spec['source_table']}")
        src_count = cur.fetchone()[0]
        src_max = None
        if incr:
            cur.execute(f"SELECT MAX([{incr}]) FROM {spec['source_table']}")
            src_max = cur.fetchone()[0]
    finally:
        conn.close()
    pg = await asyncpg.connect(cfg["target"]["dsn"])
    try:
        tgt_count = await pg.fetchval(f"SELECT COUNT(*) FROM {TARGET_SCHEMA}.{q(table)}")
        if spec.get("incremental_type") == "int":
            # int 水位列是 text，按字典序 MAX 会取到 '999999' 而非 '1050096'，需转数值
            tgt_max = await pg.fetchval(
                f"SELECT MAX(_src_incremental::numeric) FROM {TARGET_SCHEMA}.{q(table)}")
        else:
            tgt_max = await pg.fetchval(f"SELECT MAX(_src_incremental) FROM {TARGET_SCHEMA}.{q(table)}")
    finally:
        await pg.close()
    count_note = ""
    if spec.get("apply_window") and cfg.get("full_load_since"):
        count_note = f" (window>={cfg['full_load_since']}: target is a subset by design)"
    if spec.get("incremental_type") == "int" and src_max is not None and tgt_max is not None:
        # int 水位按数值比较（text 存储下字典序会误判，如 "999999" > "1050052"）
        from decimal import Decimal
        ok = tgt_count <= src_count and Decimal(str(tgt_max)) >= Decimal(str(src_max))
    else:
        ok = tgt_count <= src_count and (
            src_max is None or tgt_max is None or str(src_max) <= str(tgt_max)
        )
    print(f"[{table}] CHECK source={src_count} target={tgt_count} "
          f"src_max={src_max} tgt_max={tgt_max} -> {'OK' if ok else 'MISMATCH'}{count_note}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("table")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return asyncio.run(run_check(args.table))
    return asyncio.run(run_sync(args.table, args.full))


if __name__ == "__main__":
    raise SystemExit(main())
