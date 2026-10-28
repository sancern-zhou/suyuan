from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.project_config import load_project_context


def test_xuchang_query_and_expert_prompts_include_project_geography_memory():
    context = load_project_context("xuchang")

    for mode in ("query", "expert"):
        prompt = load_project_mode_prompt(mode, context)

        assert prompt is not None
        assert "## 项目长期地理信息" in prompt
        assert "中国河南省许昌市" in prompt
        assert "行政区代码为 `411000`" in prompt
        assert "`Asia/Shanghai`（UTC+8）" in prompt
        assert "`{city_name}` 替换为 `许昌市`" in prompt
        assert "`{city_code}` 替换为 `411000`" in prompt
        assert "北纬 `34.036`、东经 `113.852`" in prompt
        assert "用户明确指定其他城市或区域时，以用户本次指定为准" in prompt


def test_xuchang_query_prompt_combines_query_and_chart_workflows():
    context = load_project_context("xuchang")
    prompt = load_project_mode_prompt("query", context)

    assert prompt is not None
    assert "你是问数生图智能体" in prompt
    assert "## 问数生图工作流" in prompt
    assert "先调用数据查询工具取得可追溯结果" in prompt
    assert "用户已经提供完整数据时，不再调用数据查询工具" in prompt
    assert "网页交互查看的 ECharts 图表" in prompt


def test_xuchang_report_prompt_uses_dynamic_workflow_contract():
    context = load_project_context("xuchang")
    prompt = load_project_mode_prompt("report", context)

    assert prompt is not None
    assert "run_agent_workflow(workflow=" in prompt
    assert "data.node_results" in prompt
    assert "data.node_lineage" in prompt
    assert "expert_meteorology" in prompt
    assert "expert_analysis" in prompt
    assert "report_analysis_v1" not in prompt
    assert "data.report_analysis" not in prompt
    assert "template_options" not in prompt


def test_xuchang_social_prompt_coordinates_office_and_unified_schedules():
    context = load_project_context("xuchang")
    prompt = load_project_mode_prompt("assistant", context)

    assert prompt is not None
    assert "助手模式" in prompt
    assert "411000" in prompt
    assert 'target_mode="office"' in prompt
    assert "不直接查询业务或气象数据" in prompt
    assert "manage_assistant_schedule" in prompt
    assert "manage_assistant_memory" in prompt
    assert "manage_assistant_runs" in prompt
    assert "plan_id/revision" in prompt


def test_xuchang_social_tool_whitelist_matches_prompt_intent():
    context = load_project_context("xuchang")
    tools = context.manifest.backend.agent_mode_tools.get("assistant", [])

    assert "execute_sql_query" not in tools
    assert "get_weather_data" not in tools
    assert "get_weather_forecast" not in tools
    assert "knowledge_qa_workflow" not in tools
    assert "schedule_task" not in tools
    assert "create_scheduled_task" not in tools
    assert "manage_scheduled_tasks" not in tools
    assert "manage_assistant_schedule" in tools
    assert {"read_file", "edit_file"}.issubset(tools)
    assert "wait_task" not in tools
    assert {"manage_assistant_memory", "manage_assistant_runs"}.issubset(tools)
    assert "send_notification" in tools
    assert "bash" not in tools
    assert "call_sub_agent" in tools
    assert "cli_session" not in tools


def test_xuchang_forecast_retains_nmc_and_allows_open_meteo_radiation_supplement():
    context = load_project_context("xuchang")

    assert "get_weather_forecast" in context.manifest.backend.agent_mode_tools["expert"]
    assert "get_weather_forecast" not in context.manifest.backend.disabled_tools
    assert "open_meteo_air_quality_forecast" not in context.manifest.backend.fetchers
    assert "xuchang_nmc_hourly_forecast_fetcher" in context.manifest.backend.fetchers


def test_xuchang_expert_mode_exposes_project_data_query_tools():
    context = load_project_context("xuchang")
    expert_tools = context.manifest.backend.agent_mode_tools["expert"]

    assert {
        "query_airdata_platform",
        "airdata_calc_report_summary",
        "xuchang_station_catalog",
        "query_national_province_air_quality",
        # 【暂时下线 2026-10-27】query_national_city_air_quality 不对 Agent 暴露
        "resolve_station_geo",
    }.issubset(expert_tools)


def test_xuchang_expert_mode_drops_retired_analysis_tools():
    context = load_project_context("xuchang")
    expert_tools = set(context.manifest.backend.agent_mode_tools["expert"])

    assert {
        "analyze_upwind_enterprises",
        "calculate_pm_pmf",
        "calculate_vocs_pmf",
        "analyze_trajectory_sources",
        "calculate_reconstruction",
        "calculate_carbon",
        "calculate_soluble",
        "calculate_crustal",
        "calculate_trace",
        "predict_air_quality",
        "generate_map",
    }.isdisjoint(expert_tools)
    assert "meteorological_trajectory_analysis" in expert_tools


def test_xuchang_expert_modes_expose_platform_weather_image_chart_only():
    """综合专家与气象专家接入平台天气图片工具，且仅限天气形势图；其余模式不得暴露。"""
    from app.tools.query.get_platform_weather_image.tool import (
        GetPlatformWeatherImageTool,
        NMC_WEATHER_CHART_KEY,
    )

    context = load_project_context("xuchang")
    mode_tools = context.manifest.backend.agent_mode_tools

    assert "get_platform_weather_image" in mode_tools["expert"]
    assert "get_platform_weather_image" in mode_tools["expert_meteorology"]
    for mode, tools in mode_tools.items():
        if mode in {"expert", "expert_meteorology"}:
            continue
        assert "get_platform_weather_image" not in tools, f"{mode} 模式不应暴露 get_platform_weather_image"

    # 裁剪守卫：工具 schema 只暴露 nmc_surface_weather_chart（中国地面天气形势图）
    schema = GetPlatformWeatherImageTool().get_function_schema()
    assert schema["parameters"]["properties"]["product"]["enum"] == [NMC_WEATHER_CHART_KEY]
