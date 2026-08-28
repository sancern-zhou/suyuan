from pathlib import Path

from app.agent.selection_context import active_skills_dir, load_skill_selection
from app.project_config.loader import load_project_context
from app.project_config.paths import project_skills_dir
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from config.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_jiangsu_skill_directory_contains_only_project_skills():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)
    skills_dir = project_skills_dir(context)

    selection = load_skill_selection("station-alarm-diagnosis", skills_dir=skills_dir)
    assert selection.skill_id == "station-alarm-diagnosis"
    assert "江苏站点告警诊断" in selection.content
    audit_selection = load_skill_selection("ops-work-order-audit", skills_dir=skills_dir)
    assert audit_selection.skill_id == "ops-work-order-audit"
    assert "运维工单审核" in audit_selection.content
    assert "references/report-format.md" in audit_selection.content
    try:
        load_skill_selection("ops_work_order_audit", skills_dir=skills_dir)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("shared skills must not be visible to Jiangsu")


def test_runtime_skill_resolution_uses_the_jiangsu_directory(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    tool = ListSkillsTool()
    assert tool.skills_dir == active_skills_dir()

    result = __import__("asyncio").run(tool.execute())

    assert result["success"] is True
    assert result["data"]["count"] == 2
    files = {item["file"] for item in result["data"]["skills"]}
    assert any(path.endswith("station-alarm-diagnosis/SKILL.md") for path in files)
    assert any(path.endswith("ops-work-order-audit/SKILL.md") for path in files)


def test_ops_audit_report_reference_preserves_output_contract():
    report_reference = (
        REPO_ROOT
        / "projects/jiangsu-ops/skills/ops-work-order-audit/references/report-format.md"
    ).read_text(encoding="utf-8")

    assert "retained_items" in report_reference
    assert "按 `operation_unit` 运维单位分组" in report_reference
    assert "| 站点 | 中文表单 | 工单号 | 问题描述 | 原始备注/说明 | 命中规则 |" in report_reference
    assert "结论与整改建议" not in report_reference
    assert "不得只把备注藏在 `evidence` JSON" in report_reference
    assert "公式复算类问题必须列出实填值、复算值、容差/允许偏差和关键输入字段" in report_reference
    assert "表单与附件/XLS 比对问题必须列出附件文件名、表单字段、表单值、附件单元格和值" in report_reference
    assert "不得向用户展示内部英文表名 `rf_table`" in report_reference
    assert "必须完整列出所有保留问题" in report_reference
    assert "RF_DEVICE_IDENTITY_INCONSISTENT" in report_reference
