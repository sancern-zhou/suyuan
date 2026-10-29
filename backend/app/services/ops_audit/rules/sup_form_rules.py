"""组分站表单档案驱动规则（sup_rf_common 按 ruleitemtag 建档，审核二期）。

判定逻辑全部来自 configs/sup_form_profiles.yaml 档案：
- SUP_FORMULA_RECALC：档案标注公式列复算（如 PANs 设定误差）；
- SUP_RANGE_OUT_OF_SPEC：档案标注阈值列或计算表达式（min/max 区间），
  超范围有备注降级人工复核，无备注判失败；
- SUP_REQUIRED_VALUE_EMPTY：档案标注必填数值列，"/"+说明备注豁免；
- SUP_DATE_REASONABLENESS：日期对区间/覆盖检查与单日期越界检查（not_future/not_past）；
- SUP_ABNORMAL_NO_REMARK：档案声明异常取值（如"异常/不合格"），命中且无备注即问题；
- SUP_CYCLE_TIMELINESS：周期任务表单侧口径（填写滞后、质控数据文件过期）。

规则仅处理带 RULEITEMTAG 的组分站表单（含 sup_rf_common 与专用分表），主网 RF 分表不受影响。
"""

from __future__ import annotations

import ast
import json
import math
import re
from datetime import date, datetime
from typing import Any

from app.services.ops_audit.config import load_sup_form_profiles
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

FORMULA_RULE_ID = "SUP_FORMULA_RECALC"
RANGE_RULE_ID = "SUP_RANGE_OUT_OF_SPEC"
REQUIRED_RULE_ID = "SUP_REQUIRED_VALUE_EMPTY"
DATE_RULE_ID = "SUP_DATE_REASONABLENESS"
TIMELINESS_RULE_ID = "SUP_CYCLE_TIMELINESS"
ABNORMAL_RULE_ID = "SUP_ABNORMAL_NO_REMARK"

# 与 attachment_rules.ATTACHMENT_PROFILE 相同的模块级加载模式；测试可通过
# reload_sup_form_profiles() 刷新。
SUP_FORM_PROFILES = load_sup_form_profiles()


def reload_sup_form_profiles() -> dict[str, Any]:
    global SUP_FORM_PROFILES
    SUP_FORM_PROFILES = load_sup_form_profiles()
    return SUP_FORM_PROFILES

SKIP_TOKENS = {"", "/", "-", "—", "nan", "none", "null", "无", "不适用", "无此项", "未填写"}

_DATE_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日",
)

_FILENAME_DATE_PATTERNS = (
    # 日期区间（如 2026-10-12至2026-10-18）：数据文件覆盖周期以区间末为准。
    re.compile(
        r"(?P<y>20\d{2})\s*[年./-]\s*(?P<m>\d{1,2})\s*[月./-]\s*(?P<d>\d{1,2})\s*日?"
        r"\s*[至~～\-—]{1,2}\s*"
        r"(?:(?P<y2>20\d{2})\s*[年./-]?)?\s*(?P<m2>\d{1,2})\s*[月./-]\s*(?P<d2>\d{1,2})\s*日?"
    ),
    re.compile(r"(?P<y>20\d{2})\s*[年./-]\s*(?P<m>\d{1,2})\s*[月./-]\s*(?P<d>\d{1,2})\s*日?"),
    re.compile(r"(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})"),
    re.compile(r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?"),
)

_DATA_FILE_EXTENSIONS = (".xls", ".xlsx", ".csv", ".doc", ".docx", ".pdf")

_FORM_REMARK_FIELDS = ("REMARK", "REMARKS", "remark", "SUBMITREMARK")


def form_item_tag(form: dict[str, Any]) -> str | None:
    """Return the ruleitemtag (form type code) of a sup_rf_common form row."""

    for key in ("RULEITEMTAG", "ruleitemtag", "RuleItemTag"):
        value = form.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def check_sup_form_rules(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
    wo_commonfiles: list[dict[str, Any]] | None = None,
    sup_taskitems: list[dict[str, Any]] | None = None,
) -> None:
    """Run profile-driven checks over sup forms of one work order."""

    catalog = SUP_FORM_PROFILES.get("form_profiles") or {}
    if not catalog:
        return
    common_files = wo_commonfiles or []
    task_items = sup_taskitems or []
    for table, form in forms:
        if form.get("_query_error"):
            continue
        tag = form_item_tag(form)
        if not tag:
            continue
        profile = catalog.get(tag)
        if not profile or profile.get("enabled") is False:
            continue
        check_formula_columns(order, table, tag, form, profile, issues)
        check_range_columns(order, table, tag, form, profile, issues)
        check_required_value_columns(order, table, tag, form, profile, issues)
        check_date_columns(order, table, tag, form, profile, issues)
        check_abnormal_columns(order, table, tag, form, profile, issues)
        check_cycle_timeliness(order, table, tag, form, profile, common_files, task_items, issues)


# ---------------------------------------------------------------------------
# 公式复算（SUP_FORMULA_RECALC）
# ---------------------------------------------------------------------------


def check_formula_columns(
    order: dict[str, Any],
    table: str,
    tag: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    violations = []
    for spec in profile.get("formula_columns") or []:
        target = str(spec.get("target") or "")
        actual = parse_form_number(form.get(target))
        if actual is None:
            continue
        expected = evaluate_formula(
            form,
            str(spec.get("expression") or ""),
            spec.get("inputs") or [],
            skip_if_inputs_zero=bool(spec.get("skip_if_inputs_zero")),
        )
        if expected is None:
            continue
        tolerance = float(spec.get("tolerance") or 0.5)
        if tolerance_mode_is_relative(spec):
            allowed = max(tolerance * abs(expected), 1e-9)
        else:
            allowed = tolerance
        if abs(actual - expected) <= allowed:
            continue
        violations.append(
            {
                "column": target,
                "label": spec.get("label") or target,
                "filled": round(actual, 6),
                "recalculated": round(expected, 6),
                "delta": round(actual - expected, 6),
                "tolerance": tolerance,
                "expression": spec.get("expression"),
                "inputs": {name: form.get(name) for name in spec.get("inputs") or [] if name in form},
            }
        )
    if not violations:
        return
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": tag,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        FORMULA_RULE_ID,
        "数值逻辑",
        "高",
        f"sup_rf_common.{tag}.{first['column']}",
        (
            f"{profile.get('display_name') or tag}：{first['label']}填写值 "
            f"{first['filled']} 与复算值 {first['recalculated']} 不一致"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def evaluate_formula(
    form: dict[str, Any],
    expression: str,
    input_columns: list[str],
    skip_if_inputs_zero: bool = False,
) -> float | None:
    """Safely evaluate a profile formula over numeric form columns."""

    if not expression:
        return None
    values: dict[str, float] = {}
    for column in input_columns:
        value = parse_form_number(form.get(column))
        if value is None:
            return None
        values[column] = value
    if skip_if_inputs_zero and values and all(item == 0 for item in values.values()):
        # 0 填充占位行（如未执行校准的"校准后"列），不做复算。
        return None
    try:
        template = expression.format(**values)
    except (KeyError, IndexError, ValueError):
        return None
    try:
        tree = ast.parse(template, mode="eval")
    except (SyntaxError, ValueError):
        return None
    if not _ast_nodes_allowed(tree):
        return None
    try:
        result = compile(tree, "<sup_formula>", "eval")
        return float(eval(result, {"__builtins__": {}}, {}))  # noqa: S307 (AST 白名单校验后)
    except (ArithmeticError, ValueError, TypeError):
        return None


def _ast_nodes_allowed(node: ast.AST) -> bool:
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub,
               ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd)
    for child in ast.walk(node):
        if not isinstance(child, allowed):
            return False
        if isinstance(child, ast.Constant) and not isinstance(child.value, (int, float)):
            return False
    return True


def tolerance_mode_is_relative(spec: dict[str, Any]) -> bool:
    return str(spec.get("tolerance_mode") or "absolute").strip().lower() == "relative"


# ---------------------------------------------------------------------------
# 阈值/范围（SUP_RANGE_OUT_OF_SPEC）
# ---------------------------------------------------------------------------


def check_range_columns(
    order: dict[str, Any],
    table: str,
    tag: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    violations = []
    for spec in profile.get("range_columns") or []:
        expression = str(spec.get("expression") or "")
        if expression:
            # 计算型范围：对表达式结果判区间（如 示值误差=校准前读数-标准读数）；
            # 结果按 6 位小数取整，消除浮点噪声导致的贴边误判。
            column = str(spec.get("label") or "expression")
            value = evaluate_formula(form, expression, spec.get("inputs") or [])
            if value is not None:
                value = round(value, 6)
            raw = value
        else:
            column = str(spec.get("column") or "")
            raw = form.get(column)
            value = parse_form_number(raw)
        if value is None:
            continue
        min_value = spec.get("min")
        max_value = spec.get("max")
        if min_value is not None and value < float(min_value):
            pass
        elif max_value is not None and value > float(max_value):
            pass
        else:
            continue
        remark = column_remark_text(form, spec.get("remark_column"))
        violations.append(
            {
                "column": column,
                "label": spec.get("label") or column,
                "value": round(value, 6),
                "raw_value": str(raw),
                "min": min_value,
                "max": max_value,
                "unit": spec.get("unit") or "",
                "remark": remark,
                "with_remark": bool(remark),
            }
        )
    if not violations:
        return
    with_remark = [item for item in violations if item["with_remark"]]
    without_remark = [item for item in violations if not item["with_remark"]]
    display_name = profile.get("display_name") or tag
    if without_remark:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "ruleitemtag": tag,
            "with_remark": False,
            "violations": without_remark[:20],
        }
        first = without_remark[0]
        add_issue(
            issues,
            RANGE_RULE_ID,
            "数值逻辑",
            "高",
            f"sup_rf_common.{tag}.{first['column']}",
            (
                f"{display_name}：{first['label']}填写值 {first['raw_value']} 超出标准范围 "
                f"{_range_text(first)}，且无异常情况备注"
            ),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )
    if with_remark:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "ruleitemtag": tag,
            "with_remark": True,
            "needs_semantic_review": True,
            "review_basis": "超范围但已填写备注，需人工复核备注是否说明合理原因及处置结果。",
            "violations": with_remark[:20],
        }
        first = with_remark[0]
        add_issue(
            issues,
            RANGE_RULE_ID,
            "数值逻辑",
            "中",
            f"sup_rf_common.{tag}.{first['column']}",
            (
                f"{display_name}：{first['label']}填写值 {first['raw_value']} 超出标准范围 "
                f"{_range_text(first)}，已备注“{first['remark'][:30]}”，需人工复核"
            ),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _range_text(item: dict[str, Any]) -> str:
    min_value = item.get("min")
    max_value = item.get("max")
    unit = str(item.get("unit") or "").strip()
    return f"{min_value}~{max_value}{unit}".strip()


# ---------------------------------------------------------------------------
# 必填数值（SUP_REQUIRED_VALUE_EMPTY）
# ---------------------------------------------------------------------------


def check_required_value_columns(
    order: dict[str, Any],
    table: str,
    tag: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    blank_items = []
    placeholder_items = []
    for spec in profile.get("required_value_columns") or []:
        column = str(spec.get("column") or "")
        if column not in form:
            continue
        raw = form.get(column)
        text = "" if raw is None else str(raw).strip()
        remark = column_remark_text(form, spec.get("remark_column"))
        if text == "":
            blank_items.append({"column": column, "label": spec.get("label") or column, "raw": raw})
            continue
        if text in {"/", "-", "—"}:
            item = {
                "column": column,
                "label": spec.get("label") or column,
                "raw": text,
                "remark": remark,
            }
            if remark:
                continue
            placeholder_items.append(item)
    display_name = profile.get("display_name") or tag
    if blank_items:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "ruleitemtag": tag,
            "kind": "blank",
            "items": blank_items[:20],
        }
        first = blank_items[0]
        add_issue(
            issues,
            REQUIRED_RULE_ID,
            "完整性",
            "高",
            f"sup_rf_common.{tag}.{first['column']}",
            f"{display_name}：必填数值列 {first['label']} 为空",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )
    if placeholder_items:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "ruleitemtag": tag,
            "kind": "placeholder_without_remark",
            "items": placeholder_items[:20],
        }
        first = placeholder_items[0]
        add_issue(
            issues,
            REQUIRED_RULE_ID,
            "完整性",
            "中",
            f"sup_rf_common.{tag}.{first['column']}",
            (
                f"{display_name}：必填数值列 {first['label']} 填“{first['raw']}”但无说明备注，"
                "如属合理免填请补充说明"
            ),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


# ---------------------------------------------------------------------------
# 日期合理性（SUP_DATE_REASONABLENESS）
# ---------------------------------------------------------------------------


def check_date_columns(
    order: dict[str, Any],
    table: str,
    tag: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    violations = []
    check_date = parse_form_date(form.get("CHECKDATE") or form.get("checkdate"))
    for spec in profile.get("date_columns") or []:
        label = spec.get("label") or "日期"
        start = parse_form_date(form.get(str(spec.get("start"))))
        end = parse_form_date(form.get(str(spec.get("end"))))
        if start is None and end is None:
            continue
        if start is not None and end is not None:
            if start == end:
                # 同日占位（常见于未真实维护日期对的表单），不判区间。
                continue
            if end < start:
                violations.append(
                    {"kind": "end_before_start", "label": label, "start": str(start), "end": str(end)}
                )
                continue
            valid_intervals = [int(item) for item in spec.get("valid_intervals_days") or []]
            if valid_intervals:
                tolerance = int(spec.get("interval_tolerance_days") or 0)
                actual_days = (end - start).days
                if not any(abs(actual_days - expected) <= tolerance for expected in valid_intervals):
                    violations.append(
                        {
                            "kind": "interval_not_standard",
                            "label": label,
                            "start": str(start),
                            "end": str(end),
                            "actual_days": actual_days,
                            "valid_intervals_days": valid_intervals,
                            "tolerance_days": tolerance,
                        }
                    )
                    continue
            if spec.get("must_cover_checkdate") and check_date is not None and end < check_date:
                violations.append(
                    {
                        "kind": "expired_before_checkdate",
                        "label": label,
                        "start": str(start),
                        "end": str(end),
                        "checkdate": str(check_date),
                    }
                )
            continue
        single_rule = str(spec.get("single_date_rule") or "").strip()
        single_value = end if end is not None else start
        if single_rule == "not_future" and check_date is not None and single_value > check_date:
            violations.append(
                {
                    "kind": "date_after_checkdate",
                    "label": label,
                    "date": str(single_value),
                    "checkdate": str(check_date),
                }
            )
        if single_rule == "not_past" and check_date is not None and single_value < check_date:
            violations.append(
                {
                    "kind": "date_before_checkdate",
                    "label": label,
                    "date": str(single_value),
                    "checkdate": str(check_date),
                }
            )
    if not violations:
        return
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": tag,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        DATE_RULE_ID,
        "时间合理性",
        "高",
        f"sup_rf_common.{tag}.{first.get('label', 'date')}",
        f"{profile.get('display_name') or tag}：{first['label']}日期异常（{_date_violation_text(first)}）",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def check_abnormal_columns(
    order: dict[str, Any],
    table: str,
    tag: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    """异常勾选未备注（SUP_ABNORMAL_NO_REMARK）：档案声明异常取值，命中且无备注即问题。"""

    items = []
    for spec in profile.get("abnormal_columns") or []:
        column = str(spec.get("column") or "")
        if column not in form:
            continue
        value = "" if form.get(column) is None else str(form.get(column)).strip()
        abnormal_values = {str(item).strip() for item in spec.get("values") or []}
        if value not in abnormal_values:
            continue
        if column_remark_text(form, spec.get("remark_column")):
            continue
        items.append({"column": column, "label": spec.get("label") or column, "value": value})
    if not items:
        return
    display_name = profile.get("display_name") or tag
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": tag,
        "items": items[:20],
    }
    first = items[0]
    add_issue(
        issues,
        ABNORMAL_RULE_ID,
        "异常说明问题",
        "中",
        f"sup_rf_common.{tag}.{first['column']}",
        (
            f"{display_name}：{first['label']} 填“{first['value']}”，未填写异常情况说明，"
            "需补充备注并上传相关照片"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _date_violation_text(item: dict[str, Any]) -> str:
    kind = item.get("kind")
    if kind == "end_before_start":
        return f"有效期 {item['end']} 早于起始日期 {item['start']}"
    if kind == "interval_not_standard":
        return (
            f"{item['start']}→{item['end']} 间隔 {item['actual_days']} 天，"
            f"非标准周期 {item['valid_intervals_days']} 天（容差 {item['tolerance_days']} 天）"
        )
    if kind == "expired_before_checkdate":
        return f"有效期 {item['end']} 已早于检查日期 {item['checkdate']}"
    if kind == "date_after_checkdate":
        return f"日期 {item['date']} 晚于检查日期 {item['checkdate']}"
    if kind == "date_before_checkdate":
        return f"日期 {item['date']} 早于检查日期 {item['checkdate']}"
    return str(item)


# ---------------------------------------------------------------------------
# 周期及时性（SUP_CYCLE_TIMELINESS，表单侧口径）
# ---------------------------------------------------------------------------


def check_cycle_timeliness(
    order: dict[str, Any],
    table: str,
    tag: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    wo_commonfiles: list[dict[str, Any]],
    sup_taskitems: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    violations = []
    check_date = parse_form_date(form.get("CHECKDATE") or form.get("checkdate"))
    create_time = parse_form_date(order.get("CREATETIME") or order.get("createtime"))
    task_item = _matching_task_item(sup_taskitems, tag, form)
    grace_days = _plan_late_grace_days()
    if task_item is not None:
        # 计划口径（阶段 2.4）：质控计划任务项给出周期计划完成日，表单创建
        # 晚于计划完成日超过宽限天数即填写不及时。
        plan_finish = parse_form_date(task_item.get("PLANFINISHTIME"))
        if plan_finish is not None and create_time is not None:
            late_days = (_as_date(create_time) - _as_date(plan_finish)).days
            if late_days > grace_days:
                violations.append(
                    {
                        "kind": "plan_overdue",
                        "label": "填写不及时（计划口径）",
                        "planfinishtime": str(_as_date(plan_finish)),
                        "create_time": str(create_time),
                        "late_days": late_days,
                        "grace_days": grace_days,
                    }
                )
    else:
        # 回退口径：无质控计划任务项时按检查日期滞后判定。
        max_fill_lag = profile.get("max_fill_lag_days")
        if max_fill_lag is not None and check_date is not None and create_time is not None:
            lag_days = (_as_date(create_time) - _as_date(check_date)).days
            if lag_days > int(max_fill_lag):
                violations.append(
                    {
                        "kind": "fill_lag",
                        "label": "填写滞后",
                        "checkdate": str(check_date),
                        "create_time": str(create_time),
                        "lag_days": lag_days,
                        "max_fill_lag_days": int(max_fill_lag),
                    }
                )
    stale_lag = profile.get("stale_data_max_lag_days")
    if stale_lag is not None and check_date is not None:
        for record in wo_commonfiles:
            if not attachment_matches_tag(record, tag):
                continue
            filename = attachment_filename(record)
            if not filename.lower().endswith(_DATA_FILE_EXTENSIONS):
                continue
            data_date = extract_date_from_filename(filename, default_year=check_date.year)
            if data_date is None:
                continue
            stale_days = (_as_date(check_date) - data_date).days
            if stale_days > int(stale_lag):
                violations.append(
                    {
                        "kind": "stale_data_file",
                        "label": "质控数据文件过期",
                        "filename": filename,
                        "data_date": str(data_date),
                        "checkdate": str(check_date),
                        "stale_days": stale_days,
                        "stale_data_max_lag_days": int(stale_lag),
                    }
                )
    if not violations:
        return
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": tag,
        "cycle": profile.get("cycle"),
        "口径": (
            "质控计划口径（sup_mtc_taskitem.planfinishtime）"
            if task_item is not None
            else "质控计划数据源未接入前采用表单侧口径（填写滞后/数据文件过期）"
        ),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        TIMELINESS_RULE_ID,
        "时间合理性",
        "高",
        f"sup_rf_common.{tag}.timeliness",
        f"{profile.get('display_name') or tag}：{_timeliness_violation_text(first)}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _matching_task_item(
    sup_taskitems: list[dict[str, Any]], tag: str, form: dict[str, Any]
) -> dict[str, Any] | None:
    """匹配同工单+表单类型（+监测项目）的质控计划任务项。"""

    pollutant = str(form.get("POLLUTANTTYPE") or form.get("pollutanttype") or "").strip().lower()
    tag_lower = tag.lower()
    fallback = None
    for item in sup_taskitems:
        if str(item.get("RULEITEMTAG") or item.get("ruleitemtag") or "").strip().lower() != tag_lower:
            continue
        item_pollutant = str(item.get("POLLUTANTTYPE") or item.get("pollutanttype") or "").strip().lower()
        if pollutant and item_pollutant and item_pollutant != pollutant:
            continue
        if item_pollutant == pollutant:
            return item
        fallback = fallback or item
    return fallback


def _plan_late_grace_days() -> int:
    defaults = SUP_FORM_PROFILES.get("defaults") or {}
    timeliness = defaults.get("timeliness") or {}
    try:
        return max(0, int(timeliness.get("plan_late_grace_days", 5)))
    except (TypeError, ValueError):
        return 5


def _timeliness_violation_text(item: dict[str, Any]) -> str:
    if item.get("kind") == "plan_overdue":
        return (
            f"表单创建 {item['create_time']} 晚于质控计划完成日 {item['planfinishtime']} "
            f"{item['late_days']} 天，超出宽限 {item['grace_days']} 天"
        )
    if item.get("kind") == "fill_lag":
        return (
            f"检查日期 {item['checkdate']} 距工单创建 {item['create_time']} 滞后 "
            f"{item['lag_days']} 天，超出周期允许 {item['max_fill_lag_days']} 天"
        )
    return (
        f"质控数据文件“{item['filename']}”日期为 {item['data_date']}，"
        f"距检查日期 {item['checkdate']} 已 {item['stale_days']} 天，疑似未按时上传本周数据"
    )


# ---------------------------------------------------------------------------
# 共用解析与工具
# ---------------------------------------------------------------------------


def attachment_matches_tag(record: dict[str, Any], tag: str) -> bool:
    typecode = str(
        record.get("TYPECODE") or record.get("typecode") or record.get("TypeCode") or ""
    ).strip()
    if typecode:
        return typecode.lower() == tag.lower() or typecode.lower().startswith(f"{tag.lower()}_")
    filename = attachment_filename(record)
    return bool(filename) and tag.lower().replace("sup_rf_", "") in filename.lower()


def attachment_filename(record: dict[str, Any]) -> str:
    for key in ("FILENAME", "filename", "FileName", "file_name"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def extract_date_from_filename(filename: str, default_year: int | None = None) -> date | None:
    text = str(filename or "")
    for pattern in _FILENAME_DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = match.groupdict()
        year = int(parts["y"]) if parts.get("y") else (default_year or 0)
        if not year:
            continue
        try:
            first = date(year, int(parts["m"]), int(parts["d"]))
        except ValueError:
            continue
        if parts.get("m2") and parts.get("d2"):
            # 区间日期：取覆盖周期的区间末（区间年缺省沿用首日期年份）。
            end_year = int(parts["y2"]) if parts.get("y2") else year
            try:
                second = date(end_year, int(parts["m2"]), int(parts["d2"]))
            except ValueError:
                return first
            return max(first, second)
        return first
    return None


def column_remark_text(form: dict[str, Any], remark_column: Any) -> str:
    parts = []
    if remark_column:
        for key in (str(remark_column), str(remark_column).lower(), str(remark_column).upper()):
            if key in form:
                value = form.get(key)
                if value is not None and str(value).strip():
                    parts.append(str(value).strip())
                break
    for field in _FORM_REMARK_FIELDS:
        value = form.get(field)
        if value is not None and str(value).strip():
            parts.append(str(value).strip())
    return " ".join(dict.fromkeys(parts))


def parse_form_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if text.lower() in SKIP_TOKENS:
        return None
    text = text.replace("％", "%").replace("，", ",").replace(",", "")
    text = text.replace("＋", "+").replace("－", "-")
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_form_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text or text.lower() in SKIP_TOKENS:
        return None
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _as_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value
