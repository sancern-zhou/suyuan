"""Visual review of multipoint calibration curves against RF concentrations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app.services.ops_audit.config import load_semantic_review_profiles
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue
from app.services.ops_audit.semantic.ocr_adapter import extract_attachment_json


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
VALID_RESULTS = {"PASS", "ISSUE_REVIEW", "INSUFFICIENT_EVIDENCE"}
VALID_REASON_CODES = {
    "NONE",
    "GRADIENT_MISMATCH",
    "POINT_COUNT_MISMATCH",
    "NO_CLEAR_GRADIENT",
    "POLLUTANT_MISMATCH",
    "NOT_MULTIPOINT_CURVE",
    "CURVE_INCOMPLETE",
    "IMAGE_UNREADABLE",
}


def build_multipoint_curve_visual_tasks(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    *,
    evidence_dir: Path,
) -> list[dict[str, Any]]:
    """Build one visual-review task for each quarterly gas multipoint form."""

    enabled_rule_ids = load_semantic_review_profiles().get("flow_visual_enabled_rule_ids", [])
    if RULE_ID not in {str(rule_id) for rule_id in enabled_rule_ids}:
        return []
    items = _attachment_items(attachments, wo_commonfiles)
    tasks = []
    seen_forms: set[tuple[Any, ...]] = set()
    for table, form in forms:
        if table not in MULTIPOINT_TABLES or form.get("_query_error"):
            continue
        signature = _form_signature(table, form)
        if signature in seen_forms:
            continue
        seen_forms.add(signature)
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


def _form_signature(table: str, form: dict[str, Any]) -> tuple[Any, ...]:
    record_id = next(
        (
            form.get(field)
            for field in ("RFQGASEOUSCHECKID", "ID", "id")
            if form.get(field) not in (None, "")
        ),
        None,
    )
    if record_id is not None:
        return (table, "id", str(record_id))
    return (
        table,
        str(form.get("WORKINGORDERCODE") or ""),
        str(form.get("POLLUTANTTYPE") or ""),
        *(_number(form.get(field)) for field in CONCENTRATION_FIELDS),
    )


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


def run_multipoint_curve_visual_task(task: dict[str, Any], issues: list[Issue]) -> None:
    """Review all curve candidates for one RF multipoint form."""

    if len(task.get("form_concentrations", [])) < 3:
        _add_review_issue(
            task,
            _insufficient_result("CURVE_INCOMPLETE", "RF表单有效多点浓度不足3个，无法核对曲线梯度。"),
            issues,
        )
        return
    candidates = list(task.get("candidate_items", []))
    if not candidates:
        _add_review_issue(
            task,
            _insufficient_result("NOT_MULTIPOINT_CURVE", "未找到可用于审核的多点曲线图片。"),
            issues,
        )
        return

    reviews = [_review_candidate(task, item) for item in candidates]
    selected = _select_aggregate_result(reviews)
    if selected["result"] != "PASS":
        selected = {**selected, "reviewed_images": reviews}
        _add_review_issue(task, selected, issues)


def _review_candidate(task: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    try:
        evidence = _persist_attachment(task, item)
    except Exception as exc:
        return {
            **_insufficient_result("IMAGE_UNREADABLE", f"曲线图片无法保存或读取：{exc}"),
            **_attachment_evidence(item),
        }

    result = extract_attachment_json(
        evidence["attachment_local_path"],
        provider="flow_visual",
        task="multipoint_curve_gradient_review",
        prompt=_review_prompt(task, item),
    )
    model_result_path = _persist_model_result(evidence["attachment_local_path"], result)
    if result.get("status") != "success":
        return {
            **_insufficient_result(
                "IMAGE_UNREADABLE",
                f"多模态模型无法完成曲线审核：{result.get('error') or '未知错误'}",
            ),
            **evidence,
            "model_status": result.get("status"),
            "model_error": result.get("error"),
            "model_result_path": model_result_path,
        }
    data = result.get("data")
    normalized = _normalize_model_result(data)
    return {
        **normalized,
        **evidence,
        "model_status": result.get("status"),
        "model_text": result.get("text"),
        "model_result_path": model_result_path,
    }


def _review_prompt(task: dict[str, Any], item: dict[str, Any]) -> str:
    concentrations = "、".join(_display_number(value) for value in task["form_concentrations"])
    return (
        f"你正在审核{task['pollutant']}多点校准曲线，附件文件名为{item.get('filename') or '未命名'}。"
        f"RF表单填写的多点校准浓度依次为：{concentrations} {task['unit']}。"
        "请结合图片直接判断曲线是否呈现与这些表单浓度点一致的多级平台和明显浓度梯度。"
        "曲线可以按浓度升序或降序；允许轻微波动、拍摄倾斜、屏幕摩尔纹和坐标刻度不清。"
        "只比较平台数量、明显梯度、顺序和相对量级，不审核站点、作业时间、平台持续时长或校准偏差。"
        "不要求精确提取每个平台数值，不要输出置信度，也不要根据看不清的内容猜测为无问题。"
        "无法确认时返回INSUFFICIENT_EVIDENCE。"
        "只输出JSON："
        '{"result":"PASS|ISSUE_REVIEW|INSUFFICIENT_EVIDENCE",'
        '"reason_code":"NONE|GRADIENT_MISMATCH|POINT_COUNT_MISMATCH|NO_CLEAR_GRADIENT|'
        'POLLUTANT_MISMATCH|NOT_MULTIPOINT_CURVE|CURVE_INCOMPLETE|IMAGE_UNREADABLE",'
        '"reason":"简明中文原因","observed_summary":"图片中实际看到的梯度或资料不足情况"}'
    )


def _display_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _normalize_model_result(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _insufficient_result("IMAGE_UNREADABLE", "多模态模型未返回有效的结构化结果。")
    result = str(data.get("result") or "").strip().upper()
    reason_code = str(data.get("reason_code") or "").strip().upper()
    if result not in VALID_RESULTS or reason_code not in VALID_REASON_CODES:
        return _insufficient_result("IMAGE_UNREADABLE", "多模态模型返回了协议外的审核结果。")
    if result == "PASS":
        reason_code = "NONE"
    elif reason_code == "NONE":
        reason_code = "IMAGE_UNREADABLE" if result == "INSUFFICIENT_EVIDENCE" else "GRADIENT_MISMATCH"
    return {
        "result": result,
        "reason_code": reason_code,
        "reason": str(data.get("reason") or "").strip() or "模型未提供具体原因。",
        "observed_summary": str(data.get("observed_summary") or "").strip(),
    }


def _insufficient_result(reason_code: str, reason: str) -> dict[str, Any]:
    return {
        "result": "INSUFFICIENT_EVIDENCE",
        "reason_code": reason_code,
        "reason": reason,
        "observed_summary": "",
    }


def _persist_attachment(task: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    target_dir = (
        Path(task["evidence_dir"])
        / _safe_component(_working_order_code(task))
        / _safe_component(str(task["pollutant"]))
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    source = str(item.get("source_path") or "").strip()
    if not source:
        raise ValueError("附件路径为空")
    filename = _safe_filename(str(item.get("filename") or Path(source).name or "curve.jpg"))
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    target = target_dir / f"{Path(filename).stem}_{digest}{Path(filename).suffix.lower()}"
    if not target.exists():
        if source.startswith(("http://", "https://")):
            response = requests.get(source, timeout=30)
            response.raise_for_status()
            target.write_bytes(response.content)
        else:
            local_source = _resolve_local_source(source)
            if local_source is not None:
                shutil.copy2(local_source, target)
            else:
                remote_url = _relative_source_url(source)
                if not remote_url:
                    raise FileNotFoundError(source)
                response = requests.get(remote_url, timeout=30)
                response.raise_for_status()
                target.write_bytes(response.content)
    if target.stat().st_size == 0:
        raise ValueError("附件内容为空")
    return {
        **_attachment_evidence(item),
        "attachment_local_path": str(target.resolve()),
    }


def _resolve_local_source(source: str) -> Path | None:
    path = Path(source).expanduser()
    if path.is_file():
        return path
    root = str(os.getenv("OPS_ATTACHMENT_ROOT") or os.getenv("ATTACHMENT_ROOT") or "").strip()
    if root:
        rooted = Path(root).expanduser() / source.lstrip("/")
        if rooted.is_file():
            return rooted
    return None


def _relative_source_url(source: str) -> str:
    base_url = str(os.getenv("OPS_ATTACHMENT_BASE_URL") or os.getenv("ATTACHMENT_BASE_URL") or "").strip()
    if not base_url or not source.startswith("/"):
        return ""
    return urljoin(base_url.rstrip("/") + "/", source.lstrip("/"))


def _persist_model_result(attachment_local_path: str, result: dict[str, Any]) -> str:
    attachment_path = Path(attachment_local_path)
    result_path = attachment_path.with_suffix(f"{attachment_path.suffix}.review.json")
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return str(result_path.resolve())


def _attachment_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "attachment_filename": item.get("filename"),
        "attachment_original_path": item.get("original_path"),
        "attachment_url": item.get("url"),
        "attachment_local_path": item.get("attachment_local_path"),
    }


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", filename).strip(" .")
    return cleaned or "curve.jpg"


def _safe_component(value: str) -> str:
    return _safe_filename(value).replace(".", "_")


def _working_order_code(task: dict[str, Any]) -> str:
    return str(task.get("order", {}).get("WORKINGORDERCODE") or task.get("form", {}).get("WORKINGORDERCODE") or "unknown")


def _select_aggregate_result(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    issue = next((review for review in reviews if review.get("result") == "ISSUE_REVIEW"), None)
    if issue:
        return issue
    passed = next((review for review in reviews if review.get("result") == "PASS"), None)
    if passed:
        return passed
    return reviews[0] if reviews else _insufficient_result("NOT_MULTIPOINT_CURVE", "未找到多点曲线图片。")


def _add_review_issue(task: dict[str, Any], result: dict[str, Any], issues: list[Issue]) -> None:
    classification = (
        "疑似问题待人工复核"
        if result.get("result") == "ISSUE_REVIEW"
        else "资料不足待人工复核"
    )
    evidence = {
        "working_order_code": _working_order_code(task),
        "station_id": task.get("order", {}).get("STATIONID"),
        "rf_table": task.get("table"),
        "pollutant_type": task.get("pollutant"),
        "form_concentrations": task.get("form_concentrations", []),
        "concentration_unit": task.get("unit"),
        "report_classification": classification,
        "needs_manual_review": True,
        "result": result.get("result"),
        "reason_code": result.get("reason_code"),
        "reason": result.get("reason"),
        "observed_summary": result.get("observed_summary"),
        "attachment_filename": result.get("attachment_filename"),
        "attachment_local_path": result.get("attachment_local_path"),
        "attachment_original_path": result.get("attachment_original_path"),
        "attachment_url": result.get("attachment_url"),
        "model_result_path": result.get("model_result_path"),
        "reviewed_images": result.get("reviewed_images", []),
    }
    add_issue(
        issues,
        RULE_ID,
        "附件质量问题",
        "中",
        f"attachment.multipoint_curve.{str(task.get('pollutant') or '').lower()}",
        f"{classification}：{result.get('reason')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )
