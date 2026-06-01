"""RF environment humidity calibration checks."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


MISSING_RULE_ID = "RF_HY_ENV_HUMIDITY_SENSOR_VALUE_MISSING"
UNCHANGED_RULE_ID = "RF_HY_ENV_HUMIDITY_BEFORE_AFTER_UNCHANGED_SUSPECT"
DATE_RULE_ID = "RF_HY_ENV_HUMIDITY_CALIBRATION_DATE_INVALID"
TABLE = "RF_HY_EnvironmentHumidity"
SKIP_VALUES = {"", "/", "-", "无", "不适用", "none", "null", "nan"}
EXEMPTION_KEYWORDS = ("无校准功能", "无湿度功能", "仅作参考", "不具备校准", "无法校准")


def check_rf_environment_humidity_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check half-year particulate environment humidity calibration records."""

    for table, form in forms:
        if form.get("_query_error") or table != TABLE:
            continue

        remark = str(form.get("REMARK") or "")
        exempted = any(keyword in remark for keyword in EXEMPTION_KEYWORDS)
        prev_value = _num(form.get("CailbPrevReadNum"))
        next_value = _num(form.get("CailbNextReadNum"))
        standard_value = _num(form.get("StandardReadNum"))

        if not exempted and standard_value is not None and (prev_value is None and next_value is None):
            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "pollutant_type": form.get("pollutantType"),
                "standard_read_num": form.get("StandardReadNum"),
                "cailb_prev_read_num": form.get("CailbPrevReadNum"),
                "cailb_next_read_num": form.get("CailbNextReadNum"),
                "remark": form.get("REMARK"),
            }
            add_issue(
                issues,
                MISSING_RULE_ID,
                "表单完整性",
                "高",
                f"rf.{table}.CailbPrevReadNum/CailbNextReadNum",
                "环境湿度校准记录有标准湿度读数，但校准前后传感器读数均未填写",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )

        if not exempted and prev_value is not None and next_value is not None and abs(prev_value - next_value) <= 0.01:
            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "pollutant_type": form.get("pollutantType"),
                "cailb_prev_read_num": form.get("CailbPrevReadNum"),
                "cailb_next_read_num": form.get("CailbNextReadNum"),
                "standard_read_num": form.get("StandardReadNum"),
                "remark": form.get("REMARK"),
            }
            add_issue(
                issues,
                UNCHANGED_RULE_ID,
                "规范性问题",
                "中",
                f"rf.{table}.CailbPrevReadNum/CailbNextReadNum",
                "环境湿度校准前后读数完全一致且无说明，疑似未体现校准效果",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )

        _check_last_calibration_date(order, table, form, issues)


def _check_last_calibration_date(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    reference = _parse_time(form.get("SdtTime")) or _parse_time(form.get("CHECKDATE")) or _parse_time(order.get("CREATETIME"))
    if not reference:
        return
    violations = []
    for field in ("LastTimeCailbTime1", "LastTimeCailbTime2"):
        last_time = _parse_time(form.get(field))
        if not last_time:
            continue
        if last_time > reference:
            violations.append(
                {
                    "field": field,
                    "last_calibration_time": _format_time(last_time),
                    "reference_time": _format_time(reference),
                    "reason": "上次校准时间晚于本次作业时间",
                }
            )
        elif (reference - last_time).days > 366:
            violations.append(
                {
                    "field": field,
                    "last_calibration_time": _format_time(last_time),
                    "reference_time": _format_time(reference),
                    "elapsed_days": (reference - last_time).days,
                    "reason": "上次校准时间距本次作业超过一年",
                }
            )
    if not violations:
        return
    first = violations[0]
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violations": violations,
    }
    add_issue(
        issues,
        DATE_RULE_ID,
        "时间合理性",
        "中",
        f"rf.{table}.{first['field']}",
        f"环境湿度校准日期异常: {first['reason']}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace("％", "%").replace(",", "")
    if text.lower() in SKIP_VALUES:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _format_time(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")
