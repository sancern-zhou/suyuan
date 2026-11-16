"""产物可读性契约守门测试。

2026-11-16 复盘：custom 定时任务执行例行工单审核时，Agent 未加载技能、
直接对 10MB / 28 万行的 dataset.json 反复 read_file 分页读取，120 轮迭代
全部耗尽仍未形成终态，任务被判失败。修复方向是把"哪些产物可读"做成工具
结果里的确定性信号（而不是只写在提示词里），并让工具描述点名技能。
"""

from app.services.ops_audit.rule_engine import _ARTIFACT_READABILITY
from app.tools.analysis.ops_work_order_audit.tool import (
    _OUTPUT_PATH_FIELDS,
    OpsAuditRunRulesTool,
)


def test_every_output_path_has_readability_contract():
    """每个对外暴露的产物路径都必须有用途说明，否则模型只能猜。"""

    missing = [field for field in _OUTPUT_PATH_FIELDS if field not in _ARTIFACT_READABILITY]
    assert not missing, f"缺少产物用途说明: {missing}"


def test_only_report_input_is_declared_readable():
    """只有 report_input_path 允许直接读取；其余必须显式劝阻 read_file。"""

    readable = [
        field
        for field, note in _ARTIFACT_READABILITY.items()
        if "不要 read_file" not in note
    ]
    assert readable == ["report_input_path"]
    assert "不要 read_file" in _ARTIFACT_READABILITY["dataset_path"]
    assert "ops_audit_inspect" in _ARTIFACT_READABILITY["audit_result_path"]


def test_run_rules_tool_description_points_to_skill_and_readable_artifact():
    """工具描述要点名技能，并把可读产物边界写在入口。"""

    description = OpsAuditRunRulesTool().function_schema["description"]
    assert "view_skill: ops_work_order_audit" in description
    assert "report_input_path" in description
    assert "ops_audit_inspect" in description
    assert "artifact_readability" in description
