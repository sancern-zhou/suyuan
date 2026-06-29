"""OCR-backed attachment content rules for operations work order audits."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue
from app.services.ops_audit.semantic.attachment_classifier import classify_attachment_metadata
from app.services.ops_audit.semantic.ocr_adapter import extract_attachment_json
from app.services.ops_audit.semantic.reviewer import check_photo_watermark, review_attachment_quality
from app.services.ops_audit.config import load_attachment_requirements


ATTACHMENT_PROFILE = load_attachment_requirements()
PM_MEMBRANE_VISUAL_RULE_TABLES = {"RF_Q_PM10RUNSTATUSCHECK", "RF_Q_PM25RUNSTATUSCHECK"}
PM_TEMP_PRESSURE_VISUAL_RULE_TABLES = {"RF_Q_PMPRESSURE"}
FLOW_VISUAL_RULE_TABLES = {
    "RF_TW_PmFlowCalibrate",
    "RF_M_GASEOUSFLOWCHECK",
    "RF_Q_GaseousFlowCheck",
    *PM_MEMBRANE_VISUAL_RULE_TABLES,
    *PM_TEMP_PRESSURE_VISUAL_RULE_TABLES,
}
OCR_RULE_IDS = {
    "ATTACHMENT_CERT_INCOMPLETE",
    "ATTACHMENT_WATERMARK_INCOMPLETE",
    "REPORT_TOC_NOT_UPDATED",
    "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
    "ATTACHMENT_GAS_FLOW_DISPLAY_VALUE_MISMATCH",
    "ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH",
    "ATTACHMENT_PM_MEMBRANE_VALUE_MISMATCH",
    "ATTACHMENT_PM_TEMP_PRESSURE_VALUE_MISMATCH",
    "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH",
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

    max_items = max(1, int(os.getenv("OPS_AUDIT_OCR_MAX_ATTACHMENTS_PER_ORDER", "12") or "12"))
    prioritized_items = _prioritized_items(items)
    flow_items = [
        item
        for item in prioritized_items
        if "photo" in set(item.get("types", [])) and _is_flow_visual_candidate(item)
    ]
    tasks = []
    for item in flow_items[:max_items]:
        if item.get("source_path"):
            tasks.append({"task_type": "flow_visual", "order": order, "forms": forms, "item": item})
    tasks.extend(_build_reference_flowmeter_certificate_tasks(order, forms, prioritized_items, max_items=max_items))
    return tasks


def run_flow_visual_task(task: dict[str, Any], issues: list[Issue]) -> None:
    """Run one pre-filtered flow-photo vision task."""

    if task.get("task_type") == "reference_flowmeter_certificate":
        _check_reference_flowmeter_certificate(task["order"], task["forms"], task, issues)
        return
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
    for table, form in _forms_for_attachment(forms, item):
        if form.get("_query_error"):
            continue
        if table == "RF_TW_PmFlowCalibrate":
            _check_pm_flow_calibration_visual(order, table, form, item, issues)
        elif table in {"RF_M_GASEOUSFLOWCHECK", "RF_Q_GaseousFlowCheck"}:
            _check_gas_flow_display_visual(order, table, form, item, issues)
        elif table in PM_MEMBRANE_VISUAL_RULE_TABLES:
            _check_pm_membrane_visual(order, table, form, item, issues)
        elif table in PM_TEMP_PRESSURE_VISUAL_RULE_TABLES:
            _check_pm_temp_pressure_visual(order, table, form, item, issues)


def _build_reference_flowmeter_certificate_tasks(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    items: list[dict[str, Any]],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    if not any(table == "RF_M_GASEOUSFLOWCHECK" and not form.get("_query_error") for table, form in forms):
        return []
    monthly_items = [item for item in items if _is_monthly_gaseous_flow_attachment(item)]
    certificate_items = [item for item in monthly_items if _is_reference_flowmeter_certificate_candidate(item)]
    material_items = [item for item in monthly_items if _is_reference_flowmeter_material_candidate(item)]
    if not certificate_items or not material_items:
        return []
    return [
        {
            "task_type": "reference_flowmeter_certificate",
            "order": order,
            "forms": forms,
            "certificate_items": certificate_items[:max_items],
            "material_items": material_items[:max_items],
        }
    ]


def _check_reference_flowmeter_certificate(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    task: dict[str, Any],
    issues: list[Issue],
) -> None:
    if not any(table == "RF_M_GASEOUSFLOWCHECK" and not form.get("_query_error") for table, form in forms):
        return
    material_reviews = [
        _extract_reference_flowmeter_material(item)
        for item in task.get("material_items", [])
        if item.get("source_path")
    ]
    material_reviews = [review for review in material_reviews if review.get("is_reference_flowmeter_material") and review.get("factory_code")]
    if not material_reviews:
        return

    certificate_reviews = [
        _extract_reference_flowmeter_certificate(item)
        for item in task.get("certificate_items", [])
        if item.get("source_path")
    ]
    certificate_reviews = [review for review in certificate_reviews if review.get("is_flowmeter_certificate") and review.get("factory_code")]
    if not certificate_reviews:
        return

    comparisons = []
    for material in material_reviews:
        material_code = _normalize_factory_code(material.get("factory_code"))
        if not material_code:
            continue
        matched_certificate = next(
            (
                certificate
                for certificate in certificate_reviews
                if _normalize_factory_code(certificate.get("factory_code")) == material_code
            ),
            None,
        )
        if not matched_certificate:
            continue
        comparisons.extend(_compare_reference_flowmeter_dates(material, matched_certificate))

    mismatches = [
        comparison
        for comparison in comparisons
        if comparison.get("status") in {"mismatch", "missing_certificate_date", "missing_material_date", "missing_date"}
    ]
    if not mismatches:
        return
    first = mismatches[0]
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": "RF_M_GASEOUSFLOWCHECK",
        "comparisons": comparisons,
    }
    add_issue(
        issues,
        "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH",
        "时间合理性",
        "高",
        f"attachment.reference_flowmeter_certificate.{first.get('field')}",
        "月度气态流量检查参考流量计资料与匹配证书首页校准日期不一致或证书首页未提取到校准日期",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _extract_reference_flowmeter_material(item: dict[str, Any]) -> dict[str, Any]:
    result = extract_attachment_json(
        str(item["source_path"]),
        provider="document",
        task="monthly_reference_flowmeter_material",
        prompt=(
            f"附件文件名：{item.get('filename') or ''}。"
            "请判断该附件是否为月度气态流量检查中的参考流量计资料、流量计资料、标准流量计资料或参考标准器资料。"
            "如是，请提取参考流量计出厂编号/设备编号、上次校准日期、下次校准日期或有效期至。"
            "只输出JSON，格式："
            "{\"is_reference_flowmeter_material\": true/false, "
            "\"factory_code\": \"出厂编号或空\", "
            "\"last_calibration_date\": \"YYYY-MM-DD或空\", "
            "\"next_calibration_date\": \"YYYY-MM-DD或空\", "
            "\"confidence\": 0到1, \"reason\": \"简短依据\"}"
        ),
    )
    data = result.get("data") if result.get("status") == "success" else {}
    return {
        **(data if isinstance(data, dict) else {}),
        "source_filename": item.get("filename"),
        "source_path": item.get("source_path"),
        "ocr_status": result.get("status"),
    }


def _extract_reference_flowmeter_certificate(item: dict[str, Any]) -> dict[str, Any]:
    result = extract_attachment_json(
        str(item["source_path"]),
        provider="document",
        task="reference_flowmeter_certificate",
        prompt=(
            f"附件文件名：{item.get('filename') or ''}。"
            "只识别证书首页，不要识别或推断后续页面。"
            "请判断首页是否为流量计、参考流量计、标准流量计或质量流量计的校准/检定证书。"
            "请只提取首页中明确出现的设备出厂编号/序列号、校准日期或检定日期、有效期至或建议下次校准日期。"
            "如果首页没有对应日期字段，请返回空字符串，不要根据附件文件名、其他页面或常规有效期推断日期。"
            "只输出JSON，格式："
            "{\"is_flowmeter_certificate\": true/false, "
            "\"factory_code\": \"出厂编号或序列号或空\", "
            "\"calibration_date\": \"YYYY-MM-DD或空\", "
            "\"valid_until\": \"YYYY-MM-DD或空\", "
            "\"next_calibration_date\": \"YYYY-MM-DD或空\", "
            "\"confidence\": 0到1, \"reason\": \"简短依据\"}"
        ),
    )
    data = result.get("data") if result.get("status") == "success" else {}
    if isinstance(data, dict) and not data.get("factory_code"):
        data = {**data, "factory_code": _factory_code_from_filename(str(item.get("filename") or ""))}
    if isinstance(data, dict) and _is_reference_flowmeter_certificate_candidate(item):
        data = {**data, "is_flowmeter_certificate": bool(data.get("is_flowmeter_certificate", True))}
    return {
        **(data if isinstance(data, dict) else {}),
        "source_filename": item.get("filename"),
        "source_path": item.get("source_path"),
        "ocr_status": result.get("status"),
    }


def _compare_reference_flowmeter_dates(material: dict[str, Any], certificate: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = []
    last_material = _parse_date_text(material.get("last_calibration_date"))
    cert_calibration = _parse_date_text(certificate.get("calibration_date"))
    if last_material and cert_calibration:
        comparisons.append(
            _reference_date_comparison(
                "last_calibration_date",
                material,
                certificate,
                last_material,
                cert_calibration,
            )
        )
    elif last_material:
        comparisons.append(
            _reference_missing_certificate_date(
                "last_calibration_date",
                material,
                certificate,
                last_material,
            )
        )
    elif cert_calibration:
        comparisons.append(
            _reference_missing_material_date(
                "last_calibration_date",
                material,
                certificate,
                cert_calibration,
            )
        )
    else:
        comparisons.append(
            _reference_missing_both_date(
                "last_calibration_date",
                material,
                certificate,
            )
        )
    next_material = _parse_date_text(material.get("next_calibration_date"))
    cert_next = _parse_date_text(certificate.get("next_calibration_date")) or _parse_date_text(certificate.get("valid_until"))
    if next_material and cert_next:
        comparisons.append(
            _reference_date_comparison(
                "next_calibration_date",
                material,
                certificate,
                next_material,
                cert_next,
            )
        )
    elif next_material:
        comparisons.append(
            _reference_missing_certificate_date(
                "next_calibration_date",
                material,
                certificate,
                next_material,
            )
        )
    elif cert_next:
        comparisons.append(
            _reference_missing_material_date(
                "next_calibration_date",
                material,
                certificate,
                cert_next,
            )
        )
    else:
        comparisons.append(
            _reference_missing_both_date(
                "next_calibration_date",
                material,
                certificate,
            )
        )
    return comparisons


def _reference_date_comparison(
    field: str,
    material: dict[str, Any],
    certificate: dict[str, Any],
    material_date: str,
    certificate_date: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "factory_code": material.get("factory_code"),
        "material_date": material_date,
        "certificate_date": certificate_date,
        "status": "match" if material_date == certificate_date else "mismatch",
        "material_filename": material.get("source_filename"),
        "certificate_filename": certificate.get("source_filename"),
    }


def _reference_missing_certificate_date(
    field: str,
    material: dict[str, Any],
    certificate: dict[str, Any],
    material_date: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "factory_code": material.get("factory_code"),
        "material_date": material_date,
        "certificate_date": "",
        "status": "missing_certificate_date",
        "reason": "证书首页OCR未提取到对应校准日期信息",
        "material_filename": material.get("source_filename"),
        "certificate_filename": certificate.get("source_filename"),
        "certificate_ocr_status": certificate.get("ocr_status"),
    }


def _reference_missing_material_date(
    field: str,
    material: dict[str, Any],
    certificate: dict[str, Any],
    certificate_date: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "factory_code": material.get("factory_code"),
        "material_date": "",
        "certificate_date": certificate_date,
        "status": "missing_material_date",
        "reason": "参考流量计资料OCR未提取到对应校准日期信息",
        "material_filename": material.get("source_filename"),
        "certificate_filename": certificate.get("source_filename"),
        "material_ocr_status": material.get("ocr_status"),
    }


def _reference_missing_both_date(
    field: str,
    material: dict[str, Any],
    certificate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "field": field,
        "factory_code": material.get("factory_code"),
        "material_date": "",
        "certificate_date": "",
        "status": "missing_date",
        "reason": "参考流量计资料或证书首页OCR未提取到对应校准日期信息",
        "material_filename": material.get("source_filename"),
        "certificate_filename": certificate.get("source_filename"),
        "material_ocr_status": material.get("ocr_status"),
        "certificate_ocr_status": certificate.get("ocr_status"),
    }


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
        _add_visual_diagnostic_issue(issues, order, table, item, result)
        return
    data = result.get("data") or {}
    if not data.get("is_flow_calibration_photo"):
        return

    comparisons = []
    before_fields, after_fields = _pm_flow_calibration_fields_for_attachment(item)
    comparisons.extend(_compare_visual_value("before_flow", data.get("before_flow"), form, before_fields))
    comparisons.extend(_compare_visual_value("after_flow", data.get("after_flow"), form, after_fields))
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
            f"附件文件名：{item.get('filename') or ''}。"
            "请判断图片是否为气体流量检查的仪器面板、分析仪流量显示照片，或外接流量计/质量流量计测量照片，并只读取明确属于流量的读数。"
            "display_values 只能填写分析仪/仪器面板显示流量值，常见标签包括 FLOW、SAMPLE FLOW、SAMP FL、FLOW CHECK、采样流量、流量显示值、仪器显示流量、示值。"
            "measured_values 只能填写外接流量计/质量流量计/便携流量计测量值，常见标签包括 Volu Flow、LPM、SLPM、实测流量、测量值、测值、流量计读数。"
            "必须保留图片原始单位，常见单位包括 LPM、SLPM、L/min、L/h、ml/min、SCCM、cc/min，不确定单位时保持空。"
            "严禁把污染物浓度读数填入 display_values；凡是带 PPM、PPB、ug/m3、mg/m3 或标注为浓度/CONC 的数值都不是流量，应忽略。"
            "不要读取日期水印、时间、站点编号、设备序列号、证书编号、量程或百分比误差。"
            "如能从图片文字、文件名或上下文区分污染物对应的流量，请按 SO2、NO2、CO、O3 返回；不能区分则只放入 visible_flow_values，对应项保持 null。"
            "热电/THERMO 臭氧(O3)分析仪比较特殊，仪器显示值可能由图片中的流量A/Flow A 与流量B/Flow B 相加得到；"
            "如图片中明确出现这两个 O3 流量分量，请在 display_components.O3 中分别返回流量A和流量B，不要把单个分量当作合计。"
            "如果热电/THERMO O3 图片不能同时识别流量A和流量B，则 display_values.O3 保持 null，只把可见单个分量放入 visible_flow_values。"
            "只输出JSON，格式："
            "{\"is_gas_flow_panel_photo\": true/false, "
            "\"display_values\": {\"SO2\": 数值或null, \"NO2\": 数值或null, \"CO\": 数值或null, \"O3\": 数值或null}, "
            "\"display_components\": {\"O3\": [{\"label\":\"流量A或Flow A\", \"value\":数值, \"unit\":\"单位\"}, {\"label\":\"流量B或Flow B\", \"value\":数值, \"unit\":\"单位\"}]}, "
            "\"measured_values\": {\"SO2\": 数值或null, \"NO2\": 数值或null, \"CO\": 数值或null, \"O3\": 数值或null}, "
            "\"display_units\": {\"SO2\": \"原始单位或空\", \"NO2\": \"原始单位或空\", \"CO\": \"原始单位或空\", \"O3\": \"原始单位或空\"}, "
            "\"measured_units\": {\"SO2\": \"原始单位或空\", \"NO2\": \"原始单位或空\", \"CO\": \"原始单位或空\", \"O3\": \"原始单位或空\"}, "
            "\"unit\": \"原始单位或空\", "
            "\"visible_flow_values\": [{\"label\":\"原图文字标签\", \"value\":数值, \"unit\":\"单位\"}], "
            "\"confidence\": 0到1, \"reason\":\"简短依据\"}"
        ),
    )
    if result.get("status") != "success":
        _add_visual_diagnostic_issue(issues, order, table, item, result)
        return
    data = result.get("data") or {}
    if not data.get("is_gas_flow_panel_photo"):
        return

    display_values = data.get("display_values") if isinstance(data.get("display_values"), dict) else {}
    measured_values = data.get("measured_values") if isinstance(data.get("measured_values"), dict) else {}
    display_components = data.get("display_components") if isinstance(data.get("display_components"), dict) else {}
    display_units = data.get("display_units") if isinstance(data.get("display_units"), dict) else {}
    measured_units = data.get("measured_units") if isinstance(data.get("measured_units"), dict) else {}
    fallback_unit = data.get("unit")
    display_comparisons = []
    measured_comparisons = []
    photo_value_role = _gas_flow_photo_value_role(item)
    if table == "RF_M_GASEOUSFLOWCHECK":
        for gas in ("SO2", "NO2", "CO", "O3"):
            if photo_value_role != "measured":
                if _should_skip_monthly_thermo_o3_display_comparison(
                    table,
                    form,
                    gas,
                    display_components.get(gas),
                ):
                    continue
                display_value = _monthly_gas_flow_display_value(
                    table,
                    form,
                    gas,
                    display_values.get(gas),
                    display_components.get(gas),
                )
                display_comparisons.extend(
                    _compare_visual_value(
                        gas,
                        display_value,
                        form,
                        [f"DISPLAYVALUE{gas}"],
                        visual_unit=display_units.get(gas) or fallback_unit,
                    )
                )
            if photo_value_role != "display":
                measured_comparisons.extend(
                    _compare_monthly_measured_flow_candidates(
                        gas,
                        form,
                        measured_values.get(gas),
                        measured_units.get(gas) or fallback_unit,
                        (
                            display_values.get(gas)
                            if photo_value_role == "measured" and measured_values.get(gas) is not None
                            else None
                        ),
                        display_units.get(gas) or fallback_unit,
                    )
                )
    elif table == "RF_Q_GaseousFlowCheck":
        for point in ("85", "60", "35", "80", "50", "20"):
            display_comparisons.extend(
                _compare_visual_value(
                    f"DF_{point}",
                    display_values.get(point),
                    form,
                    [f"DF_Valuve_{point}"],
                    visual_unit=display_units.get(point) or fallback_unit,
                )
            )
            measured_comparisons.extend(
                _compare_visual_value(
                    f"RF_{point}",
                    measured_values.get(point),
                    form,
                    [f"RF_Valuve_{point}"],
                    visual_unit=measured_units.get(point) or fallback_unit,
                )
            )

    display_violations = [item for item in display_comparisons if item.get("status") == "mismatch"]
    if display_violations:
        _add_visual_value_issue(
            issues,
            "ATTACHMENT_GAS_FLOW_DISPLAY_VALUE_MISMATCH",
            "气体流量检查照片仪器显示值与表单填写值不一致",
            order,
            table,
            item,
            result,
            display_comparisons,
        )

    measured_violations = [item for item in measured_comparisons if item.get("status") == "mismatch"]
    if measured_violations:
        _add_visual_value_issue(
            issues,
            "ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH",
            "气体流量检查照片流量计测量值与表单填写值不一致",
            order,
            table,
            item,
            result,
            measured_comparisons,
        )


def _check_pm_membrane_visual(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    item: dict[str, Any],
    issues: list[Issue],
) -> None:
    if not _is_pm_membrane_visual_candidate(item):
        return

    result = extract_attachment_json(
        str(item["source_path"]),
        provider="flow_visual",
        task=f"pm_membrane_value_{table}",
        prompt=(
            f"附件文件名：{item.get('filename') or ''}。"
            "请判断图片是否为颗粒物PM10/PM2.5季度运行状态检查中的校准膜、标准膜、膜片检查照片，并只读取膜片校准相关读数。"
            "本规则要与表单 PM10CHECKTEMP1VALUE/PM25CHECKTEMP1VALUE、PM10CHECKTEMP2VALUE/PM25CHECKTEMP2VALUE 比对，"
            "这些表单字段对应图片屏幕中的 MASS系数、CAL MASS、MASS COEF、MASS FACTOR、质量系数等数值。"
            "original_value 只能填写原始值照片中的 MASS系数/CAL MASS/质量系数；check_value 只能填写结果、检查值、实测值照片中的 MASS系数/CAL MASS/质量系数。"
            "如果文件名或图片文字包含“原始值/初始值/膜前/检查1”，只填写 original_value，check_value 必须为 null。"
            "如果文件名或图片文字包含“结果/检查值/实测值/膜后/检查2”，只填写 check_value，original_value 必须为 null。"
            "严禁把校准膜读数、标准膜标称值、膜片标签值、膜片重量、1400/1404 μg、ug、μg 对应的数值填入 original_value 或 check_value；这些只可作为 visible_values 记录。"
            "不要读取日期水印、时间、站点编号、设备序列号、证书编号、温度、湿度、气压、流量、PM浓度或误差百分比。"
            "如果图片只包含一个明确读数，请根据文件名或图片文字放入 original_value 或 check_value；不能判断则保持 null。"
            "只输出JSON，格式："
            "{\"is_pm_membrane_photo\": true/false, "
            "\"original_value\": 数值或null, \"check_value\": 数值或null, "
            "\"visible_values\": [{\"label\":\"原图文字标签\", \"value\":数值}], "
            "\"confidence\": 0到1, \"reason\":\"简短依据\"}"
        ),
    )
    if result.get("status") != "success":
        _add_visual_diagnostic_issue(issues, order, table, item, result)
        return
    data = result.get("data") or {}
    if not data.get("is_pm_membrane_photo"):
        return

    data = _normalize_pm_membrane_values_by_filename(data, item)
    profile = _pm_membrane_profile(table)
    if not profile:
        return

    comparisons = []
    comparisons.extend(_compare_pm_membrane_value("original_value", data.get("original_value"), form, profile["original_field"]))
    comparisons.extend(_compare_pm_membrane_value("check_value", data.get("check_value"), form, profile["check_field"]))

    value_violations = [item for item in comparisons if item.get("status") == "mismatch"]
    if value_violations:
        _add_visual_value_issue(
            issues,
            "ATTACHMENT_PM_MEMBRANE_VALUE_MISMATCH",
            "颗粒物校准膜照片读数与表单填写值不一致",
            order,
            table,
            item,
            result,
            comparisons,
        )


def _check_pm_temp_pressure_visual(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    item: dict[str, Any],
    issues: list[Issue],
) -> None:
    if not _is_pm_temp_pressure_visual_candidate(item):
        return

    result = extract_attachment_json(
        str(item["source_path"]),
        provider="flow_visual",
        task=f"pm_temp_pressure_value_{table}",
        prompt=(
            f"附件文件名：{item.get('filename') or ''}。"
            "请判断图片是否为颗粒物温度、压力校准或检查照片，并只读取PM10/PM2.5分析仪对应的温度和气压读数。"
            "temperature_display 只能填写仪器显示的气温/温度值，temperature_standard 只能填写标准值或实际值。"
            "若屏幕上同时出现多个温度值，temperature_display 优先读取 AT 标签后的环境温度/气温读数。"
            "不要把 Delta、Error、Diff、误差、差值、修正值或偏差对应的温度读数填入 temperature_display。"
            "pressure_display 只能填写仪器显示的气压/压力值，pressure_standard 只能填写标准值或实际值。"
            "若屏幕上出现 BP 标签，pressure_display 优先读取 BP 标签后的气压读数；保留图片原始单位，例如 mmHg。"
            "不要读取日期水印、时间、站点编号、设备序列号、证书编号、误差值、校准情况或备注。"
            "如能从图片文字、文件名或上下文区分PM10、PM2.5，请分别返回；不能区分则保持对应项为null。"
            "只输出JSON，格式："
            "{\"is_pm_temp_pressure_photo\": true/false, "
            "\"values\": {"
            "\"PM10\": {\"temperature_display\": 数值或null, \"temperature_standard\": 数值或null, "
            "\"pressure_display\": 数值或null, \"pressure_standard\": 数值或null}, "
            "\"PM25\": {\"temperature_display\": 数值或null, \"temperature_standard\": 数值或null, "
            "\"pressure_display\": 数值或null, \"pressure_standard\": 数值或null}"
            "}, \"visible_values\": [{\"label\":\"原图文字标签\", \"value\":数值, \"unit\":\"单位\"}], "
            "\"confidence\": 0到1, \"reason\":\"简短依据\"}"
        ),
    )
    if result.get("status") != "success":
        _add_visual_diagnostic_issue(issues, order, table, item, result)
        return
    data = result.get("data") or {}
    if not data.get("is_pm_temp_pressure_photo"):
        return

    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    filename_profile = _pm_temp_pressure_filename_profile(item)
    comparisons = []
    for pollutant in filename_profile["pollutants"]:
        pollutant_values = values.get(pollutant) if isinstance(values.get(pollutant), dict) else {}
        if filename_profile["temperature"]:
            comparisons.extend(
                _compare_pm_temp_pressure_value(
                    f"{pollutant}.temperature_{filename_profile['value_role']}",
                    _pm_temp_pressure_value_for_role(pollutant_values, "temperature", filename_profile["value_role"]),
                    form,
                    f"{pollutant}CHECKTEMP{filename_profile['field_slot']}VALUE",
                )
            )
        if filename_profile["pressure"]:
            comparisons.extend(
                _compare_pm_temp_pressure_value(
                    f"{pollutant}.pressure_{filename_profile['value_role']}",
                    _pm_temp_pressure_value_for_role(pollutant_values, "pressure", filename_profile["value_role"]),
                    form,
                    f"{pollutant}CHECKPRES{filename_profile['field_slot']}VALUE",
                )
            )

    value_violations = [item for item in comparisons if item.get("status") == "mismatch"]
    if value_violations:
        _add_visual_value_issue(
            issues,
            "ATTACHMENT_PM_TEMP_PRESSURE_VALUE_MISMATCH",
            "颗粒物温度压力照片读数与表单填写值不一致",
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
    *,
    visual_unit: Any = None,
) -> list[dict[str, Any]]:
    visual_number = _parse_number(visual_value)
    if visual_number is None:
        return []

    comparisons = []
    for field in candidate_fields:
        form_value = form.get(field)
        form_number = _parse_number(form_value)
        if form_number is None:
            continue
        comparable_candidates = _flow_value_candidates_for_comparison(
            visual_number,
            visual_unit,
            form_number,
            form_value=form_value,
            form=form,
            field=field,
            label=label,
        )
        comparable_visual = next(
            (candidate for candidate in comparable_candidates if _numbers_close(candidate, form_number)),
            comparable_candidates[0],
        )
        matched = _numbers_close(comparable_visual, form_number)
        comparisons.append(
            {
                "label": label,
                "field": field,
                "visual_value": comparable_visual,
                "raw_visual_value": visual_number,
                "visual_unit": str(visual_unit or ""),
                "form_value": form_number,
                "difference": round(abs(comparable_visual - form_number), 6),
                "status": "matched" if matched else "mismatch",
            }
        )
    if any(item["status"] == "matched" for item in comparisons):
        return [item for item in comparisons if item["status"] == "matched"]
    return comparisons


def _monthly_gas_flow_display_value(
    table: str,
    form: dict[str, Any],
    gas: str,
    display_value: Any,
    display_components: Any,
) -> Any:
    if table != "RF_M_GASEOUSFLOWCHECK" or gas != "O3" or not _is_thermo_brand(form):
        return display_value
    component_sum = _sum_flow_a_b_components(display_components)
    if component_sum is None:
        return display_value
    return component_sum


def _should_skip_monthly_thermo_o3_display_comparison(
    table: str,
    form: dict[str, Any],
    gas: str,
    display_components: Any,
) -> bool:
    if table != "RF_M_GASEOUSFLOWCHECK" or gas != "O3" or not _is_thermo_brand(form):
        return False
    return _sum_flow_a_b_components(display_components) is None


def _is_thermo_brand(form: dict[str, Any]) -> bool:
    brand_text = str(form.get("DEVICEBRAND") or form.get("BRAND") or "").strip()
    if not brand_text:
        return False
    brand_upper = brand_text.upper()
    return "THERMO" in brand_upper or brand_upper in {"TE", "热电"}


def _sum_flow_a_b_components(components: Any) -> float | None:
    if not isinstance(components, list):
        return None
    flow_a = None
    flow_b = None
    for component in components:
        if not isinstance(component, dict):
            continue
        label = str(component.get("label") or "")
        value = _parse_number(component.get("value"))
        if value is None:
            continue
        normalized_label = label.upper().replace(" ", "")
        if "流量A" in label or "FLOWA" in normalized_label:
            flow_a = value
        elif "流量B" in label or "FLOWB" in normalized_label:
            flow_b = value
    if flow_a is None or flow_b is None:
        return None
    return round(flow_a + flow_b, 6)


def _compare_monthly_measured_flow_candidates(
    gas: str,
    form: dict[str, Any],
    measured_value: Any,
    measured_unit: Any,
    alternate_value: Any = None,
    alternate_unit: Any = None,
) -> list[dict[str, Any]]:
    field = f"MEASUREDVALUE{gas}"
    comparisons = _compare_visual_value(gas, measured_value, form, [field], visual_unit=measured_unit)
    if alternate_value is not None:
        comparisons.extend(_compare_visual_value(gas, alternate_value, form, [field], visual_unit=alternate_unit))
    if any(item.get("status") == "matched" for item in comparisons):
        return [item for item in comparisons if item.get("status") == "matched"]
    return comparisons


def _compare_pm_membrane_value(
    label: str,
    visual_value: Any,
    form: dict[str, Any],
    field: str,
) -> list[dict[str, Any]]:
    visual_number = _parse_number(visual_value)
    form_number = _parse_number(form.get(field))
    if visual_number is None or form_number is None:
        return []
    tolerance = float(os.getenv("OPS_AUDIT_PM_MEMBRANE_VISUAL_VALUE_TOLERANCE", "0.001") or "0.001")
    matched = abs(visual_number - form_number) <= tolerance
    return [
        {
            "label": label,
            "field": field,
            "visual_value": visual_number,
            "raw_visual_value": visual_number,
            "visual_unit": "",
            "form_value": form_number,
            "difference": round(abs(visual_number - form_number), 6),
            "status": "matched" if matched else "mismatch",
        }
    ]


def _normalize_pm_membrane_values_by_filename(data: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    slot = _pm_membrane_filename_slot(item)
    if slot not in {"original", "check"}:
        return data
    original = _parse_number(data.get("original_value"))
    check = _parse_number(data.get("check_value"))
    if original is not None and check is not None:
        value = original if slot == "original" else check
    else:
        value = original if original is not None else check
    if value is None:
        visible_values = data.get("visible_values")
        if isinstance(visible_values, list) and len(visible_values) == 1:
            value = _parse_number(visible_values[0].get("value") if isinstance(visible_values[0], dict) else None)
    if value is None:
        return data
    normalized = dict(data)
    if slot == "original":
        normalized["original_value"] = value
        normalized["check_value"] = None
    else:
        normalized["original_value"] = None
        normalized["check_value"] = value
    return normalized


def _pm_membrane_filename_slot(item: dict[str, Any]) -> str | None:
    filename = str(item.get("filename") or "").strip()
    normalized = filename.upper().replace(" ", "")
    if not any(keyword in normalized for keyword in ("膜片检查", "膜检", "校准膜", "标准膜")):
        if not any(keyword in normalized for keyword in ("原始值", "初始值", "膜前", "结果", "检查值", "实测值", "膜后")):
            return None
    if any(keyword in normalized for keyword in ("原始值", "初始值", "膜前")):
        return "original"
    if any(keyword in normalized for keyword in ("结果", "检查值", "实测值", "膜后")):
        return "check"
    if re.search(r"(?:检查|膜检|膜片|校准膜|标准膜)[_\\-（(]?(?:1|一)[）)]?", normalized):
        return "original"
    if re.search(r"(?:检查|膜检|膜片|校准膜|标准膜)[_\\-（(]?(?:2|二)[）)]?", normalized):
        return "check"
    return None


def _compare_pm_temp_pressure_value(
    label: str,
    visual_value: Any,
    form: dict[str, Any],
    field: str,
) -> list[dict[str, Any]]:
    visual_number = _parse_number(visual_value)
    form_value = form.get(field)
    form_number = _parse_number(form_value)
    if visual_number is None or form_number is None:
        return []
    comparable_visual, visual_unit = _normalize_pm_temp_pressure_value_for_comparison(
        label,
        visual_number,
        form_number,
        form_value,
    )
    comparable_form = _normalize_pm_temp_pressure_form_value_for_comparison(
        form_value,
        form_number,
    )
    matched = comparable_visual == comparable_form
    return [
        {
            "label": label,
            "field": field,
            "visual_value": round(comparable_visual, 6),
            "raw_visual_value": visual_number,
            "visual_unit": visual_unit,
            "form_value": comparable_form,
            "raw_form_value": form_number,
            "difference": round(abs(comparable_visual - comparable_form), 6),
            "status": "matched" if matched else "mismatch",
        }
    ]


def _pm_temp_pressure_filename_profile(item: dict[str, Any]) -> dict[str, Any]:
    text = _attachment_search_text(item)
    has_pm25 = "PM2.5" in text or "PM25" in text
    has_pm10 = "PM10" in text
    pollutants: list[str]
    if has_pm25 and not has_pm10:
        pollutants = ["PM25"]
    elif has_pm10 and not has_pm25:
        pollutants = ["PM10"]
    elif has_pm10 and has_pm25:
        pollutants = ["PM10", "PM25"]
    else:
        pollutants = ["PM10", "PM25"]

    has_pollutant_marker = has_pm10 or has_pm25
    return {
        "pollutants": pollutants,
        "value_role": "display" if has_pollutant_marker else "standard",
        "field_slot": "1" if has_pollutant_marker else "2",
        "temperature": _pm_temp_pressure_filename_has_temperature(text),
        "pressure": _pm_temp_pressure_filename_has_pressure(text),
    }


def _pm_temp_pressure_value_for_role(values: dict[str, Any], metric: str, role: str) -> Any:
    primary = values.get(f"{metric}_{role}")
    if primary is not None:
        return primary
    fallback_role = "standard" if role == "display" else "display"
    return values.get(f"{metric}_{fallback_role}")


def _pm_temp_pressure_filename_has_temperature(text: str) -> bool:
    return any(keyword in text for keyword in ("温度", "气温", "温湿度", "温压"))


def _pm_temp_pressure_filename_has_pressure(text: str) -> bool:
    return any(keyword in text for keyword in ("压力", "气压", "大气压", "温压"))


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
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _normalize_flow_value_for_comparison(
    visual_number: float,
    visual_unit: Any,
    form_number: float,
    *,
    form_value: Any = None,
    form: dict[str, Any] | None = None,
    field: str = "",
    label: str = "",
) -> float:
    unit = _normalize_flow_unit(visual_unit)
    form_unit = _infer_form_flow_unit(form_value, form, field, label)
    if unit == "L/min" and form_unit == "L/h":
        return round(visual_number * 60, 6)
    if unit == "ml/min" and form_unit == "L/h":
        return round(visual_number / 1000 * 60, 6)
    if unit == "L/h" and form_unit == "L/min":
        return round(visual_number / 60, 6)
    if unit == "L/h" and form_unit == "ml/min":
        return round(visual_number / 60 * 1000, 6)
    if unit == "L/min" and form_unit == "ml/min":
        return visual_number * 1000
    if unit == "ml/min" and form_unit == "L/min":
        return visual_number / 1000
    if unit == "L/min" and form_unit is None and abs(form_number) >= 10 and abs(visual_number) < 10:
        return visual_number * 1000
    if unit == "ml/min" and form_unit is None and abs(form_number) < 10 and abs(visual_number) >= 10:
        return visual_number / 1000
    return visual_number


def _flow_value_candidates_for_comparison(
    visual_number: float,
    visual_unit: Any,
    form_number: float,
    *,
    form_value: Any = None,
    form: dict[str, Any] | None = None,
    field: str = "",
    label: str = "",
) -> list[float]:
    primary = _normalize_flow_value_for_comparison(
        visual_number,
        visual_unit,
        form_number,
        form_value=form_value,
        form=form,
        field=field,
        label=label,
    )
    candidates = [primary]
    unit = _normalize_flow_unit(visual_unit)
    form_unit = _infer_form_flow_unit(form_value, form, field, label)
    if form_unit is None:
        candidates.append(visual_number)
        if unit == "L/h":
            candidates.append(round(visual_number / 60, 6))
        elif unit == "L/min":
            candidates.append(round(visual_number * 60, 6))
    deduped = []
    for candidate in candidates:
        if not any(_numbers_close(candidate, existing) for existing in deduped):
            deduped.append(candidate)
    return deduped


def _normalize_pm_temp_pressure_value_for_comparison(
    label: str,
    visual_number: float,
    form_number: float,
    form_value: Any,
) -> tuple[float, str]:
    lower_label = label.lower()
    precision = _decimal_places(form_value)
    if (
        "pressure" in lower_label
        and 600 <= abs(visual_number) <= 850
        and 80 <= abs(form_number) <= 120
    ):
        return round(visual_number * 0.133322368, precision), "mmHg->kPa"
    return round(visual_number, precision), ""


def _normalize_pm_temp_pressure_form_value_for_comparison(form_value: Any, form_number: float) -> float:
    return round(form_number, _decimal_places(form_value))


def _decimal_places(value: Any) -> int:
    text = str(value).strip()
    match = re.search(r"-?\d+(?:\.(\d+))?", text)
    if not match or match.group(1) is None:
        return 0
    return len(match.group(1))


def _normalize_flow_unit(unit: Any) -> str | None:
    text = str(unit or "").strip().lower().replace(" ", "")
    if not text:
        return None
    text = text.replace("／", "/")
    if text in {"mlpm", "sccm", "ml/min", "mlmin", "cc/m", "cc/min", "ccm", "毫升/分钟", "毫升每分钟"}:
        return "ml/min"
    if text in {"l/h", "lph", "lh", "l/hr", "l/hour", "升/小时", "升每小时"}:
        return "L/h"
    if text in {"lpm", "slpm", "slm", "l/min", "lmin", "sl/min", "升/分钟", "升每分钟"}:
        return "L/min"
    if "ml" in text or "cc" in text:
        return "ml/min"
    if "l/h" in text or "lph" in text or "l/hr" in text or "l/hour" in text:
        return "L/h"
    if "lpm" in text or "l/min" in text or "slm" in text:
        return "L/min"
    return None


def _infer_form_flow_unit(form_value: Any, form: dict[str, Any] | None, field: str, label: str) -> str | None:
    value_unit = _normalize_flow_unit(form_value)
    if value_unit:
        return value_unit
    if not form:
        return None
    range_field = _monthly_gas_flow_range_field(field, label)
    if range_field:
        range_text = str(form.get(range_field) or "").strip().lower().replace(" ", "")
        range_text = range_text.replace("／", "/")
        if _normalize_flow_unit(range_text):
            return _normalize_flow_unit(range_text)
        if "/h" in range_text or "1/h" in range_text:
            return "L/h"
        if "/min" in range_text:
            return "L/min"
    return None


def _monthly_gas_flow_range_field(field: str, label: str) -> str | None:
    upper_field = str(field or "").upper()
    upper_label = str(label or "").upper()
    for gas in ("SO2", "NO2", "CO", "O3"):
        if upper_field.endswith(gas) or upper_label == gas:
            return f"FLOWRANG{gas}"
    return None


def _gas_flow_photo_value_role(item: dict[str, Any]) -> str | None:
    text = _attachment_search_text(item)
    filename = str(item.get("filename") or "").strip()
    if re.search(r"(?:SO2|NO2|NO|NOX|CO|O3)测(?:\.[^.]+)?$", filename, flags=re.IGNORECASE):
        return "measured"
    if any(token in text for token in ("流量计测值", "流量计读数", "测量流量", "流量测量", "测量值", "测量", "实测", "测值")):
        return "measured"
    if any(token in text for token in ("仪器示值", "显示流量", "流量显示", "显示值", "显示", "分析仪示值", "仪器显示", "示值")):
        return "display"
    return None


def _pm_membrane_profile(table: str) -> dict[str, str] | None:
    if table == "RF_Q_PM25RUNSTATUSCHECK":
        return {
            "pollutant": "PM2.5",
            "original_field": "PM25CHECKTEMP1VALUE",
            "check_field": "PM25CHECKTEMP2VALUE",
            "error_field": "PM25CHECKTEMP3VALUE",
        }
    if table == "RF_Q_PM10RUNSTATUSCHECK":
        return {
            "pollutant": "PM10",
            "original_field": "PM10CHECKTEMP1VALUE",
            "check_field": "PM10CHECKTEMP2VALUE",
            "error_field": "PM10CHECKTEMP3VALUE",
        }
    return None


def _pm_flow_calibration_fields_for_attachment(item: dict[str, Any]) -> tuple[list[str], list[str]]:
    role = _pm_flow_photo_value_role(item)
    before_fields = ["Prev_S", "Prev_A", "Prev_B"]
    after_fields = ["Next_S", "Next_A", "Next_B"]
    if role == "before":
        return before_fields, before_fields
    if role == "after":
        return after_fields, after_fields
    return before_fields, after_fields


def _pm_flow_photo_value_role(item: dict[str, Any]) -> str | None:
    text = _attachment_search_text(item)
    if any(token in text for token in ("校准前", "校前", "流量检查", "检查")):
        return "before"
    if any(token in text for token in ("校准后", "校后")):
        return "after"
    return None


def _pm_flow_pollutant_from_attachment(item: dict[str, Any]) -> str | None:
    return _normalize_pm_pollutant(_attachment_search_text(item))


def _pm_flow_form_pollutant(form: dict[str, Any]) -> str | None:
    for field in ("PollutantType", "PM_DeviceType", "pollutant_type", "pollutantType"):
        pollutant = _normalize_pm_pollutant(form.get(field))
        if pollutant:
            return pollutant
    return None


def _normalize_pm_pollutant(value: Any) -> str | None:
    text = str(value or "").upper().replace(" ", "")
    if "PM2.5" in text or "PM25" in text:
        return "PM2.5"
    if "PM10" in text:
        return "PM10"
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
        "needs_visual_review": True,
        "promotion_policy": "视觉识别结果需满足高置信度、明确字段、明确单位后才进入最终问题清单；否则仅作为视觉复核候选。",
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


def _add_visual_diagnostic_issue(
    issues: list[Issue],
    order: dict[str, Any],
    rf_table: str,
    item: dict[str, Any],
    result: dict[str, Any],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": rf_table,
        "filename": item.get("filename"),
        "source": item.get("source_path"),
        "types": item.get("types", []),
        "vision_provider": result.get("provider"),
        "vision_status": result.get("status"),
        "vision_error": result.get("error"),
    }
    add_issue(
        issues,
        "ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC",
        "附件读数一致性",
        "低",
        f"attachment.vision.diagnostic.{rf_table}",
        f"流量照片视觉识别未执行成功: {item.get('filename') or item.get('source_path')}",
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
    seen: set[tuple[str, str]] = set()
    for record in list(attachments) + list(wo_commonfiles):
        filename = _first_present(record, _name_fields())
        source_path = _first_present(
            record,
            ["file_url", "fileUrl", "FILEURL", "FILE_URL", "FILEPATH", "filepath", "URL", "url", "PATH", "path"],
        )
        key = (str(filename or "").strip(), _normalize_source_key(source_path))
        if key in seen:
            continue
        seen.add(key)
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
                "typecode": _first_present(record, ["TYPECODE", "typecode", "TypeCode"]),
                "types": classified.get("types", []),
            }
        )
    return items


def _forms_for_attachment(
    forms: list[tuple[str, dict[str, Any]]],
    item: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    matched = [(table, form) for table, form in forms if _attachment_matches_table(item, table)]
    candidates = matched or forms
    pollutant = _pm_flow_pollutant_from_attachment(item)
    if pollutant:
        pollutant_matched = [
            (table, form)
            for table, form in candidates
            if table == "RF_TW_PmFlowCalibrate" and _pm_flow_form_pollutant(form) == pollutant
        ]
        if pollutant_matched:
            return pollutant_matched
    return candidates


def _attachment_matches_table(item: dict[str, Any], table: str) -> bool:
    attachment_table = _attachment_table_hint(item)
    if not attachment_table:
        return False
    attachment_normalized = _normalize_table_name(attachment_table)
    table_normalized = _normalize_table_name(table)
    return attachment_normalized == table_normalized or attachment_normalized.startswith(table_normalized)


def _attachment_table_hint(item: dict[str, Any]) -> str:
    typecode = str(item.get("typecode") or "").strip()
    if typecode:
        return typecode
    text = _attachment_search_text(item)
    for table in FLOW_VISUAL_RULE_TABLES:
        if _normalize_table_name(table) in _normalize_table_name(text):
            return table
    return ""


def _normalize_table_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _prioritized_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"certificate": 0, "report": 1, "photo": 2, "curve": 3}

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        types = set(item.get("types", []))
        best = min([priority.get(item_type, 9) for item_type in types] or [9])
        return (best, str(item.get("filename") or item.get("source_path") or ""))

    return sorted(items, key=sort_key)


def _is_flow_visual_candidate(item: dict[str, Any]) -> bool:
    filename_normalized = str(item.get("filename") or "").upper().replace(" ", "")
    text = " ".join(
        str(value or "")
        for value in (
            item.get("filename"),
            item.get("source_path"),
            item.get("descriptor"),
        )
    )
    normalized = text.upper().replace(" ", "")
    if _is_pm_temp_pressure_visual_candidate(item):
        return True
    if _is_pm_membrane_visual_candidate(item):
        return True
    if any(keyword in normalized for keyword in ("证书", "编号", "标签", "合格证", ".PDF")):
        return False
    if any(
        keyword in normalized
        for keyword in (
            "实测",
            "显示",
            "测量",
            "测值",
            "示值",
            "检查值",
            "流量检查",
            "流量校准",
            "校准流量",
            "读数",
            "仪器流量",
            "仪器显示",
            "仪器测量",
        )
    ):
        return True
    if re.search(r"(?:SO2|SO|NO2|NOX|NO|CO|O3|臭氧|二氧化硫|一氧化碳|氮氧).{0,4}测(?:\.|_|-|$)", normalized):
        return True
    if re.search(r"^(?:SO2|SO|NO2|NOX|NO|CO|O3|臭氧)(?:\.[A-Z0-9]+)?$", filename_normalized):
        return True
    return False


def _is_reference_flowmeter_certificate_candidate(item: dict[str, Any]) -> bool:
    filename_text = str(item.get("filename") or "").upper().replace(" ", "")
    descriptor_text = str(item.get("descriptor") or "").upper().replace(" ", "")
    if ".PDF" not in filename_text and "CERTIFICATE" not in filename_text and "证书" not in filename_text:
        return False
    return any(keyword in filename_text or keyword in descriptor_text for keyword in ("流量计", "FLOWMETER", "THM", "标准流量", "参考流量", "质量流量"))


def _is_reference_flowmeter_material_candidate(item: dict[str, Any]) -> bool:
    text = _attachment_search_text(item)
    if _is_reference_flowmeter_certificate_candidate(item):
        return False
    return any(keyword in text for keyword in ("参考流量计", "流量计资料", "标准流量计", "参考标准器", "THM"))


def _attachment_search_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            item.get("filename"),
            item.get("source_path"),
            item.get("descriptor"),
        )
    ).upper().replace(" ", "")


def _is_monthly_gaseous_flow_attachment(item: dict[str, Any]) -> bool:
    text = _attachment_search_text(item)
    return "RF_M_GASEOUSFLOWCHECK" in text


def _is_pm_temp_pressure_visual_candidate(item: dict[str, Any]) -> bool:
    normalized = _attachment_search_text(item)
    if any(keyword in normalized for keyword in ("证书", "编号", "标签", "合格证", ".PDF")):
        return False
    if "PMPRESSURE" in normalized:
        return True
    has_metric = _pm_temp_pressure_filename_has_temperature(normalized) or _pm_temp_pressure_filename_has_pressure(normalized)
    if not has_metric:
        return False
    return any(keyword in normalized for keyword in ("PM10", "PM25", "PM2.5", "颗粒物")) or not _pm_temp_pressure_has_unrelated_keyword(normalized)


def _pm_temp_pressure_has_unrelated_keyword(text: str) -> bool:
    return any(keyword in text for keyword in ("采样管", "采样总管", "采样支管", "风机", "清洗", "多点", "曲线", "结果"))


def _is_pm_membrane_visual_candidate(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("filename"),
            item.get("source_path"),
            item.get("descriptor"),
        )
    )
    normalized = text.upper().replace(" ", "")
    if any(keyword in normalized for keyword in ("证书", "编号", "标签", "合格证", ".PDF")):
        return False
    if not any(
        keyword in normalized
        for keyword in (
            "RF_Q_PM25RUNSTATUSCHECK",
            "RF_Q_PM10RUNSTATUSCHECK",
            "PM25RUNSTATUS",
            "PM10RUNSTATUS",
            "PM2.5",
            "PM25",
            "PM10",
        )
    ):
        return False
    return any(
        keyword in normalized
        for keyword in (
            "校准膜",
            "标准膜",
            "膜片",
            "膜检",
            "膜前",
            "膜后",
            "原始值",
            "初始值",
        )
    )


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


def _normalize_source_key(source_path: Any) -> str:
    text = str(source_path or "").strip()
    if not text:
        return ""
    match = re.search(r"/WebFiles/.+$", text, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    return text


def _factory_code_from_filename(filename: str) -> str:
    return _factory_code_from_text(filename)


def _factory_code_from_text(text: Any) -> str:
    value = str(text or "")
    label_match = re.search(
        r"(?:出厂编号|出厂号|设备编号|序列号|编号|Serial\s*No\.?|S/?N)[:：\s]*([A-Z0-9][A-Z0-9\-_/]{4,})",
        value,
        flags=re.IGNORECASE,
    )
    if label_match:
        return _normalize_factory_code(label_match.group(1))
    generic_match = re.search(r"\b[A-Z]\d{6,}[A-Z0-9]*\b", value, flags=re.IGNORECASE)
    if generic_match:
        return _normalize_factory_code(generic_match.group(0))
    return ""


def _normalize_factory_code(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _parse_date_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"([0-9]{4})[-/年.]([0-9]{1,2})[-/月.]([0-9]{1,2})", text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
