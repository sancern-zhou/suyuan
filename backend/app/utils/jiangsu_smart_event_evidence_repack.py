"""Re-project and split historic smart-event evidence packages.

Applies the current evidence projection (``instrument_status`` series mapping
and monitoring noise-column drop) and re-persists each package as an immutable
``evidence-<digest>/index.json`` + ``sources/<name>.json`` directory, then
updates the database pointer for DB-primary deployments.

Examples (run from ``backend`` with the target env file):

  # 只读演练：统计窗口内事件、投影前后体积，不写任何数据
  python -m app.utils.jiangsu_smart_event_evidence_repack \
      --env-file .env.jiangsu-ops --start 2026-09-14 --end 2026-09-17 --dry-run

  # 实际执行（需先停 worker，见 --help 说明）
  python -m app.utils.jiangsu_smart_event_evidence_repack \
      --env-file .env.jiangsu-ops --start 2026-09-14 --end 2026-09-17 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))


def project_package(package: dict) -> tuple[dict, bool]:
    """Return (projected_package, changed).

    当前方案只投影两个来源：``instrument_status`` 固定为 series 映射，
    ``monitoring`` 宽表剔除内部/派生列。已投影过的包不改动。
    """
    from app.fetchers.jiangsu_smart_event_evidence import (
        INSTRUMENT_STATUS_PROJECTION,
        _project_instrument_status,
        _project_monitoring_result,
    )

    sources = package.get("sources")
    if not isinstance(sources, dict):
        return package, False
    changed = False
    instrument = sources.get("instrument_status")
    if isinstance(instrument, dict):
        data = instrument.get("data")
        if isinstance(data, dict) and data.get("schema_version") != INSTRUMENT_STATUS_PROJECTION:
            projected = _project_instrument_status(data)
            if projected is not data:
                metadata = instrument.get("metadata") if isinstance(instrument.get("metadata"), dict) else {}
                metadata["projection"] = INSTRUMENT_STATUS_PROJECTION
                metadata["raw_record_count"] = projected.get("raw_points")
                instrument = {**instrument, "data": projected, "metadata": metadata}
                sources["instrument_status"] = instrument
                changed = True
    monitoring = sources.get("monitoring")
    if isinstance(monitoring, dict):
        projected = _project_monitoring_result(monitoring)
        if projected is not monitoring:
            sources["monitoring"] = projected
            changed = True
    return package, changed


def _parse_day(value: str, *, end: bool) -> datetime:
    day = datetime.strptime(value.strip(), "%Y-%m-%d")
    if end:
        day = day + timedelta(days=1)
    return day.replace(tzinfo=CST)


def _event_time_clause():
    from sqlalchemy import func

    from app.db.models.smart_event_db import SmartEventDB

    return func.coalesce(SmartEventDB.latest_occurrence_time, SmartEventDB.event_start_time)


async def _fetch_targets(start: datetime, end: datetime, event_id: str | None):
    from sqlalchemy import select

    from app.db.models.smart_event_db import SmartEventDB
    from app.db.sync_bridge import bridge_session

    stmt = select(SmartEventDB.event_id, SmartEventDB.data, SmartEventDB.evidence_package_path)
    if event_id:
        stmt = stmt.where(SmartEventDB.event_id == event_id)
    else:
        column = _event_time_clause()
        stmt = stmt.where(column >= start, column < end)
    async with bridge_session() as session:
        return (await session.execute(stmt)).all()


def _run_db(start: datetime, end: datetime, event_id: str | None, apply: bool) -> dict:
    from app.db.sync_bridge import run_db
    from app.services.jiangsu_smart_event_store import JiangsuEventPackages, read_package_file
    from app.services.smart_event_db import _packages
    from app.utils.path_config import format_agent_path, resolve_agent_path

    packages = _packages()
    rows = run_db(_fetch_targets(start, end, event_id))
    report = {
        "targets": len(rows), "skipped_missing": 0, "skipped_current": 0,
        "repacked": 0, "failed": 0, "old_bytes": 0, "new_bytes": 0,
        "samples": [], "backup": None,
    }
    backups: list[dict] = []
    for row in rows:
        old_ref = row.evidence_package_path
        if not old_ref:
            report["skipped_missing"] += 1
            continue
        old_path = resolve_agent_path(old_ref)
        if not old_path.exists():
            report["skipped_missing"] += 1
            continue
        old_size = old_path.stat().st_size
        try:
            package = read_package_file(old_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report["failed"] += 1
            report["samples"].append({"event_id": row.event_id, "error": str(exc)[:160]})
            continue
        projected, changed = project_package(package)
        if old_path.name == "index.json" and not changed:
            report["skipped_current"] += 1
            continue
        report["old_bytes"] += old_size
        if not apply:
            new_size = len(json.dumps(projected, ensure_ascii=False, separators=(",", ":"), default=str).encode())
            report["new_bytes"] += new_size
            report["repacked"] += 1
            if len(report["samples"]) < 12:
                report["samples"].append({
                    "event_id": row.event_id,
                    "old_bytes": old_size,
                    "projected_bytes": new_size,
                    "changed": changed,
                })
            continue
        event = dict(row.data or {})
        event["event_id"] = row.event_id
        event["evidence_package"] = projected
        packages.write_evidence_only(event)
        stub = event["evidence_package"]
        new_ref = stub.get("persisted_path")
        run_db(_update_pointer(row.event_id, event, new_ref))
        report["repacked"] += 1
        report["new_bytes"] += resolve_agent_path(new_ref).stat().st_size
        backups.append({
            "event_id": row.event_id, "old_path": old_ref, "new_path": new_ref,
            "old_bytes": old_size,
        })
    if apply and backups:
        stamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
        backup_path = packages.root / f"projection-migration-{stamp}.json"
        backup_path.write_text(json.dumps(backups, ensure_ascii=False, indent=2), encoding="utf-8")
        report["backup"] = format_agent_path(backup_path)
    return report


async def _update_pointer(event_id: str, event: dict, new_ref: str) -> None:
    from sqlalchemy import text

    from app.db.sync_bridge import bridge_session
    from app.services.smart_event_db import ADVISORY_LOCK_KEY

    async with bridge_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SELECT pg_advisory_xact_lock(hashtext('{ADVISORY_LOCK_KEY}'))"))
            await session.execute(
                text("UPDATE smart_events SET data = :data, evidence_package_path = :path "
                     "WHERE event_id = :event_id"),
                {"data": json.dumps(event, ensure_ascii=False, default=str),
                 "path": new_ref, "event_id": event_id},
            )


def _run_files(start: datetime, end: datetime, event_id: str | None, apply: bool) -> dict:
    """File-mode fallback：以 manifest 为清单逐事件重写。"""
    from app.services.jiangsu_smart_event import JiangsuSmartEventService
    from app.services.jiangsu_smart_event_store import SCHEMA, read_package_file
    from app.utils.path_config import resolve_agent_path

    service = JiangsuSmartEventService()
    store = service._load_store()
    report = {
        "targets": 0, "skipped_missing": 0, "skipped_current": 0,
        "repacked": 0, "failed": 0, "old_bytes": 0, "new_bytes": 0,
        "samples": [], "backup": None,
    }
    for event in store.get("events", []):
        if not isinstance(event, dict) or not event.get("event_id"):
            continue
        if event_id and str(event["event_id"]) != event_id:
            continue
        stamp = event.get("latest_occurrence_time") or event.get("event_start_time")
        if not event_id:
            try:
                moment = datetime.fromisoformat(str(stamp))
            except (TypeError, ValueError):
                continue
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=CST)
            if not (start <= moment < end):
                continue
        report["targets"] += 1
        reference = (event.get("evidence_package") or {}).get("persisted_path")
        if not reference:
            report["skipped_missing"] += 1
            continue
        old_path = resolve_agent_path(reference)
        if not old_path.exists():
            report["skipped_missing"] += 1
            continue
        package = read_package_file(old_path)
        projected, changed = project_package(package)
        if old_path.name == "index.json" and not changed:
            report["skipped_current"] += 1
            continue
        report["old_bytes"] += old_path.stat().st_size
        if apply:
            event["evidence_package"] = projected
        report["repacked"] += 1
    if apply:
        service._save_store(store)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=None, help="部署环境文件（如 .env.jiangsu-ops）")
    parser.add_argument("--start", required=True, help="窗口起始自然日 YYYY-MM-DD（含）")
    parser.add_argument("--end", required=True, help="窗口结束自然日 YYYY-MM-DD（含）")
    parser.add_argument("--event-id", default=None, help="只处理单个事件")
    parser.add_argument("--apply", action="store_true", help="实际写盘并更新数据库指针；缺省为只读演练")
    parser.add_argument("--dry-run", action="store_true", help="只读演练（默认行为，显式给出便于阅读）")
    args = parser.parse_args(argv)

    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=True)
        configured = os.getenv("DATA_REGISTRY_DIR")
        if configured:
            os.environ["DATA_REGISTRY_DIR"] = configured

    start = _parse_day(args.start, end=False)
    end = _parse_day(args.end, end=True)

    from app.services.smart_event_db import smart_event_db_enabled

    runner = _run_db if smart_event_db_enabled() else _run_files
    report = runner(start, end, args.event_id, args.apply)
    report["mode"] = "db" if smart_event_db_enabled() else "file"
    report["applied"] = bool(args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
