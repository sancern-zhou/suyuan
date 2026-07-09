from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.scenarios.yuncheng_trial.config import YUNCHENG_TRIAL_CONFIG
from app.scenarios.yuncheng_trial.models import AlertState, RuleHit
from app.scenarios.yuncheng_trial.paths import build_evidence_run_paths
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value(row: dict[str, Any], pollutant: str) -> float:
    measurements = row.get("measurements") if isinstance(row.get("measurements"), dict) else {}
    aliases = {
        "PM2.5": ("PM2.5", "PM2_5", "pm2_5", "pm25"),
        "PM10": ("PM10", "pm10"),
        "O3": ("O3", "O3_8h", "o3", "o3_8h"),
        "NO2": ("NO2", "no2"),
        "CO": ("CO", "co"),
        "AQI": ("AQI", "aqi"),
    }[pollutant]
    for alias in aliases:
        candidate = _as_float(row.get(alias))
        if candidate is not None:
            return candidate
        candidate = _as_float(measurements.get(alias))
        if candidate is not None:
            return candidate
    return 0.0


def _delta(rows: list[dict[str, Any]], pollutant: str, hours: int = 3) -> float:
    if len(rows) <= hours:
        return 0.0
    return _value(rows[-1], pollutant) - _value(rows[-1 - hours], pollutant)


def _rule_hit(rule_id: str, level: str, message: str, rule_basis: str) -> RuleHit:
    return RuleHit(rule_id=rule_id, level=level, message=message, rule_basis=rule_basis)


def _silent(summary: str, supporting_rule_hits: list[RuleHit] | None = None) -> dict[str, Any]:
    return AlertState(
        city=YUNCHENG_TRIAL_CONFIG.city,
        checked_at=datetime.now().astimezone().isoformat(),
        has_alert=False,
        summary=summary,
        supporting_rule_hits=supporting_rule_hits or [],
        status="silent",
    ).to_dict()


def evaluate_alert_rules(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 4:
        return _silent("数据不足，未触发告警。")

    latest_time = str(rows[-1]["time"])
    rule_hits: list[RuleHit] = []
    supporting_rule_hits: list[RuleHit] = []

    o3_delta = _delta(rows, "O3")
    pm25_delta = _delta(rows, "PM2.5")
    pm10_delta = _delta(rows, "PM10")
    co_delta = _delta(rows, "CO")
    no2_delta = _delta(rows, "NO2")

    if o3_delta >= YUNCHENG_TRIAL_CONFIG.o3_rise_3h_threshold:
        rule_hits.append(_rule_hit(
            "o3_3h_rising",
            "medium",
            f"O3连续3小时上升，当前值较3小时前升高{o3_delta:.0f}微克/立方米。",
            "参考O3日变化规律：早晚低、中午高，快速上升提示午后光化学风险。",
        ))
    if pm25_delta >= YUNCHENG_TRIAL_CONFIG.pm25_rise_3h_threshold:
        rule_hits.append(_rule_hit(
            "pm25_3h_rising",
            "medium",
            f"PM2.5近3小时升高{pm25_delta:.0f}微克/立方米，达到颗粒物快速上升告警条件。",
            "参考PM2.5污染过程数据规律：颗粒物快速上升需关注累积、传输或燃烧影响。",
        ))
    if pm10_delta >= YUNCHENG_TRIAL_CONFIG.pm10_rise_3h_threshold:
        rule_hits.append(_rule_hit(
            "pm10_3h_rising",
            "medium",
            f"PM10近3小时升高{pm10_delta:.0f}微克/立方米，达到颗粒物快速上升告警条件。",
            "参考PM10污染过程数据规律：粗颗粒快速上升需结合风场、扬尘和降水条件判断。",
        ))

    latest_aqi = _value(rows[-1], "AQI")
    if latest_aqi > YUNCHENG_TRIAL_CONFIG.aqi_watch_level:
        rule_hits.append(_rule_hit(
            "aqi_hourly_over_100",
            "medium",
            f"AQI小时值达到{latest_aqi:.0f}，超过100，已进入污染盯守范围。",
            "驻场盯守场景关注空气质量等级从良转入污染的小时节点，便于及时开展现场研判。",
        ))

    if (
        pm25_delta >= YUNCHENG_TRIAL_CONFIG.pm25_co_supporting_rise_threshold
        and pm10_delta >= YUNCHENG_TRIAL_CONFIG.pm10_rise_3h_threshold
    ):
        supporting_rule_hits.append(_rule_hit(
            "pm25_pm10_co_rising",
            "low",
            "PM2.5与PM10同步上升，符合颗粒物通常同步升高的数据规律。",
            "参考规则文档：PM10、PM2.5一般同步升高同步下降。",
        ))
    if (
        pm25_delta >= YUNCHENG_TRIAL_CONFIG.pm25_co_supporting_rise_threshold
        and co_delta >= YUNCHENG_TRIAL_CONFIG.co_supporting_rise_threshold
    ):
        supporting_rule_hits.append(_rule_hit(
            "pm25_co_combustion_clue",
            "low",
            f"PM2.5与CO同步上升，CO近3小时升高{co_delta:.1f}毫克/立方米。",
            "参考规则文档：PM2.5、CO正相关性较好，不完全燃烧等污染过程两者会同步升高。",
        ))
    if no2_delta >= YUNCHENG_TRIAL_CONFIG.no2_supporting_rise_threshold and o3_delta < 0:
        supporting_rule_hits.append(_rule_hit(
            "no2_rise_o3_drop_titration_clue",
            "low",
            "NO2上升同时O3下降，提示可能存在NO消耗O3生成NO2的局地NOx影响特征。",
            "参考规则文档：一般情况下NO2与O3负相关较好，NO会消耗O3生成NO2。",
        ))
    elif no2_delta >= YUNCHENG_TRIAL_CONFIG.no2_supporting_rise_threshold and o3_delta > 0:
        supporting_rule_hits.append(_rule_hit(
            "no2_o3_both_rising_photochemical_precursor_clue",
            "low",
            "NO2与O3同步上升，提示前体物累积叠加光化学生成风险，需结合气象进一步验证。",
            "参考规则文档：NO2/O3关系需结合日变化和气象条件判断，不能直接归因。",
        ))

    for pollutant, threshold in (
        ("O3", YUNCHENG_TRIAL_CONFIG.o3_watch_level),
        ("PM2.5", YUNCHENG_TRIAL_CONFIG.pm25_watch_level),
        ("PM10", YUNCHENG_TRIAL_CONFIG.pm10_watch_level),
        ("NO2", YUNCHENG_TRIAL_CONFIG.no2_watch_level),
        ("CO", YUNCHENG_TRIAL_CONFIG.co_watch_level),
    ):
        latest_values = [_value(row, pollutant) for row in rows[-3:]]
        if len(latest_values) == 3 and all(value >= threshold for value in latest_values):
            rule_hits.append(_rule_hit(
                f"{pollutant.lower().replace('.', '')}_3h_sustained_high",
                "medium",
                f"{pollutant}连续3小时达到关注水平，最新值为{_value(rows[-1], pollutant):.1f}。",
                "试用阶段可配置的城市小时盯守阈值，用于触发驻场团队关注。",
            ))

    if not rule_hits:
        return _silent("未发现需要推送的告警。", supporting_rule_hits=supporting_rule_hits)

    target_pollutant = _target_pollutant(rule_hits[0].rule_id)
    return AlertState(
        city=YUNCHENG_TRIAL_CONFIG.city,
        checked_at=datetime.now().astimezone().isoformat(),
        has_alert=True,
        alert_id=f"yuncheng-{latest_time[:10].replace('-', '')}-{latest_time[11:13]}00-{target_pollutant.lower().replace('.', '').replace('2', '2')}",
        alert_level="medium",
        alert_type="aqi_watch" if target_pollutant == "AQI" else "pollutant_rise",
        target_pollutant=target_pollutant,
        target_time=latest_time,
        lookback_hours=YUNCHENG_TRIAL_CONFIG.default_lookback_hours,
        summary=f"运城市{target_pollutant}触发小时盯守告警，需开展告警后溯源分析。",
        rule_hits=rule_hits,
        supporting_rule_hits=supporting_rule_hits,
        status="pending_trace",
    ).to_dict()


def _target_pollutant(rule_id: str) -> str:
    if rule_id.startswith("aqi"):
        return "AQI"
    if rule_id.startswith("pm25"):
        return "PM2.5"
    if rule_id.startswith("pm10"):
        return "PM10"
    if rule_id.startswith("no2"):
        return "NO2"
    if rule_id.startswith("co"):
        return "CO"
    return "O3"


def _parse_checked_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now().astimezone()


def write_alert_evidence(registry_root: Path, state: dict[str, Any]) -> Path:
    paths = build_evidence_run_paths(registry_root, _parse_checked_at(state.get("checked_at")))
    output_path = paths.alert_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _parse_cli_time(value: str | None) -> datetime:
    if value:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    return now.replace(minute=0, second=0, microsecond=0)


def _format_cli_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_city_hour_record(record: dict[str, Any]) -> dict[str, Any]:
    time_value = record.get("TimePoint")
    return {
        "time": _format_cli_time(time_value) if isinstance(time_value, datetime) else str(time_value),
        "city": record.get("Area"),
        "PM2.5": record.get("PM2_5"),
        "PM10": record.get("PM10"),
        "O3": record.get("O3"),
        "NO2": record.get("NO2"),
        "SO2": record.get("SO2"),
        "CO": record.get("CO"),
        "AQI": record.get("AQI"),
        "primary_pollutant": record.get("PrimaryPollutant"),
        "quality": record.get("Quality"),
    }


def fetch_target_city_hourly_rows(
    city: str,
    end_time: datetime,
    hours: int,
    sql_client: Any | None = None,
) -> list[dict[str, Any]]:
    start_time = end_time - timedelta(hours=max(1, hours - 1))
    client = sql_client or get_sql_server_client()
    raw_records = client.query(
        cities=[city],
        start_time=_format_cli_time(start_time),
        end_time=_format_cli_time(end_time),
        table="CityAQIPublishHistory",
    )
    return [_normalize_city_hour_record(record) for record in raw_records]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Yuncheng data and evaluate watch alerts.")
    parser.add_argument("--registry-root", required=True)
    parser.add_argument("--input-json", help="Optional fixture data file for tests and dry runs.")
    parser.add_argument("--city", default=YUNCHENG_TRIAL_CONFIG.city)
    parser.add_argument("--end-time", help="End time in YYYY-MM-DD HH:MM:SS. Defaults to current whole hour.")
    parser.add_argument("--hours", type=int, default=YUNCHENG_TRIAL_CONFIG.default_lookback_hours)
    args = parser.parse_args()

    if args.input_json:
        rows = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    else:
        rows = fetch_target_city_hourly_rows(
            city=args.city,
            end_time=_parse_cli_time(args.end_time),
            hours=args.hours,
        )
    state = evaluate_alert_rules(rows)
    output_path = write_alert_evidence(Path(args.registry_root), state)
    print(f"ALERT_EVIDENCE:{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
