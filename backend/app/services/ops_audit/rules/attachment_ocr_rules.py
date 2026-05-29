"""OCR-backed attachment content rules for operations work order audits."""

from __future__ import annotations

import json
import os
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue
from app.services.ops_audit.semantic.attachment_classifier import classify_attachment_metadata
from app.services.ops_audit.semantic.ocr_adapter import extract_attachment_json
from app.services.ops_audit.semantic.reviewer import check_photo_watermark, review_attachment_quality
from app.services.ops_audit.config import load_attachment_requirements


ATTACHMENT_PROFILE = load_attachment_requirements()
FLOW_VISUAL_RULE_TABLES = {"RF_TW_PmFlowCalibrate", "RF_M_GASEOUSFLOWCHECK", "RF_Q_GaseousFlowCheck"}
OCR_RULE_IDS = {
    "ATTACHMENT_CERT_INCOMPLETE",
    "ATTACHMENT_WATERMARK_INCOMPLETE",
    "REPORT_TOC_NOT_UPDATED",
    "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
    "ATTACHMENT_GAS_FLOW_DISPLAY_VALUE_MISMATCH",
}


def check_attachment_ocr_quality(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Run bounded flow-photo vision checks for attachment contents.

    Certificate, report, and watermark OCR checks are intentionally not
    scheduled here. The current production path only validates flow readings
    recognized from calibration/check photos.
    """

    tasks = build_flow_visual_tasks(order, forms, attachments, wo_commonfiles)
    for task in tasks:
        run_flow_visual_task(task, issues)


def build_flow_visual_tasks(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build flow-photo vision tasks without calling the vision model."""

    if not _has_flow_visual_forms(forms):
        return []

    items = _attachment_items(attachments, wo_commonfiles)
    if not items:
        return []

    max_items = max(1, int(os.getenv("OPS_AUDIT_OCR_MAX_ATTACHMENTS_PER_ORDER", "3") or "3"))
    flow_items = [
        item
        for item in _prioritized_items(items)
        if "photo" in set(item.get("types", [])) and _is_flow_visual_candidate(item)
    ]
    tasks = []
    for item in flow_items[:max_items]:
        if item.get("source_path"):
            tasks.append({"order": order, "forms": forms, "item": item})
    return tasks


def run_flow_visual_task(task: dict[str, Any], issues: list[Issue]) -> None:
    """Run one pre-filtered flow-photo vision task."""

    _check_flow_visual_values(task["order"], task["forms"], task["item"], issues)


def _check_certificate(order: dict[str, Any], item: dict[str, Any], issues: list[Issue]) -> None:
    review = review_attachment_quality(str(item["source_path"]), "cert")
    if review.get("ocr_result", {}).get("status") != "success":
        return
    if review.get("is_complete", True):
        return
    _add_attachment_issue(
        issues,
        "ATTACHMENT_CERT_INCOMPLETE",
        "证书只附封面或不完整",
        order,
        item,
        review,
    )


def _check_report(order: dict[str, Any], item: dict[str, Any], issues: list[Issue]) -> None:
    review = review_attachment_quality(str(item["source_path"]), "report")
    if review.get("ocr_result", {}).get("status") != "success":
        return
    issue_text = " ".join(str(issue) for issue in review.get("issues", []))
    if review.get("is_complete", True) or "目录" not in issue_text:
        return
    _add_attachment_issue(
        issues,
        "REPORT_TOC_NOT_UPDATED",
        "报告目录未更新",
        order,
        item,
        review,
    )


def _check_photo(order: dict[str, Any], item: dict[str, Any], issues: list[Issue]) -> None:
    review = check_photo_watermark(str(item["source_path"]))
    if review.get("ocr_result", {}).get("status") != "success":
        return
    if review.get("has_date"):
        return
    _add_attachment_issue(
        issues,
        "ATTACHMENT_WATERMARK_INCOMPLETE",
        "照片水印时间缺日期",
        order,
        item,
        review,
    )


def _check_flow_visual_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    item: dict[str, Any],
    issues: list[Issue],
) -> None:
    for table, form in forms:
        if form.get("_query_error"):
            continue
        if table == "RF_TW_PmFlowCalibrate":
            _check_pm_flow_calibration_visual(order, table, form, item, issues)
        elif table in {"RF_M_GASEOUSFLOWCHECK", "RF_Q_GaseousFlowCheck"}:
            _check_gas_flow_display_visual(order, table, form, item, issues)


def _check_pm_flow_calibration_visual(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    item: dict[str, Any],
    issues: list[Issue],
) -> None:
    result = extract_attachment_json(
        str(item["source_path"]),
        provider="flow_visual",
        task="pm_flow_calibration_value",
        prompt=(
            "请判断图片是否为颗粒物流量校准前/校准后相关照片，并只读取照片中明确属于流量读数的数值。"
            "不要读取日期水印、时间、站点编号、设备序列号、证书编号、量程、百分比误差或表格编号。"
            "如果图片同时包含校准前和校准后，请分别返回；如果只能看出一个读数，请按图片文字或上下文放到对应字段。"
            "只输出JSON，格式："
            "{\"is_flow_calibration_photo\": true/false, "
            "\"before_flow\": 数值或null, \"after_flow\": 数值或null, "
            "\"unit\": \"L/min或ml/min或空\", "
            "\"visible_flow_values\": [{\"label\":\"原图文字标签\", \"value\":数值, \"unit\":\"单位\"}], "
            "\"confidence\": 0到1, \"reason\":\"简短依据\"}"
        ),
    )
    if result.get("status") != "success":
        return
    data = result.get("data") or {}
    if not data.get("is_flow_calibration_photo"):
        return

    comparisons = []
    comparisons.extend(_compare_visual_value("before_flow", data.get("before_flow"), form, ["Prev_A", "Prev_B"]))
    comparisons.extend(_compare_visual_value("after_flow", data.get("after_flow"), form, ["Next_A", "Next_B"]))
    violations = [item for item in comparisons if item.get("status") == "mismatch"]
    if not violations:
        return

    _add_visual_value_issue(
        issues,
        "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
        "流量校准前后照片读数与表单填写值不一致",
        order,
        table,
        item,
        result,
        comparisons,
    )


def _check_gas_flow_display_visual(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    item: dict[str, Any],
    issues: list[Issue],
) -> None:
    result = extract_attachment_json(
        str(item["source_path"]),
        provider="flow_visual",
        task=f"gas_flow_display_value_{table}",
        prompt=(
            "请判断图片是否为气体流量检查的仪器面板/流量显示照片，并只读取明确属于流量的读数。"
            "display_values 只能填写流量值，常见标签包括 FLOW、SAMPLE FLOW、SAMP FL、FLOW CHECK、采样流量、流量显示值。"
            "严禁把污染物浓度读数填入 display_values；凡是带 PPM、PPB、ug/m3、mg/m3 或标注为浓度/CONC 的数值都不是流量，应忽略。"
            "不要读取日期水印、时间、站点编号、设备序列号、证书编号、量程、百分比误差或外接流量计测量值。"
            "如能从图片文字或上下文区分污染物对应的流量，请按 SO2、NO2、CO、O3 返回；不能区分则只放入 visible_flow_values，display_values 对应项保持 null。"
            "只输出JSON，格式："
            "{\"is_gas_flow_panel_photo\": true/false, "
            "\"display_values\": {\"SO2\": 数值或null, \"NO2\": 数值或null, \"CO\": 数值或null, \"O3\": 数值或null}, "
            "\"unit\": \"L/min或ml/min或空\", "
            "\"visible_flow_values\": [{\"label\":\"原图文字标签\", \"value\":数值, \"unit\":\"单位\"}], "
            "\"confidence\": 0到1, \"reason\":\"简短依据\"}"
        ),
    )
    if result.get("status") != "success":
        return
    data = result.get("data") or {}
    if not data.get("is_gas_flow_panel_photo"):
        return

    display_values = data.get("display_values") if isinstance(data.get("display_values"), dict) else {}
    comparisons = []
    if table == "RF_M_GASEOUSFLOWCHECK":
        for gas in ("SO2", "NO2", "CO", "O3"):
            comparisons.extend(_compare_visual_value(gas, display_values.get(gas), form, [f"DISPLAYVALUE{gas}"]))
    elif table == "RF_Q_GaseousFlowCheck":
        for point in ("85", "60", "35", "80", "50", "20"):
            comparisons.extend(_compare_visual_value(f"DF_{point}", display_values.get(point), form, [f"DF_Valuve_{point}"]))

    violations = [item for item in comparisons if item.get("status") == "mismatch"]
    if not violations:
        return

    _add_visual_value_issue(
        issues,
        "ATTACHMENT_GAS_FLOW_DISPLAY_VALUE_MISMATCH",
        "气体流量检查照片仪器显示值与表单填写值不一致",
        order,
        table,
        item,
        result,
        comparisons,
    )


def _compare_visual_value(
    label: str,
    visual_value: Any,
    form: dict[str, Any],
    candidate_fields: list[str],
) -> list[dict[str, Any]]:
    visual_number = _parse_number(visual_value)
    if visual_number is None:
        return []

    comparisons = []
    for field in candidate_fields:
        form_number = _parse_number(form.get(field))
        if form_number is None:
            continue
        matched = _numbers_close(visual_number, form_number)
        comparisons.append(
            {
                "label": label,
                "field": field,
                "visual_value": visual_number,
                "form_value": form_number,
                "difference": round(abs(visual_number - form_number), 6),
                "status": "matched" if matched else "mismatch",
            }
        )
    if any(item["status"] == "matched" for item in comparisons):
        return [item for item in comparisons if item["status"] == "matched"]
    return comparisons


def _numbers_close(left: float, right: float) -> bool:
    tolerance = float(os.getenv("OPS_AUDIT_FLOW_VISUAL_VALUE_TOLERANCE", "0.05") or "0.05")
    relative_tolerance = float(os.getenv("OPS_AUDIT_FLOW_VISUAL_VALUE_REL_TOLERANCE", "0.01") or "0.01")
    return abs(left - right) <= max(tolerance, abs(right) * relative_tolerance)


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    import re

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _add_visual_value_issue(
    issues: list[Issue],
    rule_id: str,
    message: str,
    order: dict[str, Any],
    rf_table: str,
    item: dict[str, Any],
    result: dict[str, Any],
    comparisons: list[dict[str, Any]],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": rf_table,
        "filename": item.get("filename"),
        "source": item.get("source_path"),
        "types": item.get("types", []),
        "vision_status": result.get("status"),
        "vision_confidence": (result.get("data") or {}).get("confidence"),
        "vision_reason": (result.get("data") or {}).get("reason"),
        "vision_data": result.get("data"),
        "comparisons": comparisons,
    }
    first = next((item for item in comparisons if item.get("status") == "mismatch"), comparisons[0])
    add_issue(
        issues,
        rule_id,
        "附件读数一致性",
        "高",
        f"attachment.vision.{rule_id}.{rf_table}",
        f"{message}: {first.get('label')} 图片值 {first.get('visual_value')} / 表单 {first.get('field')}={first.get('form_value')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_attachment_issue(
    issues: list[Issue],
    rule_id: str,
    message: str,
    order: dict[str, Any],
    item: dict[str, Any],
    review: dict[str, Any],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "filename": item.get("filename"),
        "source": item.get("source_path"),
        "types": item.get("types", []),
        "ocr_status": review.get("ocr_result", {}).get("status"),
        "ocr_confidence": review.get("ocr_result", {}).get("confidence"),
        "review_confidence": review.get("confidence"),
        "issues": review.get("issues") or review.get("suggestion"),
        "ocr_text_excerpt": str(review.get("ocr_result", {}).get("text") or "")[:500],
    }
    add_issue(
        issues,
        rule_id,
        "附件内容质量",
        "中",
        f"attachment.ocr.{rule_id}",
        f"{message}: {item.get('filename') or item.get('source_path')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _attachment_items(attachments: list[dict[str, Any]], wo_commonfiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in list(attachments) + list(wo_commonfiles):
        filename = _first_present(record, _name_fields())
        source_path = _first_present(
            record,
            ["file_url", "fileUrl", "FILEURL", "FILE_URL", "FILEPATH", "filepath", "URL", "url", "PATH", "path"],
        )
        descriptor = " ".join(str(value) for value in [filename, source_path, record.get("REMARK"), record.get("remark")] if value)
        classified = classify_attachment_metadata(
            descriptor,
            filename=str(filename or ""),
            global_keywords=ATTACHMENT_PROFILE.get("global_keywords", {}),
            photo_extensions=ATTACHMENT_PROFILE.get("photo_extensions", []),
        )
        items.append(
            {
                "filename": filename,
                "source_path": source_path,
                "descriptor": descriptor,
                "types": classified.get("types", []),
            }
        )
    return items


def _prioritized_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"certificate": 0, "report": 1, "photo": 2, "curve": 3}

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        types = set(item.get("types", []))
        best = min([priority.get(item_type, 9) for item_type in types] or [9])
        return (best, str(item.get("filename") or item.get("source_path") or ""))

    return sorted(items, key=sort_key)


def _is_flow_visual_candidate(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("filename"),
            item.get("source_path"),
            item.get("descriptor"),
        )
    )
    return any(keyword in text for keyword in ("流量", "实测", "显示", "测量"))


def _has_flow_visual_forms(forms: list[tuple[str, dict[str, Any]]]) -> bool:
    return any(table in FLOW_VISUAL_RULE_TABLES and not form.get("_query_error") for table, form in forms)


def _name_fields() -> list[str]:
    return [
        "FILENAME",
        "filename",
        "FileName",
        "FILE_NAME",
        "NAME",
        "name",
        "ORIGINALFILENAME",
        "originalfilename",
        "COMMONFILENAME",
        "commonfilename",
        "TITLE",
        "title",
    ]


def _first_present(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return value
    return None
