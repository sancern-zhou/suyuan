"""O3 value-pass XLS attachment checks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH"
FLOW_MISSING_RULE_ID = "RF_O3_VALUE_PASS_FLOW_VALUE_MISSING"
FIELD_POSITION_RULE_ID = "RF_O3_VALUE_PASS_FIELD_POSITION_SUSPECT"
RF_TABLE = "RF_HY_O3VALUEPASS"

COMPARISONS = [
    {"field": "DEVICEDELIVERMODEL", "label": "斜率", "cell": "F"},
    {"field": "DELIVERFC", "label": "截距(ppb)", "cell": "F"},
    {"field": "DENSITY1VALUE", "label": "相对于前一次传递的改变(%)", "cell": "F"},
]


def check_o3_value_pass_xls_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Compare RF_HY_O3VALUEPASS values with the uploaded XLS first sheet."""

    relevant_forms = [form for table, form in forms if table == RF_TABLE and not form.get("_query_error")]
    if not relevant_forms:
        return

    records = attachments + wo_commonfiles
    xls_items = _xls_items(records)
    pdf_items = _pdf_items(records)
    for form in relevant_forms:
        _check_o3_value_pass_form_fields(order, form, issues)
        selected_items = [item for item in (_select_item(xls_items), _select_item(pdf_items)) if item]
        if not selected_items:
            continue
        for item in selected_items:
            cell_values = _read_cells(item)
            if cell_values.get("status") != "success":
                if item.get("attachment_kind") == "pdf" or _is_unavailable_attachment_source_error(cell_values.get("error")):
                    continue
                _add_issue(order, form, item, [{"status": "xls_read_error", "error": cell_values.get("error")}], issues)
                continue

            comparisons = _compare_values(form, cell_values["cells"])
            failed = [comparison for comparison in comparisons if comparison["status"] != "match"]
            if failed:
                _add_issue(order, form, item, failed, issues)


def _check_o3_value_pass_form_fields(
    order: dict[str, Any],
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    missing = []
    position_suspects = []
    # In the current RF_HY_O3VALUEPASS template, groups 4-6 store metadata such
    # as dates, model, serial number, and formula fragments. Only groups 1-3
    # are stable enough for deterministic transfer-flow completeness checks.
    for point in range(1, 4):
        flow_field = f"DELIVER{point}VALUE"
        related_fields = [
            f"WORKDENSITY{point}VALUE",
            f"DELIVERFROM{point}VALUE",
            f"DELIVERTO{point}VALUE",
        ]
        raw_flow = form.get(flow_field)
        related_values = {field: form.get(field) for field in related_fields if field in form}
        if _is_low_value(raw_flow) and any(not _is_low_value(value) for value in related_values.values()):
            missing.append(
                {
                    "point": point,
                    "field": flow_field,
                    "value": raw_flow,
                    "related_values": related_values,
                }
            )
        if _looks_like_non_flow_value(raw_flow):
            position_suspects.append(
                {
                    "point": point,
                    "field": flow_field,
                    "value": raw_flow,
                    "suggested_check": "传递流量字段疑似填入日期或设备信息",
                }
            )
    if missing:
        _add_form_field_issue(
            order,
            form,
            FLOW_MISSING_RULE_ID,
            "表单完整性",
            "高",
            f"rf.{RF_TABLE}.{missing[0]['field']}",
            f"O3量值传递第{missing[0]['point']}组传递流量未填写",
            missing,
            issues,
        )
    if position_suspects:
        _add_form_field_issue(
            order,
            form,
            FIELD_POSITION_RULE_ID,
            "表单数值逻辑",
            "高",
            f"rf.{RF_TABLE}.{position_suspects[0]['field']}",
            "O3量值传递传递流量字段疑似填入日期或设备信息",
            position_suspects,
            issues,
        )


def _add_form_field_issue(
    order: dict[str, Any],
    form: dict[str, Any],
    rule_id: str,
    category: str,
    severity: str,
    field: str,
    message: str,
    violations: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE") or form.get("WORKINGORDERCODE"),
        "rf_table": RF_TABLE,
        "violations": violations[:20],
    }
    add_issue(
        issues,
        rule_id,
        category,
        severity,
        field,
        message,
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _is_low_value(value: Any) -> bool:
    return str(value or "").strip() in {"", "/", "-", "无", "NA", "N/A", "nan", "NaN", "null", "None"}


def _looks_like_non_flow_value(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or _is_low_value(text):
        return False
    if re.search(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}", text):
        return True
    upper = text.upper()
    return any(token in upper for token in ("TE-", "49I", "146I", "CM", "LGH", "MODEL", "????"))


def _xls_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for record in records:
        name = _first_present(record, ["FILENAME", "filename", "FileName", "NAME", "name", "TITLE", "title"])
        sources = _source_candidates(record)
        source = sources[0] if sources else None
        if not _is_xls_attachment(name, sources):
            continue
        items.append({"filename": name, "source_path": source, "source_paths": sources, "raw": record})
    return items


def _pdf_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for record in records:
        name = _first_present(record, ["FILENAME", "filename", "FileName", "NAME", "name", "TITLE", "title"])
        sources = _source_candidates(record)
        source = sources[0] if sources else None
        if not _is_pdf_attachment(name, sources):
            continue
        descriptor = " ".join(str(value or "") for value in [name, *sources]).lower()
        if "o3" not in descriptor and "臭氧" not in descriptor:
            continue
        items.append({"filename": name, "source_path": source, "source_paths": sources, "raw": record, "attachment_kind": "pdf"})
    return items


def _is_xls_attachment(name: Any, sources: list[str]) -> bool:
    for value in [name, *sources]:
        suffix = Path(urlparse(str(value or "")).path).suffix.lower()
        if suffix in {".xls", ".xlsx"}:
            return True
    return False


def _is_pdf_attachment(name: Any, sources: list[str]) -> bool:
    for value in [name, *sources]:
        suffix = Path(urlparse(str(value or "")).path).suffix.lower()
        if suffix == ".pdf":
            return True
    return False


def _select_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return sorted(items, key=lambda item: str(item.get("filename") or item.get("source_path") or ""))[0]


def _read_cells(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("attachment_kind") == "pdf":
        return _read_cells_from_pdf_item(item)
    sources = item.get("source_paths")
    if not isinstance(sources, list) or not sources:
        sources = [item.get("source_path")]
    errors = []
    for source_value in sources:
        source = str(source_value or "").strip()
        if not source:
            continue
        resolved = _resolve_source(source)
        if resolved.get("status") == "success":
            return _read_cells_from_path(Path(str(resolved["path"])))
        errors.append(f"{source}: {resolved.get('error')}")
    return {"status": "error", "error": "；".join(errors) or "附件路径为空"}


def _read_cells_from_pdf_item(item: dict[str, Any]) -> dict[str, Any]:
    result = _read_pdf_text(item)
    if result.get("status") != "success":
        return result
    return {"status": "success", "cells": _cells_from_pdf_text(str(result.get("text") or ""))}


def _read_pdf_text(item: dict[str, Any]) -> dict[str, Any]:
    sources = item.get("source_paths")
    if not isinstance(sources, list) or not sources:
        sources = [item.get("source_path")]
    errors = []
    for source_value in sources:
        source = str(source_value or "").strip()
        if not source:
            continue
        resolved = _resolve_source(source)
        if resolved.get("status") != "success":
            errors.append(f"{source}: {resolved.get('error')}")
            continue
        path = Path(str(resolved["path"]))
        try:
            completed = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            continue
        return {"status": "success", "text": completed.stdout}
    return {"status": "error", "error": "；".join(errors) or "PDF附件路径为空"}


def _cells_from_pdf_text(text: str) -> dict[str, list[dict[str, Any]]]:
    cells = {
        "__source_type": "pdf_text",
        "DEVICEDELIVERMODEL": [],
        "DELIVERFC": [],
        "DENSITY1VALUE": [],
        "TRANSFER_FORMULA": [],
    }
    for index, line in enumerate(text.splitlines(), start=1):
        normalized = _normalize_label(line)
        if not normalized:
            continue
        if "斜率" in normalized and not cells["DEVICEDELIVERMODEL"]:
            cells["DEVICEDELIVERMODEL"].append({"cell": f"pdf:{index}", "value": _first_number_text(line)})
        if "截距" in normalized and not cells["DELIVERFC"]:
            cells["DELIVERFC"].append({"cell": f"pdf:{index}", "value": _first_number_text(line)})
        if "改变" in normalized and "前一次" in normalized:
            cells["DENSITY1VALUE"].append({"cell": f"pdf:{index}", "value": _first_number_text(line)})
        if "公式" in normalized and ("传递" in normalized or "拟合" in normalized or "线性" in normalized):
            cells["TRANSFER_FORMULA"].append({"cell": f"pdf:{index}", "value": line.strip()})
    return cells


def _first_number_text(text: str) -> str:
    match = re.search(r"[-+]?\d+(?:\.\d+)?%?", str(text or ""))
    return match.group(0) if match else ""


def _read_cells_from_path(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            from openpyxl import load_workbook

            wb = load_workbook(path, data_only=True, read_only=True)
            ws = wb.worksheets[0]
            cells = _worksheet_dynamic_cells(ws)
            wb.close()
            return {"status": "success", "cells": cells}
        if suffix == ".xls":
            import xlrd

            book = xlrd.open_workbook(str(path))
            sheet = book.sheet_by_index(0)
            cells = _xls_sheet_dynamic_cells(sheet)
            return {"status": "success", "cells": cells}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "error", "error": f"不支持的附件格式：{suffix}"}


def _source_candidates(record: dict[str, Any]) -> list[str]:
    candidates = []
    for field in (
        "file_url",
        "fileUrl",
        "FILEURL",
        "FILE_URL",
        "URL",
        "url",
        "FILEPATH",
        "filepath",
        "PATH",
        "path",
    ):
        value = record.get(field)
        if value is None:
            continue
        source = str(value).strip()
        if source and source not in candidates:
            candidates.append(source)
    return candidates


def _worksheet_dynamic_cells(ws: Any) -> dict[str, list[dict[str, Any]]]:
    slope_row, intercept_row = _find_o3_value_pass_rows(
        ((row_index, ws[f"D{row_index}"].value) for row_index in range(1, ws.max_row + 1))
    )
    cells = _dynamic_value_cells(
        slope_row,
        intercept_row,
        lambda row_index: ws[f"F{row_index}"].value,
    )
    formula_row = _find_formula_row((row_index, ws[f"D{row_index}"].value) for row_index in range(1, ws.max_row + 1))
    if formula_row is not None:
        cells["TRANSFER_FORMULA"] = [{"cell": f"F{formula_row}", "value": ws[f"F{formula_row}"].value}]
    return cells


def _xls_sheet_dynamic_cells(sheet: Any) -> dict[str, list[dict[str, Any]]]:
    slope_row, intercept_row = _find_o3_value_pass_rows(
        ((row_index + 1, sheet.cell_value(row_index, 3)) for row_index in range(sheet.nrows))
    )
    cells = _dynamic_value_cells(
        slope_row,
        intercept_row,
        lambda row_index: sheet.cell_value(row_index - 1, 5) if row_index <= sheet.nrows else None,
    )
    formula_row = _find_formula_row((row_index + 1, sheet.cell_value(row_index, 3)) for row_index in range(sheet.nrows))
    if formula_row is not None:
        cells["TRANSFER_FORMULA"] = [
            {"cell": f"F{formula_row}", "value": sheet.cell_value(formula_row - 1, 5) if formula_row <= sheet.nrows else None}
        ]
    return cells


def _find_o3_value_pass_rows(labels: Any) -> tuple[int | None, int | None]:
    slope_row = None
    intercept_row = None
    for row_index, value in labels:
        label = _normalize_label(value)
        if slope_row is None and "斜率" in label:
            slope_row = row_index
        if intercept_row is None and "截距" in label:
            intercept_row = row_index
        if slope_row is not None and intercept_row is not None:
            break
    return slope_row, intercept_row


def _find_formula_row(labels: Any) -> int | None:
    for row_index, value in labels:
        label = _normalize_label(value)
        if not label:
            continue
        if "公式" in label and ("传递" in label or "拟合" in label or "线性" in label):
            return row_index
    return None


def _dynamic_value_cells(
    slope_row: int | None,
    intercept_row: int | None,
    value_at: Any,
) -> dict[str, list[dict[str, Any]]]:
    cells = {
        "DEVICEDELIVERMODEL": [],
        "DELIVERFC": [],
        "DENSITY1VALUE": [],
    }
    if slope_row is not None:
        cells["DEVICEDELIVERMODEL"].append({"cell": f"F{slope_row}", "value": value_at(slope_row)})
    if intercept_row is not None:
        cells["DELIVERFC"].append({"cell": f"F{intercept_row}", "value": value_at(intercept_row)})
        cells["DENSITY1VALUE"].extend(
            {"cell": f"F{row_index}", "value": value_at(row_index)}
            for row_index in range(intercept_row + 1, intercept_row + 4)
        )
    return cells


def _normalize_label(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("（", "(").replace("）", ")")


def _resolve_source(source: str) -> dict[str, Any]:
    if not source:
        return {"status": "error", "error": "附件路径为空"}

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return _download_to_temp(source)

    path = Path(source).expanduser()
    if path.exists():
        return {"status": "success", "path": str(path)}

    attachment_root = os.getenv("OPS_ATTACHMENT_ROOT") or os.getenv("ATTACHMENT_ROOT")
    if attachment_root:
        rooted = Path(attachment_root).expanduser() / source.lstrip("/")
        if rooted.exists():
            return {"status": "success", "path": str(rooted)}

    attachment_base_url = os.getenv("OPS_ATTACHMENT_BASE_URL") or os.getenv("ATTACHMENT_BASE_URL")
    if attachment_base_url and source.startswith("/"):
        return _download_to_temp(urljoin(attachment_base_url.rstrip("/") + "/", source.lstrip("/")))

    return {"status": "error", "error": f"文件不存在且未配置附件根路径/基础URL：{source}"}


def _download_to_temp(url: str) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"status": "error", "error": f"下载附件失败：{exc}"}
    suffix = Path(urlparse(url).path).suffix or ".xls"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        handle.write(response.content)
        return {"status": "success", "path": handle.name}
    finally:
        handle.close()


def _is_unavailable_attachment_source_error(error: Any) -> bool:
    text = str(error or "")
    return "附件路径为空" in text or "文件不存在且未配置附件根路径/基础URL" in text


def _compare_values(form: dict[str, Any], cells: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = []
    for comparison in COMPARISONS:
        field = comparison["field"]
        if cells.get("__source_type") == "pdf_text" and not cells.get(field):
            continue
        cell = comparison["cell"]
        form_raw = form.get(field)
        form_value = _number(form_raw)
        form_precision = _decimal_places(form_raw)
        cell_candidates = _cell_candidates(cells.get(field), comparison)
        matched_cell = _matched_cell(form_value, form_precision, cell_candidates, field)
        first_numeric_cell = next((item for item in cell_candidates if item["number"] is not None), None)
        used_cell = first_numeric_cell or (
            cell_candidates[0] if cell_candidates else {"cell": cell, "value": None, "number": None}
        )
        if form_value is None:
            status = "missing_form_value"
        elif matched_cell is not None:
            status = "match"
            used_cell = matched_cell
        elif first_numeric_cell is None:
            status = "missing_xls_value"
        else:
            status = "mismatch"
        comparisons.append(
            {
                **comparison,
                "configured_cell": cell,
                "candidate_cells": [item["cell"] for item in cell_candidates],
                "cell_candidates": [
                    {"cell": item["cell"], "value": item["value"], "number": item["number"]}
                    for item in cell_candidates
                ],
                "cell": used_cell["cell"],
                "form_value": form_raw,
                "xls_value": used_cell["value"],
                "form_number": form_value,
                "xls_number": used_cell["number"],
                "comparison_number": used_cell.get("comparison_number"),
                "comparison_transform": used_cell.get("comparison_transform", ""),
                "form_precision": form_precision,
                "status": status,
            }
        )
    comparisons.extend(_compare_transfer_formula(form, cells.get("TRANSFER_FORMULA")))
    return comparisons


def _compare_transfer_formula(form: dict[str, Any], cell_data: Any) -> list[dict[str, Any]]:
    cell_candidates = _cell_candidates(cell_data, {"cell": "F", "field": "TRANSFER_FORMULA"})
    formula_cell = next((item for item in cell_candidates if str(item.get("value") or "").strip()), None)
    if formula_cell is None:
        return []

    form_slope = _number(form.get("DEVICEDELIVERMODEL"))
    form_intercept = _number(form.get("DELIVERFC"))
    parsed = _parse_linear_formula(formula_cell.get("value"))
    base = {
        "field": "TRANSFER_FORMULA",
        "label": "最佳拟合线性的传递公式",
        "configured_cell": "F",
        "candidate_cells": [item["cell"] for item in cell_candidates],
        "cell_candidates": [
            {"cell": item["cell"], "value": item["value"], "number": item["number"]}
            for item in cell_candidates
        ],
        "cell": formula_cell["cell"],
        "form_value": f"斜率={_display_value(form.get('DEVICEDELIVERMODEL'))}, 截距={_display_value(form.get('DELIVERFC'))}",
        "xls_value": formula_cell.get("value"),
        "form_number": None,
        "xls_number": None,
        "comparison_number": None,
        "comparison_transform": "linear_formula",
        "form_precision": max(_decimal_places(form.get("DEVICEDELIVERMODEL")), _decimal_places(form.get("DELIVERFC"))),
    }
    if form_slope is None or form_intercept is None:
        return [{**base, "status": "missing_form_value"}]
    if parsed is None:
        return [{**base, "status": "formula_unparseable"}]
    formula_slope, formula_intercept = parsed
    slope_precision = _decimal_places(form.get("DEVICEDELIVERMODEL"))
    intercept_precision = _decimal_places(form.get("DELIVERFC"))
    if (
        round(formula_slope, slope_precision) == round(form_slope, slope_precision)
        and round(formula_intercept, intercept_precision) == round(form_intercept, intercept_precision)
    ):
        return [{**base, "status": "match", "formula_slope": formula_slope, "formula_intercept": formula_intercept}]
    return [{**base, "status": "mismatch", "formula_slope": formula_slope, "formula_intercept": formula_intercept}]


def _parse_linear_formula(value: Any) -> tuple[float, float] | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*\*?\s*[xXｘＸ]", text)
    if not match:
        return None
    slope = float(match.group(1))
    tail = text[match.end():]
    intercept_match = re.search(r"([-+]\s*\d+(?:\.\d+)?)", tail)
    if not intercept_match:
        return None
    intercept = float(intercept_match.group(1).replace(" ", ""))
    return slope, intercept


def _cell_candidates(cell_data: Any, comparison: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(cell_data, list):
        raw_items = cell_data
    elif isinstance(cell_data, dict):
        raw_items = [cell_data]
    else:
        raw_items = [{"cell": comparison["cell"], "value": cell_data}]

    candidates = []
    for item in raw_items:
        if isinstance(item, dict):
            cell = str(item.get("cell") or comparison["cell"])
            value = item.get("value")
        else:
            cell = str(comparison["cell"])
            value = item
        candidates.append({"cell": cell, "value": value, "number": _number(value)})
    return candidates


def _matched_cell(
    form_value: float | None,
    form_precision: int,
    candidates: list[dict[str, Any]],
    field: str,
) -> dict[str, Any] | None:
    if form_value is None:
        return None
    for candidate in candidates:
        for comparison_number, transform in _comparison_numbers(candidate.get("number"), field):
            if round(comparison_number, form_precision) == round(form_value, form_precision):
                matched = dict(candidate)
                matched["comparison_number"] = comparison_number
                matched["comparison_transform"] = transform
                return matched
    return None


def _comparison_numbers(value: float | None, field: str) -> list[tuple[float, str]]:
    if value is None:
        return []
    values = [(value, "")]
    if field == "DENSITY1VALUE":
        values.append((value * 100, "percent_scale"))
    return values


def _decimal_places(value: Any) -> int:
    text = str(value or "").strip()
    match = re.search(r"[-+]?\d+(?:\.(\d+))?", text)
    if not match or match.group(1) is None:
        return 0
    return len(match.group(1))


def _add_issue(
    order: dict[str, Any],
    form: dict[str, Any],
    item: dict[str, Any] | None,
    comparisons: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE") or form.get("WORKINGORDERCODE"),
        "rf_table": RF_TABLE,
        "attachment": item,
        "comparisons": comparisons,
    }
    add_issue(
        issues,
        RULE_ID,
        "附件读数一致性",
        "高",
        f"attachment.{RF_TABLE}.xls",
        _issue_message(comparisons),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _issue_message(comparisons: list[dict[str, Any]]) -> str:
    details = [_comparison_detail(comparison) for comparison in comparisons[:3]]
    details = [detail for detail in details if detail]
    if details:
        return f"O3量值传递表单与XLS附件不一致：{'；'.join(details)}"
    return "O3量值传递表单与XLS附件不一致"


def _comparison_detail(comparison: dict[str, Any]) -> str:
    status = comparison.get("status")
    if status == "xls_read_error":
        return f"XLS附件读取失败，原因：{_display_value(comparison.get('error'))}"
    if status == "missing_xls_attachment":
        return "未找到O3量值传递XLS附件"

    label = _display_value(comparison.get("label"))
    field = _display_value(comparison.get("field"))
    cell = _display_value(comparison.get("cell") or comparison.get("configured_cell"))
    form_value = _display_value(comparison.get("form_value"))
    xls_value = _display_value(comparison.get("xls_value"))

    if status == "mismatch":
        return f"{label}不一致：表单字段{field}表单值{form_value}，XLS {cell}值{xls_value}"
    if status == "missing_form_value":
        return f"{label}表单字段{field}为空，XLS {cell}值{xls_value}"
    if status == "missing_xls_value":
        return f"{label}XLS {cell}为空，表单字段{field}值{form_value}"
    if status == "formula_unparseable":
        return f"{label}XLS {cell}无法解析，公式文本{xls_value}"
    return f"{label}异常：{_display_value(status)}"


def _display_value(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return text or "空"


def _first_present(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return value
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"/", "-", "无", "NA", "N/A"}:
        return None
    text = text.replace("％", "%")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def _is_blank(value: Any) -> bool:
    return value is None or not str(value).strip()
