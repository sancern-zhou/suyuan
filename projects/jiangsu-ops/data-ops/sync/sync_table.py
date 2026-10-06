"""Jiangsu ops ODS sync engine.

Pulls rows from source SQL Server (11.54.200.199) into local PostgreSQL
jiangsu_ods.<table>, with watermark tracking in jiangsu_sync.

Window rule (user requirement 2026-09-21): fact/business tables only backfill
rows from 2026-08-01 onwards ("full_load_since"); master/dictionary tables
sync in full so August facts can join their dimensions.

Incremental modes per table (sync_config.json):
  - incremental_column + incremental_type=datetime  -> watermark - 1s overlap
  - incremental_column + incremental_type=int       -> strict > watermark
  - incremental_expr (SQL expression)               -> watermark on MAX(expr);
      SELECT gains "__incr" column; state changes bump the coalesced timestamp
  - mode "daily_full"                               -> no watermark; --full reload
      (small dictionaries / tables without a reliable update column)

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
        return json.load(fh)


def source_conn(cfg: dict, db: str) -> pyodbc.Connection:
    src = cfg["source"]
    conn_str = (
        f"Driver={{{src['driver']}}};"
        f"Server={src['server']};Database={db};"
        f"UID={src['user']};PWD={src['password']};"
    )
    return pyodbc.connect(conn_str, timeout=30)


def q(name: str) -> str:
    return '"' + name.lower() + '"'


TARGET_SCHEMA = "jiangsu_ods"

DDL_WATERMARK = """
CREATE TABLE IF NOT EXISTS jiangsu_sync.sync_watermark (
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
CREATE TABLE IF NOT EXISTS jiangsu_sync.sync_log (
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
    await pg.execute(DDL_WATERMARK)
    await pg.execute(DDL_SYNCLOG)
    # v1 of this engine created watermark columns as timestamp; v2 stores
    # normalized text (int and datetime watermarks). Migrate in place.
    for stmt in (
        "ALTER TABLE jiangsu_sync.sync_watermark ALTER COLUMN watermark TYPE text",
        "ALTER TABLE jiangsu_sync.sync_log ALTER COLUMN watermark_before TYPE text",
        "ALTER TABLE jiangsu_sync.sync_log ALTER COLUMN watermark_after TYPE text",
    ):
        try:
            await pg.execute(stmt)
        except asyncpg.PostgresError:
            pass


async def ensure_ods_table(pg: asyncpg.Connection, table: str, spec: dict) -> None:
    exists = await pg.fetchval(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=$1 AND table_name=$2",
        TARGET_SCHEMA, table,
    )
    if not exists:
        types = spec.get("column_types", {})
        cols = ",\n  ".join(f"{q(c)} {types.get(c, 'text')}" for c in spec["columns"])
        ddl = (
            f"CREATE TABLE {TARGET_SCHEMA}.{q(table)} (\n  {cols},\n"
            f"  _src_incremental text,\n  _sync_batch uuid,\n"
            f"  _synced_at timestamp default now(),\n"
            f"  PRIMARY KEY ({', '.join(q(p) for p in spec['pk'])})\n)"
        )
        await pg.execute(ddl)
    else:
        # v1 tables had _src_incremental as timestamp; v2 stores normalized text.
        col_type = await pg.fetchval(
            """SELECT data_type FROM information_schema.columns
               WHERE table_schema=$1 AND table_name=$2 AND column_name='_src_incremental'""",
            TARGET_SCHEMA, table,
        )
        if col_type and col_type != "text":
            await pg.execute(
                f"ALTER TABLE {TARGET_SCHEMA}.{q(table)} ALTER COLUMN _src_incremental TYPE text"
            )


async def get_watermark(pg, table: str) -> str | None:
    row = await pg.fetchrow(
        "SELECT watermark FROM jiangsu_sync.sync_watermark WHERE table_name=$1", table
    )
    return row["watermark"] if row else None


async def log_batch(pg, entry: dict) -> None:
    await pg.execute(
        """INSERT INTO jiangsu_sync.sync_log
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


def build_source_sql(spec: dict, watermark, full: bool, since: str | None) -> str:
    cols = spec["columns"]
    col_sql = ", ".join(f"[{c}]" for c in cols)
    expr = spec.get("incremental_expr")
    if expr:
        col_sql += f", {expr} AS [{INCR_COL}]"
    clauses = []
    incr = spec.get("incremental_expr") or spec.get("incremental_column")
    if full:
        if spec.get("apply_window") and since:
            if spec.get("initial_where_tpl"):
                clauses.append(spec["initial_where_tpl"].format(since=since))
            elif incr:
                clauses.append(f"[{incr.split(' AS ')[0].strip()}] >= '{since}'")
    elif watermark is not None and incr:
        if spec.get("incremental_type") == "datetime":
            low = dt.datetime.fromisoformat(watermark) - (
                DATETIME_OVERLAP if not expr else dt.timedelta(0)
            )
            since_str = low.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        else:
            since_str = str(watermark)
        if expr:
            clauses.append(f"({expr}) > '{since_str}'")
        else:
            clauses.append(f"[{incr}] > '{since_str}'")
    where = (" WHERE " + " AND ".join(f"({c})" for c in clauses)) if clauses else ""
    if not incr:
        order = ""
    elif expr:
        order = f" ORDER BY ({expr}) ASC"
    else:
        order = f" ORDER BY [{incr}] ASC"
    return f"SELECT {col_sql} FROM {spec['source_table']}{where}{order}"


def fetch_source_rows(spec: dict, cfg: dict, watermark, full: bool):
    since = cfg.get("full_load_since")
    sql = build_source_sql(spec, watermark, full, since)
    conn = source_conn(cfg, spec["source_db"])
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
    has_expr = bool(spec.get("incremental_expr"))
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
        if has_expr:
            incr_raw = vals.pop()
            incr_val = str(incr_raw) if incr_raw is not None else None
        elif incr_idx is not None:
            incr_val = str(vals[incr_idx]) if vals[incr_idx] is not None else None
        else:
            incr_val = None
        vals.append(incr_val)
        vals.append(batch_id)
        data.append(vals)
    await pg.executemany(sql, data)


def batch_watermark(spec: dict, rows: list[tuple], current):
    expr = spec.get("incremental_expr")
    col = None if expr else spec.get("incremental_column")
    if not expr and not col:
        return current
    idx = -1 if expr else spec["columns"].index(col)
    candidates = [r[idx] for r in rows if r[idx] is not None]
    if not candidates:
        return current
    best = str(max(candidates))
    if spec.get("incremental_type") == "int" and not expr:
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
        wm = None if full else await get_watermark(pg, table)
        if wm is None and spec.get("mode") == "daily_full":
            full = True
            entry["mode"] = mode = "full"
        # First run of an incremental table (no watermark yet) must honour the
        # full-load window instead of silently pulling all history.
        query_full = full or wm is None
        entry["watermark_before"] = wm
        new_wm = wm
        total = 0
        for rows in fetch_source_rows(spec, cfg, None if query_full else wm, query_full):
            new_wm = batch_watermark(spec, rows, new_wm)
            await upsert_rows(pg, table, spec, rows, batch_id)
            total += len(rows)
            print(f"[{table}] fetched {total}", flush=True)
        await pg.execute(
            """INSERT INTO jiangsu_sync.sync_watermark
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
    incr = spec.get("incremental_expr") or spec.get("incremental_column")
    conn = source_conn(cfg, spec["source_db"])
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {spec['source_table']}")
        src_count = cur.fetchone()[0]
        src_max = None
        if incr:
            cur.execute(f"SELECT MAX({incr}) FROM {spec['source_table']}")
            src_max = cur.fetchone()[0]
    finally:
        conn.close()
    pg = await asyncpg.connect(cfg["target"]["dsn"])
    try:
        tgt_count = await pg.fetchval(f"SELECT COUNT(*) FROM {TARGET_SCHEMA}.{q(table)}")
        tgt_max = await pg.fetchval(f"SELECT MAX(_src_incremental) FROM {TARGET_SCHEMA}.{q(table)}")
    finally:
        await pg.close()
    count_note = ""
    if spec.get("apply_window") and cfg.get("full_load_since"):
        count_note = f" (window>={cfg['full_load_since']}: target is a subset by design)"
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
