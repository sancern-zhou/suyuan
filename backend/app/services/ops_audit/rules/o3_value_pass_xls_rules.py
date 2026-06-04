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
TYPECODE = "RF_HY_O3ValuePass"
TOLERANCE = 1e-6

COMPARISONS = [
    {"field": "DEVICEDELIVERMODEL", "label": "斜率", "cell": "G26", "fallback_cells": ["F26"]},
    {"field": "DELIVERFC", "label": "截距(ppb)", "cell": "G27", "fallback_cells": ["F27"]},
    {"field": "DENSITY1VALUE", "label": "相对于前一次传递的改变(%)", "cell": "G29", "fallback_cells": ["F29"]},
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
        typecode = _first_present(record, ["TYPECODE", "typecode", "TypeCode", "FUNCTIONCODE", "functioncode"])
        name = _first_present(record, ["FILENAME", "filename", "FileName", "NAME", "name", "TITLE", "title"])
        sources = _source_candidates(record)
        source = sources[0] if sources else None
        text = f"{typecode or ''} {name or ''} {' '.join(sources)}"
        if TYPECODE.lower() not in text.lower():
            continue
        suffix_text = str(name or source or "").lower()
        if not suffix_text.endswith((".xls", ".xlsx")):
            continue
        items.append({"filename": name, "source_path": source, "source_paths": sources, "raw": record})
    return items


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
            cells = {comparison["cell"]: _worksheet_cell_value(ws, comparison) for comparison in COMPARISONS}
            wb.close()
            return {"status": "success", "cells": cells}
        if suffix == ".xls":
            import xlrd

            book = xlrd.open_workbook(str(path))
            sheet = book.sheet_by_index(0)
            cells = {comparison["cell"]: _xls_sheet_cell_value(sheet, comparison) for comparison in COMPARISONS}
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
    cells = [str(comparison["cell"])]
    cells.extend(str(cell) for cell in comparison.get("fallback_cells", []))
    return cells


def _worksheet_cell_value(ws: Any, comparison: dict[str, Any]) -> Any:
    for cell in _comparison_cells(comparison):
        value = ws[cell].value
        if not _is_blank(value):
            return {"cell": cell, "value": value}
    return {"cell": comparison["cell"], "value": None}


def _xls_sheet_cell_value(sheet: Any, comparison: dict[str, Any]) -> Any:
    for cell in _comparison_cells(comparison):
        value = sheet.cell_value(*_xls_cell_indexes(cell))
        if not _is_blank(value):
            return {"cell": cell, "value": value}
    return {"cell": comparison["cell"], "value": None}


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
        cell_data = cells.get(cell)
        used_cell = cell
        if isinstance(cell_data, dict):
            used_cell = str(cell_data.get("cell") or cell)
            cell_raw = cell_data.get("value")
        else:
            cell_raw = cell_data
        form_value = _number(form_raw)
        cell_value = _number(cell_raw)
        if form_value is None:
            status = "missing_form_value"
        elif cell_value is None:
            status = "missing_xls_value"
        elif abs(form_value - cell_value) <= TOLERANCE:
            status = "match"
        else:
            status = "mismatch"
        comparisons.append(
            {
                **comparison,
                "configured_cell": cell,
                "cell": used_cell,
                "form_value": form_raw,
                "xls_value": cell_raw,
                "form_number": form_value,
                "xls_number": cell_value,
                "status": status,
            }
        )
    return comparisons


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
