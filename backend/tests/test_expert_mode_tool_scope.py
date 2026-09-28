"""专家模式工具范围守卫。

组分在线分析、PMF 源解析、空气质量预测、轨迹溯源、生成地图类工具
不再暴露给专家模式（其实现仍可被后端工作流复用），避免专家 Agent
误用未闭环的分析链路。
"""
from app.agent.prompts.tool_registry import EXPERT_TOOL_NAMES, get_tools_by_mode


RETIRED_EXPERT_TOOLS = [
    "calculate_pm_pmf",
    "calculate_vocs_pmf",
    "analyze_upwind_enterprises",
    "analyze_trajectory_sources",
    "calculate_reconstruction",
    "calculate_carbon",
    "calculate_soluble",
    "calculate_crustal",
    "calculate_trace",
    "predict_air_quality",
    "generate_map",
]


def test_shared_expert_whitelist_drops_retired_analysis_tools():
    leaked = set(RETIRED_EXPERT_TOOLS).intersection(EXPERT_TOOL_NAMES)
    assert not leaked, f"retired tools must not be whitelisted: {sorted(leaked)}"


def test_expert_mode_excludes_retired_analysis_tools():
    tools = get_tools_by_mode("expert")

    assert set(RETIRED_EXPERT_TOOLS).isdisjoint(tools)


def test_expert_mode_keeps_trajectory_and_report_tools():
    tools = get_tools_by_mode("expert")

    assert "meteorological_trajectory_analysis" in tools
    assert "create_report_chart" in tools
    assert "execute_sql_query" in tools
