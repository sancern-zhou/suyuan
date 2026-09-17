"""Deterministic scenario analysis for Jiangsu daily supervision & risk prevention.

The two builders combine the committed August-2026 demo dataset (plans,
certificates, two-rates, approvals, door logs, standard materials, sign-ins)
with real platform records (fault work orders, alarm records).  All rules are
plain, auditable functions: no LLM judgement is involved here.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

PERIOD_LABEL = "2026年8月"
PERIOD = "2026-08"

_DEMO_DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools" / "jiangsu" / "demo_data" / "august_2026.json"
)


@lru_cache(maxsize=1)
def load_demo_dataset() -> dict[str, Any]:
    """Load the committed demo dataset without importing the tool registry.

    ``app.tools`` initialisation depends on project configuration, which is not
    guaranteed inside the bubblewrap sandbox; this local loader keeps the report
    computation importable there.
    """
    if not _DEMO_DATASET_PATH.exists():
        raise FileNotFoundError(f"演示数据集不存在：{_DEMO_DATASET_PATH}")
    return json.loads(_DEMO_DATASET_PATH.read_text(encoding="utf-8"))


# 处置时效豁免类别（细则：电力/通信类故障不纳入响应/到场超时认定）
EXEMPT_KEYWORDS = ("停电", "断电", "电力", "通信", "网络", "离线", "传输", "采集")
# 报警积压优先关注的关键报警类型
KEY_ALARM_KEYWORDS = ("断数", "断电", "超量程", "离线", "数据缺失", "停电")

TRACK_SPEED_LIMIT_KMH = 250.0
TRACK_SAME_MINUTE_GAP_SECONDS = 120
FAR_SIGNIN_KM = 2.0
BACKUP_REPLACE_LIMIT_HOURS = 48
BACKUP_OVERDUE_DAYS = 30
ALARM_BACKLOG_DAYS = 7
FAULT_CLOSURE_LIMIT_HOURS = 72.0


def _pct(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 2)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split(".")[0].split("+")[0].strip(), fmt)
        except ValueError:
            continue
    return None


def _plan_rate(plan: dict[str, Any]) -> float:
    planned = float(plan.get("planned_count") or 0)
    return (float(plan.get("executed_count") or 0) / planned) if planned else 0.0


def build_daily_supervision_analysis(
    fault_orders: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dataset = dataset or load_demo_dataset()
    plans = dataset.get("operation_plans") or []
    signins = dataset.get("attendance_signins") or []
    certificates = dataset.get("personnel_certificates") or []
    two_rates = dataset.get("performance_two_rates") or []
    qc_stats = dataset.get("qc_pass_rate_stats") or []
    materials = dataset.get("standard_materials") or []
    station_count = len(two_rates) or 293

    # ---- 1.1 计划覆盖与执行 --------------------------------------------
    no_plan_codes = set(dataset.get("no_plan_station_codes") or [])
    not_executed = [p for p in plans if not p.get("executed_count")]
    partial = [p for p in plans if 0 < _plan_rate(p) <= 0.5]
    total_planned = sum(int(p.get("planned_count") or 0) for p in plans)
    total_executed = sum(int(p.get("executed_count") or 0) for p in plans)
    city_plan_missing = Counter(
        p.get("city_name") or "未知" for p in plans if p.get("station_code") in no_plan_codes
    )
    # 无计划站点的城市归属需要站点表补齐：plans 不含无计划站点，用签到/两率反查
    city_by_station = {
        row.get("station_code"): row.get("city_name")
        for row in two_rates
    }
    no_plan_rows = [
        {
            "station_code": code,
            "station_name": next(
                (r.get("station_name") for r in two_rates if r.get("station_code") == code), code
            ),
            "city_name": city_by_station.get(code, "未知"),
        }
        for code in sorted(no_plan_codes)
    ]

    plan_summary = {
        "station_count": station_count,
        "stations_with_plan": len(plans),
        "coverage_rate": _pct(len(plans), station_count),
        "total_planned": total_planned,
        "total_executed": total_executed,
        "execution_rate": _pct(total_executed, total_planned),
        "no_plan": no_plan_rows,
        "not_executed": not_executed,
        "partial_executed": sorted(partial, key=_plan_rate),
        "city_plan_missing": dict(city_plan_missing),
    }

    # ---- 1.2 人员资质 ---------------------------------------------------
    signin_names = {row.get("user_name") for row in signins}
    unlicensed = [
        {
            "person_name": row.get("person_name"),
            "unit_name": row.get("unit_name"),
            "cert_status": row.get("status"),
            "cert_no": row.get("cert_no"),
            "expiry_date": row.get("expiry_date"),
            "august_signins": sum(
                1 for s in signins if s.get("user_name") == row.get("person_name")
            ),
        }
        for row in certificates
        if row.get("status") in ("无证", "已过期") and row.get("person_name") in signin_names
    ]
    expiring_soon = [
        {"person_name": row.get("person_name"), "unit_name": row.get("unit_name"),
         "expiry_date": row.get("expiry_date")}
        for row in certificates
        if row.get("status") == "30天内到期"
    ]
    expiring_soon.sort(key=lambda r: str(r.get("expiry_date")))
    unit_cert: dict[str, Counter] = defaultdict(Counter)
    for row in certificates:
        unit = row.get("unit_name") or "未知"
        unit_cert[unit]["total"] += 1
        if row.get("status") not in ("无证",):
            unit_cert[unit]["certified"] += 1
    cert_summary = {
        "total_persons": len(certificates),
        "certified_rate": _pct(
            sum(1 for r in certificates if r.get("status") not in ("无证",)), len(certificates)
        ),
        "unlicensed_on_duty": unlicensed,
        "expiring_in_30d": expiring_soon,
        "unit_certified_rate": {
            unit: {
                "total": counter["total"],
                "certified": counter["certified"],
                "rate": _pct(counter["certified"], counter["total"]),
            }
            for unit, counter in sorted(unit_cert.items())
        },
    }

    # ---- 1.3 执行处置异常（真实故障工单） --------------------------------
    closures: list[float] = []
    overdue_orders: list[dict[str, Any]] = []
    missing_fields: list[dict[str, Any]] = []
    exempt_count = 0
    for row in fault_orders:
        title = str(row.get("orderTitle") or "")
        created = _parse_ts(row.get("createTime"))
        finished = _parse_ts(row.get("finishTime"))
        if not title or not row.get("orderContent") or not row.get("deviceInfo") or not row.get("stationCodeStr"):
            missing_fields.append({
                "working_order_code": row.get("workingOrderCode"),
                "station_name": row.get("stationName"),
                "missing": [k for k, v in (
                    ("orderTitle", title), ("orderContent", row.get("orderContent")),
                    ("deviceInfo", row.get("deviceInfo")), ("stationCodeStr", row.get("stationCodeStr")),
                ) if not v],
            })
        if not created or not finished:
            continue
        hours = (finished - created).total_seconds() / 3600
        closures.append(hours)
        if any(k in title for k in EXEMPT_KEYWORDS):
            exempt_count += 1
            continue
        if hours > FAULT_CLOSURE_LIMIT_HOURS:
            overdue_orders.append({
                "working_order_code": row.get("workingOrderCode"),
                "station_code": row.get("stationCodeStr"),
                "station_name": row.get("stationName"),
                "city_name": row.get("city"),
                "operation_unit": row.get("operationUnitName"),
                "device_info": row.get("deviceInfo"),
                "title": title[:40],
                "created": row.get("createTime"),
                "finished": row.get("finishTime"),
                "closure_hours": round(hours, 1),
            })
    overdue_orders.sort(key=lambda r: -float(r.get("closure_hours") or 0))
    overdue_codes = {o["working_order_code"] for o in overdue_orders}
    unit_fault: dict[str, Counter] = defaultdict(Counter)
    city_fault: Counter = Counter()
    for row in fault_orders:
        unit = row.get("operationUnitName") or "未知"
        unit_fault[unit]["total"] += 1
        if row.get("workingOrderCode") in overdue_codes:
            unit_fault[unit]["overdue"] += 1
        city_fault[row.get("city") or "未知"] += 1
    disposal_summary = {
        "total_orders": len(fault_orders),
        "closure_limit_hours": FAULT_CLOSURE_LIMIT_HOURS,
        "avg_closure_hours": _mean(closures),
        "median_closure_hours": round(sorted(closures)[len(closures) // 2], 2) if closures else None,
        "overdue_orders": overdue_orders[:20],
        "overdue_total": len(overdue_orders),
        "on_time_rate": _pct(len(fault_orders) - len(overdue_orders) - exempt_count,
                            max(len(fault_orders) - exempt_count, 1)),
        "exempt_orders": exempt_count,
        "missing_required_fields": missing_fields,
        "missing_required_fields_total": len(missing_fields),
        "unit_overview": {
            unit: {"total": c["total"], "overdue": c["overdue"]}
            for unit, c in sorted(unit_fault.items(), key=lambda kv: -kv[1]["total"])
        },
        "city_overview": dict(city_fault.most_common()),
    }

    # ---- 1.4 两率与质控合格率（演示数据） --------------------------------
    low_acq = [r for r in two_rates if float(r.get("data_acquisition_rate") or 100) < 95.0]
    low_valid = [r for r in two_rates if float(r.get("data_valid_rate") or 100) < 98.0]
    low_qc = [r for r in two_rates if float(r.get("qc_pass_rate") or 100) < 80.0]
    qc_by_station = {row.get("station_code"): row for row in qc_stats}
    below_rows = []
    for row in two_rates:
        if not row.get("below_threshold"):
            continue
        trend = (qc_by_station.get(row.get("station_code")) or {}).get("monthly_trend") or {}
        below_rows.append({
            "station_code": row.get("station_code"),
            "station_name": row.get("station_name"),
            "city_name": row.get("city_name"),
            "operation_unit": row.get("operation_unit"),
            "data_acquisition_rate": row.get("data_acquisition_rate"),
            "data_valid_rate": row.get("data_valid_rate"),
            "qc_pass_rate": row.get("qc_pass_rate"),
            "two_rate_score": row.get("two_rate_score"),
            "qc_trend_3m": [trend.get("2026-06"), trend.get("2026-07"), trend.get("2026-08")],
            "root_cause_hint": row.get("root_cause_hint"),
        })
    below_rows.sort(key=lambda r: float(r.get("two_rate_score") or 100))
    rates_summary = {
        "thresholds": {"acquisition": 95.0, "valid": 98.0, "qc": 80.0},
        "avg_acquisition": _mean([float(r.get("data_acquisition_rate") or 0) for r in two_rates]),
        "avg_valid": _mean([float(r.get("data_valid_rate") or 0) for r in two_rates]),
        "avg_qc_pass": _mean([float(r.get("qc_pass_rate") or 0) for r in two_rates]),
        "avg_two_rate_score": _mean([float(r.get("two_rate_score") or 0) for r in two_rates]),
        "low_acquisition": low_acq,
        "low_valid": low_valid,
        "low_qc": low_qc,
        "below_threshold_detail": below_rows,
        "below_threshold_total": len(below_rows),
    }

    # ---- 1.5/1.6 数据门禁 + 标准物质 -------------------------------------
    expired_materials = [r for r in materials if r.get("status") in ("已过期", "库存不足")]
    gating = {
        "shutdown_records": "停运管理接口未接入，站点停运合规性分析（1.5）无法开展",
        "device_lifecycle": "设备生命周期/借出/库存接口未接入，设备闭环监管（1.6）无法开展",
        "performance_source": "两率/合格率统计为演示数据集，正式考核需接入绩效管理接口",
        "attendance_source": "考勤签到为演示数据集（平台8月无签到数据）",
        "plan_source": "运维计划为演示数据集",
    }
    return {
        "period": PERIOD_LABEL,
        "plan_summary": plan_summary,
        "cert_summary": cert_summary,
        "disposal_summary": disposal_summary,
        "rates_summary": rates_summary,
        "expired_materials": expired_materials,
        "data_gating": gating,
    }


def build_risk_prevention_analysis(
    fault_orders: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dataset = dataset or load_demo_dataset()
    signins = dataset.get("attendance_signins") or []
    approvals = dataset.get("operation_approvals") or []
    door_logs = dataset.get("door_remote_open_logs") or []
    two_rates = dataset.get("performance_two_rates") or []
    city_by_station = {r.get("station_code"): r.get("city_name") for r in two_rates}

    def _covers(approval: dict[str, Any], station_code: str, when: datetime) -> bool:
        if approval.get("station_code") != station_code:
            return False
        start = _parse_ts(approval.get("start_time"))
        end = _parse_ts(approval.get("end_time"))
        return bool(start and end and start - timedelta(hours=2) <= when <= end + timedelta(hours=2))

    # ---- 2.1 高值窗口无报备计划性运维（确定违规） -------------------------
    alarm_ts_by_station: dict[str, list[datetime]] = defaultdict(list)
    for row in alarms:
        ts = _parse_ts(row.get("alarmtime"))
        if ts and row.get("stacode"):
            alarm_ts_by_station[row["stacode"]].append(ts)
    order_ts_by_station: dict[str, list[datetime]] = defaultdict(list)
    for row in fault_orders:
        ts = _parse_ts(row.get("createTime"))
        if ts and row.get("stationCodeStr"):
            order_ts_by_station[row["stationCodeStr"]].append(ts)

    high_value_rows = []
    for visit in dataset.get("high_value_window_visits") or []:
        code = visit.get("station_code")
        when = _parse_ts(visit.get("sign_in_time"))
        if not when:
            continue
        approved = any(_covers(a, code, when) for a in approvals)
        has_fault = any(abs((t - when).total_seconds()) <= 12 * 3600 for t in order_ts_by_station.get(code, []))
        has_alarm = any(abs((t - when).total_seconds()) <= 12 * 3600 for t in alarm_ts_by_station.get(code, []))
        if approved:
            classification = "已报备计划性运维"
        elif has_fault or has_alarm:
            classification = "疑似故障处置（有故障/报警记录佐证）"
        else:
            classification = "高值窗口无报备运维（确定违规）"
        high_value_rows.append({
            "station_code": code,
            "station_name": visit.get("station_name"),
            "city_name": visit.get("city_name"),
            "high_value_window": visit.get("high_value_window"),
            "peak_o3": visit.get("peak_o3_ugm3"),
            "sign_in_time": visit.get("sign_in_time"),
            "user_name": visit.get("user_name"),
            "approved": approved,
            "fault_evidence": has_fault,
            "alarm_evidence": has_alarm,
            "classification": classification,
        })
    hv_violations = [r for r in high_value_rows if r["classification"].startswith("高值窗口无报备")]

    # ---- 2.2 工单轨迹合理性（演示签到数据重算） ---------------------------
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in signins:
        if row.get("user_name"):
            by_person[row["user_name"]].append(row)
    track_leads: list[dict[str, Any]] = []
    for person, rows in by_person.items():
        rows.sort(key=lambda r: str(r.get("sign_in_time")))
        for prev, curr in zip(rows, rows[1:], strict=False):
            t1 = _parse_ts(prev.get("sign_in_time"))
            t2 = _parse_ts(curr.get("sign_in_time"))
            if not t1 or not t2 or prev.get("station_code") == curr.get("station_code"):
                continue
            gap_seconds = (t2 - t1).total_seconds()
            lead: dict[str, Any] | None = None
            if abs(gap_seconds) <= TRACK_SAME_MINUTE_GAP_SECONDS:
                lead = {
                    "person_name": person,
                    "kind": "同一时间多点签到",
                    "detail": [prev, curr],
                }
            else:
                try:
                    lon1, lat1 = float(prev.get("longitude")), float(prev.get("latitude"))
                    lon2, lat2 = float(curr.get("longitude")), float(curr.get("latitude"))
                    from math import asin, cos, radians, sin, sqrt

                    dlon = radians(lon2 - lon1)
                    dlat = radians(lat2 - lat1)
                    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
                    km = 6371.0 * 2 * asin(sqrt(a))
                    speed = km / (abs(gap_seconds) / 3600.0)
                    if speed > TRACK_SPEED_LIMIT_KMH:
                        lead = {
                            "person_name": person,
                            "kind": "相邻签到隐含速度超限（疑似跨市串单）",
                            "implied_speed_kmh": round(speed, 1),
                            "distance_km": round(km, 1),
                            "detail": [prev, curr],
                        }
                except (TypeError, ValueError):
                    pass
            if lead:
                lead["unit_name"] = prev.get("unit_name")
                lead["city_a"] = prev.get("city_name") or city_by_station.get(prev.get("station_code"))
                lead["city_b"] = curr.get("city_name") or city_by_station.get(curr.get("station_code"))
                track_leads.append(lead)
    far_signins = [
        {
            "person_name": row.get("user_name"),
            "station_code": row.get("station_code"),
            "station_name": row.get("station_name"),
            "sign_in_time": row.get("sign_in_time"),
            "distance_km": row.get("distance_to_station_km"),
        }
        for row in signins
        if float(row.get("distance_to_station_km") or 0) > FAR_SIGNIN_KM
    ]
    track_summary = {
        "speed_limit_kmh": TRACK_SPEED_LIMIT_KMH,
        "cross_city_leads": [lead for lead in track_leads if "速度超限" in lead["kind"]],
        "same_time_leads": [lead for lead in track_leads if lead["kind"] == "同一时间多点签到"],
        "far_signins": far_signins,
    }

    # ---- 2.4 报警积压（真实报警） -----------------------------------------
    month_end = datetime(2026, 8, 31, 23, 59, 59)
    backlog = []
    for row in alarms:
        if str(row.get("ddalarmstateName") or "") != "未处理":
            continue
        ts = _parse_ts(row.get("alarmtime"))
        if not ts:
            continue
        age_days = (month_end - ts).days
        if age_days <= ALARM_BACKLOG_DAYS:
            continue
        content = str(row.get("content") or "")
        backlog.append({
            "station_code": row.get("stacode"),
            "station_name": row.get("positionName"),
            "city_name": row.get("areaname"),
            "alarm_time": row.get("alarmtime"),
            "age_days": age_days,
            "level": row.get("alarmlevel"),
            "rule_type": row.get("ddRuleType"),
            "content": content[:60],
            "key_alarm": any(k in content for k in KEY_ALARM_KEYWORDS),
        })
    backlog.sort(key=lambda r: (-int(r["key_alarm"]), -r["age_days"]))
    backlog_by_city = Counter(r.get("city_name") or "未知" for r in backlog)
    backlog_by_station = Counter(
        f"{r.get('station_code')} {r.get('station_name')}" for r in backlog
    )
    backlog_summary = {
        "unhandled_total": sum(1 for r in alarms if str(r.get("ddalarmstateName") or "") == "未处理"),
        "backlog_total": len(backlog),
        "key_backlog_total": sum(1 for r in backlog if r["key_alarm"]),
        "over_7d": len(backlog),
        "over_15d": sum(1 for r in backlog if r["age_days"] > 15),
        "top_stations": backlog_by_station.most_common(10),
        "by_city": backlog_by_city.most_common(),
        "samples": backlog[:20],
    }

    # ---- 2.5 门禁-考勤-工单三方一致性（演示门禁日志） ----------------------
    door_leads = []
    for row in door_logs:
        if not row.get("same_day_signin") and not row.get("same_day_work_order"):
            door_leads.append({
                "log_id": row.get("log_id"),
                "station_code": row.get("station_code"),
                "station_name": row.get("station_name"),
                "city_name": row.get("city_name"),
                "operator_name": row.get("operator_name"),
                "open_time": row.get("open_time"),
                "reason": row.get("reason"),
                "lead": "远程开门当日无签到且无工单（疑似违规进入/漏记）",
            })
    door_summary = {
        "door_logs_total": len(door_logs),
        "lead_total": len(door_leads),
        "leads": door_leads,
        "note": "门禁远程开门日志为演示数据；考勤签到为演示数据；工单为平台真实数据。反向（签到无门禁）因门禁日志覆盖率有限暂不输出。",
    }

    # ---- 2.3/2.6 数据门禁 --------------------------------------------------
    gating = {
        "backup_lifecycle": "设备生命周期/备机使用综合查询/延期备案审批接口未接入，备机更换超时（>48h）与超期顶岗（>30天）无法计算",
        "manual_supplement": "自动监测数据手工补录接口未接入，补录合规风险分析无法开展",
        "offline_status": "站点在线/离线状态历史接口未接入，高值期离线时长以报警与工单佐证替代",
    }

    # ---- 汇总 ---------------------------------------------------------------
    confirmed_total = len(hv_violations)
    suspected_total = (
        len(track_leads)
        + len(far_signins)
        + len(backlog)
        + len(door_leads)
    )
    by_kind = Counter()
    for lead in track_leads:
        by_kind[lead["kind"]] += 1
    by_kind["签到位置远离站点"] += len(far_signins)
    by_kind["报警长期未处置"] += len(backlog)
    by_kind["门禁三方不一致"] += len(door_leads)
    by_kind["高值窗口无报备运维（确定违规）"] += len(hv_violations)
    return {
        "period": PERIOD_LABEL,
        "high_value_visits": high_value_rows,
        "high_value_violations": hv_violations,
        "track_summary": track_summary,
        "backlog_summary": backlog_summary,
        "door_summary": door_summary,
        "data_gating": gating,
        "overview": {
            "confirmed_total": confirmed_total,
            "suspected_total": suspected_total,
            "by_kind": dict(by_kind),
            "by_city_top": backlog_by_city.most_common(5),
        },
    }


def build_both_scenario_analyses(
    fault_orders: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single entry point used by the operations-analysis agent's report flow."""
    dataset = dataset or load_demo_dataset()
    return {
        "period": PERIOD_LABEL,
        "dataset_meta": dataset.get("meta") or {},
        "daily_supervision": build_daily_supervision_analysis(fault_orders, alarms, dataset),
        "risk_prevention": build_risk_prevention_analysis(fault_orders, alarms, dataset),
    }


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault-orders", type=Path, required=True)
    parser.add_argument("--alarms", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    orders = json.loads(args.fault_orders.read_text(encoding="utf-8"))
    alarms = json.loads(args.alarms.read_text(encoding="utf-8"))
    if isinstance(orders, dict):
        orders = orders.get("data") or []
    if isinstance(alarms, dict):
        alarms = alarms.get("data") or []
    result = build_both_scenario_analyses(orders, alarms)
    payload = json.dumps(result, ensure_ascii=False, indent=1, default=str)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    _main()
