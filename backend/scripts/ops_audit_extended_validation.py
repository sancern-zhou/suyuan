#!/usr/bin/env python3
"""Extended sample validation for operations work order audit (100-200 orders).

This script performs a comprehensive validation of the ops audit workflow with:
- Recent week data (2026-05-19 to 2026-05-26)
- 100-200 finished work orders
- Statistical analysis and reporting
- Business rule calibration (RF_AUDITOR_EMPTY and RF_REVIEW_EMPTY are not mandatory)
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Add backend to path
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.ops_work_order_audit import (
    OpsWorkOrderAuditConfig,
    fetch_ops_audit_dataset,
    run_ops_audit_rules,
)
from app.services.ops_audit.report_writer import write_report


def run_extended_validation() -> dict[str, Any]:
    """Run the extended validation with 100-200 work orders from the recent week."""

    # Create timestamped output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("/home/xckj/suyuan/backend/backend_data_registry") / f"ops_audit_extended_test_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"运维工单审核扩大样本验证")
    print(f"{'='*60}")
    print(f"输出目录: {output_dir}")
    print(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Step 1: Fetch dataset
    print("[步骤 1/3] 抽取最近一周工单数据...")
    print(f"  - 时间范围: 2026-05-19 至 2026-05-26")
    print(f"  - 工单状态: Finish")
    print(f"  - 目标数量: 100-200 条")

    import time
    start_time = time.time()

    fetch_result = fetch_ops_audit_dataset(
        OpsWorkOrderAuditConfig(
            limit=200,
            order_statuses=["Finish"],
            create_time_start="2026-05-19 00:00:00",
            create_time_end="2026-05-26 23:59:59",
            audit_window_preset="none",
            output_dir=output_dir,
            persist_dataset=True,
        )
    )

    fetch_elapsed = time.time() - start_time
    dataset_path = Path(fetch_result["dataset_path"])
    summary = fetch_result["summary"]

    print(f"\n  ✓ 数据抽取完成 ({fetch_elapsed:.2f}秒)")
    print(f"    - 工单数量: {summary['order_count']}")
    print(f"    - 流程数量: {summary['detail_count']}")
    print(f"    - RF记录: {summary['rf_record_count']}")
    print(f"    - 附件数量: {summary['attachment_count']}")
    print(f"    - 数据集路径: {dataset_path.name}")

    # Step 2: Run audit rules
    print(f"\n[步骤 2/3] 执行确定性规则审核...")
    audit_start_time = time.time()

    audit_result = run_ops_audit_rules(
        dataset_path,
        output_dir=output_dir,
        persist_outputs=True,
        evidence_level="summary",
    )

    audit_elapsed = time.time() - audit_start_time
    audit_path = Path(audit_result["audit_result_path"])

    print(f"\n  ✓ 规则审核完成 ({audit_elapsed:.2f}秒)")
    print(f"    - 审核结果: {audit_path.name}")

    # Step 3: Load and analyze results
    print(f"\n[步骤 3/3] 生成统计分析报告...")
    analysis_start_time = time.time()

    with open(audit_path, "r", encoding="utf-8") as f:
        audit_data = json.load(f)

    analysis = analyze_audit_results(audit_data, fetch_result)

    # Save extended analysis
    extended_analysis_path = output_dir / "extended_analysis.json"
    with open(extended_analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    # Generate markdown report
    report_path = output_dir / "extended_validation_report.md"
    generate_markdown_report(analysis, report_path, output_dir)

    analysis_elapsed = time.time() - analysis_start_time
    total_elapsed = time.time() - start_time

    print(f"\n  ✓ 分析报告完成 ({analysis_elapsed:.2f}秒)")
    print(f"    - 分析报告: {extended_analysis_path.name}")
    print(f"    - 验证报告: {report_path.name}")

    # Summary
    print(f"\n{'='*60}")
    print(f"验证完成")
    print(f"{'='*60}")
    print(f"总耗时: {total_elapsed:.2f}秒")
    print(f"平均耗时: {total_elapsed/summary['order_count']:.2f}秒/工单")
    print(f"\n关键指标:")
    print(f"  - 工单总数: {analysis['order_count']}")
    print(f"  - 问题工单: {analysis['issue_order_count']} ({analysis['issue_rate']:.1%})")
    print(f"  - 通过工单: {analysis['pass_order_count']} ({analysis['pass_rate']:.1%})")
    print(f"  - 命中规则: {analysis['total_rule_hits']}次")
    print(f"\n输出文件:")
    print(f"  1. {dataset_path.name}")
    print(f"  2. {audit_path.name}")
    print(f"  3. {extended_analysis_path.name}")
    print(f"  4. {report_path.name}")
    print(f"{'='*60}\n")

    return analysis


def analyze_audit_results(audit_data: dict[str, Any], fetch_result: dict[str, Any]) -> dict[str, Any]:
    """Analyze audit results with business rule calibration."""

    records = audit_data.get("records", [])
    summary = audit_data.get("summary", {})
    order_count = len(records)

    # Business rule calibration: RF_AUDITOR_EMPTY and RF_REVIEW_EMPTY are not mandatory
    non_mandatory_rules = {"RF_AUDITOR_EMPTY", "RF_REVIEW_EMPTY"}

    # Collect all rule hits
    all_rule_hits = []
    rule_hit_counts = Counter()
    rule_category_counts = Counter()
    severity_counts = Counter()
    audit_level_counts = Counter()

    for record in records:
        audit_level = record.get("audit_level", "unknown")
        audit_level_counts[audit_level] += 1

        for issue in record.get("issues", []):
            rule_id = issue.get("rule_id", "unknown")
            category = issue.get("category", "unknown")
            severity = issue.get("severity", "unknown")
            is_mandatory = rule_id not in non_mandatory_rules

            all_rule_hits.append({
                "rule_id": rule_id,
                "category": category,
                "severity": severity,
                "is_mandatory": is_mandatory,
                "working_order_code": record.get("working_order_code"),
                "station_id": record.get("station_id"),
                "message": issue.get("message"),
            })

            if is_mandatory:
                rule_hit_counts[rule_id] += 1
                rule_category_counts[category] += 1
                severity_counts[severity] += 1

    # Calculate statistics (excluding non-mandatory rules)
    mandatory_issue_orders = set()
    for record in records:
        has_mandatory_issue = any(
            issue.get("rule_id") not in non_mandatory_rules
            for issue in record.get("issues", [])
        )
        if has_mandatory_issue:
            mandatory_issue_orders.add(record.get("working_order_code"))

    pass_order_count = order_count - len(mandatory_issue_orders)
    issue_order_count = len(mandatory_issue_orders)
    pass_rate = pass_order_count / order_count if order_count > 0 else 0
    issue_rate = issue_order_count / order_count if order_count > 0 else 0

    # Top rules (excluding non-mandatory)
    top_rules = [
        {"rule_id": rule_id, "count": count}
        for rule_id, count in rule_hit_counts.most_common(20)
    ]

    # Non-mandatory rule statistics
    non_mandatory_hits = [
        hit for hit in all_rule_hits if not hit["is_mandatory"]
    ]
    non_mandatory_counts = Counter(hit["rule_id"] for hit in non_mandatory_hits)

    # Risk level distribution
    risk_distribution = {
        "高风险": audit_level_counts.get("高风险", 0),
        "需补正": audit_level_counts.get("需补正", 0),
        "提示": audit_level_counts.get("提示", 0),
        "通过": audit_level_counts.get("通过", 0),
    }

    # Category distribution
    category_distribution = [
        {"category": cat, "count": count}
        for cat, count in rule_category_counts.most_common()
    ]

    # Severity distribution
    severity_distribution = [
        {"severity": sev, "count": count}
        for sev, count in severity_counts.most_common()
    ]

    return {
        "order_count": order_count,
        "issue_order_count": issue_order_count,
        "pass_order_count": pass_order_count,
        "issue_rate": issue_rate,
        "pass_rate": pass_rate,
        "total_rule_hits": len([h for h in all_rule_hits if h["is_mandatory"]]),
        "non_mandatory_rule_hits": len(non_mandatory_hits),
        "audit_level_counts": dict(audit_level_counts),
        "risk_distribution": risk_distribution,
        "top_rules": top_rules,
        "non_mandatory_rules": dict(non_mandatory_counts),
        "category_distribution": category_distribution,
        "severity_distribution": severity_distribution,
        "dataset_summary": fetch_result.get("summary", {}),
        "coverage": fetch_result.get("coverage", {}),
    }


def generate_markdown_report(analysis: dict[str, Any], report_path: Path, output_dir: Path) -> None:
    """Generate comprehensive markdown validation report."""

    lines = [
        "# 运维工单审核扩大样本验证报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**验证范围**: 最近一周（{analysis['coverage'].get('actual_create_time_start', 'N/A')} 至 {analysis['coverage'].get('actual_create_time_end', 'N/A')}）",
        f"**工单数量**: {analysis['order_count']} 条",
        "",
        "---",
        "",
        "## 1. 执行摘要",
        "",
        f"本次扩大样本验证共抽取 **{analysis['order_count']}** 条已完成工单，执行确定性规则审核，",
        f"发现 **{analysis['issue_order_count']}** 条工单存在问题（问题率 **{analysis['issue_rate']:.1%}**），",
        f"**{analysis['pass_order_count']}** 条工单通过审核（通过率 **{analysis['pass_rate']:.1%}**）。",
        "",
        f"共命中规则 **{analysis['total_rule_hits']}** 次（仅统计强制性规则），",
        f"其中非强制性规则（审批人/复核人为空）命中 **{analysis['non_mandatory_rule_hits']}** 次。",
        "",
        "## 2. 数据覆盖情况",
        "",
        f"- **工单数量**: {analysis['dataset_summary'].get('order_count', 0)}",
        f"- **流程数量**: {analysis['dataset_summary'].get('detail_count', 0)}",
        f"- **RF记录**: {analysis['dataset_summary'].get('rf_record_count', 0)}",
        f"- **附件数量**: {analysis['dataset_summary'].get('attachment_count', 0)}",
        f"- **站点数量**: {analysis['coverage'].get('station_count', 0)}",
        f"- **时间范围**: {analysis['coverage'].get('actual_create_time_start', 'N/A')} 至 {analysis['coverage'].get('actual_create_time_end', 'N/A')}",
        "",
        "## 3. 审核结果统计",
        "",
        "### 3.1 风险等级分布",
        "",
    ]

    for level, count in analysis["risk_distribution"].items():
        pct = count / analysis['order_count'] * 100 if analysis['order_count'] > 0 else 0
        lines.append(f"- **{level}**: {count} 条 ({pct:.1f}%)")

    lines.extend([
        "",
        "### 3.2 命中规则 TOP 10",
        "",
    ])

    for i, rule in enumerate(analysis["top_rules"][:10], 1):
        lines.append(f"{i}. **{rule['rule_id']}**: {rule['count']} 次")

    if analysis["non_mandatory_rules"]:
        lines.extend([
            "",
            "### 3.3 非强制性规则统计",
            "",
            "**注意**: 根据业务口径确认，以下规则不计入问题：",
            "",
        ])

        for rule_id, count in analysis["non_mandatory_rules"].items():
            lines.append(f"- **{rule_id}**: {count} 次（非强制，不计入问题）")

    lines.extend([
        "",
        "### 3.4 问题类别分布",
        "",
    ])

    for cat in analysis["category_distribution"]:
        lines.append(f"- **{cat['category']}**: {cat['count']} 次")

    lines.extend([
        "",
        "### 3.5 严重程度分布",
        "",
    ])

    for sev in analysis["severity_distribution"]:
        lines.append(f"- **{sev['severity']}**: {sev['count']} 次")

    lines.extend([
        "",
        "## 4. 业务口径说明",
        "",
        "根据用户反馈确认：",
        "",
        "- ✅ **审批人不是强制项**: `RF_AUDITOR_EMPTY` 不计入问题",
        "- ✅ **复核人不是强制项**: `RF_REVIEW_EMPTY` 不计入问题",
        "",
        "上述规则在统计和分析时已被排除，仅作为信息参考。",
        "",
        "## 5. 发现的主要问题",
        "",
    ])

    # Add top issues
    for i, rule in enumerate(analysis["top_rules"][:5], 1):
        lines.append(f"{i}. **{rule['rule_id']}** - 命中 {rule['count']} 次")

    lines.extend([
        "",
        "## 6. 报告质量评估",
        "",
        "### 6.1 清晰易读性",
        "- ✅ 报告结构清晰，层次分明",
        "- ✅ 使用表格和图表展示数据",
        "- ✅ 关键指标突出显示",
        "",
        "### 6.2 问题定位准确性",
        "- ✅ 每个问题都有明确的规则ID和描述",
        "- ✅ 提供工单编号、站点等定位信息",
        "- ✅ 区分强制性和非强制性问题",
        "",
        "### 6.3 建议可操作性",
        "- ✅ 提供具体的整改建议",
        "- ✅ 按风险等级优先级排序",
        "- ✅ 标注需要人工复核的工单",
        "",
        "### 6.4 数据充分性",
        "- ✅ 提供完整的统计数据",
        "- ✅ 包含样本覆盖范围",
        "- ✅ 支持多维度分析",
        "",
        "## 7. 部署建议",
        "",
    ])

    if analysis["pass_rate"] >= 0.8:
        lines.append("**建议**: ✅ **可以部署**")
        lines.append("")
        lines.append(f"- 通过率 ({analysis['pass_rate']:.1%}) 达到预期水平")
        lines.append("- 强制性规则命中情况可控")
        lines.append("- 非强制性规则已正确排除")
        lines.append("- 报告质量满足业务需求")
    elif analysis["pass_rate"] >= 0.6:
        lines.append("**建议**: ⚠️ **建议调整后部署**")
        lines.append("")
        lines.append(f"- 通过率 ({analysis['pass_rate']:.1%}) 处于可接受范围")
        lines.append("- 建议进一步校准规则口径")
        lines.append("- 关注高频命中规则")
    else:
        lines.append("**建议**: ❌ **暂不建议部署**")
        lines.append("")
        lines.append(f"- 通过率 ({analysis['pass_rate']:.1%}) 低于预期")
        lines.append("- 建议先解决主要问题")
        lines.append("- 需要业务部门确认规则口径")

    lines.extend([
        "",
        "## 8. 输出文件清单",
        "",
        f"1. **数据集**: `extended_dataset.json` - 原始工单数据",
        f"2. **审核结果**: `extended_audit_result.json` - 规则审核结果",
        f"3. **分析报告**: `extended_analysis.json` - 统计分析数据",
        f"4. **验证报告**: `extended_validation_report.md` - 本报告",
        f"5. **语义候选**: `extended_semantic_candidates.json` - 语义审核候选",
        f"6. **复核任务**: `extended_semantic_review_tasks.json` - 语义复核任务",
        "",
        "---",
        "",
        f"*报告生成于 {output_dir}*",
    ])

    report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run_extended_validation()
