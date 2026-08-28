from pathlib import Path

from app.agent.selection_context import load_skill_selection
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "backend/docs/skills/ops_work_order_audit.md"
REPORT_REFERENCE_PATH = (
    REPO_ROOT
    / "backend/docs/skills/ops_work_order_audit/references/report-format.md"
)
REVIEW_REFERENCE_PATH = (
    REPO_ROOT
    / "backend/docs/skills/ops_work_order_audit/references/final-review.md"
)


def test_shared_ops_audit_skill_is_concise_and_uses_progressive_references():
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert len(content.splitlines()) < 100
    assert "ops_audit_fetch_dataset" in content
    assert "ops_audit_run_rules" in content
    assert "backend/docs/skills/ops_work_order_audit/references/final-review.md" in content
    assert "backend/docs/skills/ops_work_order_audit/references/report-format.md" in content
    assert "RF_CREATEDATE_EMPTY" not in content
    assert "common_patterns" not in content


def test_shared_ops_audit_skill_frontmatter_is_visible_to_skill_listing():
    name, description = ListSkillsTool()._parse_skill_file(SKILL_PATH)
    selection = load_skill_selection("ops_work_order_audit", skills_dir=SKILL_PATH.parent)

    assert name == "运维工单审核分析技能"
    assert "正式审核报告" in description
    assert selection.skill_id == "ops_work_order_audit"
    assert "read_file" in selection.required_tools


def test_shared_ops_audit_report_and_review_contracts_are_preserved():
    report_reference = REPORT_REFERENCE_PATH.read_text(encoding="utf-8")
    review_reference = REVIEW_REFERENCE_PATH.read_text(encoding="utf-8")

    assert "按 `operation_unit` 运维单位分组" in report_reference
    assert "| 站点 | 中文表单 | 工单号 | 问题描述 | 备注状态 | 原始备注/说明 | 命中规则 |" in report_reference
    assert "不得只把备注藏在 `evidence` JSON" in report_reference
    assert "公式复算类问题必须列出实填值、复算值、容差/允许偏差和关键输入字段" in report_reference
    assert "表单与附件/XLS 比对问题必须列出附件文件名、表单字段、表单值、附件单元格和值" in report_reference
    assert "不得向用户展示内部英文表名 `rf_table`" in report_reference
    assert "必须完整列出所有保留问题" in report_reference
    assert "RF_DEVICE_IDENTITY_INCONSISTENT" in report_reference
    assert "issue_id" in review_reference
    assert "report_input_path" in review_reference
    assert "report_input.items" in review_reference
