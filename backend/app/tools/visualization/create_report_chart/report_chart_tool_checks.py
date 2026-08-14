from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from PIL import Image

from app.tools.visualization.create_report_chart.tool import (
    CreateReportChartTool,
    report_chart_reference_paths,
)
from app.tools.visualization.create_report_chart.renderer import (
    _cache_figure,
    _create_figure,
    _draw_line,
    _position_legends_below_plot,
    select_chinese_font,
)
from app.utils.font_utils import get_font_manager


def test_schema_stays_compact_and_points_to_progressive_references():
    tool = CreateReportChartTool()

    schema = tool.get_function_schema()
    properties = schema["parameters"]["properties"]

    assert schema["name"] == "create_report_chart"
    assert set(properties) == {
        "chart_id",
        "chart_type",
        "title",
        "data",
        "file_path",
        "output_context",
        "style_profile",
        "notes",
        "options",
    }
    assert schema["parameters"]["required"] == ["chart_type", "title"]
    assert schema["parameters"]["anyOf"] == [
        {"required": ["data"]},
        {"required": ["file_path"]},
    ]
    assert len(str(schema)) < 7000
    assert "references/index.md" in schema["description"]
    assert "两层规范" in schema["description"]
    assert "无需另读输入、A4 或布局规范" in schema["description"]
    assert "data 或 file_path" in schema["description"]
    assert properties["chart_type"]["enum"] == [
        "bar",
        "horizontal_bar",
        "line",
        "timeseries",
        "scatter",
        "pie",
        "stacked_area",
        "dual_axis_line",
        "stacked_bar",
        "percent_stacked_bar",
        "histogram",
        "correlation_heatmap",
        "boxplot",
        "table_image",
        "combo",
        "range_line",
        "waterfall",
        "pareto",
        "diverging_bar",
        "step_line",
        "error_bar",
        "pollutant_calendar",
        "generic_pollutant_wind_rose",
        "wind_timeseries",
        "aqi_calendar",
        "pollutant_wind_rose",
    ]
    assert "不是 ECharts option" in properties["data"]["description"]
    assert "series[0].data" in properties["data"]["description"]
    assert "series[0].values" in properties["data"]["description"]
    assert "多序列" in properties["data"]["description"]
    assert "file_path" in properties["data"]["description"]
    assert "不会自动推断" in properties["data"]["description"]
    assert "ExecutionContext" in properties["file_path"]["description"]
    assert "无需调用 get_raw_data" in properties["file_path"]["description"]
    assert "来源追踪" in properties["file_path"]["description"]
    assert "原样复用" in properties["file_path"]["description"]
    assert "save_data" in properties["file_path"]["description"]
    assert "不得自行构造、猜测或改写存储路径" in properties["file_path"]["description"]
    assert "执行环境内自行写入的中间路径" in properties["file_path"]["description"]
    assert "reference_lines" in properties["options"]["description"]
    assert "wind_direction_convention" in properties["options"]["description"]
    assert "east_u/north_v" in properties["options"]["description"]


def test_reference_paths_include_specialized_chart_type_documents():
    paths = report_chart_reference_paths()

    expected_keys = {
        "index",
        "pie_rules",
        "bar_chart",
        "line_chart",
        "scatter_chart",
        "stacked_area",
        "dual_axis_line",
        "stacked_bar",
        "histogram",
        "correlation_heatmap",
        "boxplot",
        "table_image",
        "combo_chart",
        "range_and_error",
        "waterfall_chart",
        "pareto_chart",
        "comparison_charts",
        "pollutant_calendar",
        "generic_pollutant_wind_rose",
        "wind_timeseries",
        "aqi_calendar",
        "pollutant_wind_rose",
    }

    assert set(paths) == expected_keys
    for path in paths.values():
        assert Path(path).exists()

    aqi_calendar_text = Path(paths["aqi_calendar"]).read_text(encoding="utf-8")
    pollutant_wind_rose_text = Path(paths["pollutant_wind_rose"]).read_text(encoding="utf-8")
    pollutant_calendar_text = Path(paths["pollutant_calendar"]).read_text(encoding="utf-8")
    generic_wind_rose_text = Path(paths["generic_pollutant_wind_rose"]).read_text(encoding="utf-8")
    wind_timeseries_text = Path(paths["wind_timeseries"]).read_text(encoding="utf-8")
    index_text = Path(paths["index"]).read_text(encoding="utf-8")
    assert "aqi_calendar" in aqi_calendar_text
    assert "广东省专用" in aqi_calendar_text
    assert "pollutant_wind_rose" in pollutant_wind_rose_text
    assert "广东省专用" in pollutant_wind_rose_text
    assert "pollutant_calendar" in pollutant_calendar_text
    assert "generic_pollutant_wind_rose" in generic_wind_rose_text
    assert "wind_timeseries" in wind_timeseries_text
    assert "meteorological_from" in wind_timeseries_text
    assert "Supply at least one of `data` or `file_path`" in index_text
    assert "current session" in index_text
    assert "not infer arbitrary record fields" in index_text
    assert "exactly one matching chart document" in index_text


def test_renderer_selects_existing_chinese_font_file_when_available():
    font_path = select_chinese_font()
    font_manager = get_font_manager()

    assert font_path is not None
    assert Path(font_path).exists()
    assert font_manager.preferred_font_name() == "FZXiaoBiaoSong-B05S"
    assert Path(font_path).resolve() == font_manager.FONT_FILE_PATHS[0].resolve()


def test_label_normalization_converts_ionic_superscripts_and_subscripts_to_mathtext():
    from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text

    assert (
        normalize_matplotlib_label_text("各城市PM2.5中SO₄²⁻/NO₃⁻比值对比")
        == "各城市PM2.5中SO$_4^{2-}$/NO$_3^-$比值对比"
    )
    assert normalize_matplotlib_label_text("NH₄⁺贡献占比") == "NH$_4^+$贡献占比"


@pytest.mark.asyncio
async def test_specialized_chart_type_routes_through_unified_tool_metadata():
    result = await CreateReportChartTool().execute(
        chart_type="aqi_calendar",
        title="AQI 日历",
        data={"dates": ["2026-01-01"], "aqi": [80]},
        options={"dry_run": True},
    )

    assert result["success"] is True
    assert result["metadata"]["tool_name"] == "create_report_chart"
    assert result["metadata"]["chart_type"] == "aqi_calendar"
    assert result["data"]["render_mode"] == "dry_run"


@pytest.mark.asyncio
async def test_report_chart_returns_resource_refs_and_resume_hints():
    result = await CreateReportChartTool().execute(
        chart_id="resource_refs_case",
        chart_type="bar",
        title="资源协议测试图",
        data={"labels": ["A"], "values": [1]},
        file_path="/configured/data/root/sessions/agent_session_test/data/resource-refs.json",
    )

    image_path = Path(result["visuals"][0]["local_path"])

    assert result["success"] is True
    assert image_path.exists()
    assert result["visuals"][0]["url"].startswith("/api/image/")
    assert result["visuals"][0]["image_url"] == result["visuals"][0]["url"]
    assert result["refs"]["data"] == [
        {
            "file_path": "/configured/data/root/sessions/agent_session_test/data/resource-refs.json",
            "usage": "source",
        }
    ]
    assert result["refs"]["files"][0]["path"] == str(image_path)
    assert result["refs"]["files"][0]["type"] == "image"
    assert result["refs"]["files"][0]["usage"] == "report_chart"
    assert result["refs"]["visuals"][0]["tool_path"] == str(image_path)
    assert result["refs"]["visuals"][0]["image_url"] == result["visuals"][0]["image_url"]
    assert result["llm_resume"]["source_file_path"] == "/configured/data/root/sessions/agent_session_test/data/resource-refs.json"
    assert result["llm_resume"]["generated_visuals"][0]["tool_path"] == str(image_path)
    assert result["llm_resume"]["generated_visuals"][0]["image_url"] == result["visuals"][0]["image_url"]
    assert str(image_path) in result["llm_resume"]["tool_hint"]


@pytest.mark.asyncio
async def test_aqi_calendar_renders_prepared_city_data_map():
    result = await CreateReportChartTool().execute(
        chart_id="aqi_calendar_inline_case",
        chart_type="aqi_calendar",
        title="AQI 日历",
        data={
            "year": 2026,
            "month": 5,
            "pollutant": "AQI",
            "city_data_map": {
                "广州": {"1": 82, "2": 49, "3": 56},
                "深圳": {"1": 42, "2": 51, "3": 62},
            },
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "aqi_calendar"
    assert result["data"]["metadata"]["scope"] == "guangdong_only"
    assert result["data"]["metadata"]["city_count"] == 2
    assert result["data"]["metadata"]["covered_days"] == 6
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_aqi_calendar_renders_records_loaded_from_context_file_path():
    records = [
        {"city": "广州", "date": "2026-05-01", "aqi": 82},
        {"city": "广州", "date": "2026-05-02", "aqi": 49},
        {"city": "深圳", "date": "2026-05-01", "aqi": 42},
        {"city": "深圳", "date": "2026-05-02", "aqi": 51},
    ]

    result = await CreateReportChartTool().execute(
        context=FakeChartContext(records),
        chart_id="aqi_calendar_file_path_case",
        chart_type="aqi_calendar",
        title="AQI 日历",
        file_path="chart_data:v1:abc",
        options={"year": 2026, "month": 5, "pollutant": "AQI", "cities": ["广州", "深圳"]},
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    assert result["data"]["metadata"]["applied_chart_type"] == "aqi_calendar"
    assert result["data"]["metadata"]["scope"] == "guangdong_only"
    assert result["data"]["metadata"]["covered_days"] == 4
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_pollutant_wind_rose_renders_prepared_arrays():
    wind_directions = list(range(0, 360, 15)) * 2
    wind_speeds = [1 + (index % 8) * 0.35 for index in range(len(wind_directions))]
    concentrations = [35 + (index % 12) * 4 for index in range(len(wind_directions))]

    result = await CreateReportChartTool().execute(
        chart_id="pollutant_wind_rose_inline_case",
        chart_type="pollutant_wind_rose",
        title="PM10 污染物风玫瑰图",
        data={
            "wind_directions": wind_directions,
            "wind_speeds": wind_speeds,
            "concentrations": concentrations,
        },
        options={"pollutant_name": "PM10", "unit": "μg/m³", "use_six_level": False},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "pollutant_wind_rose"
    assert result["data"]["metadata"]["scope"] == "guangdong_only"
    assert result["data"]["metadata"]["valid_point_count"] == len(wind_directions)
    assert result["data"]["metadata"]["unit"] == "μg/m$^3$"
    assert "³" not in result["data"]["metadata"]["unit"]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_pollutant_wind_rose_renders_records_loaded_from_context_file_path():
    records = []
    for index, direction in enumerate(list(range(0, 360, 15)) * 2):
        records.append(
            {
                "timestamp": f"2026-05-01 {index % 24:02d}:00:00",
                "wind_direction_10m": direction,
                "wind_speed_10m": 1 + (index % 8) * 0.35,
                "PM10": 35 + (index % 12) * 4,
            }
        )

    result = await CreateReportChartTool().execute(
        context=FakeChartContext(records),
        chart_id="pollutant_wind_rose_file_path_case",
        chart_type="pollutant_wind_rose",
        title="PM10 污染物风玫瑰图",
        file_path="chart_data:v1:abc",
        options={"pollutant_name": "PM10", "unit": "μg/m³", "time_resolution": "5min", "use_six_level": False},
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    assert result["data"]["metadata"]["applied_chart_type"] == "pollutant_wind_rose"
    assert result["data"]["metadata"]["scope"] == "guangdong_only"
    assert result["data"]["metadata"]["valid_point_count"] == len(records)
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_pollutant_calendar_renders_generic_single_region_daily_values():
    result = await CreateReportChartTool().execute(
        chart_id="pollutant_calendar_generic_case",
        chart_type="pollutant_calendar",
        title="PM₂.₅月度日历图",
        data={
            "year": 2026,
            "month": 5,
            "pollutant": "PM₂.₅",
            "unit": "μg/m³",
            "values": [
                {"date": "2026-05-01", "value": 18},
                {"date": "2026-05-02", "value": 22},
                {"date": "2026-05-03", "value": 35},
            ],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "pollutant_calendar"
    assert result["data"]["metadata"]["scope"] == "generic"
    assert result["data"]["metadata"]["covered_days"] == 3
    assert result["data"]["metadata"]["unit"] == "μg/m$^3$"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_generic_pollutant_wind_rose_renders_non_guangdong_distribution():
    wind_directions = list(range(0, 360, 30)) * 2
    wind_speeds = [1 + (index % 6) * 0.4 for index in range(len(wind_directions))]
    concentrations = [20 + (index % 8) * 5 for index in range(len(wind_directions))]

    result = await CreateReportChartTool().execute(
        chart_id="generic_pollutant_wind_rose_case",
        chart_type="generic_pollutant_wind_rose",
        title="PM₂.₅通用污染物风玫瑰图",
        data={
            "wind_directions": wind_directions,
            "wind_speeds": wind_speeds,
            "concentrations": concentrations,
        },
        options={"pollutant_name": "PM₂.₅", "unit": "μg/m³", "direction_bins": 8},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "generic_pollutant_wind_rose"
    assert result["data"]["metadata"]["scope"] == "generic"
    assert result["data"]["metadata"]["direction_bin_count"] == 8
    assert result["data"]["metadata"]["valid_point_count"] == len(wind_directions)
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_wind_timeseries_renders_speed_direction_and_pm25_arrays():
    timestamps = [f"2026-05-01 {hour:02d}:00:00" for hour in range(24)]
    result = await CreateReportChartTool().execute(
        chart_id="wind_timeseries_pm25_case",
        chart_type="wind_timeseries",
        title="风场与PM2.5浓度变化",
        data={
            "timestamps": timestamps,
            "wind_speeds": [1.0 + (index % 6) * 0.4 for index in range(24)],
            "wind_directions": [(index * 20) % 360 for index in range(24)],
            "concentrations": [20 + (index % 8) * 3 for index in range(24)],
            "wind_direction_convention": "meteorological_from",
        },
        options={"pollutant_name": "PM2.5", "unit": "μg/m³", "max_vectors": 18},
    )

    assert result["success"] is True
    metadata = result["data"]["metadata"]
    assert metadata["applied_chart_type"] == "wind_timeseries"
    assert metadata["input_mode"] == "speed_direction"
    assert metadata["wind_direction_convention"] == "meteorological_from"
    assert metadata["pollutant_name"] == "PM2.5"
    assert metadata["unit"] == "μg/m$^3$"
    assert metadata["valid_point_count"] == 24
    assert metadata["rendered_vector_count"] == 18
    assert "wind_vectors_thinned" in result["data"]["layout_warnings"]
    assert len(result["visuals"]) == 1
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_wind_timeseries_renders_custom_pollutant_records_from_file_path():
    records = [
        {
            "monitor_time": f"2026-05-01 {hour:02d}:00:00",
            "ws": 1.5 + hour * 0.1,
            "wd": (hour * 30) % 360,
            "O3_8h": 60 + hour,
        }
        for hour in range(8)
    ]
    result = await CreateReportChartTool().execute(
        context=FakeChartContext(records),
        chart_id="wind_timeseries_o3_case",
        chart_type="wind_timeseries",
        title="风场与O3浓度变化",
        file_path="chart_data:v1:abc",
        options={
            "pollutant_name": "O3",
            "unit": "μg/m³",
            "time_field": "monitor_time",
            "wind_speed_field": "ws",
            "wind_direction_field": "wd",
            "concentration_field": "O3_8h",
            "wind_direction_convention": "meteorological_from",
        },
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    metadata = result["data"]["metadata"]
    assert metadata["input_mode"] == "records_speed_direction"
    assert metadata["pollutant_name"] == "O3"
    assert metadata["valid_point_count"] == len(records)
    assert Path(result["visuals"][0]["local_path"]).exists()


def test_wind_timeseries_converts_meteorological_direction_to_components():
    from app.tools.visualization.create_report_chart.domain.wind_timeseries import (
        _components_from_speed_direction,
    )

    east_u, north_v = _components_from_speed_direction(
        [2.0, 3.0, 4.0],
        [0.0, 90.0, 180.0],
        "meteorological_from",
    )

    assert east_u == pytest.approx([0.0, -3.0, 0.0], abs=1e-10)
    assert north_v == pytest.approx([-2.0, 0.0, 4.0], abs=1e-10)


@pytest.mark.asyncio
async def test_wind_timeseries_requires_explicit_direction_convention_for_angles():
    result = await CreateReportChartTool().execute(
        chart_type="wind_timeseries",
        title="风场与PM2.5浓度变化",
        data={
            "timestamps": ["2026-05-01 00:00", "2026-05-01 01:00"],
            "wind_speeds": [2.0, 3.0],
            "wind_directions": [180.0, 270.0],
            "concentrations": [20.0, 22.0],
        },
    )

    assert result["success"] is False
    assert "必须显式提供 wind_direction_convention" in result["error"]


@pytest.mark.asyncio
async def test_wind_timeseries_plots_supplied_components_without_direction_assumption():
    result = await CreateReportChartTool().execute(
        chart_id="wind_timeseries_components_case",
        chart_type="wind_timeseries",
        title="风场与PM10浓度变化",
        data={
            "timestamps": ["2026-05-01 00:00", "2026-05-01 01:00"],
            "east_u": [-2.0, 3.0],
            "north_v": [4.0, -5.0],
            "concentrations": [30.0, 35.0],
        },
        options={"pollutant_name": "PM10"},
    )

    assert result["success"] is True
    metadata = result["data"]["metadata"]
    assert metadata["input_mode"] == "components"
    assert metadata["wind_direction_convention"] == "components"


@pytest.mark.asyncio
async def test_long_labels_are_rendered_as_horizontal_bar_with_warning():
    result = await CreateReportChartTool().execute(
        chart_id="long_label_case",
        chart_type="bar",
        title="长标签费用排行",
        data={
            "labels": [
                "广东省深圳市南山区科技园超长客户名称一号",
                "广东省广州市天河区复杂项目名称二号",
                "佛山市顺德区跨区域物流服务三号",
            ],
            "values": [32, 28, 17],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "horizontal_bar"
    assert "long_labels_horizontal_bar" in result["data"]["layout_warnings"]
    assert result["visuals"][0]["local_path"].endswith(".png")
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_crowded_categorical_bar_labels_are_rendered_horizontally():
    result = await CreateReportChartTool().execute(
        chart_id="crowded_station_bar_case",
        chart_type="bar",
        title="深圳市各站点O₃峰值浓度排名（7月5日16-20时）",
        data={
            "labels": [
                "观澜",
                "新湖街道",
                "洪湖",
                "西乡",
                "南海子站",
                "南山",
                "南油",
                "莲花山",
                "田心",
                "盐田",
                "华侨城",
                "坪山",
                "南澳",
                "葵涌",
                "梅沙",
                "西丽",
                "荔园",
                "龙岗",
            ],
            "values": [65, 64, 64, 60, 60, 60, 59, 59, 59, 58, 57, 57, 56, 55, 53, 53, 51, 44],
        },
        output_context="word",
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "horizontal_bar"
    assert "crowded_categorical_labels_horizontal_bar" in result["data"]["layout_warnings"]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_bar_chart_accepts_categories_with_single_series_data():
    result = await CreateReportChartTool().execute(
        chart_id="single_series_bar_case",
        chart_type="bar",
        title="2026年5月济宁市首要污染物分布",
        data={
            "categories": ["O3_8h", "无(优)"],
            "series": [
                {
                    "name": "天数",
                    "data": [25, 6],
                }
            ],
        },
        output_context="word",
        notes="5月首要污染物分布：O3_8h为25天，6天为优无首要污染物",
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "bar"
    assert result["visuals"][0]["local_path"].endswith(".png")
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_line_chart_accepts_labels_with_single_series_values():
    result = await CreateReportChartTool().execute(
        chart_id="single_series_line_values_case",
        chart_type="line",
        title="2026年5月济宁市AQI日变化趋势",
        data={
            "labels": ["05-01", "05-02", "05-03"],
            "series": [
                {
                    "name": "AQI",
                    "values": [82, 49, 56],
                }
            ],
        },
        output_context="word",
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "line"
    assert result["visuals"][0]["local_path"].endswith(".png")
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_line_chart_renders_multiple_series_with_reference_line_and_axis_labels():
    result = await CreateReportChartTool().execute(
        chart_id="multi_series_line_case",
        chart_type="line",
        title="AQI与O3趋势",
        data={
            "labels": ["05-01", "05-02", "05-03"],
            "series": [
                {"name": "AQI", "values": [82, 49, 56]},
                {"name": "O3_8H", "values": [138, 97, 107]},
            ],
        },
        options={
            "x_label": "日期",
            "y_label": "浓度",
            "reference_lines": [{"axis": "y", "value": 100, "label": "良/轻度污染"}],
            "legend": True,
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["series_count"] == 2
    assert result["data"]["metadata"]["reference_line_count"] == 1
    assert "axis_labels_applied" in result["data"]["layout_warnings"]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_line_chart_normalizes_title_legend_and_reference_labels_with_subscripts():
    result = await CreateReportChartTool().execute(
        chart_id="subscript_text_case",
        chart_type="line",
        title="AQI与O₃_8H趋势",
        data={
            "labels": ["05-01", "05-02", "05-03"],
            "series": [
                {"name": "PM₂.₅ (μg/m³)", "values": [18, 20, 19]},
                {"name": "O₃_8H (μg/m³)", "values": [138, 97, 107]},
            ],
        },
        options={
            "y_label": "浓度 (μg/m³)",
            "reference_lines": [{"axis": "y", "value": 100, "label": "O₃_8H日均限值"}],
        },
    )

    assert result["success"] is True
    normalized_text = result["data"]["metadata"]["normalized_text"]
    assert normalized_text["title"] == "AQI与O$_3$_8H趋势"
    assert normalized_text["series_names"] == ["PM$_{2.5}$ (μg/m$^3$)", "O$_3$_8H (μg/m$^3$)"]
    assert normalized_text["y_label"] == "浓度 (μg/m$^3$)"
    assert normalized_text["reference_labels"] == ["O$_3$_8H日均限值"]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_line_chart_thins_dense_daily_x_axis_labels_for_word_reports():
    labels = [f"05-{day:02d}" for day in range(1, 32)]
    result = await CreateReportChartTool().execute(
        chart_id="dense_daily_line_case",
        chart_type="line",
        title="31天日变化趋势",
        data={"labels": labels, "values": list(range(31))},
        output_context="word",
    )

    assert result["success"] is True
    assert "dense_x_tick_labels_thinned" in result["data"]["layout_warnings"]
    assert result["data"]["metadata"]["x_tick_label_strategy"]["original_count"] == 31
    assert result["data"]["metadata"]["x_tick_label_strategy"]["shown_count"] <= 12
    assert result["data"]["metadata"]["x_tick_label_strategy"]["interval"] > 1
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_text_layout_thins_measured_x_tick_collisions_and_preserves_endpoints():
    labels = [f"第{index}个非常长的横坐标分类名称" for index in range(10)]

    result = await CreateReportChartTool().execute(
        chart_id="measured_dense_x_ticks_case",
        chart_type="line",
        title="密集横坐标",
        data={"labels": labels, "values": list(range(10))},
    )

    layout = result["data"]["metadata"]["text_layout"]
    omitted_ticks = [item["label"] for item in layout["omitted_items"] if item["role"] == "x_tick"]

    assert result["success"] is True
    assert layout["initial_conflicts"] > 0
    assert layout["final_conflicts"] == 0
    assert omitted_ticks
    assert labels[0] not in omitted_ticks
    assert labels[-1] not in omitted_ticks
    assert "text_overlap_unresolved" not in result["data"]["layout_warnings"]


@pytest.mark.asyncio
async def test_text_layout_reaches_title_font_floor_before_declaring_unresolved():
    result = await CreateReportChartTool().execute(
        chart_id="long_title_font_floor_case",
        chart_type="line",
        title="超长正式报告图表标题" * 4,
        data={"labels": ["A", "B", "C"], "values": [1, 2, 3]},
        output_context="screen",
    )

    layout = result["data"]["metadata"]["text_layout"]

    assert result["success"] is True
    assert layout["initial_conflicts"] > 0
    assert layout["actions"]["font_reductions"] > 3
    assert layout["final_conflicts"] == 0
    assert "text_overlap_unresolved" not in result["data"]["layout_warnings"]


@pytest.mark.asyncio
async def test_text_layout_can_omit_unreadable_x_tick_labels_after_reaching_font_floor():
    labels = ["第一个极端超长横坐标端点标签" * 3, "第二个极端超长横坐标端点标签" * 3]

    result = await CreateReportChartTool().execute(
        chart_id="two_dense_x_ticks_case",
        chart_type="line",
        title="两个端点",
        data={"labels": labels, "values": [1, 2]},
        output_context="screen",
    )

    layout = result["data"]["metadata"]["text_layout"]
    omitted = [item for item in layout["omitted_items"] if item["role"] == "x_tick"]

    assert result["success"] is True
    assert layout["initial_conflicts"] > 0
    assert layout["final_conflicts"] == 0
    assert {item["label"] for item in omitted} == set(labels)


@pytest.mark.asyncio
async def test_text_layout_omits_overlapping_reference_labels_but_keeps_reference_lines():
    reference_lines = [
        {"axis": "y", "value": 1.500 + index * 0.001, "label": f"参考线{index + 1}"}
        for index in range(5)
    ]

    result = await CreateReportChartTool().execute(
        chart_id="dense_reference_labels_case",
        chart_type="line",
        title="密集参考线",
        data={"labels": ["A", "B", "C"], "values": [1.4, 1.6, 1.5]},
        options={"reference_lines": reference_lines},
    )

    layout = result["data"]["metadata"]["text_layout"]
    omitted = [item for item in layout["omitted_items"] if item["role"] == "reference_label"]

    assert result["success"] is True
    assert result["data"]["metadata"]["reference_line_count"] == len(reference_lines)
    assert layout["initial_conflicts"] > 0
    assert layout["final_conflicts"] == 0
    assert layout["actions"]["omitted_reference_labels"] == len(omitted)
    assert omitted
    assert omitted == sorted(omitted, key=lambda item: item["label"], reverse=True)
    assert "text_overlap_unresolved" not in result["data"]["layout_warnings"]


@pytest.mark.asyncio
async def test_stacked_area_renders_multi_pollutant_contribution_trend():
    result = await CreateReportChartTool().execute(
        chart_id="stacked_area_case",
        chart_type="stacked_area",
        title="污染物贡献变化",
        data={
            "labels": ["05-01", "05-02", "05-03"],
            "series": [
                {"name": "PM₂.₅", "values": [12, 16, 14]},
                {"name": "PM₁₀", "values": [30, 28, 35]},
                {"name": "O₃_8H", "values": [80, 95, 120]},
            ],
        },
        options={"y_label": "浓度 (μg/m³)"},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "stacked_area"
    assert result["data"]["metadata"]["series_count"] == 3
    assert result["data"]["metadata"]["stack_mode"] == "area"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_dual_axis_line_renders_two_metric_trends_with_secondary_axis():
    result = await CreateReportChartTool().execute(
        chart_id="dual_axis_line_case",
        chart_type="dual_axis_line",
        title="AQI与O₃_8H日变化趋势",
        data={
            "labels": ["05-01", "05-02", "05-03"],
            "series": [
                {"name": "AQI", "values": [82, 49, 56], "axis": "left"},
                {"name": "O₃_8H", "values": [138, 97, 107], "axis": "right"},
            ],
        },
        options={"left_y_label": "AQI", "right_y_label": "O₃_8H (μg/m³)"},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "dual_axis_line"
    assert result["data"]["metadata"]["axis_series_counts"] == {"left": 1, "right": 1}
    assert result["data"]["metadata"]["normalized_text"]["right_y_label"] == "O$_3$_8H (μg/m$^3$)"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_bar_chart_renders_grouped_multiple_series():
    result = await CreateReportChartTool().execute(
        chart_id="multi_series_bar_case",
        chart_type="bar",
        title="污染物同比对比",
        data={
            "labels": ["PM2.5", "PM10", "O3"],
            "series": [
                {"name": "2025年5月", "data": [31, 63, 202]},
                {"name": "2026年5月", "data": [18, 45, 169]},
            ],
        },
        options={"y_label": "浓度", "legend": True},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["series_count"] == 2
    assert result["data"]["metadata"]["bar_mode"] == "grouped"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_bar_chart_supports_month_over_month_pollutant_comparison():
    result = await CreateReportChartTool().execute(
        chart_id="month_over_month_bar_case",
        chart_type="bar",
        title="污染物浓度环比对比",
        data={
            "labels": ["PM₂.₅", "PM₁₀", "SO₂", "NO₂", "CO", "O₃_8H"],
            "series": [
                {"name": "2026年4月", "values": [27, 57, 6, 16, 0.6, 151]},
                {"name": "2026年5月", "values": [18, 45, 4, 10, 0.6, 169]},
            ],
        },
        options={"y_label": "浓度", "legend": True},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "bar"
    assert result["data"]["metadata"]["bar_mode"] == "grouped"
    assert result["data"]["metadata"]["series_count"] == 2
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_correlation_heatmap_renders_pollutant_matrix_with_coefficients():
    result = await CreateReportChartTool().execute(
        chart_id="pollutant_correlation_heatmap_case",
        chart_type="correlation_heatmap",
        title="污染物相关性分析",
        data={
            "labels": ["SO₂", "NO₂", "PM₁₀", "PM₂.₅", "CO", "O₃_8H"],
            "matrix": [
                [1.00, 0.30, 0.66, 0.38, -0.01, 0.61],
                [0.30, 1.00, 0.33, -0.11, -0.42, 0.37],
                [0.66, 0.33, 1.00, 0.48, -0.19, 0.79],
                [0.38, -0.11, 0.48, 1.00, 0.63, 0.41],
                [-0.01, -0.42, -0.19, 0.63, 1.00, -0.15],
                [0.61, 0.37, 0.79, 0.41, -0.15, 1.00],
            ],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "correlation_heatmap"
    assert result["data"]["metadata"]["matrix_shape"] == [6, 6]
    assert result["data"]["metadata"]["annotated_cells"] == 36
    assert result["data"]["metadata"]["color_scale"] == [-1, 1]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_boxplot_renders_pollutant_distribution_groups():
    result = await CreateReportChartTool().execute(
        chart_id="pollutant_boxplot_case",
        chart_type="boxplot",
        title="污染物浓度分布",
        data={
            "groups": [
                {"name": "PM₂.₅", "values": [12, 14, 18, 21, 35, 42]},
                {"name": "PM₁₀", "values": [30, 36, 45, 52, 65, 80]},
                {"name": "O₃_8H", "values": [80, 105, 130, 150, 170, 202]},
            ]
        },
        options={"y_label": "浓度 (μg/m³)"},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "boxplot"
    assert result["data"]["metadata"]["group_count"] == 3
    assert result["data"]["metadata"]["sample_counts"] == [6, 6, 6]
    assert result["data"]["metadata"]["normalized_text"]["y_label"] == "浓度 (μg/m$^3$)"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_stacked_bar_renders_pollutant_composition_by_period():
    result = await CreateReportChartTool().execute(
        chart_id="stacked_bar_case",
        chart_type="stacked_bar",
        title="污染物组成对比",
        data={
            "labels": ["2026年4月", "2026年5月"],
            "series": [
                {"name": "PM₂.₅", "values": [27, 18]},
                {"name": "PM₁₀", "values": [57, 45]},
                {"name": "O₃_8H", "values": [151, 169]},
            ],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "stacked_bar"
    assert result["data"]["metadata"]["stack_mode"] == "absolute"
    assert result["data"]["metadata"]["series_count"] == 3
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_percent_stacked_bar_normalizes_each_category_to_100_percent():
    result = await CreateReportChartTool().execute(
        chart_id="percent_stacked_bar_case",
        chart_type="percent_stacked_bar",
        title="污染物组成占比",
        data={
            "labels": ["2026年4月", "2026年5月"],
            "series": [
                {"name": "PM₂.₅", "values": [27, 18]},
                {"name": "PM₁₀", "values": [57, 45]},
                {"name": "O₃_8H", "values": [151, 169]},
            ],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "percent_stacked_bar"
    assert result["data"]["metadata"]["stack_mode"] == "percent"
    assert result["data"]["metadata"]["category_totals"] == [235.0, 232.0]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_histogram_renders_pollutant_frequency_distribution():
    result = await CreateReportChartTool().execute(
        chart_id="histogram_case",
        chart_type="histogram",
        title="PM₂.₅浓度频次分布",
        data={"values": [12, 14, 18, 21, 35, 42, 45, 47, 55, 60]},
        options={"bins": 5, "x_label": "PM₂.₅ (μg/m³)", "y_label": "频次"},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "histogram"
    assert result["data"]["metadata"]["sample_count"] == 10
    assert result["data"]["metadata"]["bin_count"] == 5
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_long_label_bar_chart_renders_grouped_horizontal_multiple_series():
    result = await CreateReportChartTool().execute(
        chart_id="long_label_multi_series_bar_case",
        chart_type="bar",
        title="长标签同比对比",
        data={
            "labels": [
                "广东省深圳市南山区科技园一号站点",
                "广东省广州市天河区复杂项目二号站点",
            ],
            "series": [
                {"name": "2025年", "data": [31, 63]},
                {"name": "2026年", "data": [18, 45]},
            ],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "horizontal_bar"
    assert result["data"]["metadata"]["series_count"] == 2
    assert result["data"]["metadata"]["bar_mode"] == "grouped_horizontal"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_timeseries_alias_renders_as_line_chart():
    result = await CreateReportChartTool().execute(
        chart_id="timeseries_alias_case",
        chart_type="timeseries",
        title="小时趋势",
        data={"x": ["01:00", "02:00"], "y": [10, 12]},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["requested_chart_type"] == "timeseries"
    assert result["data"]["metadata"]["applied_chart_type"] == "line"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_line_chart_rejects_mismatched_label_and_value_lengths():
    result = await CreateReportChartTool().execute(
        chart_type="line",
        title="错误趋势",
        data={"labels": ["05-01", "05-02", "05-03"], "values": [82, 49]},
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "labels/x 长度为 3，values/y 长度为 2" in result["error"]
    assert result["visuals"] == []


@pytest.mark.asyncio
async def test_missing_data_and_file_path_returns_input_contract_error():
    result = await CreateReportChartTool().execute(
        chart_type="bar",
        title="缺少数据输入",
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "必须提供 data 或 file_path" in result["error"]


@pytest.mark.asyncio
async def test_file_path_without_context_returns_tool_error():
    result = await CreateReportChartTool().execute(
        chart_type="line",
        title="file_path 趋势",
        file_path="chart_data:v1:abc",
    )

    assert result["success"] is False
    assert "需要 ExecutionContext" in result["error"]


class FakeChartContext:
    def __init__(self, payload):
        self.payload = payload

    def get_raw_data(self, file_path):
        assert file_path == "chart_data:v1:abc"
        return [self.payload]


@pytest.mark.asyncio
async def test_file_path_loads_chart_payload_from_context():
    result = await CreateReportChartTool().execute(
        context=FakeChartContext({"labels": ["A", "B"], "values": [1, 2]}),
        chart_id="file_path_case",
        chart_type="bar",
        title="file_path 柱状图",
        file_path="chart_data:v1:abc",
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_runtime_positional_context_call_does_not_conflict_with_chart_type():
    result = await CreateReportChartTool().execute(
        FakeChartContext({"labels": ["A", "B"], "values": [1, 2]}),
        chart_id="runtime_context_case",
        chart_type="bar",
        title="runtime context 柱状图",
        file_path="chart_data:v1:abc",
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_pie_small_slices_use_outside_label_strategy_metadata():
    result = await CreateReportChartTool().execute(
        chart_id="pie_small_slice_case",
        chart_type="pie",
        title="费用占比",
        data={
            "labels": ["A", "B", "C", "D", "E"],
            "values": [82, 9, 4, 3, 2],
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["label_strategy"] == "outside_leader_lines"
    assert "pie_small_slices_outside_labels" in result["data"]["layout_warnings"]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_dense_pie_layout_omits_smallest_annotations_without_residual_overlap():
    labels = [f"细分类项目{index:02d}文字说明" for index in range(1, 17)]
    values = list(range(1, 17))

    result = await CreateReportChartTool().execute(
        chart_id="dense_pie_text_layout_case",
        chart_type="pie",
        title="细分类饼图",
        data={"labels": labels, "values": values},
    )

    layout = result["data"]["metadata"]["text_layout"]
    omitted = [item for item in layout["omitted_items"] if item["role"] == "pie_label"]

    assert result["success"] is True
    assert layout["status"] == "degraded", layout
    assert layout["initial_conflicts"] > 0
    assert layout["final_conflicts"] == 0
    assert omitted
    assert [item["share"] for item in omitted] == sorted(item["share"] for item in omitted)
    assert labels[-1] not in {item["label"] for item in omitted}
    assert len(layout["full_label_mapping"]) == len(labels)
    assert [item["index"] for item in layout["pie_slices"]] == list(range(len(labels)))
    assert [item["label"] for item in layout["pie_slices"]] == labels
    assert [item["value"] for item in layout["pie_slices"]] == values
    assert [item["share"] for item in layout["pie_slices"]] == pytest.approx(
        [value / sum(values) for value in values]
    )
    assert sum(item["omitted"] for item in layout["pie_slices"]) == len(omitted)
    assert all(item["visible"] != item["omitted"] for item in layout["pie_slices"])
    assert "text_overlap_unresolved" not in result["data"]["layout_warnings"]


@pytest.mark.asyncio
async def test_dense_legend_layout_reflows_and_omits_overflow_items_deterministically():
    series = [
        {
            "name": f"污染物超长名称监测系列{index:02d}",
            "values": [index, index + 1, index + 2, index + 3],
        }
        for index in range(1, 31)
    ]

    result = await CreateReportChartTool().execute(
        chart_id="dense_legend_text_layout_case",
        chart_type="line",
        title="多系列趋势",
        data={"labels": ["一月", "二月", "三月", "四月"], "series": series},
    )

    layout = result["data"]["metadata"]["text_layout"]
    omitted_legend = [item for item in layout["omitted_items"] if item["role"] == "legend"]

    assert result["success"] is True
    assert layout["status"] == "degraded", layout
    assert layout["final_conflicts"] == 0
    assert layout["actions"]["legend_reflows"] == 1
    assert layout["actions"]["omitted_legend_items"] == len(omitted_legend)
    assert omitted_legend
    assert omitted_legend == sorted(
        omitted_legend,
        key=lambda item: item["label"],
    )
    assert "text_overlap_unresolved" not in result["data"]["layout_warnings"]


def test_report_legend_is_positioned_below_and_does_not_overlap_plot():
    fig, ax = _create_figure("word", "report")
    try:
        _draw_line(
            ax,
            "多系列趋势",
            {
                "labels": ["一月", "二月", "三月"],
                "series": [
                    {"name": "PM2.5", "values": [30, 40, 35]},
                    {"name": "PM10", "values": [55, 60, 58]},
                ],
            },
            {},
        )

        layout = _position_legends_below_plot(fig)
        fig.tight_layout(pad=1.1, rect=(0.0, layout["reserved_bottom_fraction"], 1.0, 1.0))
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()

        assert layout["position"] == "outside_bottom"
        assert layout["reserved_bottom_fraction"] > 0
        assert not ax.get_legend().get_window_extent(renderer=renderer).overlaps(
            ax.get_window_extent(renderer=renderer)
        )

        baseline = BytesIO()
        fig.savefig(baseline, format="png", bbox_inches="tight", dpi=180)
        baseline.seek(0)
        with Image.open(baseline) as image:
            baseline_height = image.height

        exported = _cache_figure(fig, "legend_export_regression", "多系列趋势")
        with Image.open(exported["local_path"]) as image:
            exported_height = image.height

        assert exported_height > baseline_height + 20
    finally:
        import matplotlib.pyplot as plt

        plt.close(fig)


@pytest.mark.asyncio
async def test_multi_chart_request_is_split_into_separate_report_images():
    result = await CreateReportChartTool().execute(
        chart_id="split_case",
        chart_type="bar",
        title="多个视角",
        data={
            "charts": [
                {"title": "月度趋势", "chart_type": "line", "data": {"x": ["1月", "2月"], "y": [1, 3]}},
                {"title": "TOP排行", "chart_type": "bar", "data": {"labels": ["A", "B"], "values": [3, 2]}},
            ]
        },
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["render_strategy"] == "split_images"
    assert all(
        child["text_layout"]["status"] in {"resolved", "degraded"}
        for child in result["data"]["metadata"]["child_charts"]
    )
    assert "split_complex_multi_chart_request" in result["data"]["layout_warnings"]
    assert len(result["visuals"]) == 2
    for visual in result["visuals"]:
        assert Path(visual["local_path"]).exists()


NEW_ANALYTICAL_CASES = [
    (
        "combo",
        {
            "labels": ["一季度", "二季度", "三季度"],
            "series": [
                {"name": "产量", "type": "bar", "values": [120, 150, 180]},
                {"name": "增速", "type": "line", "axis": "right", "values": [8, 12, 10]},
            ],
        },
        {"left_y_label": "产量（吨）", "right_y_label": "增速（%）"},
    ),
    (
        "range_line",
        {
            "labels": ["一月", "二月", "三月"],
            "series": [{"name": "浓度", "values": [42, 38, 35], "lower": [35, 31, 29], "upper": [49, 45, 42]}],
        },
        {},
    ),
    (
        "waterfall",
        {"labels": ["结构调整", "产量变化", "治理措施"], "values": [-12, 8, -6], "start_value": 100},
        {},
    ),
    ("pareto", {"labels": ["来源B", "来源A", "来源C"], "values": [30, 45, 25]}, {}),
    ("diverging_bar", {"labels": ["城市A", "城市B", "城市C"], "values": [-8.2, 3.1, -1.5]}, {}),
    ("step_line", {"labels": ["阶段一", "阶段二", "阶段三"], "values": [1, 2, 1.5]}, {"step": "post"}),
    (
        "error_bar",
        {"labels": ["A组", "B组", "C组"], "series": [{"name": "均值", "values": [12, 15, 11], "errors": [1.2, 1.5, 0.8]}]},
        {},
    ),
]

EXPECTED_NEW_GEOMETRIES = {
    "combo": ["bar", "line"],
    "range_line": ["line", "interval_band"],
    "waterfall": ["bar", "connector_line"],
    "pareto": ["bar", "line"],
    "diverging_bar": ["bar"],
    "step_line": ["line"],
    "error_bar": ["point", "error_bar"],
}


@pytest.mark.asyncio
@pytest.mark.parametrize(("chart_type", "data", "options"), NEW_ANALYTICAL_CASES)
async def test_new_analytical_chart_types_render_report_images(chart_type, data, options):
    result = await CreateReportChartTool().execute(
        chart_id=f"new_{chart_type}_case",
        chart_type=chart_type,
        title=f"{chart_type} 测试图",
        data=data,
        options=options,
    )

    metadata = result["data"]["metadata"]
    image_path = Path(result["visuals"][0]["local_path"])
    assert result["success"] is True, result
    assert metadata["applied_chart_type"] == chart_type
    assert metadata["series_count"] >= 1
    assert metadata["axis_count"] in {1, 2}
    assert metadata["geometry_types"] == EXPECTED_NEW_GEOMETRIES[chart_type]
    assert image_path.exists()
    with Image.open(image_path) as rendered_image:
        assert rendered_image.width >= 1000
        assert rendered_image.height >= 700
        grayscale = rendered_image.convert("L")
        minimum, maximum = grayscale.getextrema()
        assert maximum - minimum > 20


@pytest.mark.asyncio
async def test_combo_reports_axes_geometry_stacks_and_many_series_warning():
    result = await CreateReportChartTool().execute(
        chart_id="combo_metadata_case",
        chart_type="combo",
        title="结构与增长趋势",
        data={
            "labels": ["一月", "二月", "三月"],
            "series": [
                {"name": "工业", "type": "bar", "stack": "构成", "values": [20, 22, 21]},
                {"name": "交通", "type": "bar", "stack": "构成", "values": [10, 11, 9]},
                {"name": "目标", "type": "bar", "values": [35, 35, 35]},
                {"name": "总量", "type": "line", "values": [30, 33, 30]},
                {"name": "增速", "type": "line", "axis": "right", "values": [3, 10, -9]},
            ],
        },
        options={"left_y_label": "排放量（吨）", "right_y_label": "增速（%）"},
    )

    metadata = result["data"]["metadata"]
    assert result["success"] is True
    assert metadata["axis_count"] == 2
    assert metadata["axis_series_counts"] == {"left": 4, "right": 1}
    assert metadata["geometry_types"] == ["bar", "line"]
    assert metadata["stack_groups"] == ["构成"]
    assert "combo_many_series" in result["data"]["layout_warnings"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("series", "options", "expected_axis_count"),
    [
        (
            [
                {"name": "数量", "type": "bar", "values": [10, 12]},
                {"name": "趋势", "type": "line", "values": [9, 13]},
            ],
            {},
            1,
        ),
        (
            [
                {"name": "A", "type": "bar", "values": [10, 12]},
                {"name": "B", "type": "bar", "values": [8, 9]},
                {"name": "趋势", "type": "line", "axis": "right", "values": [2, 3]},
            ],
            {"left_y_label": "数量", "right_y_label": "增速"},
            2,
        ),
    ],
)
async def test_combo_supports_single_axis_and_grouped_dual_axis_variants(
    series, options, expected_axis_count
):
    result = await CreateReportChartTool().execute(
        chart_type="combo",
        title="组合变体",
        data={"labels": ["A", "B"], "series": series},
        options=options,
    )

    assert result["success"] is True, result
    assert result["data"]["metadata"]["axis_count"] == expected_axis_count


@pytest.mark.asyncio
async def test_combo_emits_density_and_dual_axis_scale_warnings():
    dense_series = [
        {"name": f"柱{index}", "type": "bar", "values": [index + 1] * 10}
        for index in range(5)
    ] + [{"name": "趋势", "type": "line", "values": list(range(10))}]
    dense_result = await CreateReportChartTool().execute(
        chart_type="combo",
        title="密集组合图",
        data={"labels": [f"分类{index}" for index in range(10)], "series": dense_series},
    )
    scale_result = await CreateReportChartTool().execute(
        chart_type="combo",
        title="双轴量级检查",
        data={
            "labels": ["A", "B"],
            "series": [
                {"name": "总量", "type": "bar", "values": [10000, 12000]},
                {"name": "比例", "type": "line", "axis": "right", "values": [1, 1.2]},
            ],
        },
        options={"left_y_label": "总量", "right_y_label": "比例"},
    )
    zero_scale_result = await CreateReportChartTool().execute(
        chart_type="combo",
        title="零值双轴检查",
        data={
            "labels": ["A", "B"],
            "series": [
                {"name": "总量", "type": "bar", "values": [100, 120]},
                {"name": "比例", "type": "line", "axis": "right", "values": [0, 0]},
            ],
        },
        options={"left_y_label": "总量", "right_y_label": "比例"},
    )

    assert dense_result["success"] is True
    assert "combo_many_series" in dense_result["data"]["layout_warnings"]
    assert "combo_narrow_bars" in dense_result["data"]["layout_warnings"]
    assert scale_result["success"] is True
    assert "combo_dual_axis_scale_disparity" in scale_result["data"]["layout_warnings"]
    assert zero_scale_result["success"] is True
    assert zero_scale_result["data"]["metadata"]["axis_magnitude_ratio"] == "infinite"
    assert "combo_dual_axis_scale_disparity" in zero_scale_result["data"]["layout_warnings"]


@pytest.mark.asyncio
async def test_new_analytical_chart_boundary_variants():
    overlap = await CreateReportChartTool().execute(
        chart_type="range_line",
        title="重叠区间",
        data={
            "labels": ["A", "B"],
            "series": [
                {"name": "系列一", "values": [5, 6], "lower": [3, 4], "upper": [7, 8]},
                {"name": "系列二", "values": [5.2, 6.2], "lower": [3.2, 4.2], "upper": [7.2, 8.2]},
            ],
        },
    )
    asymmetric = await CreateReportChartTool().execute(
        chart_type="error_bar",
        title="非对称误差",
        data={
            "labels": ["A", "B"],
            "series": [
                {"values": [5, 6], "lower_errors": [0.5, 0.8], "upper_errors": [1, 1.2]}
            ],
        },
    )
    multi_step = await CreateReportChartTool().execute(
        chart_type="step_line",
        title="多阶段线",
        data={
            "labels": ["A", "B"],
            "series": [
                {"name": "标准一", "values": [1, 2]},
                {"name": "标准二", "values": [2, 3]},
            ],
        },
        options={"step": "mid"},
    )
    horizontal = await CreateReportChartTool().execute(
        chart_type="diverging_bar",
        title="长标签变化",
        data={"labels": ["这是一个很长的分类标签", "另一个很长的分类标签"], "values": [-1, 2]},
    )
    no_total = await CreateReportChartTool().execute(
        chart_type="waterfall",
        title="不显示合计",
        data={"labels": ["变化一", "变化二"], "values": [2, -1], "show_total": False},
    )
    six_series = [
        {"name": f"柱{index}", "type": "bar", "values": [index + 1]}
        for index in range(5)
    ] + [{"name": "趋势", "type": "line", "values": [6]}]
    at_limit = await CreateReportChartTool().execute(
        chart_type="combo",
        title="六系列组合",
        data={"labels": ["A"], "series": six_series},
    )

    assert overlap["success"] is True
    assert "range_intervals_heavily_overlap" in overlap["data"]["layout_warnings"]
    assert asymmetric["success"] is True
    assert asymmetric["data"]["metadata"]["error_modes"] == ["asymmetric"]
    assert multi_step["success"] is True
    assert multi_step["data"]["metadata"]["series_count"] == 2
    assert multi_step["data"]["metadata"]["step_where"] == "mid"
    assert horizontal["success"] is True
    assert horizontal["data"]["metadata"]["orientation"] == "horizontal"
    assert no_total["success"] is True
    assert "total" not in no_total["data"]["metadata"]["bar_kinds"]
    assert at_limit["success"] is True
    assert at_limit["data"]["metadata"]["series_count"] == 6


@pytest.mark.asyncio
async def test_pareto_returns_sorted_and_cumulative_metadata():
    result = await CreateReportChartTool().execute(
        chart_id="pareto_metadata_case",
        chart_type="pareto",
        title="来源累计贡献",
        data={"labels": ["B", "A", "C"], "values": [30, 45, 25]},
    )

    metadata = result["data"]["metadata"]
    assert result["success"] is True
    assert metadata["sorted_labels"] == ["A", "B", "C"]
    assert metadata["cumulative_values"] == [45, 75, 100]
    assert metadata["cumulative_percentages"] == pytest.approx([45, 75, 100])
    assert metadata["threshold_percent"] == 80


@pytest.mark.asyncio
async def test_waterfall_supports_explicit_subtotal_without_duplicate_total():
    result = await CreateReportChartTool().execute(
        chart_id="waterfall_subtotal_case",
        chart_type="waterfall",
        title="阶段变化拆解",
        data={
            "labels": ["因素一", "阶段小计", "最终值"],
            "values": [-10, 90, 82],
            "measures": ["relative", "subtotal", "total"],
            "start_value": 100,
        },
    )

    metadata = result["data"]["metadata"]
    assert result["success"] is True
    assert metadata["measures"] == ["relative", "subtotal", "total"]
    assert metadata["cumulative_positions"] == [90, 90, 82]
    assert metadata["bar_kinds"] == ["start", "decrease", "subtotal", "total"]
    assert metadata["final_value"] == 82


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chart_type", "data", "options", "error_fragment"),
    [
        (
            "combo",
            {
                "labels": ["A", "B"],
                "series": [
                    {"name": "值", "type": "bar", "values": [1, 2]},
                    {"name": "率", "type": "line", "axis": "right", "values": [3, 4]},
                ],
            },
            {},
            "必须提供左右轴标题或单位",
        ),
        ("pareto", {"labels": ["A", "B"], "values": [0, 0]}, {}, "合计必须大于 0"),
        (
            "range_line",
            {"labels": ["A"], "series": [{"values": [2], "lower": [3], "upper": [4]}]},
            {},
            "lower[0] 不得大于 values[0]",
        ),
        (
            "error_bar",
            {"labels": ["A"], "series": [{"values": [2], "errors": [-1]}]},
            {},
            "不允许包含负数",
        ),
        ("diverging_bar", {"labels": ["A"], "values": [float("nan")]}, {}, "必须是有限数值"),
        (
            "error_bar",
            {"labels": ["A"], "series": [{"values": [2], "lower_errors": [1]}]},
            {},
            "同时提供 lower_errors 和 upper_errors",
        ),
        (
            "combo",
            {
                "labels": ["A"],
                "series": [
                    {"name": "柱", "type": "bar", "values": [1]},
                    {"name": "线", "type": "line", "values": [float("inf")]},
                ],
            },
            {},
            "必须是有限数值",
        ),
    ],
)
async def test_new_analytical_chart_validation_returns_precise_failures(chart_type, data, options, error_fragment):
    result = await CreateReportChartTool().execute(
        chart_type=chart_type,
        title="非法输入",
        data=data,
        options=options,
    )

    assert result["success"] is False
    assert error_fragment in result["error"]
    assert result["visuals"] == []


ANALYTICAL_VALIDATION_MATRIX = [
    ("combo-empty", "combo", {"labels": [], "series": []}),
    (
        "combo-length",
        "combo",
        {
            "labels": ["A", "B"],
            "series": [
                {"type": "bar", "values": [1]},
                {"type": "line", "values": [1, 2]},
            ],
        },
    ),
    (
        "combo-nonfinite",
        "combo",
        {
            "labels": ["A"],
            "series": [
                {"type": "bar", "values": [1]},
                {"type": "line", "values": [float("nan")]},
            ],
        },
    ),
    ("range-empty", "range_line", {"labels": [], "series": []}),
    (
        "range-length",
        "range_line",
        {"labels": ["A"], "series": [{"values": [1, 2], "lower": [0], "upper": [2]}]},
    ),
    (
        "range-nonfinite",
        "range_line",
        {"labels": ["A"], "series": [{"values": [float("inf")], "lower": [0], "upper": [2]}]},
    ),
    ("waterfall-empty", "waterfall", {"labels": [], "values": []}),
    ("waterfall-length", "waterfall", {"labels": ["A", "B"], "values": [1]}),
    ("waterfall-nonfinite", "waterfall", {"labels": ["A"], "values": [float("nan")]}),
    ("pareto-empty", "pareto", {"labels": [], "values": []}),
    ("pareto-length", "pareto", {"labels": ["A", "B"], "values": [1]}),
    ("pareto-nonfinite", "pareto", {"labels": ["A"], "values": [float("inf")]}),
    ("diverging-empty", "diverging_bar", {"labels": [], "values": []}),
    ("diverging-length", "diverging_bar", {"labels": ["A", "B"], "values": [1]}),
    (
        "diverging-nonfinite",
        "diverging_bar",
        {"labels": ["A"], "values": [float("nan")]},
    ),
    ("step-empty", "step_line", {"labels": [], "values": []}),
    ("step-length", "step_line", {"labels": ["A", "B"], "values": [1]}),
    ("step-nonfinite", "step_line", {"labels": ["A"], "values": [float("inf")]}),
    ("error-empty", "error_bar", {"labels": [], "series": []}),
    (
        "error-length",
        "error_bar",
        {"labels": ["A", "B"], "series": [{"values": [1], "errors": [0.2]}]},
    ),
    (
        "error-nonfinite",
        "error_bar",
        {"labels": ["A"], "series": [{"values": [float("nan")], "errors": [0.2]}]},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "chart_type", "data"),
    ANALYTICAL_VALIDATION_MATRIX,
    ids=[case[0] for case in ANALYTICAL_VALIDATION_MATRIX],
)
async def test_new_analytical_protocols_reject_empty_mismatched_and_nonfinite_data(
    case_id, chart_type, data
):
    result = await CreateReportChartTool().execute(
        chart_type=chart_type,
        title=case_id,
        data=data,
    )

    assert result["success"] is False
    assert result["visuals"] == []


@pytest.mark.asyncio
async def test_combo_enforces_six_series_limit_and_rejects_line_stack():
    seven_series = [
        {"name": f"柱{index}", "type": "bar", "values": [index + 1]}
        for index in range(6)
    ] + [{"name": "趋势", "type": "line", "values": [1]}]
    too_many = await CreateReportChartTool().execute(
        chart_type="combo",
        title="系列上限",
        data={"labels": ["A"], "series": seven_series},
    )
    line_stack = await CreateReportChartTool().execute(
        chart_type="combo",
        title="非法堆叠",
        data={
            "labels": ["A"],
            "series": [
                {"name": "柱", "type": "bar", "values": [1]},
                {"name": "线", "type": "line", "stack": "组", "values": [2]},
            ],
        },
    )

    assert too_many["success"] is False
    assert "最多支持 6 个系列" in too_many["error"]
    assert line_stack["success"] is False
    assert "stack 仅适用于 bar 系列" in line_stack["error"]


@pytest.mark.asyncio
async def test_failed_report_chart_render_does_not_leak_matplotlib_figures():
    before = set(plt.get_fignums())
    result = await CreateReportChartTool().execute(
        chart_type="range_line",
        title="非法区间",
        data={
            "labels": ["A"],
            "series": [{"values": [2], "lower": [3], "upper": [4]}],
        },
    )

    assert result["success"] is False
    assert set(plt.get_fignums()) == before
