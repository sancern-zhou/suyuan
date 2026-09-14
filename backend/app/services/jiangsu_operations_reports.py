"""Deterministic calculations for Jiangsu periodic operations reports.

The functions accept normalized platform rows so report orchestration can fetch
from the live API or a replayed evidence snapshot without changing the rules.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


def _value(row: dict[str, Any], *keys: str) -> Any:
    return next((row.get(key) for key in keys if row.get(key) not in (None, "")), None)


def _time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Keep arithmetic stable when platform mixes ISO timestamps with and
        # without offsets.
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def _station(row: dict[str, Any]) -> str:
    return str(_value(row, "station_code", "StationCode", "stationCode", "station_id", "StationID") or _value(row, "station_name", "StationName", "stationName") or "未知站点")


def _category(row: dict[str, Any]) -> str:
    return str(_value(row, "fault_category", "FaultCategory", "faultType", "FaultType", "order_title", "orderTitle", "OrderTitle") or "其他故障")


def identify_recurrent_outage_rows(rows: list[dict[str, Any]], *, gap_hours: float = 24, min_cluster_size: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate repeated outage/power rows from normal population statistics.

    A cluster is station-local, outage-like (断电/停电/断数/通信), and has
    consecutive events no more than ``gap_hours`` apart. Cluster rows remain in
    the returned ``recurrent`` list for a dedicated station risk section.
    """
    groups: dict[tuple[str, str], list[tuple[datetime, dict[str, Any]]]] = defaultdict(list)
    for row in rows:
        category = _category(row)
        if not any(token in category for token in ("断电", "停电", "断数", "通信", "离线")):
            continue
        when = _time(_value(row, "created_at", "CreateTime", "createTime", "fault_time", "FaultTime"))
        if when:
            groups[(_station(row), category)].append((when, row))
    recurrent_ids: set[int] = set()
    recurrent: list[dict[str, Any]] = []
    for events in groups.values():
        events.sort(key=lambda item: item[0])
        cluster: list[dict[str, Any]] = []
        previous: datetime | None = None
        for when, row in events:
            if previous is None or (when - previous).total_seconds() <= gap_hours * 3600:
                cluster.append(row)
            else:
                if len(cluster) >= min_cluster_size:
                    recurrent.extend(cluster)
                    recurrent_ids.update(id(item) for item in cluster)
                cluster = [row]
            previous = when
        if len(cluster) >= min_cluster_size:
            recurrent.extend(cluster)
            recurrent_ids.update(id(item) for item in cluster)
    normal = [row for row in rows if id(row) not in recurrent_ids]
    return normal, recurrent


def build_fault_monthly_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normal, recurrent = identify_recurrent_outage_rows(rows)
    station_counts = Counter(_station(row) for row in normal)
    unit_counts = Counter(str(_value(row, "unit_name", "UnitName", "operationUnitName") or "未知单位") for row in normal)
    category_counts = Counter(_category(row) for row in normal)
    durations: list[float] = []
    for row in normal:
        start = _time(_value(row, "created_at", "CreateTime", "createTime", "fault_time", "FaultTime"))
        end = _time(_value(row, "completed_at", "FinishTime", "finishTime", "closed_at", "CloseTime"))
        if start and end and end >= start:
            durations.append((end - start).total_seconds() / 3600)
    durations.sort()
    return {
        "input_count": len(rows), "excluded_recurrent_outage_count": len(recurrent),
        "analyzed_count": len(normal), "recurrent_outage_rows": recurrent,
        "top_stations": [{"station": name, "count": count} for name, count in station_counts.most_common(15)],
        "unit_counts": dict(unit_counts), "category_counts": dict(category_counts),
        "duration_hours": {"count": len(durations), "average": round(sum(durations) / len(durations), 2) if durations else None,
                            "median": round(durations[len(durations) // 2], 2) if durations else None},
    }


def build_backup_quarterly_report(rows: list[dict[str, Any]], *, as_of: datetime | None = None) -> dict[str, Any]:
    """Evaluate backup rules using explicit records or an asset-ledger inference.

    ``backup_on_time``/``backup_off_time`` are treated as explicit lifecycle
    evidence.  ``useDate``/``stopDate`` are only an inferred fallback and are
    never silently presented as a confirmed platform replacement event.
    """
    as_of = as_of or datetime.now()
    if as_of.tzinfo:
        as_of = as_of.replace(tzinfo=None)
    results: list[dict[str, Any]] = []
    station_frequency: Counter[str] = Counter()
    for row in rows:
        station = _station(row)
        fault = _time(_value(row, "fault_time", "FaultTime", "created_at", "CreateTime"))
        explicit_on = _value(row, "backup_on_time", "BackupOnTime", "device_on_time", "DeviceOnTime", "replacement_time", "ReplacementTime")
        explicit_off = _value(row, "backup_off_time", "BackupOffTime", "device_off_time", "DeviceOffTime")
        inferred_on = _value(row, "useDate", "use_date", "UseDate")
        inferred_off = _value(row, "stopDate", "stop_date", "StopDate")
        on = _time(explicit_on if explicit_on not in (None, "") else inferred_on)
        off = _time(explicit_off if explicit_off not in (None, "") else inferred_off)
        evidence = "explicit" if explicit_on not in (None, "") or explicit_off not in (None, "") else "ledger_inferred" if inferred_on not in (None, "") else "unavailable"
        role = str(_value(row, "backup_role", "BackupRole", "device_role", "DeviceRole", "is_backup", "IsBackup") or "").strip().lower()
        original_machine = _value(row, "originalMachine", "original_machine", "OriginalMachine")
        is_backup = role in {"backup", "备用", "备机", "true", "1", "yes"}
        identity_source = ("explicit" if role or explicit_on not in (None, "") else
                           "inferred_from_asset_flags" if original_machine in (0, False, "0", "false", "False") or _value(row, "masterSlaveNum", "master_slave_num", "MasterSlaveNum") not in (None, "") else "unknown")
        days = ((off or as_of) - on).total_seconds() / 86400 if on else None
        activation_hours = (on - fault).total_seconds() / 3600 if fault and on else None
        analyzable = on is not None and identity_source != "unknown"
        if analyzable:
            station_frequency[station] += 1
        results.append({"station": station, "fault_time": fault, "backup_on_time": on,
                        "backup_off_time": off, "evidence_source": evidence,
                        "identity_source": identity_source, "analyzable": analyzable,
                        "activation_hours": round(activation_hours, 2) if activation_hours is not None else None,
                        "continuous_days": round(days, 2) if days is not None else None,
                        "has_deferment": bool(_value(row, "has_deferment", "HasDeferment", "备案状态")),
                        "activation_over_48h": analyzable and activation_hours is not None and activation_hours > 48,
                        "over_30_days": analyzable and days is not None and days > 30})
    return {"record_count": len(results), "analyzable_count": sum(1 for r in results if r["analyzable"]),
            "evidence_counts": dict(Counter(r["evidence_source"] for r in results)),
            "unavailable_records": [r for r in results if not r["analyzable"]],
            "activation_over_48h": [r for r in results if r["activation_over_48h"] and not r["has_deferment"]],
            "over_30_days": [r for r in results if r["over_30_days"] and not r["has_deferment"]],
            "station_frequency": [{"station": s, "count": c} for s, c in station_frequency.most_common()], "records": results}
