from pathlib import Path

from app.agent.prompts.project_prompt import (
    load_project_mode_prompt,
    load_project_report_final_review_prompt,
)
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.react_agent import ReActAgent
from app.project_config.loader import load_project_context
from config.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[2]

# 编排工具名豁免：2026-11-17 report 转整合者后，编排段与运行时注入的委派契约
# 必然引用 run_agent_workflow/call_sub_agent（许昌/广东同款），禁止的仍是业务取数工具选型。
DELEGATION_TOOL_NAMES = {"run_agent_workflow", "call_sub_agent"}


def test_jiangxi_report_mode_loads_project_owned_prompt():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    prompt = load_project_mode_prompt("report", context=context)

    assert prompt is not None
    assert "你是声环境报告生成专家" in prompt
    assert "report_final_complete" in prompt
    assert "GB 3096" in prompt


def test_jiangxi_report_prompt_keeps_tool_selection_out_of_system_prompt():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    prompt = load_project_mode_prompt("report", context=context)

    leaked = [
        name for name in get_tools_by_mode("report")
        if name in prompt and name not in DELEGATION_TOOL_NAMES
    ]
    assert leaked == []


def test_jiangxi_report_system_prompt_has_no_air_quality_or_tool_names(monkeypatch):
    """报告模式最终系统提示词不得混入空气质量语义与工具选型。"""
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    prompt = build_react_system_prompt("report")

    leaked = [
        name for name in get_tools_by_mode("report")
        if name in prompt and name not in DELEGATION_TOOL_NAMES
    ]
    assert leaked == []
    assert "## 数据源地图" not in prompt
    for keyword in ("PM2.5", "PM10", "臭氧", "AQI", "空气质量", "源解析"):
        assert keyword not in prompt
    assert "环境空气质量标准过渡实施阶段" not in prompt
    assert "report_final_complete" in prompt


def test_jiangxi_report_final_review_prompt_is_project_owned(monkeypatch):
    """自动复核轮不得沿用大气排名与 PM2.5 新标准字段。"""
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    prompt = load_project_report_final_review_prompt()

    assert prompt is not None
    assert "GB 3096" in prompt
    for keyword in ("PM2.5", "PM10", "O3", "AQI", "analyze_city_pollutant_rankings"):
        assert keyword not in prompt
    assert ReActAgent._resolve_report_final_review_prompt() == prompt
