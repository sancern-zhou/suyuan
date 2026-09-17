"""Generate the deterministic August-2026 demo dataset for Jiangsu ops scenarios.

The dataset is anchored to real platform data (stations, high-value O3 windows,
August fault work orders and alarm records) while business records that the
platform does not expose yet (plans, certificates, two-rates, approvals, door
remote-open logs, standard materials, sign-ins) are fabricated for demo
purposes.  Person names in violation scenarios are invented to avoid framing
real individuals.

Usage:
    cd backend && /path/to/python -m \
        app.tools.jiangsu.demo_data.generate_august_dataset \
        --anchors /tmp/opencode/augdata --out august_2026.json
"""

from __future__ import annotations

import argparse
import json
import random
import zlib
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SEED = 20260831
PERIOD_START = datetime(2026, 8, 1)
PERIOD_END = datetime(2026, 8, 31, 23, 59, 59)

UNITS = ["江苏苏力", "武汉天虹", "隆力德"]

# (姓名, 单位) —— 演示用虚构人员，避免指向真实自然人。
# 每家 26 人 × 13 个设区市 ≈ 每个城市每家单位 2 人，保证按片区作业。
ROSTER: list[tuple[str, str]] = (
    [(f"苏力运维{i:02d}", "江苏苏力") for i in range(1, 27)]
    + [(f"天虹运维{i:02d}", "武汉天虹") for i in range(1, 27)]
    + [(f"隆力德运维{i:02d}", "隆力德") for i in range(1, 27)]
)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(str(value).replace("T", " ").split(".")[0])
    except ValueError:
        return None


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    import math

    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = r2 - r1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def generate(anchors: Path) -> dict[str, Any]:
    rng = random.Random(SEED)
    stations = json.loads((anchors / "stations.json").read_text())
    fault_orders = json.loads((anchors / "fault_orders_aug.json").read_text())
    alarms = json.loads((anchors / "alarms_aug.json").read_text())
    windows = json.loads((anchors / "high_value_windows.json").read_text())

    stations = [s for s in stations if s.get("stationCode")]
    station_by_code = {s["stationCode"]: s for s in stations}
    # 平台部分站点未回填运维单位字段；演示数据集按站点编码做确定性分配，
    # 保证按单位聚合可行，meta 中已标注该演示口径。
    demo_unit_assignment = {code: UNITS[i % 3] for i, code in enumerate(sorted(station_by_code))}
    unit_of = {
        s["stationCode"]: (s.get("operationUnitName") or demo_unit_assignment[s["stationCode"]])
        for s in stations
    }
    city_of = {s["stationCode"]: (s.get("cityName") or "") for s in stations}
    name_of = {s["stationCode"]: (s.get("positionName") or "") for s in stations}
    lonlat_of = {
        s["stationCode"]: (float(s["longitude"]), float(s["latitude"]))
        for s in stations
        if s.get("longitude") and s.get("latitude")
    }
    all_codes = sorted(station_by_code)

    roster_by_unit: dict[str, list[str]] = {u: [] for u in UNITS}
    for person, unit in ROSTER:
        roster_by_unit[unit].append(person)
    for pool in roster_by_unit.values():
        rng.shuffle(pool)

    # 运维人员按城市片区作业：把站点城市轮转分配给本单位人员，
    # 保证正常签到只出现在本片区，串单类线索仅来自下方设计的异常。
    cities = sorted({city_of[c] for c in all_codes if city_of.get(c)})
    staff_by_city_unit: dict[tuple[str, str], list[str]] = {}
    for city in cities:
        for unit in UNITS:
            staff_by_city_unit[(city, unit)] = []
    for idx, (person, unit) in enumerate(ROSTER):
        staff_by_city_unit[(cities[idx % len(cities)], unit)].append(person)
    city_of_person = {
        person: city
        for (city, _unit), staff in staff_by_city_unit.items()
        for person in staff
    }

    stations_by_city_unit: dict[tuple[str, str], list[str]] = defaultdict(list)
    for code in all_codes:
        city, unit = city_of.get(code) or "", unit_of.get(code) or "江苏苏力"
        stations_by_city_unit[(city, unit)].append(code)

    def pool_of(station_code: str) -> list[str]:
        unit = unit_of.get(station_code) or "江苏苏力"
        city = city_of.get(station_code) or cities[0]
        return staff_by_city_unit.get((city, unit)) or roster_by_unit.get(unit) or ["演示人员"]

    busy_days: set[tuple[str, int]] = set()

    def free_person(station_code: str, day: int) -> str | None:
        """同一人员每天至多一次签到，避免随机排班产生分钟级误报。"""
        pool = pool_of(station_code)
        available = [p for p in pool if (p, day) not in busy_days]
        if not available:
            return None
        return available[zlib.crc32(station_code.encode()) % len(available)]

    def staff_for(station_code: str) -> str:
        pool = pool_of(station_code)
        return pool[zlib.crc32(station_code.encode()) % len(pool)]

    alarm_ts_by_station: dict[str, list[datetime]] = {}
    for row in alarms:
        ts = _parse_ts(row.get("alarmtime"))
        if ts and row.get("stacode"):
            alarm_ts_by_station.setdefault(row["stacode"], []).append(ts)
    order_ts_by_station: dict[str, list[datetime]] = {}
    for row in fault_orders:
        ts = _parse_ts(row.get("createTime"))
        if ts and row.get("stationCodeStr"):
            order_ts_by_station.setdefault(row["stationCodeStr"], []).append(ts)

    def has_nearby(ts_map: dict[str, list[datetime]], code: str, when: datetime, hours: float) -> bool:
        return any(abs((t - when).total_seconds()) <= hours * 3600 for t in ts_map.get(code, []))

    # ------------------------------------------------------------------ plans
    codes = list(all_codes)
    rng.shuffle(codes)
    no_plan_codes = set(codes[:9])
    planned_codes = codes[9:]
    not_executed_codes = set(planned_codes[:6])
    partial_codes = set(planned_codes[6:13])
    normal_codes = planned_codes[13:]

    plans: list[dict[str, Any]] = []
    executed_of: dict[str, int] = {}
    for code in planned_codes:
        planned = 4
        if code in not_executed_codes:
            executed = 0
        elif code in partial_codes:
            executed = rng.choice([1, 2])
        else:
            executed = planned - rng.choice([0, 0, 0, 1])
        executed_of[code] = executed
        plans.append({
            "plan_id": f"PLAN-2608-{len(plans) + 1:04d}",
            "period": "2026-08",
            "station_code": code,
            "station_name": name_of[code],
            "city_name": city_of[code],
            "operation_unit": unit_of[code] or None,
            "plan_type": "月度例行运维",
            "plan_kind": "计划内",
            "planned_count": planned,
            "executed_count": executed,
        })

    # ------------------------------------------------------------- attendance
    signins: list[dict[str, Any]] = []
    visit_dates: dict[str, list[datetime]] = {}

    def add_signin(code: str, when: datetime, person: str | None = None,
                   distance_km: float | None = None) -> dict[str, Any]:
        lon, lat = lonlat_of.get(code, (119.5, 33.0))
        dist = distance_km if distance_km is not None else round(rng.uniform(0.05, 0.6), 3)
        jitter = 0.004 if (distance_km or 0.5) < 2 else 0.05
        row = {
            "user_name": person or staff_for(code),
            "unit_name": unit_of.get(code) or None,
            "station_code": code,
            "station_name": name_of[code],
            "city_name": city_of[code],
            "sign_in_time": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "longitude": round(lon + rng.uniform(-jitter, jitter), 6),
            "latitude": round(lat + rng.uniform(-jitter, jitter), 6),
            "distance_to_station_km": dist,
            "sign_result": "正常" if dist <= 1.0 else "异常-远离站点",
        }
        signins.append(row)
        visit_dates.setdefault(code, []).append(when)
        busy_days.add((row["user_name"], when.day))
        return row

    for code in planned_codes:
        executed = executed_of[code]
        days = sorted(rng.sample(range(1, 32), min(executed, 31)))
        for day in days:
            person = free_person(code, day)
            if person is None:
                continue
            when = datetime(2026, 8, day, rng.randint(9, 16), rng.randint(0, 59))
            add_signin(code, when, person=person)
    # 无计划站点仍有少量现场签到（有作业、无计划）
    for code in sorted(no_plan_codes)[:7]:
        for _ in range(rng.randint(1, 2)):
            day = rng.randint(1, 31)
            person = free_person(code, day)
            if person is None:
                continue
            when = datetime(2026, 8, day, rng.randint(9, 16), rng.randint(0, 59))
            add_signin(code, when, person=person)

    def free_day(person: str, low: int = 4, high: int = 28) -> int:
        candidates = [d for d in range(low, high + 1) if (person, d) not in busy_days]
        return rng.choice(candidates) if candidates else rng.randint(low, high)

    # 异常一：跨市串单（相邻签到隐含速度>250km/h，同一人员两次签到）
    far_pairs = []
    pool = [c for c in codes if c in lonlat_of]
    for _ in range(40):
        a, b = rng.sample(pool, 2)
        km = _haversine_km(*lonlat_of[a], *lonlat_of[b])
        if km > 300:
            far_pairs.append((a, b, km))
        if len(far_pairs) >= 3:
            break
    track_anomalies: list[dict[str, Any]] = []
    for idx, (a, b, km) in enumerate(far_pairs, 1):
        person = staff_for(a)
        t0 = datetime(2026, 8, free_day(person), 9, 30)
        row_a = add_signin(a, t0, person=person)
        row_b = add_signin(b, t0 + timedelta(minutes=45), person=person)
        speed = km / 0.75
        track_anomalies.append({
            "anomaly_id": f"TRK-2608-{idx:02d}",
            "kind": "跨市串单-相邻签到速度超限",
            "user_name": row_a["user_name"],
            "detail": [
                {"station_code": a, "station_name": name_of[a], "sign_in_time": row_a["sign_in_time"]},
                {"station_code": b, "station_name": name_of[b], "sign_in_time": row_b["sign_in_time"]},
            ],
            "implied_speed_kmh": round(speed, 1),
            "threshold_kmh": 250,
        })

    # 异常二：同一时间多站点签到（同一人员）
    for idx in range(2):
        a, b = rng.sample([c for c in pool if city_of.get(c)], 2)
        person = staff_for(a)
        t0 = datetime(2026, 8, free_day(person), rng.randint(10, 15), rng.randint(0, 59))
        row_a = add_signin(a, t0, person=person)
        row_b = add_signin(b, t0, person=person)
        track_anomalies.append({
            "anomaly_id": f"TRK-2608-{len(track_anomalies) + idx + 1:02d}",
            "kind": "同一时间多点签到",
            "user_name": row_a["user_name"],
            "detail": [
                {"station_code": a, "station_name": name_of[a], "sign_in_time": row_a["sign_in_time"]},
                {"station_code": b, "station_name": name_of[b], "sign_in_time": row_b["sign_in_time"]},
            ],
            "implied_speed_kmh": None,
            "threshold_kmh": 250,
        })

    # 异常三：签到位置远离站点
    for idx in range(4):
        code = rng.choice([c for c in normal_codes if c in lonlat_of])
        person = staff_for(code)
        when = datetime(2026, 8, free_day(person), rng.randint(9, 16), rng.randint(0, 59))
        row = add_signin(code, when, person=person, distance_km=round(rng.uniform(3.0, 7.5), 2))
        track_anomalies.append({
            "anomaly_id": f"TRK-2608-{len(track_anomalies) + idx + 1:02d}",
            "kind": "签到位置远离站点",
            "user_name": row["user_name"],
            "detail": [{"station_code": code, "station_name": name_of[code],
                        "sign_in_time": row["sign_in_time"],
                        "distance_to_station_km": row["distance_to_station_km"]}],
            "implied_speed_kmh": None,
            "threshold_kmh": None,
        })

    # 异常四：高值窗口到场且当期无故障报警（疑似人为干预线索）
    high_value_visits: list[dict[str, Any]] = []
    hv_candidates = [w for w in windows if w.get("station_code") in station_by_code]
    rng.shuffle(hv_candidates)
    for w in hv_candidates:
        if len(high_value_visits) >= 6:
            break
        code = w["station_code"]
        start = _parse_ts(w["start"])
        if not start:
            continue
        visit = start + timedelta(minutes=60)
        if not (PERIOD_START <= visit <= PERIOD_END):
            continue
        if has_nearby(order_ts_by_station, code, visit, 12) or has_nearby(alarm_ts_by_station, code, visit, 12):
            continue
        row = add_signin(code, visit)
        high_value_visits.append({
            "lead_id": f"HV-2608-{len(high_value_visits) + 1:02d}",
            "station_code": code,
            "station_name": name_of[code],
            "city_name": city_of[code],
            "high_value_window": [w["start"], w["end"]],
            "peak_o3_ugm3": w.get("peak_o3"),
            "sign_in_time": row["sign_in_time"],
            "user_name": row["user_name"],
        })

    signins.sort(key=lambda r: r["sign_in_time"])

    # ------------------------------------------------------------ approvals
    approvals: list[dict[str, Any]] = []
    protected = {(v["station_code"], v["sign_in_time"][:13]) for v in high_value_visits}
    hv_codes = {w["station_code"] for w in hv_candidates}
    approval_pool = [c for c in normal_codes if c not in hv_codes]
    while len(approvals) < 50 and approval_pool:
        code = approval_pool.pop(rng.randrange(len(approval_pool)))
        day = rng.randint(1, 30)
        start = datetime(2026, 8, day, rng.randint(9, 13))
        if (code, start.strftime("%Y-%m-%dT%H")) in protected:
            continue
        approvals.append({
            "approval_id": f"APPR-2608-{len(approvals) + 1:03d}",
            "period": "2026-08",
            "station_code": code,
            "station_name": name_of[code],
            "city_name": city_of[code],
            "operation_unit": unit_of[code] or None,
            "apply_type": rng.choice(["计划性运维报备", "校准作业报备", "停电维护报备"]),
            "applicant": staff_for(code),
            "start_time": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": (start + timedelta(hours=rng.randint(2, 5))).strftime("%Y-%m-%dT%H:%M:%S"),
            "approve_status": "已批准",
            "approver": "省站运维管理",
        })
    # 高值窗口到场线索对应的站点均无报备（protected 集合保证），
    # 分析模块据此输出“高值窗口无报备计划性运维”确定违规。

    # ---------------------------------------------------------- certificates
    certificates: list[dict[str, Any]] = []
    no_cert, expired, expiring = 10, 12, 18
    for idx, (person, unit) in enumerate(ROSTER):
        if idx < no_cert:
            row = {"person_name": person, "unit_name": unit, "cert_type": "空气站运维上岗证",
                   "cert_no": None, "issue_date": None, "expiry_date": None, "status": "无证"}
        elif idx < no_cert + expired:
            expiry = date(2026, 7, 20) + timedelta(days=rng.randint(0, 30))
            row = {"person_name": person, "unit_name": unit, "cert_type": "空气站运维上岗证",
                   "cert_no": f"JSYW{rng.randrange(100000, 999999)}",
                   "issue_date": "2023-06-30", "expiry_date": expiry.isoformat(), "status": "已过期"}
        elif idx < no_cert + expired + expiring:
            expiry = date(2026, 9, 1) + timedelta(days=rng.randint(0, 29))
            row = {"person_name": person, "unit_name": unit, "cert_type": "空气站运维上岗证",
                   "cert_no": f"JSYW{rng.randrange(100000, 999999)}",
                   "issue_date": "2023-09-30", "expiry_date": expiry.isoformat(), "status": "30天内到期"}
        else:
            row = {"person_name": person, "unit_name": unit, "cert_type": "空气站运维上岗证",
                   "cert_no": f"JSYW{rng.randrange(100000, 999999)}",
                   "issue_date": "2025-06-30",
                   "expiry_date": f"{rng.choice([2027, 2028])}-06-30", "status": "有效"}
        certificates.append(row)
    # 让 3 名已过期人员 8 月仍有签到记录 → 过期上岗违规
    expired_names = [r["person_name"] for r in certificates if r["status"] == "已过期"][:3]
    # 过期人员在本人片区内照常排班（违规点是证书状态，不是作业地点）
    for person in expired_names:
        unit = next(r["unit_name"] for r in certificates if r["person_name"] == person)
        home_city = city_of_person.get(person)
        person_city_pool = [
            c for c in all_codes
            if (unit_of.get(c) or "江苏苏力") == unit
            and c in lonlat_of
            and (not home_city or city_of.get(c) == home_city)
        ]
        if not person_city_pool:
            person_city_pool = [c for c in all_codes if (unit_of.get(c) or "江苏苏力") == unit and c in lonlat_of]
        code = rng.choice(person_city_pool)
        when = datetime(2026, 8, free_day(person, low=2), rng.randint(9, 15), rng.randint(0, 59))
        row = add_signin(code, when, person=person)
        certificates_next = [r for r in certificates if r["person_name"] == person][0]
        track_anomalies.append({
            "anomaly_id": f"TRK-2608-{len(track_anomalies) + 1:02d}",
            "kind": "证书过期后仍到站作业",
            "user_name": person,
            "detail": [{"station_code": code, "station_name": name_of[code],
                        "sign_in_time": row["sign_in_time"],
                        "cert_expiry_date": certificates_next["expiry_date"]}],
            "implied_speed_kmh": None,
            "threshold_kmh": None,
        })

    # ------------------------------------------------------ two rates & QC
    low_acq = set(rng.sample(normal_codes, 10))
    low_valid = set(rng.sample(normal_codes, 8))
    low_qc = set(rng.sample(normal_codes, 6))
    fault_count: dict[str, int] = {}
    for row in fault_orders:
        code = row.get("stationCodeStr")
        if code:
            fault_count[code] = fault_count.get(code, 0) + 1

    two_rates: list[dict[str, Any]] = []
    qc_stats: list[dict[str, Any]] = []
    for code in codes:
        acq = round(rng.uniform(95.6, 100.0), 2)
        valid = round(rng.uniform(98.3, 100.0), 2)
        qc = round(rng.uniform(84.0, 100.0), 2)
        root = None
        if code in low_acq:
            acq = round(rng.uniform(88.0, 94.5), 2)
            root = "设备故障处置不及时" if fault_count.get(code, 0) >= 2 else "外部停电断网"
        if code in low_valid:
            valid = round(rng.uniform(95.0, 97.8), 2)
            root = root or "设备故障处置不及时"
        if code in low_qc:
            qc = round(rng.uniform(62.0, 79.0), 2)
            root = root or "质控作业不到位"
        score = round(0.5 * acq + 0.3 * valid + 0.2 * qc, 2)
        two_rates.append({
            "period": "2026-08",
            "station_code": code,
            "station_name": name_of[code],
            "city_name": city_of[code],
            "operation_unit": unit_of[code] or None,
            "data_acquisition_rate": acq,
            "data_valid_rate": valid,
            "qc_pass_rate": qc,
            "two_rate_score": score,
            "acquisition_threshold": 95.0,
            "valid_threshold": 98.0,
            "qc_threshold": 80.0,
            "below_threshold": acq < 95.0 or valid < 98.0 or qc < 80.0,
            "root_cause_hint": root,
        })
        total = rng.randint(18, 42)
        qc_stats.append({
            "station_code": code,
            "station_name": name_of[code],
            "period": "2026-08",
            "qc_total_tests": total,
            "qc_passed_tests": int(round(total * qc / 100)),
            "monthly_trend": {
                "2026-06": round(min(100.0, qc + rng.uniform(0.5, 6.0)), 2),
                "2026-07": round(min(100.0, qc + rng.uniform(0.2, 3.0)), 2),
                "2026-08": qc,
            },
        })

    # -------------------------------------------------------- door records
    door_logs: list[dict[str, Any]] = []
    door_pool = [c for c in codes if c in lonlat_of]
    suspicious_door = 0
    while len(door_logs) < 30:
        code = rng.choice(door_pool)
        when = datetime(2026, 8, rng.randint(2, 30), rng.randint(7, 19), rng.randint(0, 59))
        day_str = when.strftime("%Y-%m-%d")
        has_visit = any(r["station_code"] == code and r["sign_in_time"][:10] == day_str for r in signins)
        has_order = any(t.strftime("%Y-%m-%d") == day_str for t in order_ts_by_station.get(code, []))
        is_suspicious = not has_visit and not has_order
        if not is_suspicious and suspicious_door >= 8 and rng.random() < 0.35:
            continue
        if is_suspicious:
            suspicious_door += 1
            if suspicious_door > 8:
                continue
        door_logs.append({
            "log_id": f"DOOR-2608-{len(door_logs) + 1:03d}",
            "period": "2026-08",
            "station_code": code,
            "station_name": name_of[code],
            "city_name": city_of[code],
            "operator_name": staff_for(code),
            "operation_type": "远程开门",
            "open_time": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "reason": rng.choice(["例行运维", "设备维护", "校准作业", "现场核查"]),
            "same_day_signin": has_visit,
            "same_day_work_order": has_order,
        })
    door_logs.sort(key=lambda r: r["open_time"])

    # ---------------------------------------------------- standard materials
    materials: list[dict[str, Any]] = []
    catalog = [
        ("SO2标准气体", "标气"), ("NO标准气体", "标气"), ("O3标准气体", "标气"),
        ("CO标准气体", "标气"), ("零气发生器", "校准设备"), ("流量校准器", "校准设备"),
        ("渗透管", "标气"), ("动态稀释仪", "校准设备"),
    ]
    for idx in range(36):
        unit = UNITS[idx % 3]
        name, category = catalog[idx % len(catalog)]
        expired_item = idx < 4
        low_stock = 4 <= idx < 7
        materials.append({
            "material_no": f"STD-2608-{idx + 1:03d}",
            "name": name,
            "category": category,
            "operation_unit": unit,
            "station_code": rng.choice(codes),
            "expire_date": ("2026-08-" + f"{rng.randint(1, 25):02d}") if expired_item else f"2027-0{rng.randint(1, 9)}-15",
            "last_verify_date": f"2026-0{rng.randint(1, 6)}-1{rng.randint(0, 9)}",
            "stock_qty": rng.randint(0, 2) if low_stock else rng.randint(3, 10),
            "stock_status": "库存不足" if low_stock else "正常",
            "status": "已过期" if expired_item else ("库存不足" if low_stock else "正常"),
        })

    return {
        "meta": {
            "dataset_id": "jiangsu_demo_august_2026",
            "period": "2026-08",
            "demo": True,
            "seed": SEED,
            "description": "江苏运维监管演示数据集：业务记录为预设编造数据（人员姓名为虚构），站点、高值窗口、故障工单、报警锚定平台真实数据。",
            "anchors": {
                "stations": len(stations),
                "persons": len(ROSTER),
                "real_high_value_windows": len(windows),
                "real_fault_orders": len(fault_orders),
                "real_alarms": len(alarms),
                "demo_unit_assignment": "平台未回填运维单位的站点按演示口径分配到三家运维单位",
            },
            "counts": {
                "operation_plans": len(plans),
                "attendance_signins": len(signins),
                "personnel_certificates": len(certificates),
                "performance_two_rates": len(two_rates),
                "qc_pass_rate_stats": len(qc_stats),
                "operation_approvals": len(approvals),
                "door_remote_open_logs": len(door_logs),
                "standard_materials": len(materials),
                "track_anomalies": len(track_anomalies),
                "high_value_visits": len(high_value_visits),
            },
        },
        "no_plan_station_codes": sorted(no_plan_codes),
        "operation_plans": plans,
        "attendance_signins": signins,
        "track_anomalies": track_anomalies,
        "high_value_window_visits": high_value_visits,
        "personnel_certificates": certificates,
        "performance_two_rates": two_rates,
        "qc_pass_rate_stats": qc_stats,
        "operation_approvals": approvals,
        "door_remote_open_logs": door_logs,
        "standard_materials": materials,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchors", type=Path, default=Path("/tmp/opencode/augdata"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    dataset = generate(args.anchors)
    out_path = args.out or Path(__file__).with_name("august_2026.json")
    out_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=1))
    print(f"written: {out_path}")
    print(json.dumps(dataset["meta"]["counts"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
