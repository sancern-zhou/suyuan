"""Visual review of multipoint calibration curves against RF concentrations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


RULE_ID = "ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW"
MULTIPOINT_TABLES = {
    "RF_Q_GASEOUSMULTIPOINT_CO": ("CO", "ppm"),
    "RF_Q_GASEOUSMULTIPOINT_NO2": ("NO2", "ppb"),
    "RF_Q_GASEOUSMULTIPOINT_O3": ("O3", "ppb"),
    "RF_Q_GASEOUSMULTIPOINT_SO2": ("SO2", "ppb"),
}
CONCENTRATION_FIELDS = ("MCLBZ10", "MCLBZ20", "MCLBZ40", "MCLBZ60", "MCLBZ80")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CURVE_KEYWORDS = ("曲线", "梯度图", "gradient", "curve")
EXCLUDED_IMAGE_KEYWORDS = ("记录表", "计算表", "结果表")
SKIP_VALUES = {"", "/", "-", "无", "不适用", "none", "null", "nan"}


def build_multipoint_curve_visual_tasks(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    *,
    evidence_dir: Path,
) -> list[dict[str, Any]]:
    """Build one visual-review task for each quarterly gas multipoint form."""

    items = _attachment_items(attachments, wo_commonfiles)
    tasks = []
    for table, form in forms:
        if table not in MULTIPOINT_TABLES or form.get("_query_error"):
            continue
        pollutant, unit = MULTIPOINT_TABLES[table]
        candidates = [
            item
            for item in items
            if _attachment_matches_table(item, table) and _is_curve_candidate(item)
        ]
        tasks.append(
            {
                "task_type": "multipoint_curve_visual",
                "order": order,
                "table": table,
                "form": form,
                "pollutant": pollutant,
                "unit": unit,
                "form_concentrations": _form_concentrations(form),
                "candidate_items": candidates,
                "evidence_dir": str(evidence_dir.resolve()),
            }
        )
    return tasks


def _form_concentrations(form: dict[str, Any]) -> list[float]:
    values = []
    for field in CONCENTRATION_FIELDS:
        parsed = _number(form.get(field))
        if parsed is not None:
            values.append(parsed)
    return values


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in SKIP_VALUES:
        return None
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None


def _attachment_items(
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    seen = set()
    for record in [*attachments, *wo_commonfiles]:
        filename = _first(record, "filename", "FILENAME")
        original_path = _first(record, "filepath", "FILEPATH", "path", "PATH")
        url = _first(record, "file_url", "FILEURL", "url", "URL")
        typecode = _first(record, "typecode", "TYPECODE", "TypeCode")
        source = url or original_path
        key = (str(filename or ""), str(source or ""))
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "filename": filename,
                "source_path": source,
                "original_path": original_path,
                "url": url,
                "typecode": typecode,
            }
        )
    return items


def _first(record: dict[str, Any], *fields: str) -> Any:
    for field in fields:
        if record.get(field) not in (None, ""):
            return record[field]
    return None


def _attachment_matches_table(item: dict[str, Any], table: str) -> bool:
    typecode = _normalized_table(item.get("typecode"))
    return bool(typecode) and typecode == _normalized_table(table)


def _normalized_table(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _is_curve_candidate(item: dict[str, Any]) -> bool:
    filename = str(item.get("filename") or "").strip()
    if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
        return False
    normalized = filename.lower().replace(" ", "")
    if any(keyword in normalized for keyword in EXCLUDED_IMAGE_KEYWORDS):
        return False
    return any(keyword in normalized for keyword in CURVE_KEYWORDS)
