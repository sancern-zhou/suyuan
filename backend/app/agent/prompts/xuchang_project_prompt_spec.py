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
    assert "网页交互查看的图表" in prompt


def test_xuchang_social_prompt_targets_mobile_query_workflow():
    context = load_project_context("xuchang")
    prompt = load_project_mode_prompt("social", context)

    assert prompt is not None
    assert "许昌市问数分析助理" in prompt
    assert "## 项目长期地理信息" in prompt
    assert "中国河南省许昌市" in prompt
    assert "`411000`" in prompt
    assert "## 数据源选择" in prompt
    assert "`get_weather_data`" in prompt
    assert "`XuchangNmcHourlyWeatherForecast`" in prompt
    assert "不得凭记忆或猜测补数" in prompt
    assert "微信端没有右侧面板预览" in prompt
    assert "`schedule_task`" in prompt
    assert "`send_notification`" in prompt


def test_xuchang_social_tool_whitelist_matches_prompt_intent():
    context = load_project_context("xuchang")
    tools = context.manifest.backend.agent_mode_tools.get("social", [])

    assert "execute_sql_query" in tools
    assert "get_weather_data" in tools
    assert "get_weather_forecast" in tools
    assert "knowledge_qa_workflow" in tools
    assert "schedule_task" in tools
    assert "send_notification" in tools
    assert "bash" not in tools
    assert "call_sub_agent" not in tools
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
        "query_national_city_air_quality",
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
