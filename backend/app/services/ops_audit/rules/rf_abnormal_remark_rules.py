"""RF abnormal result and missing remark checks for operations work order audits."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.ops_audit.config import load_low_value_remarks
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

RULE_ID = "RF_ABNORMAL_VALUE_NO_REMARK"
LOW_VALUE_REMARKS = load_low_value_remarks()
TRIGGER_RULE_IDS = {
    "RF_RANGE_OUT_OF_SPEC",
    "RF_RANGE_VALUE_MISSING",
    "RF_PM_TEMP_ERROR_OUT_OF_RANGE",
    "RF_HY_ENV_HUMIDITY_BEFORE_AFTER_UNCHANGED_SUSPECT",
}
REMARK_FIELD_PATTERNS = (
    "REMARK",
    "REMARKS",
    "CHECKREMARK",
    "BZ",
    "COMMENT",
    "EXPLAIN",
    "EXCEPTION",
    "ABNORMAL",
    "DESCRIPTION",
)
RESULT_FIELD_PATTERNS = ("SITUATION", "CHECKRESULT", "RESULT", "ISNORMAL")
ABNORMAL_TEXT_TOKENS = ("异常", "不合格", "未通过", "超限", "超标", "失败", "待定", "不正常")
NORMAL_TEXT_TOKENS = ("正常", "合格", "通过", "无异常")


def check_rf_abnormal_remarks(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Require meaningful remarks when RF data already indicates abnormality."""

    form_by_table = {
        table: form
        for table, form in forms
        if not form.get("_query_error")
    }
    if not form_by_table:
        return

    emitted: set[tuple[str, str]] = set()
    for issue in list(issues):
        if issue.rule_id not in TRIGGER_RULE_IDS:
            continue
        table = _issue_table(issue, form_by_table)
        if not table:
            continue
        trigger_evidence = _issue_evidence(issue)
        _add_if_no_remark(
            order,
            table,
            form_by_table[table],
            issues,
            emitted,
            reason_rule_id=issue.rule_id,
            abnormal_field=issue.field,
            abnormal_message=issue.message,
            extra_remark_candidates=_trigger_remark_candidates(trigger_evidence),
        )

    for table, form in form_by_table.items():
        if table == "RF_W_PMCHECK":
            _check_pm_sample_tube_temperature(order, table, form, issues, emitted)
        if table == "RF_W_OTHERDEVICECHECK":
            _check_other_device_no_device_remark(order, table, form, issues)
        for field, value in form.items():
            if table == "RF_W_PMCHECK" and str(field).upper() in {"AIRTEMPVALUE", "AIRTEMPISNORMAL"}:
                continue
            if not _is_abnormal_result_field(field, value):
                continue
            fact_evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "field": field,
                "raw_value": value,
                "remark_candidates": _remark_candidates(form),
            }
            add_issue(
                issues,
                "RF_ABNORMAL_RESULT_FIELD",
                "结果合理性",
                "高",
                f"rf.{table}.{field}",
                f"{field} 表示异常结果: {value}",
                json.dumps(fact_evidence, ensure_ascii=False, default=str),
            )
            extra_candidates = {field: value} if _abnormal_result_value_has_context(value) else None
            _add_if_no_remark(
                order,
                table,
                form,
                issues,
                emitted,
                reason_rule_id="RF_ABNORMAL_RESULT_FIELD",
                abnormal_field=f"rf.{table}.{field}",
                abnormal_message=f"{field} 表示异常结果: {value}",
                extra_remark_candidates=extra_candidates,
            )


def _check_other_device_no_device_remark(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    pairs = [
        ("WEATHERDEVICEMODEL", "WEATHERSITUATION", "气象设备"),
        ("VISIBILITYDEVICEMODEL", "VISIBILITYSITUATION", "能见度设备"),
        ("CITYCAMERADEVICEMODEL", "CITYCAMERASITUATION", "城市摄像设备"),
        ("DATAACQUISITIONDEVICEMODEL", "DATAACQUISITIONSITUATION", "数据采集仪"),
    ]
    violations = []
    for model_field, situation_field, label in pairs:
        if model_field not in form and situation_field not in form:
            continue
        model = str(form.get(model_field) or "").strip()
        if not _is_unclear_no_device_value(model):
            continue
        situation = str(form.get(situation_field) or "").strip()
        violations.append(
            {
                "label": label,
                "model_field": model_field,
                "model_value": model,
                "situation_field": situation_field,
                "situation_value": situation,
            }
        )
    if not violations:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violations": violations,
    }
    first = violations[0]
    add_issue(
        issues,
        "RF_NO_DEVICE_WITHOUT_REMARK",
        "异常说明问题",
        "中",
        f"rf.{table}.{first['model_field']}",
        f"其他设备周检存在无对应设备但说明不清: {first['label']}={first['model_value'] or '<空>'}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_pm_sample_tube_temperature(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
    emitted: set[tuple[str, str]],
) -> None:
    value = form.get("AIRTEMPVALUE")
    status = str(form.get("AIRTEMPISNORMAL") or "").strip()
    number = _num(value)
    missing = value is None or str(value).strip() in {"", "/", "-", "未填", "无"}
    abnormal_status = _is_pm_sample_tube_temp_status_abnormal(status)
    out_of_range = number is not None and (number < 0 or number > 60)
    if not (missing or abnormal_status or out_of_range):
        return
    reason_parts = []
    if missing:
        reason_parts.append("采样管温度未填")
    if abnormal_status:
        reason_parts.append(f"状态={status}")
    if out_of_range:
        reason_parts.append(f"温度值={number}")
    abnormal_message = "、".join(reason_parts)
    fact_evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "field": "AIRTEMPVALUE/AIRTEMPISNORMAL",
        "temperature_value": value,
        "temperature_status": status,
        "missing": missing,
        "abnormal_status": abnormal_status,
        "out_of_range": out_of_range,
        "remark_candidates": _remark_candidates(form),
    }
    add_issue(
        issues,
        "RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL",
        "结果合理性",
        "高",
        f"rf.{table}.AIRTEMPVALUE/AIRTEMPISNORMAL",
        abnormal_message,
        json.dumps(fact_evidence, ensure_ascii=False, default=str),
    )
    _add_if_no_remark(
        order,
        table,
        form,
        issues,
        emitted,
        reason_rule_id="RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL",
        abnormal_field=f"rf.{table}.AIRTEMPVALUE/AIRTEMPISNORMAL",
        abnormal_message=abnormal_message,
    )


def _trigger_remark_candidates(evidence: dict[str, Any]) -> dict[str, Any]:
    candidates: dict[str, Any] = {}
    for key in ("remark_candidates", "handling_record_candidates"):
        value = evidence.get(key)
        if isinstance(value, dict):
            candidates.update(value)
    for violation in evidence.get("violations") or []:
        if not isinstance(violation, dict):
            continue
        field = str(violation.get("calibration_situation_field") or "").strip()
        if field:
            candidates[field] = violation.get("calibration_situation")
    return candidates


def _is_pm_sample_tube_temp_status_abnormal(status: str) -> bool:
    if not status or status in LOW_VALUE_REMARKS:
        return False
    text = status.strip()
    lowered = text.lower()
    normal_values = {"是", "1", "1.0", "true", "正常", "合格", "通过", "无异常"}
    abnormal_values = {"否", "0", "0.0", "false"}
    if text in normal_values or lowered in normal_values:
        return False
    if text in abnormal_values or lowered in abnormal_values:
        return True
    if any(token in text for token in NORMAL_TEXT_TOKENS):
        return False
    if any(token in text for token in ABNORMAL_TEXT_TOKENS):
        return True
    return True


def _abnormal_result_value_has_context(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    context_markers = (
        "交接遗留",
        "遗留问题",
        "已处理",
        "已修复",
        "已恢复",
        "已更换",
        "已通知",
        "已报备",
    )
    return any(marker in text for marker in context_markers)


def _add_if_no_remark(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
    emitted: set[tuple[str, str]],
    *,
    reason_rule_id: str,
    abnormal_field: str,
    abnormal_message: str,
    extra_remark_candidates: dict[str, Any] | None = None,
) -> None:
    key = (table, str(abnormal_field))
    if key in emitted:
        return
    emitted.add(key)
    remark_candidates = _remark_candidates(form)
    for field, value in (extra_remark_candidates or {}).items():
        if str(field).upper() == "PROCESSTYPE":
            continue
        if str(field) not in remark_candidates:
            remark_candidates[str(field)] = value
    has_remark = any(str(value or "").strip() for value in remark_candidates.values())
    remark_content = _remark_content_text(remark_candidates) if has_remark else ""
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "reason_rule_id": reason_rule_id,
        "abnormal_field": abnormal_field,
        "abnormal_message": abnormal_message,
        "remark_candidates": remark_candidates,
        "needs_semantic_review": has_remark,
    }
    add_issue(
        issues,
        RULE_ID,
        "结果合理性",
        "高",
        f"rf.{table}.remark",
        (
            "RF表单存在异常/漏填/错配，备注说明不充分，需语义判断；"
            f"备注内容：{remark_content}。"
            if has_remark
            else "RF表单存在异常/漏填/错配且未填写有效备注: "
        )
        + abnormal_message,
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _issue_table(issue: Issue, form_by_table: dict[str, dict[str, Any]]) -> str | None:
    field = str(issue.field or "")
    message = str(issue.message or "")
    evidence = str(issue.evidence or "")
    haystack = f"{field} {message} {evidence}"
    for table in form_by_table:
        if re.search(rf"(^|[.\s\"']){re.escape(table)}($|[.\s\"'])", haystack):
            return table
    return None


def _issue_evidence(issue: Issue) -> dict[str, Any]:
    try:
        parsed = json.loads(issue.evidence or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_meaningful_remark(form: dict[str, Any]) -> bool:
    for _field, value in _remark_candidates(form).items():
        text = str(value or "").strip()
        if text and text not in LOW_VALUE_REMARKS:
            return True
    return False


def _remark_candidates(form: dict[str, Any]) -> dict[str, Any]:
    candidates = {}
    for field, value in form.items():
        upper = str(field).upper()
        if upper == "PROCESSTYPE":
            continue
        if any(pattern in upper for pattern in REMARK_FIELD_PATTERNS):
            candidates[field] = value
    return candidates


def _remark_content_text(remark_candidates: dict[str, Any]) -> str:
    """Render non-empty remark candidates for human-readable issue messages."""

    parts = []
    for field, value in remark_candidates.items():
        text = str(value or "").strip()
        if not text or field.upper() in {"PROCESSTYPE"}:
            continue
        parts.append(f"{field}={text}")
    return "；".join(parts) or "<未识别到有效备注内容>"


def _is_abnormal_result_field(field: Any, value: Any) -> bool:
    if value is None:
        return False
    upper = str(field).upper()
    text = str(value).strip()
    if not text or text in LOW_VALUE_REMARKS:
        return False
    if upper == "XZJG":
        return text in {"0", "0.0"} or any(token in text for token in ABNORMAL_TEXT_TOKENS)
    if not any(pattern in upper for pattern in RESULT_FIELD_PATTERNS):
        return False
    if any(token in text for token in NORMAL_TEXT_TOKENS):
        return False
    return any(token in text for token in ABNORMAL_TEXT_TOKENS)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _is_unclear_no_device_value(value: str) -> bool:
    if value in {"", "/", "-", "无", "无该项指标", "不适用"}:
        return True
    return False
