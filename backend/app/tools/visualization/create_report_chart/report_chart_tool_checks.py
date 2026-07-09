from pathlib import Path

import pytest

from app.tools.visualization.create_report_chart.tool import (
    CreateReportChartTool,
    report_chart_reference_paths,
)
from app.tools.visualization.create_report_chart.renderer import select_chinese_font


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
        "data_id",
        "output_context",
        "style_profile",
        "notes",
        "options",
    }
    assert schema["parameters"]["required"] == ["chart_type", "title"]
    assert len(str(schema)) < 7000
    assert "references/index.md" in schema["description"]
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
        "pollutant_calendar",
        "generic_pollutant_wind_rose",
        "aqi_calendar",
        "pollutant_wind_rose",
    ]
    assert "不是 ECharts option" in properties["data"]["description"]
    assert "series[0].data" in properties["data"]["description"]
    assert "series[0].values" in properties["data"]["description"]
    assert "多序列" in properties["data"]["description"]
    assert "data_id" in properties["data"]["description"]
    assert "reference_lines" in properties["options"]["description"]


def test_reference_paths_include_specialized_chart_type_documents():
    paths = report_chart_reference_paths()

    expected_keys = {
        "index",
        "word_a4_rules",
        "layout_rules",
        "long_label_rules",
        "pie_rules",
        "chart_types",
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
        "pollutant_calendar",
        "generic_pollutant_wind_rose",
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
    assert "aqi_calendar" in aqi_calendar_text
    assert "广东省专用" in aqi_calendar_text
    assert "pollutant_wind_rose" in pollutant_wind_rose_text
    assert "广东省专用" in pollutant_wind_rose_text
    assert "pollutant_calendar" in pollutant_calendar_text
    assert "generic_pollutant_wind_rose" in generic_wind_rose_text


def test_renderer_selects_existing_chinese_font_file_when_available():
    font_path = select_chinese_font()

    assert font_path is not None
    assert Path(font_path).exists()
    assert font_path == "/home/xckj/.local/share/fonts/方正小标宋简.TTF"


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
        data_id="chart_data:v1:resource_refs",
    )

    image_path = Path(result["visuals"][0]["local_path"])

    assert result["success"] is True
    assert image_path.exists()
    assert result["refs"]["data"] == [
        {
            "data_id": "chart_data:v1:resource_refs",
            "usage": "source",
            "tool": "read_data_registry",
        }
    ]
    assert result["refs"]["files"][0]["path"] == str(image_path)
    assert result["refs"]["files"][0]["type"] == "image"
    assert result["refs"]["files"][0]["usage"] == "report_chart"
    assert result["refs"]["visuals"][0]["tool_path"] == str(image_path)
    assert result["llm_resume"]["source_data_id"] == "chart_data:v1:resource_refs"
    assert result["llm_resume"]["generated_visuals"][0]["tool_path"] == str(image_path)
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
async def test_aqi_calendar_renders_records_loaded_from_context_data_id():
    records = [
        {"city": "广州", "date": "2026-05-01", "aqi": 82},
        {"city": "广州", "date": "2026-05-02", "aqi": 49},
        {"city": "深圳", "date": "2026-05-01", "aqi": 42},
        {"city": "深圳", "date": "2026-05-02", "aqi": 51},
    ]

    result = await CreateReportChartTool().execute(
        context=FakeChartContext(records),
        chart_id="aqi_calendar_data_id_case",
        chart_type="aqi_calendar",
        title="AQI 日历",
        data_id="chart_data:v1:abc",
        options={"year": 2026, "month": 5, "pollutant": "AQI", "cities": ["广州", "深圳"]},
    )

    assert result["success"] is True
    assert result["metadata"]["source_data_id"] == "chart_data:v1:abc"
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
async def test_pollutant_wind_rose_renders_records_loaded_from_context_data_id():
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
        chart_id="pollutant_wind_rose_data_id_case",
        chart_type="pollutant_wind_rose",
        title="PM10 污染物风玫瑰图",
        data_id="chart_data:v1:abc",
        options={"pollutant_name": "PM10", "unit": "μg/m³", "time_resolution": "5min", "use_six_level": False},
    )

    assert result["success"] is True
    assert result["metadata"]["source_data_id"] == "chart_data:v1:abc"
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
async def test_data_id_without_context_returns_tool_error():
    result = await CreateReportChartTool().execute(
        chart_type="line",
        title="data_id 趋势",
        data_id="chart_data:v1:abc",
    )

    assert result["success"] is False
    assert "需要 ExecutionContext" in result["error"]


class FakeChartContext:
    def __init__(self, payload):
        self.payload = payload

    def get_raw_data(self, data_id):
        assert data_id == "chart_data:v1:abc"
        return [self.payload]


@pytest.mark.asyncio
async def test_data_id_loads_chart_payload_from_context():
    result = await CreateReportChartTool().execute(
        context=FakeChartContext({"labels": ["A", "B"], "values": [1, 2]}),
        chart_id="data_id_case",
        chart_type="bar",
        title="data_id 柱状图",
        data_id="chart_data:v1:abc",
    )

    assert result["success"] is True
    assert result["metadata"]["source_data_id"] == "chart_data:v1:abc"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_runtime_positional_context_call_does_not_conflict_with_chart_type():
    result = await CreateReportChartTool().execute(
        FakeChartContext({"labels": ["A", "B"], "values": [1, 2]}),
        chart_id="runtime_context_case",
        chart_type="bar",
        title="runtime context 柱状图",
        data_id="chart_data:v1:abc",
    )

    assert result["success"] is True
    assert result["metadata"]["source_data_id"] == "chart_data:v1:abc"
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
    assert "split_complex_multi_chart_request" in result["data"]["layout_warnings"]
    assert len(result["visuals"]) == 2
    for visual in result["visuals"]:
        assert Path(visual["local_path"]).exists()
