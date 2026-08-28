"""Rule scheduling and inspection helpers for operations work order audits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ops_audit.config import load_rule_catalog, rules_for_review_stage
from app.services.ops_audit.evidence_builder import build_dataset_evidence, build_inspection_item
from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.review_artifacts import REVIEW_INPUT_FILENAME, build_review_input, persist_review_input
from app.services.ops_audit.semantic.reviewer import build_semantic_review_results, build_semantic_review_tasks
from app.services.ops_audit.semantic_candidates import build_semantic_candidates
from app.services.ops_audit.visual_evidence import archive_visual_evidence
from app.services.ops_work_order_audit_engine import OUTPUT_DIR, audit_dataset


def list_rule_catalog() -> dict[str, Any]:
    """Return rule catalog metadata for tools and calibration."""

    rules = load_rule_catalog()
    return {
        "success": True,
        "rule_count": len(rules),
        "rules": rules,
    }


def run_rule_engine(
    dataset: dict[str, Any],
    *,
    output_dir: Path | None = None,
    persist_outputs: bool = True,
    evidence_level: str = "summary",
    enable_visual: bool = True,
) -> dict[str, Any]:
    """Run deterministic rules, classify issues, and persist audit outputs."""

    output_dir = (output_dir or OUTPUT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = audit_dataset(
        dataset,
        enable_visual=enable_visual,
        visual_evidence_dir=output_dir / "visual_evidence" / "multipoint_curves",
    )
    audit["evidence"] = build_dataset_evidence(dataset, audit=audit, evidence_level=evidence_level)
    semantic_candidates = build_semantic_candidates(audit)
    semantic_review_tasks = build_semantic_review_tasks(audit)
    semantic_review_results = build_semantic_review_results(audit, dataset)
    visual_evidence = archive_visual_evidence(audit, output_dir)
    final_issue_list = build_final_issue_list(audit, semantic_review_results)

    audit_path = output_dir / "latest_finished_work_orders_deterministic_audit.json"
    candidates_path = output_dir / "latest_finished_work_orders_semantic_candidates.json"
    semantic_review_path = output_dir / "latest_finished_work_orders_semantic_review_tasks.json"
    semantic_review_results_path = output_dir / "latest_finished_work_orders_semantic_review_results.json"
    final_issue_list_path = output_dir / "latest_finished_work_orders_final_issue_list.json"
    review_input_path = output_dir / REVIEW_INPUT_FILENAME

    if persist_outputs:
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        candidates_path.write_text(json.dumps(semantic_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        semantic_review_path.write_text(json.dumps(semantic_review_tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        semantic_review_results_path.write_text(json.dumps(semantic_review_results, ensure_ascii=False, indent=2), encoding="utf-8")
        final_issue_list_path.write_text(json.dumps(final_issue_list, ensure_ascii=False, indent=2), encoding="utf-8")
        review_input = persist_review_input(final_issue_list, review_input_path)
    else:
        review_input = build_review_input(final_issue_list)

    return {
        "success": True,
        "audit_result_path": str(audit_path),
        "semantic_candidates_path": str(candidates_path),
        "semantic_review_tasks_path": str(semantic_review_path),
        "semantic_review_results_path": str(semantic_review_results_path),
        "final_issue_list_path": str(final_issue_list_path),
        "review_input_path": str(review_input_path),
        "review_source_sha256": review_input.get("source", {}).get("sha256") if review_input else None,
        "visual_evidence_manifest_path": visual_evidence["manifest_path"],
        "summary": audit.get("summary", {}),
        "audit_info": audit.get("audit_info", {}),
        "enable_visual": enable_visual,
        "semantic_candidate_count": semantic_candidates.get("candidate_count", 0),
        "semantic_review_task_count": semantic_review_tasks.get("task_count", 0),
        "semantic_review_result_count": semantic_review_results.get("result_count", 0),
        "final_issue_count": final_issue_list.get("issue_count", 0),
        "final_affected_order_count": final_issue_list.get("affected_order_count", 0),
        "visual_evidence_success_count": visual_evidence["success_count"],
        "visual_evidence_failed_count": visual_evidence["failed_count"],
        "device_consistency_issue_count": audit.get("summary", {}).get("device_consistency_issue_count", 0),
        "attachment_review_candidate_count": audit.get("summary", {}).get("attachment_review_candidate_count", 0),
        "attachment_issue_count": audit.get("summary", {}).get("attachment_issue_count", 0),
        "common_patterns": [],
        "business_review": _business_review_summary(audit),
        "semantic_review_results": semantic_review_results,
        "final_issue_list": final_issue_list,
        "representative_issues": _representative_issues(audit, limit=12),
    }


def inspect_rule_engine(
    audit_result_path: Path,
    *,
    dataset_path: Path | None = None,
    mode: str = "sample_rule",
    working_order_code: str | None = None,
    rule_id: str | None = None,
    risk_level: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Inspect audit outputs and build evidence-focused samples."""

    audit = json.loads(audit_result_path.resolve().read_text(encoding="utf-8"))
    dataset = json.loads(dataset_path.resolve().read_text(encoding="utf-8")) if dataset_path else None
    records = audit.get("records", [])

    if mode == "rules":
        return list_rule_catalog()
    if mode == "order":
        selected = [record for record in records if record.get("working_order_code") == working_order_code]
    elif mode == "risk":
        selected = [record for record in records if record.get("audit_level") == risk_level]
    elif mode == "semantic_candidates":
        semantic_rule_ids = rules_for_review_stage("semantic_remark")
        selected = [
            record
            for record in records
            if any(
                issue.get("rule_id") in semantic_rule_ids
                for issue in record.get("scoring_issues", [])
            )
        ]
    elif mode == "review_samples":
        sample_items = _review_samples(audit, dataset, limit=max(1, min(int(limit or 10), 50)))
        return {"success": True, "mode": mode, "count": len(sample_items), "items": sample_items}
    elif mode == "semantic_review_results":
        results = _load_semantic_review_results(audit, audit_result_path)
        selected = results.get("results", [])[: max(1, min(int(limit or 10), 50))]
        return {
            "success": True,
            "mode": mode,
            "count": len(selected),
            "summary": results.get("summary", {}),
            "items": selected,
        }
    else:
        selected = [record for record in records if any(issue.get("rule_id") == rule_id for issue in record.get("issues", []))]

    selected = selected[: max(1, min(int(limit or 10), 50))]
    items = [build_inspection_item(record, dataset, focus_rule_id=rule_id if mode == "sample_rule" else None) for record in selected]
    return {
        "success": True,
        "mode": mode,
        "count": len(items),
        "items": items,
    }


def _business_review_summary(audit: dict[str, Any]) -> dict[str, Any]:
    records = audit.get("records", [])
    confirmed_rules: dict[str, dict[str, Any]] = {}
    candidate_rules: dict[str, dict[str, Any]] = {}
    calibration_rules: dict[str, dict[str, Any]] = {}

    for record in records:
        for issue in record.get("issues", []):
            target = candidate_rules
            assessment = issue.get("assessment")
            if assessment == "deterministic_issue":
                target = confirmed_rules
            rule_id = issue.get("rule_id") or "<unknown>"
            entry = target.setdefault(
                rule_id,
                {
                    "rule_id": rule_id,
                    "message": issue.get("message"),
                    "severity": issue.get("severity"),
                    "category": issue.get("category"),
                    "hit_count": 0,
                    "affected_order_codes": set(),
                    "sample_order_codes": [],
                },
            )
            entry["hit_count"] += 1
            code = record.get("working_order_code")
            if code:
                entry["affected_order_codes"].add(code)
                if len(entry["sample_order_codes"]) < 5 and code not in entry["sample_order_codes"]:
                    entry["sample_order_codes"].append(code)

    return {
        "confirmed_issues": _finalize_rule_group(confirmed_rules),
        "candidate_issues": _finalize_rule_group(candidate_rules),
        "calibration_items": [],
        "recommended_next_steps": [
            "先处理 confirmed_issues 中的确定性规则问题。",
            "对 candidate_issues 抽样查看 RF 表、流程备注和附件后再批量定性。",
        ],
    }


def _finalize_rule_group(group: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    finalized = []
    for item in group.values():
        order_codes = item.pop("affected_order_codes")
        item["affected_order_count"] = len(order_codes)
        finalized.append(item)
    return sorted(finalized, key=lambda item: (item["affected_order_count"], item["hit_count"]), reverse=True)


def _representative_issues(audit: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    representatives = []
    seen_rules: set[str] = set()
    for record in audit.get("records", []):
        if not (record.get("deterministic_issues") or record.get("candidate_issues") or record.get("issues")):
            continue
        issue = (record.get("deterministic_issues") or record.get("candidate_issues") or record.get("issues"))[0]
        rule_id = issue.get("rule_id")
        if rule_id in seen_rules and len(representatives) >= limit:
            continue
        seen_rules.add(rule_id)
        representatives.append(
            {
                "working_order_code": record.get("working_order_code"),
                "station_id": record.get("station_id"),
                "order_type": record.get("order_type"),
                "audit_level": record.get("audit_level"),
                "matched_rule": issue,
                "matched_rule_count": len(record.get("issues", [])),
                "workflow_steps": record.get("workflow_steps", []),
                "rf_tables": record.get("rf_tables", []),
            }
        )
        if len(representatives) >= limit:
            break
    return representatives


def _review_samples(audit: dict[str, Any], dataset: dict[str, Any] | None, limit: int) -> list[dict[str, Any]]:
    business_review = _business_review_summary(audit)
    records = audit.get("records", [])
    samples = []
    per_group_limit = max(1, limit // 3)
    groups = [
        ("confirmed_issues", "硬性结构或逻辑问题，可作为整改清单候选。"),
        ("candidate_issues", "待确认问题，需要结合流程、RF 表和语义判断复核。"),
    ]
    for group_name, review_hint in groups:
        for rule in business_review.get(group_name, [])[:per_group_limit]:
            rule_id = rule.get("rule_id")
            matched = [
                record
                for record in records
                if any(issue.get("rule_id") == rule_id for issue in record.get("issues", []))
            ][:2]
            samples.append(
                {
                    "group": group_name,
                    "rule": rule,
                    "review_hint": review_hint,
                    "samples": [build_inspection_item(record, dataset, focus_rule_id=rule_id) for record in matched],
                }
            )
            if len(samples) >= limit:
                return samples
    return samples


def _load_semantic_review_results(audit: dict[str, Any], audit_result_path: Path) -> dict[str, Any]:
    embedded = audit.get("semantic_review_results")
    if isinstance(embedded, dict) and embedded.get("results"):
        return embedded
    candidate_path = audit_result_path.with_name("latest_finished_work_orders_semantic_review_results.json")
    if candidate_path.exists():
        try:
            return json.loads(candidate_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"result_count": 0, "results": [], "summary": {}}
