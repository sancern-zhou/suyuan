"""O3 value-pass XLS attachment checks."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH"
RF_TABLE = "RF_HY_O3VALUEPASS"
TOLERANCE = 1e-6

COMPARISONS = [
    {"field": "DEVICEDELIVERMODEL", "label": "斜率", "cell": "F25", "candidate_cells": ["F25", "F24"]},
    {"field": "DELIVERFC", "label": "截距(ppb)", "cell": "F26", "candidate_cells": ["F26", "F25"]},
    {"field": "DENSITY1VALUE", "label": "相对于前一次传递的改变(%)", "cell": "F28", "candidate_cells": ["F28", "F26"]},
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

    items = _xls_items(attachments + wo_commonfiles)
    for form in relevant_forms:
        item = _select_item(items)
        if not item:
            _add_issue(order, form, None, [{"status": "missing_xls_attachment"}], issues)
            continue

        cell_values = _read_cells(item)
        if cell_values.get("status") != "success":
            _add_issue(order, form, item, [{"status": "xls_read_error", "error": cell_values.get("error")}], issues)
            continue

        comparisons = _compare_values(form, cell_values["cells"])
        failed = [comparison for comparison in comparisons if comparison["status"] != "match"]
        if failed:
            _add_issue(order, form, item, failed, issues)


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


def _is_xls_attachment(name: Any, sources: list[str]) -> bool:
    for value in [name, *sources]:
        suffix = Path(urlparse(str(value or "")).path).suffix.lower()
        if suffix in {".xls", ".xlsx"}:
            return True
    return False


def _select_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return sorted(items, key=lambda item: str(item.get("filename") or item.get("source_path") or ""))[0]


def _read_cells(item: dict[str, Any]) -> dict[str, Any]:
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


def _read_cells_from_path(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            from openpyxl import load_workbook

            wb = load_workbook(path, data_only=True, read_only=True)
            ws = wb.worksheets[0]
            cells = {comparison["cell"]: _worksheet_cell_values(ws, comparison) for comparison in COMPARISONS}
            wb.close()
            return {"status": "success", "cells": cells}
        if suffix == ".xls":
            import xlrd

            book = xlrd.open_workbook(str(path))
            sheet = book.sheet_by_index(0)
            cells = {comparison["cell"]: _xls_sheet_cell_values(sheet, comparison) for comparison in COMPARISONS}
            return {"status": "success", "cells": cells}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "error", "error": f"不支持的附件格式：{suffix}"}


def _source_candidates(record: dict[str, Any]) -> list[str]:
    candidates = []
    for field in (
        "FILEPATH",
        "filepath",
        "PATH",
        "path",
        "file_url",
        "fileUrl",
        "FILEURL",
        "FILE_URL",
        "URL",
        "url",
    ):
        value = record.get(field)
        if value is None:
            continue
        source = str(value).strip()
        if source and source not in candidates:
            candidates.append(source)
    return candidates


def _comparison_cells(comparison: dict[str, Any]) -> list[str]:
    configured = comparison.get("candidate_cells")
    if configured:
        return [str(cell) for cell in configured]
    cells = [str(comparison["cell"])]
    cells.extend(str(cell) for cell in comparison.get("fallback_cells", []))
    return cells


def _worksheet_cell_values(ws: Any, comparison: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"cell": cell, "value": ws[cell].value} for cell in _comparison_cells(comparison)]


def _xls_sheet_cell_values(sheet: Any, comparison: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"cell": cell, "value": sheet.cell_value(*_xls_cell_indexes(cell))}
        for cell in _comparison_cells(comparison)
    ]


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


def _compare_values(form: dict[str, Any], cells: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = []
    for comparison in COMPARISONS:
        field = comparison["field"]
        cell = comparison["cell"]
        form_raw = form.get(field)
        form_value = _number(form_raw)
        form_precision = _decimal_places(form_raw)
        cell_candidates = _cell_candidates(cells.get(cell), comparison)
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
    return comparisons


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


def _xls_cell_indexes(cell: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", cell.upper())
    if not match:
        raise ValueError(f"非法单元格地址：{cell}")
    letters, row_text = match.groups()
    col = 0
    for char in letters:
        col = col * 26 + ord(char) - ord("A") + 1
    return int(row_text) - 1, col - 1
