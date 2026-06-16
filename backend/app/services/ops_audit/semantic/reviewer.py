"""Semantic and visual review helpers for ops audits."""

from __future__ import annotations

import asyncio
import json
import math
import re
import threading
import time
from concurrent.futures import TimeoutError
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from app.services.llm_service import LLMService, llm_service
from app.services.ops_audit.config import load_semantic_review_profiles, rules_for_review_stage
from app.services.ops_audit.semantic.ocr_adapter import extract_attachment_text
from app.services.ops_audit.semantic.prompts import (
    ATTACHMENT_QUALITY_JSON_PROMPT,
    ATTACHMENT_REVIEW_PROMPT,
    FILENAME_BATCH_SEMANTIC_JSON_PROMPT,
    NO_DEVICE_BATCH_JSON_PROMPT,
    ORDER_DESCRIPTION_SEMANTIC_JSON_PROMPT,
    ORDER_DESCRIPTION_BATCH_JSON_PROMPT,
    PM_TAPE_USAGE_BATCH_JSON_PROMPT,
    REMARK_BATCH_SEMANTIC_JSON_PROMPT,
    REMARK_REVIEW_PROMPT,
    REMARK_SEMANTIC_JSON_PROMPT,
)


REMARK_REVIEW_RULE_IDS = rules_for_review_stage("semantic_remark")
ATTACHMENT_REVIEW_RULE_IDS: set[str] = set()
SPECIALIZED_REMARK_REVIEW_RULE_IDS = {
    "RF_NO_DEVICE_WITHOUT_REMARK",
    "RF_PM_TAPE_USAGE_INVALID",
    "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING",
}
GENERIC_REMARK_REVIEW_RULE_IDS = REMARK_REVIEW_RULE_IDS - SPECIALIZED_REMARK_REVIEW_RULE_IDS

SEMANTIC_REVIEW_RULE_IDS = REMARK_REVIEW_RULE_IDS | ATTACHMENT_REVIEW_RULE_IDS

SEMANTIC_PROFILES = load_semantic_review_profiles()
_SEMANTIC_CACHE: dict[str, dict[str, Any]] = {}
_SEMANTIC_CACHE_LIMIT = 128
SEMANTIC_LLM_CALL_TIMEOUT_SECONDS = 180
SEMANTIC_BATCH_TOTAL_TIMEOUT_SECONDS = 240

STATION_MAINTAIN_TYPE_DEFINITIONS = {
    "particle_clock_photo": "颗粒物仪器、监测仪器或仪器显示数据及时间相关现场照片",
    "data_logger_clock_photo": "数据采集仪、数采仪显示数据及时间或时间一致性相关现场照片",
    "filter_cleaning_photo": "空调滤网、仪器防尘网、过滤网、滤膜网清洗相关现场照片",
}


def review_remark_semantic(remark: str, context: dict | None = None) -> dict[str, Any]:
    """Judge whether a remark explains cause, action and result."""

    remark_text = str(remark or "").strip()
    if not remark_text:
        return {
            "is_complete": False,
            "has_cause": False,
            "has_action": False,
            "has_result": False,
            "problem_description": "备注为空，未说明原因、处置措施和处理结果。",
            "confidence": 0.0,
        }

    cache_key = _cache_key("remark", remark_text, context)
    if cache_key in _SEMANTIC_CACHE:
        return dict(_SEMANTIC_CACHE[cache_key])

    llm_result = _call_semantic_llm_json(
        REMARK_SEMANTIC_JSON_PROMPT,
        remark_text,
        context=context or {},
    )
    if llm_result:
        parsed = _normalize_remark_result(llm_result, remark_text)
        _cache_store(cache_key, parsed)
        return parsed

    fallback = _heuristic_remark_semantic(remark_text)
    _cache_store(cache_key, fallback)
    return fallback


def review_order_description_semantic(
    order: dict[str, Any],
    rf_forms: list[tuple[str, dict[str, Any]]],
    details: list[dict[str, Any]],
    context: dict | None = None,
) -> dict[str, Any]:
    """Judge whether generic order title/content is sufficient for the work context."""

    title = str(order.get("ORDERTITLE") or order.get("title") or "").strip()
    content = str(order.get("ORDERCONTENT") or order.get("content") or "").strip()
    payload = {
        "title": title,
        "content": content,
        "order_type": order.get("DDWORKINGORDERTYPE") or order.get("order_type"),
        "maintenance_type": order.get("MAINTENANCETYPE") or order.get("maintenance_type"),
        "rf_tables": [table for table, _form in rf_forms[:20]],
        "workflow_steps": [_first_present(detail, ["STEPNAME", "step_name", "NODENAME", "node_name"]) for detail in details[:20]],
    }
    cache_key = _cache_key("order_description", json.dumps(payload, ensure_ascii=False, default=str), context)
    if cache_key in _SEMANTIC_CACHE:
        return dict(_SEMANTIC_CACHE[cache_key])

    llm_result = _call_semantic_llm_json(
        ORDER_DESCRIPTION_SEMANTIC_JSON_PROMPT,
        json.dumps(payload, ensure_ascii=False, default=str),
        context=context or {},
    )
    if llm_result:
        parsed = _normalize_order_description_result(llm_result)
        _cache_store(cache_key, parsed)
        return parsed

    return {
        "is_sufficient": False,
        "has_task_object": False,
        "has_task_type": False,
        "reason": "未完成工单描述语义复核。",
        "problem_description": "未完成工单主表标题和内容的语义复核。",
        "confidence": 0.0,
    }


def review_attachment_quality(attachment_path: str, attachment_type: str) -> dict[str, Any]:
    """Check attachment completeness using OCR text and semantic review."""

    attachment_type = str(attachment_type or "report").strip().lower() or "report"
    ocr_type = _ocr_provider_for_attachment_type(attachment_type)
    ocr_result = extract_attachment_text(attachment_path, provider=ocr_type)
    if ocr_result.get("status") != "success":
        return {
            "is_complete": False,
            "issues": [ocr_result.get("error") or "OCR识别失败"],
            "problem_description": "附件 OCR 识别失败，无法判断附件内容完整性。",
            "confidence": 0.0,
            "ocr_result": ocr_result,
        }

    text = str(ocr_result.get("text") or "").strip()
    if not text:
        return {
            "is_complete": False,
            "issues": ["OCR未识别到有效文本"],
            "problem_description": "附件 OCR 未识别到有效文本，无法判断附件是否完整。",
            "confidence": 0.1,
            "ocr_result": ocr_result,
        }

    context = {"attachment_type": attachment_type, "source": attachment_path, "ocr_text": text[:6000]}
    llm_result = _call_semantic_llm_json(
        ATTACHMENT_QUALITY_JSON_PROMPT,
        text,
        context=context,
    )
    if llm_result:
        parsed = _normalize_attachment_quality_result(llm_result, attachment_type, text)
        parsed["ocr_result"] = ocr_result
        return parsed

    fallback = _heuristic_attachment_quality(attachment_type, text)
    fallback["ocr_result"] = ocr_result
    return fallback


def check_photo_watermark(photo_path: str) -> dict[str, Any]:
    """Check whether photo watermark text includes a date."""

    ocr_result = extract_attachment_text(photo_path, provider="general")
    if ocr_result.get("status") != "success":
        return {
            "has_watermark": False,
            "has_date": False,
            "date_text": "",
            "problem_description": "照片水印 OCR 识别失败，无法判断是否包含日期。",
            "confidence": 0.0,
            "ocr_result": ocr_result,
        }

    text = str(ocr_result.get("text") or "")
    date_text = _first_date_text(text)
    has_watermark = bool(date_text or _contains_any(text, SEMANTIC_PROFILES["attachment_keywords"]["watermark"]))
    has_date = bool(date_text)
    confidence = 0.8 if has_date else 0.55 if has_watermark else 0.3
    return {
        "has_watermark": has_watermark,
        "has_date": has_date,
        "date_text": date_text,
        "problem_description": "" if has_date else "照片 OCR 文本未识别到明确日期水印。",
        "confidence": confidence,
        "ocr_result": ocr_result,
    }


def check_attachment_value_consistency(attachment_path: str, form_value: str) -> dict[str, Any]:
    """Check whether the attachment value is consistent with the form value."""

    ocr_result = extract_attachment_text(attachment_path, provider="general")
    if ocr_result.get("status") != "success":
        return {
            "is_consistent": False,
            "attachment_value": "",
            "form_value": str(form_value or ""),
            "difference": None,
            "problem_description": "附件读数 OCR 识别失败，无法与表单值比对。",
            "confidence": 0.0,
            "ocr_result": ocr_result,
        }

    attachment_text = str(ocr_result.get("text") or "")
    attachment_value = _extract_numeric_text(attachment_text)
    form_numeric = _parse_numeric(form_value)
    if attachment_value is None or form_numeric is None:
        return {
            "is_consistent": False,
            "attachment_value": attachment_value if attachment_value is not None else "",
            "form_value": str(form_value or ""),
            "difference": None,
            "problem_description": "附件读数或表单值无法解析为数值，无法完成一致性比对。",
            "confidence": 0.4,
            "ocr_result": ocr_result,
        }

    difference = abs(attachment_value - form_numeric)
    tolerance = float(SEMANTIC_PROFILES.get("value_tolerance", 0.05))
    scale = max(abs(form_numeric), 1.0)
    is_consistent = difference <= max(tolerance, scale * tolerance)
    return {
        "is_consistent": is_consistent,
        "attachment_value": _format_number(attachment_value),
        "form_value": _format_number(form_numeric),
        "difference": round(difference, 6),
        "problem_description": "" if is_consistent else "附件读数与表单填写值不一致。",
        "confidence": 0.85 if is_consistent else 0.75,
        "ocr_result": ocr_result,
    }


def build_semantic_review_tasks(audit: dict[str, Any]) -> dict[str, Any]:
    """Build remark-closure semantic review tasks for follow-up."""

    tasks = []
    for record in audit.get("records", []):
        matched_issues = [issue for issue in record.get("scoring_issues", []) if issue.get("rule_id") in SEMANTIC_REVIEW_RULE_IDS]
        if not matched_issues:
            continue

        attachment_rules = [issue.get("rule_id") for issue in matched_issues if issue.get("rule_id") in ATTACHMENT_REVIEW_RULE_IDS]
        remark_rules = [issue.get("rule_id") for issue in matched_issues if issue.get("rule_id") in REMARK_REVIEW_RULE_IDS]

        if attachment_rules and not remark_rules:
            review_kind = "attachment_visual"
            prompt = ATTACHMENT_REVIEW_PROMPT
            focus = sorted(set(attachment_rules))
        elif remark_rules and not attachment_rules:
            review_kind = "remark_semantics"
            prompt = REMARK_REVIEW_PROMPT
            focus = sorted(set(remark_rules))
        else:
            review_kind = "mixed"
            prompt = ATTACHMENT_REVIEW_PROMPT
            focus = sorted({issue["rule_id"] for issue in matched_issues})

        tasks.append(
            {
                "working_order_code": record["working_order_code"],
                "station_id": record["station_id"],
                "order_type": record["order_type"],
                "maintenance_type": record["maintenance_type"],
                "finish_time": record["finish_time"],
                "review_kind": review_kind,
                "semantic_focus": focus,
                "evidence_summary": _build_evidence_summary(record, matched_issues),
                "confidence_hint": _confidence_hint(record, matched_issues),
                "model_judgment": "needs_review",
                "prompt": prompt,
                "attachment_review_rules": record.get("attachment_review_rules", []),
            }
        )

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "remark_closure_semantic_review_queue",
        "task_count": len(tasks),
        "tasks": tasks,
    }


def build_semantic_review_results(
    audit: dict[str, Any],
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build completed remark-closure semantic review results for the current audit batch."""

    dataset = dataset or {}
    tasks_bundle = build_semantic_review_tasks(audit)
    audit_records = {record.get("working_order_code"): record for record in audit.get("records", [])}
    dataset_orders = {order.get("WORKINGORDERCODE"): order for order in dataset.get("orders", []) if order.get("WORKINGORDERCODE")}
    details_by_code = _group_details_by_order_code(dataset.get("details", []))
    rf_forms_by_code = _group_rf_forms_by_order_code(dataset.get("rf_forms", {}))
    attachments_by_code = _group_attachments_by_order_code(dataset.get("attachments", []), dataset.get("wo_commonfile", []))

    results = []
    tasks = list(tasks_bundle.get("tasks", []))
    batch_results = _review_batch_semantic_tasks(
        tasks,
        audit_records,
        dataset_orders,
        details_by_code,
        rf_forms_by_code,
    )
    handled_codes = {
        str(result.get("working_order_code"))
        for result in batch_results.values()
        if result.get("working_order_code")
    }
    results.extend(batch_results.values())

    for task in tasks:
        code = task.get("working_order_code")
        if code in handled_codes:
            continue
        record = audit_records.get(code, {})
        order = dataset_orders.get(code, {})
        details = details_by_code.get(code, [])
        rf_forms = rf_forms_by_code.get(code, [])
        attachments = attachments_by_code.get(code, [])
        results.append(
            _review_semantic_task(
                task,
                record,
                order,
                details,
                rf_forms,
                attachments,
            )
        )

    summary = _summarize_semantic_review_results(results)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "remark_closure_semantic_review_results",
        "result_count": len(results),
        "summary": summary,
        "results": results,
    }


def _review_batch_semantic_tasks(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    details_by_code: dict[str, list[dict[str, Any]]],
    rf_forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    order_description_tasks = [
        task for task in tasks
        if _is_order_description_review(task.get("semantic_focus", []))
    ]
    no_device_tasks = [
        task for task in tasks
        if "RF_NO_DEVICE_WITHOUT_REMARK" in set(task.get("semantic_focus", []))
    ]
    pm_tape_tasks = [
        task for task in tasks
        if "RF_PM_TAPE_USAGE_INVALID" in set(task.get("semantic_focus", []))
    ]
    filename_attachment_tasks = [
        task for task in tasks
        if "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING" in set(task.get("semantic_focus", []))
    ]
    remark_tasks = [
        _task_with_semantic_focus(task, sorted(set(task.get("semantic_focus", [])) & GENERIC_REMARK_REVIEW_RULE_IDS))
        for task in tasks
        if task.get("review_kind") == "remark_semantics"
        and set(task.get("semantic_focus", [])) & GENERIC_REMARK_REVIEW_RULE_IDS
    ]

    batch_calls = [
        (
            order_description_tasks,
            _review_order_description_tasks_batch,
            (order_description_tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code),
        ),
        (
            no_device_tasks,
            _review_no_device_tasks_batch,
            (no_device_tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code),
        ),
        (
            pm_tape_tasks,
            _review_pm_tape_usage_tasks_batch,
            (pm_tape_tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code),
        ),
        (
            filename_attachment_tasks,
            _review_filename_attachment_tasks_batch,
            (filename_attachment_tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code),
        ),
        (
            remark_tasks,
            _review_remark_tasks_batch,
            (remark_tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code),
        ),
    ]
    active_calls = [(task_group, fn, args) for task_group, fn, args in batch_calls if task_group]
    if len(active_calls) <= 1:
        for task_group, fn, args in active_calls:
            try:
                results.update(fn(*args))
            except Exception as exc:
                results.update(_fallback_semantic_results(task_group, audit_records, dataset_orders, "failed", exc))
        return results

    executor = ThreadPoolExecutor(max_workers=min(4, len(active_calls)), thread_name_prefix="ops-semantic-batch")
    future_to_call = {executor.submit(fn, *args): (task_group, fn.__name__) for task_group, fn, args in active_calls}
    pending = set(future_to_call)
    deadline = time.monotonic() + SEMANTIC_BATCH_TOTAL_TIMEOUT_SECONDS
    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                completed = next(as_completed(pending, timeout=remaining))
            except TimeoutError:
                break
            pending.remove(completed)
            task_group, _name = future_to_call[completed]
            try:
                results.update(completed.result())
            except Exception as exc:
                results.update(_fallback_semantic_results(task_group, audit_records, dataset_orders, "failed", exc))
        for future in pending:
            future.cancel()
            task_group, _name = future_to_call[future]
            results.update(_fallback_semantic_results(task_group, audit_records, dataset_orders, "timeout", None))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _fallback_semantic_results(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    status: str,
    exc: BaseException | None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    reason = "语义复核批次超时，已降级为待人工确认。" if status == "timeout" else "语义复核批次失败，已降级为待人工确认。"
    if exc:
        reason = f"{reason} {type(exc).__name__}: {str(exc)[:200]}"
    for task in tasks:
        code = str(task.get("working_order_code") or "")
        result = _build_semantic_task_result(
            task,
            audit_records.get(code, {}),
            dataset_orders.get(code, {}),
            "needs_followup",
            reason,
            0.0,
            {
                "is_complete": False,
                "has_cause": False,
                "has_action": False,
                "has_result": False,
                "problem_description": reason,
                "confidence": 0.0,
                "remark": "",
            },
            [],
            "",
        )
        result["review_status"] = status
        results[code] = result
    return results


def _review_order_description_tasks_batch(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    details_by_code: dict[str, list[dict[str, Any]]],
    rf_forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    if not tasks:
        return {}
    items = []
    for task in tasks:
        code = task.get("working_order_code")
        order = dataset_orders.get(code, {})
        rf_forms = rf_forms_by_code.get(code, [])
        details = details_by_code.get(code, [])
        items.append(
            {
                "working_order_code": code,
                "title": order.get("ORDERTITLE") or order.get("title"),
                "content": order.get("ORDERCONTENT") or order.get("content"),
                "order_type": order.get("DDWORKINGORDERTYPE") or task.get("order_type"),
                "maintenance_type": order.get("MAINTENANCETYPE") or task.get("maintenance_type"),
                "rf_tables": [table for table, _form in rf_forms[:20]],
                "workflow_steps": [_first_present(detail, ["PROCESSSTEP", "STEPNAME", "step_name", "NODENAME", "node_name"]) for detail in details[:20]],
            }
        )
    raw = _call_semantic_llm_json(
        ORDER_DESCRIPTION_BATCH_JSON_PROMPT,
        json.dumps({"items": items}, ensure_ascii=False, default=str),
        context={"review_kind": "order_description_batch", "rule_ids": []},
    )
    parsed_by_code = _batch_results_by_key(raw, "working_order_code")
    results: dict[str, dict[str, Any]] = {}
    for task in tasks:
        code = task.get("working_order_code")
        parsed = _normalize_order_description_result(parsed_by_code.get(str(code), {}))
        remark_review = _remark_review_from_order_description(parsed)
        judgment, conclusion, confidence = _judge_semantic_result("remark_semantics", remark_review, [], task)
        results[str(code)] = _build_semantic_task_result(
            task,
            audit_records.get(code, {}),
            dataset_orders.get(code, {}),
            judgment,
            conclusion,
            confidence,
            remark_review,
            [],
            _compose_review_text(dataset_orders.get(code, {}), details_by_code.get(code, []), rf_forms_by_code.get(code, [])),
            order_description_review=parsed,
        )
    return results


def _review_no_device_tasks_batch(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    details_by_code: dict[str, list[dict[str, Any]]],
    rf_forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    candidates = []
    task_by_item: dict[str, dict[str, Any]] = {}
    for task in tasks:
        for issue in task.get("evidence_summary", {}).get("sample_issues", []):
            if issue.get("rule_id") != "RF_NO_DEVICE_WITHOUT_REMARK":
                continue
            for index, violation in enumerate(_issue_violations(issue)):
                item_id = f"{task.get('working_order_code')}::{index}"
                candidates.append({"item_id": item_id, "working_order_code": task.get("working_order_code"), **violation})
                task_by_item[item_id] = task
    if not candidates:
        return {}
    raw = _call_semantic_llm_json(
        NO_DEVICE_BATCH_JSON_PROMPT,
        json.dumps({"items": candidates}, ensure_ascii=False, default=str),
        context={"review_kind": "no_device_explanation_batch", "rule_id": "RF_NO_DEVICE_WITHOUT_REMARK"},
    )
    parsed_by_item = _batch_results_by_key(raw, "item_id")
    insufficient_by_code: dict[str, list[dict[str, Any]]] = {}
    reviewed_by_code: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        item_id = str(candidate["item_id"])
        parsed = parsed_by_item.get(item_id, {})
        if _is_plain_no_device_situation(candidate.get("situation_value")):
            parsed = {
                **parsed,
                "is_explained": True,
                "reason": "运行情况填写无，按当前口径视为无对应设备。",
                "problem_description": "",
                "confidence": max(_bounded_confidence(parsed.get("confidence"), default=0.0), 0.95),
            }
        confidence = _bounded_confidence(parsed.get("confidence"), default=0.0)
        reviewed = {**candidate, **parsed, "confidence": confidence}
        code = str(candidate.get("working_order_code") or "")
        reviewed_by_code.setdefault(code, []).append(reviewed)
        if confidence >= 0.7 and not bool(parsed.get("is_explained")):
            insufficient_by_code.setdefault(code, []).append(reviewed)

    results: dict[str, dict[str, Any]] = {}
    for code, task in {str(task.get("working_order_code")): task for task in tasks}.items():
        confirmed = insufficient_by_code.get(code, [])
        if confirmed:
            judgment = "confirmed_issue"
            problem_description = _compose_no_device_problem_description(confirmed)
            conclusion = problem_description
            confidence = max(item.get("confidence", 0.0) for item in confirmed)
            remark_review = {
                "is_complete": False,
                "has_cause": False,
                "has_action": False,
                "has_result": False,
                "problem_description": problem_description,
                "confidence": confidence,
                "remark": json.dumps(confirmed, ensure_ascii=False, default=str),
            }
        else:
            judgment = "cleared"
            conclusion = "运行情况已能合理解释型号字段缺失或占位原因。"
            confidence = max([item.get("confidence", 0.0) for item in reviewed_by_code.get(code, [])] or [0.7])
            remark_review = {
                "is_complete": True,
                "has_cause": True,
                "has_action": True,
                "has_result": True,
                "problem_description": "",
                "confidence": confidence,
                "remark": json.dumps(reviewed_by_code.get(code, []), ensure_ascii=False, default=str),
            }
        result = _build_semantic_task_result(
            task,
            audit_records.get(code, {}),
            dataset_orders.get(code, {}),
            judgment,
            conclusion,
            confidence,
            remark_review,
            [],
            json.dumps(reviewed_by_code.get(code, []), ensure_ascii=False, default=str),
        )
        _attach_no_device_rf_context(result, confirmed or reviewed_by_code.get(code, []))
        results[code] = result
        _limit_supported_rule_ids(results[code], "RF_NO_DEVICE_WITHOUT_REMARK")
    return results


def _is_plain_no_device_situation(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = text.replace(" ", "")
    return normalized in {
        "无",
        "无设备",
        "无此设备",
        "无该设备",
        "无对应设备",
        "无能见度设备",
        "无能见度仪",
        "无能见度仪器",
        "未配置",
        "未安装",
        "不适用",
    }


def _attach_no_device_rf_context(result: dict[str, Any], items: list[dict[str, Any]]) -> None:
    if not items:
        return
    item = items[0]
    model_field = str(item.get("model_field") or "").strip()
    result["rf_table"] = "RF_W_OTHERDEVICECHECK"
    if model_field:
        result["rf_field"] = model_field
        result["field"] = f"rf.RF_W_OTHERDEVICECHECK.{model_field}"
        result["rf_record_key"] = "::".join(
            part
            for part in (
                str(result.get("working_order_code") or "").strip(),
                "RF_W_OTHERDEVICECHECK",
                model_field,
            )
            if part
        )
    label = str(item.get("label") or "").strip()
    if label:
        result["field_label"] = label


def _review_remark_tasks_batch(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    details_by_code: dict[str, list[dict[str, Any]]],
    rf_forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    if not tasks:
        return {}
    items = []
    text_by_code = {}
    for task in tasks:
        code = str(task.get("working_order_code") or "")
        text = _compose_review_text(dataset_orders.get(code, {}), details_by_code.get(code, []), rf_forms_by_code.get(code, []))
        text_by_code[code] = text
        items.append(
            {
                "working_order_code": code,
                "semantic_focus": task.get("semantic_focus", []),
                "text": text,
                "evidence_summary": task.get("evidence_summary", {}),
            }
        )
    raw = _call_semantic_llm_json(
        REMARK_BATCH_SEMANTIC_JSON_PROMPT,
        json.dumps({"items": items}, ensure_ascii=False, default=str),
        context={"review_kind": "remark_semantics_batch"},
    )
    parsed_by_code = _batch_results_by_key(raw, "working_order_code")
    results: dict[str, dict[str, Any]] = {}
    for task in tasks:
        code = str(task.get("working_order_code") or "")
        parsed = _normalize_remark_result(parsed_by_code.get(code, {}), text_by_code.get(code, ""))
        judgment, conclusion, confidence = _judge_semantic_result("remark_semantics", parsed, [], task)
        results[code] = _build_semantic_task_result(
            task,
            audit_records.get(code, {}),
            dataset_orders.get(code, {}),
            judgment,
            conclusion,
            confidence,
            parsed,
            [],
            text_by_code.get(code, ""),
        )
    return results


def _compose_no_device_problem_description(items: list[dict[str, Any]]) -> str:
    descriptions = [
        str(item.get("problem_description") or "").strip()
        for item in items
        if str(item.get("problem_description") or "").strip()
    ]
    if descriptions:
        return "；".join(descriptions)

    fallback_parts = []
    for item in items:
        label = str(item.get("label") or "其他设备").strip()
        model_value = str(item.get("model_value") or "<空>").strip()
        situation_value = str(item.get("situation_value") or "<空>").strip()
        reason = str(item.get("reason") or "").strip()
        text = f"{label}型号填写为{model_value}，运行情况为“{situation_value}”"
        if reason:
            text = f"{text}，{reason}"
        else:
            text = f"{text}，未解释型号字段为何缺失或占位。"
        fallback_parts.append(text)
    if fallback_parts:
        return "；".join(fallback_parts)
    return "其他设备型号为占位值，运行情况未解释型号字段为何缺失或占位。"


def _review_pm_tape_usage_tasks_batch(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    details_by_code: dict[str, list[dict[str, Any]]],
    rf_forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    candidates = []
    task_by_item: dict[str, dict[str, Any]] = {}
    issue_by_item: dict[str, dict[str, Any]] = {}
    immediate_results: dict[str, dict[str, Any]] = {}
    for task in tasks:
        code = str(task.get("working_order_code") or "")
        for index, issue in enumerate(_focus_issues(task, "RF_PM_TAPE_USAGE_INVALID")):
            evidence = _issue_evidence(issue)
            value = str(evidence.get("value") or "").strip()
            field = str(evidence.get("field") or issue.get("field") or "PM_CONSUMABLE")
            pollutant_type = str(evidence.get("pollutant_type") or index or "").strip()
            item_id = f"{code}::{pollutant_type or index}::{field}"
            if value in {"", "/"}:
                immediate_results[item_id] = _pm_tape_semantic_result(
                    task,
                    audit_records.get(code, {}),
                    dataset_orders.get(code, {}),
                    issue=issue,
                    is_valid=False,
                    reason=f"{evidence.get('field_label') or '耗材使用/处置字段'}为空或/，无法判断对应耗材状态。",
                    problem_description=f"{evidence.get('field_label') or '耗材使用/处置字段'}为空或/，无法判断对应耗材状态。",
                    evidence_text=value or "<空>",
                )
                continue
            candidates.append(
                {
                    "item_id": item_id,
                    "working_order_code": code,
                    "pollutant_type": evidence.get("pollutant_type"),
                    "device_model": evidence.get("device_model"),
                    "instrument_type": evidence.get("instrument_type"),
                    "field": field,
                    "field_label": evidence.get("field_label"),
                    "field_value": value,
                }
            )
            task_by_item[item_id] = task
            issue_by_item[item_id] = issue

    raw = None
    if candidates:
        raw = _call_semantic_llm_json(
            PM_TAPE_USAGE_BATCH_JSON_PROMPT,
            json.dumps({"items": candidates}, ensure_ascii=False, default=str),
            context={"review_kind": "pm_consumable_usage_batch", "rule_id": "RF_PM_TAPE_USAGE_INVALID"},
        )
    parsed_by_item = _batch_results_by_key(raw, "item_id")
    results: dict[str, dict[str, Any]] = dict(immediate_results)
    for candidate in candidates:
        item_id = str(candidate["item_id"])
        task = task_by_item[item_id]
        code = str(candidate.get("working_order_code") or "")
        issue = issue_by_item[item_id]
        parsed = parsed_by_item.get(item_id, {})
        if not parsed:
            results[item_id] = _pm_tape_semantic_result(
                task,
                audit_records.get(code, {}),
                dataset_orders.get(code, {}),
                issue=issue,
                is_valid=True,
                reason="未完成耗材使用/处置情况语义复核，非空自然语言描述暂不作为最终问题。",
                problem_description="非空自然语言描述尚未完成语义复核，暂不确认为问题。",
                evidence_text=str(candidate.get("field_value") or ""),
                judgment="needs_followup",
            )
            continue
        is_valid = bool(parsed.get("is_valid"))
        results[item_id] = _pm_tape_semantic_result(
            task,
            audit_records.get(code, {}),
            dataset_orders.get(code, {}),
            issue=issue,
            is_valid=is_valid,
            reason=str(parsed.get("reason") or ("耗材使用/处置说明充分。" if is_valid else "耗材使用/处置说明不足。")),
            problem_description=str(
                parsed.get("problem_description")
                or parsed.get("reason")
                or ("" if is_valid else "耗材使用/处置说明不足，无法判断对应耗材状态。")
            ),
            evidence_text=str(candidate.get("field_value") or ""),
        )
    return results


def _pm_tape_semantic_result(
    task: dict[str, Any],
    audit_record: dict[str, Any],
    order: dict[str, Any],
    *,
    issue: dict[str, Any],
    is_valid: bool,
    reason: str,
    problem_description: str,
    evidence_text: str,
    judgment: str | None = None,
) -> dict[str, Any]:
    if judgment is None:
        judgment = "cleared" if is_valid else "confirmed_issue"
    remark_review = {
        "is_complete": is_valid,
        "has_cause": is_valid,
        "has_action": is_valid,
        "has_result": is_valid,
        "problem_description": problem_description,
        "confidence": None,
        "remark": reason,
    }
    evidence = _issue_evidence(issue)
    field_label = evidence.get("field_label") or "耗材使用/处置情况"
    conclusion = f"{field_label}说明充分。" if is_valid else f"{field_label}填写不规范，无法判断对应耗材状态。"
    if judgment == "needs_followup":
        conclusion = "耗材使用/处置情况语义复核未完成，暂不进入最终问题清单。"
    result = _build_semantic_task_result(
        task,
        audit_record,
        order,
        judgment,
        conclusion,
        None,
        remark_review,
        [],
        evidence_text,
    )
    result["field"] = issue.get("field") or evidence.get("field")
    result["rf_table"] = evidence.get("rf_table")
    result["rf_field"] = evidence.get("field")
    result["rf_record_key"] = "::".join(
        part
        for part in [
            str(evidence.get("working_order_code") or "").strip(),
            str(evidence.get("rf_table") or "").strip(),
            str(evidence.get("pollutant_type") or "").strip(),
            str(evidence.get("field") or "").strip(),
        ]
        if part
    )
    result["field_label"] = field_label
    result["pollutant_type"] = evidence.get("pollutant_type")
    result["device_model"] = evidence.get("device_model")
    result["instrument_type"] = evidence.get("instrument_type")
    _limit_supported_rule_ids(result, "RF_PM_TAPE_USAGE_INVALID")
    return result


def _limit_supported_rule_ids(result: dict[str, Any], rule_id: str) -> None:
    if result.get("judgment") == "confirmed_issue":
        result["supported_rule_ids"] = [rule_id]
        result["can_promote_to_final_issue"] = True
    else:
        result["supported_rule_ids"] = []
        result["can_promote_to_final_issue"] = False


def _review_filename_attachment_tasks_batch(
    tasks: list[dict[str, Any]],
    audit_records: dict[str, dict[str, Any]],
    dataset_orders: dict[str, dict[str, Any]],
    details_by_code: dict[str, list[dict[str, Any]]],
    rf_forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    if not tasks:
        return {}
    items = []
    for task in tasks:
        code = str(task.get("working_order_code") or "")
        issue = _first_focus_issue(task, "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING")
        evidence = _issue_evidence(issue)
        required_types = [str(item) for item in evidence.get("required_types", []) if str(item).strip()]
        rf_remarks = _station_maintain_rf_remarks(rf_forms_by_code.get(code, []))
        items.append(
            {
                "working_order_code": code,
                "required_types": required_types,
                "type_definitions": {
                    key: STATION_MAINTAIN_TYPE_DEFINITIONS[key]
                    for key in required_types
                    if key in STATION_MAINTAIN_TYPE_DEFINITIONS
                },
                "filenames": [
                    item.get("name") or item.get("descriptor")
                    for item in evidence.get("sample_attachments", [])
                    if isinstance(item, dict) and (item.get("name") or item.get("descriptor"))
                ],
                "rf_remarks": rf_remarks,
                "exemption_review_required": bool(rf_remarks.strip()),
            }
        )
    raw = _call_semantic_llm_json(
        FILENAME_BATCH_SEMANTIC_JSON_PROMPT,
        json.dumps({"items": items}, ensure_ascii=False, default=str),
        context={"review_kind": "station_maintain_filename_batch"},
    )
    parsed_by_code = _batch_results_by_key(raw, "working_order_code")
    results: dict[str, dict[str, Any]] = {}
    for task in tasks:
        code = str(task.get("working_order_code") or "")
        parsed = parsed_by_code.get(code, {})
        confidence = _bounded_confidence(parsed.get("confidence"), default=0.0)
        missing_types = [str(item) for item in (parsed.get("missing_types") or []) if str(item).strip()]
        if bool(parsed.get("is_exempt")) and confidence >= 0.7:
            judgment = "cleared"
            conclusion = f"站点设备维护现场照片要求已豁免：{parsed.get('exemption_reason') or '语义复核确认存在合理豁免说明'}。"
            remark_review = {
                "is_complete": True,
                "has_cause": True,
                "has_action": True,
                "has_result": True,
                "problem_description": "",
                "confidence": confidence,
                "remark": json.dumps(parsed, ensure_ascii=False, default=str),
            }
        elif confidence >= 0.7 and missing_types:
            judgment = "confirmed_issue"
            conclusion = f"站点设备维护现场照片缺失：{', '.join(missing_types)}。"
            remark_review = {
                "is_complete": False,
                "has_cause": False,
                "has_action": False,
                "has_result": False,
                "problem_description": "站点设备维护现场照片文件名语义未覆盖颗粒物仪器时钟、数据采集仪时钟或过滤网清洗等必需照片类型。",
                "confidence": confidence,
                "remark": json.dumps(parsed, ensure_ascii=False, default=str),
            }
        else:
            judgment = "cleared"
            conclusion = "附件文件名语义已覆盖站点设备维护现场照片要求。"
            remark_review = {
                "is_complete": True,
                "has_cause": True,
                "has_action": True,
                "has_result": True,
                "problem_description": "",
                "confidence": confidence,
                "remark": json.dumps(parsed, ensure_ascii=False, default=str),
            }
        results[code] = _build_semantic_task_result(
            task,
            audit_records.get(code, {}),
            dataset_orders.get(code, {}),
            judgment,
            conclusion,
            confidence,
            remark_review,
            [],
            json.dumps(parsed, ensure_ascii=False, default=str),
        )
    return results


def _station_maintain_rf_remarks(rf_forms: list[tuple[str, dict[str, Any]]]) -> str:
    station_maintain_tables = {
        "RF_M_STATIONDEVICEMAINTAIN",
        "RF_M_StationMaintainCheck",
        "RF_HY_STATIONDEVICEMAINTAIN",
    }
    remark_fields = (
        "REMARK",
        "Remark",
        "remark",
        "REMARKS",
        "Remarks",
        "remarks",
        "DESCRIPTION",
        "Description",
        "DESCRIPTIONTA",
        "SITUATION",
        "Situation",
    )
    remarks: list[str] = []
    for table, form in rf_forms:
        if table not in station_maintain_tables or form.get("_query_error"):
            continue
        for field in remark_fields:
            value = str(form.get(field) or "").strip()
            if value and value not in remarks:
                remarks.append(value)
    return "\n".join(remarks)[:2000]


def _build_semantic_task_result(
    task: dict[str, Any],
    audit_record: dict[str, Any],
    order: dict[str, Any],
    judgment: str,
    conclusion: str,
    confidence: float,
    remark_review: dict[str, Any],
    attachment_reviews: list[dict[str, Any]],
    evidence_text: str,
    *,
    order_description_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_focus = task.get("semantic_focus", [])
    supported_rule_ids = _supported_final_rule_ids(semantic_focus, judgment)
    reviewed_result = {
        "working_order_code": task.get("working_order_code"),
        "station_id": task.get("station_id"),
        "order_type": task.get("order_type"),
        "maintenance_type": task.get("maintenance_type"),
        "finish_time": task.get("finish_time"),
        "review_kind": task.get("review_kind", "remark_semantics"),
        "semantic_focus": semantic_focus,
        "review_status": "completed",
        "judgment": judgment,
        "conclusion": conclusion,
        "confidence": confidence,
        "remark_review": remark_review,
        "order_description_review": order_description_review,
        "attachment_reviews": attachment_reviews,
        "reviewed_attachment_count": len(attachment_reviews),
        "reviewed_issues": _build_reviewed_issue_list(task, remark_review, attachment_reviews, judgment),
        "can_promote_to_final_issue": bool(supported_rule_ids),
        "supported_rule_ids": supported_rule_ids,
        "evidence_text": evidence_text[:2000],
        "evidence_summary": task.get("evidence_summary", {}),
        "source_rules": task.get("semantic_focus", []),
        "matched_rules": task.get("evidence_summary", {}).get("matched_rules", []),
        "audit_level": audit_record.get("audit_level"),
        "workflow_steps": audit_record.get("workflow_steps", []),
    }
    if order:
        reviewed_result["order_title"] = order.get("ORDERTITLE") or order.get("title")
        reviewed_result["order_content"] = order.get("ORDERCONTENT") or order.get("content")
    return reviewed_result


def _batch_results_by_key(raw: dict[str, Any] | None, key: str) -> dict[str, dict[str, Any]]:
    results = raw.get("results", []) if isinstance(raw, dict) else []
    if not isinstance(results, list):
        return {}
    return {
        str(item.get(key)): item
        for item in results
        if isinstance(item, dict) and item.get(key) is not None
    }


def _issue_violations(issue: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        evidence = json.loads(issue.get("evidence") or "{}")
    except Exception:
        return []
    violations = evidence.get("violations") or []
    return [violation for violation in violations if isinstance(violation, dict)]


def _first_focus_issue(task: dict[str, Any], rule_id: str) -> dict[str, Any]:
    for issue in task.get("evidence_summary", {}).get("sample_issues", []):
        if issue.get("rule_id") == rule_id:
            return issue
    return {}


def _focus_issues(task: dict[str, Any], rule_id: str) -> list[dict[str, Any]]:
    return [
        issue
        for issue in task.get("evidence_summary", {}).get("sample_issues", [])
        if issue.get("rule_id") == rule_id
    ]


def _issue_evidence(issue: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(issue.get("evidence") or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _task_with_semantic_focus(task: dict[str, Any], focus: list[str]) -> dict[str, Any]:
    narrowed = dict(task)
    narrowed["semantic_focus"] = focus
    summary = dict(task.get("evidence_summary") or {})
    sample_issues = [
        issue
        for issue in summary.get("sample_issues", [])
        if isinstance(issue, dict) and issue.get("rule_id") in set(focus)
    ]
    summary["matched_rules"] = sorted(set(focus))
    summary["sample_issues"] = sample_issues
    narrowed["evidence_summary"] = summary
    return narrowed


def _call_semantic_llm_json(prompt: str, text: str, *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Call the project-wide LLM service for semantic JSON review."""

    if not getattr(llm_service, "base_url", "") or not getattr(llm_service, "model", ""):
        return None

    user_payload = {
        "prompt": prompt,
        "text": text[:12000],
        "context": context or {},
    }
    full_prompt = (
        "你是运维工单审核语义复核员。你必须只输出一个JSON对象，不要输出解释文字，"
        "不要输出Markdown代码块。\n\n"
        f"{json.dumps(user_payload, ensure_ascii=False)}"
    )
    try:
        parsed = _run_async_llm_json(full_prompt)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _run_async_llm_json(prompt: str) -> dict[str, Any]:
    async def call() -> dict[str, Any]:
        service = LLMService()
        return await asyncio.wait_for(
            service.call_llm_with_json_response(prompt=prompt, max_retries=1),
            timeout=SEMANTIC_LLM_CALL_TIMEOUT_SECONDS,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(call())

    result: dict[str, Any] | None = None
    error: BaseException | None = None

    def runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(call())
        except BaseException as exc:
            error = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout=SEMANTIC_LLM_CALL_TIMEOUT_SECONDS)
    if thread.is_alive():
        raise TimeoutError(f"semantic LLM call exceeded {SEMANTIC_LLM_CALL_TIMEOUT_SECONDS}s")
    if error:
        raise error
    return result or {}


def _normalize_remark_result(raw: dict[str, Any], remark: str) -> dict[str, Any]:
    has_cause = bool(raw.get("has_cause"))
    has_action = bool(raw.get("has_action"))
    has_result = bool(raw.get("has_result"))
    is_complete = bool(raw.get("is_complete")) if "is_complete" in raw else all([has_cause, has_action, has_result])
    confidence = _bounded_confidence(raw.get("confidence"), default=0.75 if is_complete else 0.55)
    problem_description = str(
        raw.get("problem_description")
        or _remark_problem_description(has_cause, has_action, has_result)
    ).strip()
    return {
        "is_complete": is_complete,
        "has_cause": has_cause,
        "has_action": has_action,
        "has_result": has_result,
        "problem_description": problem_description,
        "confidence": confidence,
        "remark": remark,
    }


def _normalize_order_description_result(raw: dict[str, Any]) -> dict[str, Any]:
    is_sufficient = bool(raw.get("is_sufficient"))
    confidence = _bounded_confidence(raw.get("confidence"), default=0.75 if is_sufficient else 0.55)
    return {
        "is_sufficient": is_sufficient,
        "has_task_object": bool(raw.get("has_task_object")),
        "has_task_type": bool(raw.get("has_task_type")),
        "reason": str(raw.get("reason") or "").strip(),
        "problem_description": str(
            raw.get("problem_description")
            or raw.get("reason")
            or "工单主表标题和内容未充分说明作业对象、作业类型或任务目的。"
        ).strip(),
        "confidence": confidence,
    }


def _heuristic_remark_semantic(remark: str) -> dict[str, Any]:
    cause = _contains_any(remark, SEMANTIC_PROFILES["remark_keywords"]["cause"])
    action = _contains_any(remark, SEMANTIC_PROFILES["remark_keywords"]["action"])
    result = _contains_any(remark, SEMANTIC_PROFILES["remark_keywords"]["result"])
    is_complete = cause and action and result
    confidence = 0.7 if is_complete else 0.45 if sum([cause, action, result]) >= 2 else 0.25
    return {
        "is_complete": is_complete,
        "has_cause": cause,
        "has_action": action,
        "has_result": result,
        "problem_description": _remark_problem_description(cause, action, result),
        "confidence": confidence,
        "remark": remark,
    }


def _normalize_attachment_quality_result(raw: dict[str, Any], attachment_type: str, text: str) -> dict[str, Any]:
    issues = raw.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]
    issues = [str(item) for item in issues if str(item).strip()]
    is_complete = bool(raw.get("is_complete")) if "is_complete" in raw else not issues
    if not issues and not is_complete:
        issues = _heuristic_attachment_issues(attachment_type, text)
    return {
        "is_complete": is_complete,
        "issues": issues,
        "problem_description": str(
            raw.get("problem_description")
            or _attachment_problem_description(issues, attachment_type)
        ),
        "confidence": _bounded_confidence(raw.get("confidence"), default=0.75 if is_complete else 0.55),
    }


def _heuristic_attachment_quality(attachment_type: str, text: str) -> dict[str, Any]:
    issues = _heuristic_attachment_issues(attachment_type, text)
    is_complete = not issues
    return {
        "is_complete": is_complete,
        "issues": issues,
        "problem_description": _attachment_problem_description(issues, attachment_type),
        "confidence": 0.7 if is_complete else 0.45,
    }


def _heuristic_attachment_issues(attachment_type: str, text: str) -> list[str]:
    lowered = text.lower()
    issues: list[str] = []
    if attachment_type == "cert":
        if _contains_any(lowered, SEMANTIC_PROFILES["attachment_keywords"]["certificate_cover"]) and not _contains_any(
            lowered,
            ["签章", "章", "证书编号", "有效期", "检定结果", "校准结果", "certificate no", "serial"],
        ):
            issues.append("证书只附封面或首页")
    elif attachment_type == "report":
        has_toc = _contains_any(lowered, SEMANTIC_PROFILES["attachment_keywords"]["report_toc"])
        has_pages = bool(re.search(r"第?\s*\d+\s*页|page\s*\d+", lowered, flags=re.I))
        if has_toc and not has_pages:
            issues.append("报告目录未更新")
    return issues


def _attachment_problem_description(issues: list[str], attachment_type: str) -> str:
    if not issues:
        return "附件内容基本完整。"
    if attachment_type == "cert":
        return "证书附件疑似只包含封面或首页，缺少正文、编号、结论、有效期或签章等完整内容。"
    if attachment_type == "report":
        return "报告附件疑似目录或正文页码不完整，无法证明报告内容完整。"
    return "附件内容不完整或不清晰，无法支持工单结论。"


def _build_evidence_summary(record: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    sample_issues = _sample_issues_covering_rules(issues, limit=8)
    return {
        "audit_level": record.get("audit_level"),
        "issue_count": len(issues),
        "deterministic_issue_count": record.get("deterministic_issue_count", 0),
        "candidate_issue_count": record.get("candidate_issue_count", 0),
        "attachment_count": record.get("attachment_count", 0),
        "attachment_review_rules": record.get("attachment_review_rules", []),
        "workflow_steps": record.get("workflow_steps", []),
        "rf_tables": record.get("rf_tables", []),
        "matched_rules": sorted({issue.get("rule_id") for issue in issues}),
        "sample_issues": sample_issues,
    }


def _sample_issues_covering_rules(issues: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    sample = list(issues[:limit])
    seen_rules = {issue.get("rule_id") for issue in sample}
    for issue in issues[limit:]:
        rule_id = issue.get("rule_id")
        if rule_id in seen_rules:
            continue
        sample.append(issue)
        seen_rules.add(rule_id)
    return sample


def _review_semantic_task(
    task: dict[str, Any],
    audit_record: dict[str, Any],
    order: dict[str, Any],
    details: list[dict[str, Any]],
    rf_forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    semantic_focus = task.get("semantic_focus", [])
    review_kind = task.get("review_kind", "mixed")
    remark_context_text = _compose_review_text(order, details, rf_forms)
    semantic_context = {
        "working_order_code": task.get("working_order_code"),
        "review_kind": review_kind,
        "semantic_focus": semantic_focus,
    }
    order_description_review = None
    if _is_order_description_review(semantic_focus):
        order_description_review = review_order_description_semantic(order, rf_forms, details, context=semantic_context)
        remark_review = _remark_review_from_order_description(order_description_review)
    else:
        remark_review = review_remark_semantic(
            remark_context_text,
            context=semantic_context,
        )
    attachment_reviews = []
    if review_kind in {"attachment_visual", "mixed"} and ATTACHMENT_REVIEW_RULE_IDS.intersection(semantic_focus):
        for attachment in attachments[:12]:
            attachment_review = _review_attachment_by_metadata(attachment)
            if attachment_review:
                attachment_reviews.append(attachment_review)

    judgment, conclusion, confidence = _judge_semantic_result(review_kind, remark_review, attachment_reviews, task)
    reviewed_issues = _build_reviewed_issue_list(task, remark_review, attachment_reviews, judgment)
    reviewed_attachment_count = len(attachment_reviews)
    supported_rule_ids = _supported_final_rule_ids(semantic_focus, judgment)
    reviewed_result = {
        "working_order_code": task.get("working_order_code"),
        "station_id": task.get("station_id"),
        "order_type": task.get("order_type"),
        "maintenance_type": task.get("maintenance_type"),
        "finish_time": task.get("finish_time"),
        "review_kind": review_kind,
        "semantic_focus": semantic_focus,
        "review_status": "completed",
        "judgment": judgment,
        "conclusion": conclusion,
        "confidence": confidence,
        "remark_review": remark_review,
        "order_description_review": order_description_review,
        "attachment_reviews": attachment_reviews,
        "reviewed_attachment_count": reviewed_attachment_count,
        "reviewed_issues": reviewed_issues,
        "can_promote_to_final_issue": bool(supported_rule_ids),
        "supported_rule_ids": supported_rule_ids,
        "evidence_text": remark_context_text[:2000],
        "evidence_summary": task.get("evidence_summary", {}),
        "source_rules": task.get("semantic_focus", []),
        "matched_rules": task.get("evidence_summary", {}).get("matched_rules", []),
        "audit_level": audit_record.get("audit_level"),
        "workflow_steps": audit_record.get("workflow_steps", []),
    }
    if order:
        reviewed_result["order_title"] = order.get("ORDERTITLE") or order.get("title")
        reviewed_result["order_content"] = order.get("ORDERCONTENT") or order.get("content")
    return reviewed_result


def _supported_final_rule_ids(semantic_focus: list[str], judgment: str) -> list[str]:
    if judgment != "confirmed_issue":
        return []
    return sorted({rule_id for rule_id in semantic_focus if rule_id in GENERIC_REMARK_REVIEW_RULE_IDS})


def _is_order_description_review(semantic_focus: list[str]) -> bool:
    return False


def _remark_review_from_order_description(review: dict[str, Any]) -> dict[str, Any]:
    is_sufficient = bool(review.get("is_sufficient"))
    return {
        "is_complete": is_sufficient,
        "has_cause": is_sufficient,
        "has_action": is_sufficient,
        "has_result": is_sufficient,
        "problem_description": review.get("problem_description") or "工单主表描述不足，缺少作业对象、作业类型或任务目的。",
        "confidence": review.get("confidence", 0.0),
        "remark": review.get("reason") or "",
    }


def _compose_review_text(
    order: dict[str, Any],
    details: list[dict[str, Any]],
    rf_forms: list[tuple[str, dict[str, Any]]],
) -> str:
    parts: list[str] = []
    for field in ["ORDERTITLE", "title", "ORDERCONTENT", "content"]:
        value = order.get(field)
        if value and str(value).strip():
            parts.append(str(value).strip())

    for detail in details[:20]:
        for field in ["SUBMITREMARK", "REMARK", "COMMENT", "CONTENT", "PROCESSREMARK"]:
            value = detail.get(field)
            if value and str(value).strip():
                parts.append(str(value).strip())
                break

    for table, form in rf_forms[:12]:
        for field in ["REMARK", "REMARKS", "CleaningRemark", "SUBMITREMARK"]:
            value = form.get(field)
            if value and str(value).strip():
                parts.append(f"{table}:{str(value).strip()}")
                break
        for field, value in form.items():
            if not _is_field_level_explanation_field(field):
                continue
            if value and str(value).strip() and str(value).strip() not in {"/", "-", "无"}:
                parts.append(f"{table}.{field}:{str(value).strip()}")

    return "\n".join(parts).strip()


def _is_field_level_explanation_field(field: Any) -> bool:
    upper = str(field or "").upper()
    tokens = (
        "EXCEPTION",
        "ABNORMAL",
        "HANDLE",
        "HANDLING",
        "PROCESS",
        "DISPOSAL",
        "TREAT",
        "RECORD",
        "REMARK",
        "DESCRIPTION",
        "异常",
        "处理",
        "处置",
        "记录",
        "备注",
        "说明",
    )
    return upper.endswith("ROW") or any(token in upper for token in tokens)


def _first_present(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return value
    return None


def _review_attachment_by_metadata(attachment: dict[str, Any]) -> dict[str, Any] | None:
    source = attachment.get("filepath") or attachment.get("file_path") or attachment.get("file_url")
    filename = str(attachment.get("filename") or "")
    attachment_type = _infer_attachment_type(filename, str(attachment.get("typecode") or ""))
    if source and Path(str(source)).expanduser().exists():
        review = review_attachment_quality(str(source), attachment_type)
        review["source"] = str(source)
        review["filename"] = filename
        review["mode"] = "ocr"
        return review

    issues = _heuristic_attachment_issues(attachment_type, filename)
    return {
        "source": str(source or ""),
        "filename": filename,
        "attachment_type": attachment_type,
        "mode": "metadata",
        "is_complete": not issues,
        "issues": issues,
        "problem_description": _attachment_problem_description(issues, attachment_type) if issues else "附件名称和类型未见明显异常，但未执行OCR复核。",
        "confidence": 0.55 if issues else 0.45,
    }


def _infer_attachment_type(filename: str, typecode: str) -> str:
    text = f"{filename} {typecode}".lower()
    if _contains_any(text, ["证书", "cert", "检定", "校准"]):
        return "cert"
    if _contains_any(text, ["曲线", "线性", "多点", "curve"]):
        return "curve"
    if _contains_any(text, ["照片", "图片", "现场", "photo", "image", "jpg", "jpeg", "png"]):
        return "photo"
    if _contains_any(text, ["报告", "record", "检查单", "维护单", "pdf"]):
        return "report"
    return "general"


def _heuristic_attachment_issues(attachment_type: str, text: str) -> list[str]:
    lowered = text.lower()
    issues: list[str] = []
    if attachment_type == "cert":
        if _contains_any(lowered, ["封面", "首页"]) and not _contains_any(lowered, ["编号", "有效期", "结果", "签章"]):
            issues.append("证书只附封面或首页")
    elif attachment_type == "report":
        if not _contains_any(lowered, ["报告", "record", "检查单", "维护单"]):
            issues.append("附件文件名未明确体现报告属性")
    elif attachment_type == "curve":
        if not _contains_any(lowered, ["曲线", "线性", "多点", "图"]):
            issues.append("附件文件名未明确体现曲线图属性")
    elif attachment_type == "photo":
        if not _contains_any(lowered, ["照片", "图片", "现场", "photo", "image"]):
            issues.append("附件文件名未明确体现现场照片属性")
    return issues


def _judge_semantic_result(
    review_kind: str,
    remark_review: dict[str, Any],
    attachment_reviews: list[dict[str, Any]],
    task: dict[str, Any],
) -> tuple[str, str, float]:
    remark_complete = bool(remark_review.get("is_complete"))
    has_attachment_issue = any(not review.get("is_complete", True) for review in attachment_reviews)
    has_attachment_complete = bool(attachment_reviews) and not has_attachment_issue
    if review_kind == "remark_semantics":
        if _is_order_description_review(task.get("semantic_focus", [])):
            if remark_complete:
                return "cleared", "工单主表描述虽较泛化，但结合工单类型、周期或RF表可支持任务识别。", min(0.92, float(remark_review.get("confidence", 0.7)) + 0.1)
            return "confirmed_issue", "工单主表描述不足，缺少作业对象、作业类型或任务目的。", min(0.92, float(remark_review.get("confidence", 0.6)) + 0.15)
        if remark_complete:
            return "cleared", "备注语义完整，可支持当前语义复核点。", min(0.92, float(remark_review.get("confidence", 0.7)) + 0.1)
        return "confirmed_issue", "备注语义不完整，缺少原因、措施或结果。", min(0.92, float(remark_review.get("confidence", 0.6)) + 0.15)
    if review_kind == "attachment_visual":
        if has_attachment_complete:
            return "cleared", "附件内容未见明显缺陷。", 0.8
        if has_attachment_issue:
            return "confirmed_issue", "附件内容或命名显示存在复核疑点。", 0.78
        return "needs_followup", "附件未能完成有效复核。", 0.55

    if remark_complete and has_attachment_complete:
        return "cleared", "备注与附件均未见明显复核缺陷。", 0.85
    if not remark_complete and has_attachment_issue:
        return "confirmed_issue", "备注和附件均存在复核疑点。", 0.9
    if not remark_complete:
        return "confirmed_issue", "备注语义不完整，需要补充闭环说明。", 0.82
    if has_attachment_issue:
        return "confirmed_issue", "附件复核存在疑点。", 0.8
    return "needs_followup", "语义复核证据不足，需人工确认。", 0.6


def _build_reviewed_issue_list(
    task: dict[str, Any],
    remark_review: dict[str, Any],
    attachment_reviews: list[dict[str, Any]],
    judgment: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    semantic_focus = task.get("semantic_focus", [])
    if remark_review and judgment != "cleared":
        issues.append(
            {
                "kind": "remark",
                "focus": semantic_focus,
                "is_complete": remark_review.get("is_complete"),
                "confidence": remark_review.get("confidence"),
                "problem_description": remark_review.get("problem_description"),
            }
        )
    for review in attachment_reviews:
        if review.get("is_complete", True):
            continue
        issues.append(
            {
                "kind": "attachment",
                "focus": semantic_focus,
                "filename": review.get("filename"),
                "source": review.get("source"),
                "issues": review.get("issues", []),
                "confidence": review.get("confidence"),
            }
        )
    return issues


def _summarize_semantic_review_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"cleared": 0, "confirmed_issue": 0, "needs_followup": 0}
    focus_counts: dict[str, int] = {}
    for result in results:
        judgment = str(result.get("judgment") or "needs_followup")
        counts[judgment] = counts.get(judgment, 0) + 1
        for focus in result.get("semantic_focus", []):
            focus_counts[focus] = focus_counts.get(focus, 0) + 1
    return {
        "judgment_counts": counts,
        "focus_counts": dict(sorted(focus_counts.items(), key=lambda item: item[0])),
        "reviewed_order_count": len(results),
        "confirmed_issue_count": counts.get("confirmed_issue", 0),
        "needs_followup_count": counts.get("needs_followup", 0),
    }


def _group_details_by_order_code(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        code = record.get("WORKINGORDERCODE")
        if not code:
            continue
        grouped.setdefault(str(code), []).append(record)
    return grouped


def _group_rf_forms_by_order_code(rf_forms: dict[str, list[dict[str, Any]]]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for table, rows in rf_forms.items():
        for row in rows:
            code = row.get("WORKINGORDERCODE")
            if not code:
                continue
            grouped.setdefault(str(code), []).append((table, row))
    return grouped


def _group_attachments_by_order_code(
    attachments: list[dict[str, Any]],
    wo_commonfile: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in list(attachments) + list(wo_commonfile):
        code = record.get("refid") or record.get("REFID")
        if not code:
            continue
        grouped.setdefault(str(code), []).append(record)
    return grouped


def _confidence_hint(record: dict[str, Any], issues: list[dict[str, Any]]) -> float:
    score = 0.5
    if record.get("attachment_review_required"):
        score += 0.2
    if any(issue.get("rule_id", "").startswith("ATTACHMENT_") for issue in issues):
        score += 0.15
    if any(issue.get("severity") == "高" for issue in issues):
        score += 0.1
    return round(min(score, 0.95), 2)


def _ocr_provider_for_attachment_type(attachment_type: str) -> str:
    if attachment_type in {"cert", "report"}:
        return "document"
    if attachment_type == "table":
        return "table"
    return "general"


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(str(keyword).lower() in lowered for keyword in keywords)


def _first_date_text(text: str) -> str:
    for pattern in SEMANTIC_PROFILES.get("date_patterns", []):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def _extract_numeric_text(text: str) -> float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _format_number(value: float) -> str:
    if math.isfinite(value) and float(value).is_integer():
        return str(int(value))
    return f"{value:.6g}"


def _remark_problem_description(has_cause: bool, has_action: bool, has_result: bool) -> str:
    missing = []
    if not has_cause:
        missing.append("原因")
    if not has_action:
        missing.append("处置措施")
    if not has_result:
        missing.append("处理结果")
    if not missing:
        return "备注已覆盖原因、处置措施和处理结果。"
    return f"备注未说明{ '、'.join(missing) }。"


def _bounded_confidence(value: Any, *, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return round(min(max(score, 0.0), 0.99), 2)


def _cache_key(prefix: str, text: str, context: dict[str, Any] | None) -> str:
    payload = json.dumps({"prefix": prefix, "text": text, "context": context or {}}, ensure_ascii=False, sort_keys=True)
    return sha1(payload.encode("utf-8")).hexdigest()


def _cache_store(key: str, value: dict[str, Any]) -> None:
    if len(_SEMANTIC_CACHE) >= _SEMANTIC_CACHE_LIMIT:
        _SEMANTIC_CACHE.pop(next(iter(_SEMANTIC_CACHE)))
    _SEMANTIC_CACHE[key] = dict(value)
