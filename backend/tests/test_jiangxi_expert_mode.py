from pathlib import Path

from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.project_config.loader import load_project_context
from config.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jiangxi_expert_mode_loads_project_owned_prompt():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    prompt = load_project_mode_prompt("expert", context=context)

    assert prompt is not None
    assert "你是声环境专业分析专家" in prompt
    assert "大气环境专业分析专家" not in prompt


def test_jiangxi_expert_prompt_keeps_tool_selection_out_of_system_prompt():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    prompt = load_project_mode_prompt("expert", context=context)

    leaked = [name for name in get_tools_by_mode("expert") if name in prompt]
    assert leaked == []


def test_jiangxi_expert_system_prompt_has_no_tool_names(monkeypatch):
    """最终注入模型的系统提示词（含共享段落）不得出现工具选型。"""
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    prompt = build_react_system_prompt("expert")

    leaked = [name for name in get_tools_by_mode("expert") if name in prompt]
    assert leaked == []
    assert "## 数据源地图" not in prompt
    assert "## 工具选择" not in prompt


def test_jiangxi_expert_prompt_has_no_air_quality_rules(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    prompt = build_react_system_prompt("expert")

    assert "PM2.5" not in prompt
    assert "臭氧" not in prompt
    assert "源解析" not in prompt
    assert "环境空气质量标准过渡实施阶段" not in prompt
