from app.tools.query.get_platform_weather_image.tool import (
    GetPlatformWeatherImageTool,
    NMC_WEATHER_CHART_KEY,
)
from app.utils.path_config import resolve_agent_path


def test_schema_only_exposes_weather_situation_products():
    schema = GetPlatformWeatherImageTool().get_function_schema()
    product_schema = schema["parameters"]["properties"]["product"]

    assert product_schema["enum"] == [NMC_WEATHER_CHART_KEY]
    assert "仅用于" in schema["description"]
    assert "nmc_weather_chart_fetcher" in schema["description"]


def test_guide_only_documents_weather_situation_products():
    guide = resolve_agent_path(
        "backend/app/tools/query/get_platform_weather_image/"
        "GET_PLATFORM_WEATHER_IMAGE_GUIDE.md"
    ).read_text(encoding="utf-8")

    assert "`nmc_surface_weather_chart`（中国地面天气形势图）" in guide
    for excluded in (
        "forecast_trajectory",
        "backward_trajectory",
        "降水量预报图",
        "风场实况图",
        "能见度图",
        "雷达拼图",
        "可降水量",
        "气温预报图",
    ):
        assert excluded not in guide
