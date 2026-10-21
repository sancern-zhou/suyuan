from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from PIL import Image

from app.utils.font_utils import get_font_manager
from app.utils.path_config import resolve_agent_path
from app.tools.visualization.create_business_chart.tool import (
    CreateBusinessChartTool,
    business_chart_reference_paths,
)
from app.tools.visualization.create_business_chart.renderer import (
    _cache_figure,
    _create_figure,
    _draw_dual_axis_line,
    _draw_line,
    _position_legends_below_plot,
    select_chinese_font,
)
from app.tools.visualization.create_business_chart.theme import SERIES_COLORS
from config.settings import settings


@pytest.fixture(autouse=True)
def _use_default_project(monkeypatch):
    """共享图型目录测试固定 default 项目，避免项目裁剪影响枚举与引用路径。"""
    monkeypatch.setattr(settings, "project_id", "default")


def test_schema_stays_compact_and_points_to_progressive_references():
    tool = CreateBusinessChartTool()

    schema = tool.get_function_schema()
    properties = schema["parameters"]["properties"]

    assert schema["name"] == "create_business_chart"
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
    assert len(str(schema)) < 10000
    assert "references/index.md" in schema["description"]
    assert "两层规范" in schema["description"]
    assert "无需另读输入、A4 或布局规范" in schema["description"]
    assert "data 或 file_path" in schema["description"]
    assert set(properties["chart_type"]["enum"]) == {
        "aqi_calendar", "pollutant_calendar", "pollutant_wind_rose",
        "generic_pollutant_wind_rose", "wind_timeseries", "weather_timeseries",
        "henan_city_map",
    }
    assert "不是 ECharts option" in properties["data"]["description"]
    assert "file_path" in properties["data"]["description"]
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
    paths = business_chart_reference_paths()

    expected_keys = {
        "index", "pollutant_calendar", "generic_pollutant_wind_rose",
        "wind_timeseries", "weather_timeseries", "aqi_calendar", "pollutant_wind_rose",
        "henan_city_map",
    }

    assert set(paths) == expected_keys
    for path in paths.values():
        assert path.startswith("backend/")
        assert resolve_agent_path(path).exists()

    aqi_calendar_text = resolve_agent_path(paths["aqi_calendar"]).read_text(encoding="utf-8")
    pollutant_wind_rose_text = resolve_agent_path(paths["pollutant_wind_rose"]).read_text(encoding="utf-8")
    pollutant_calendar_text = resolve_agent_path(paths["pollutant_calendar"]).read_text(encoding="utf-8")
    generic_wind_rose_text = resolve_agent_path(paths["generic_pollutant_wind_rose"]).read_text(encoding="utf-8")
    wind_timeseries_text = resolve_agent_path(paths["wind_timeseries"]).read_text(encoding="utf-8")
    weather_timeseries_text = resolve_agent_path(paths["weather_timeseries"]).read_text(encoding="utf-8")
    henan_city_map_text = resolve_agent_path(paths["henan_city_map"]).read_text(encoding="utf-8")
    index_text = resolve_agent_path(paths["index"]).read_text(encoding="utf-8")
    assert "aqi_calendar" in aqi_calendar_text
    assert "广东省专用" in aqi_calendar_text
    assert "pollutant_wind_rose" in pollutant_wind_rose_text
    assert "广东省专用" in pollutant_wind_rose_text
    assert "pollutant_calendar" in pollutant_calendar_text
    assert "generic_pollutant_wind_rose" in generic_wind_rose_text
    assert "wind_timeseries" in wind_timeseries_text
    assert "meteorological_from" in wind_timeseries_text
    assert "henan_city_map" in henan_city_map_text
    assert "Supply at least one of `data` or `file_path`" in index_text
    assert "current session" in index_text
    assert "not infer arbitrary record fields" in index_text
    assert "exactly one matching chart document" in index_text


def test_renderer_selects_existing_chinese_font_file_when_available():
    font_path = select_chinese_font()
    font_paths = get_font_manager().FONT_FILE_PATHS
    expected = next(
        (path for path in font_paths if path.exists()),
        None,
    )
    fangzheng_path = Path("/home/xckj/.local/share/fonts/方正小标宋简.TTF")
    gb_xbs_path = Path("/usr/share/fonts/gb-cjk/GB_XBS_GB18030.TTF")
    noto_path = Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc")

    assert font_paths.index(fangzheng_path) < font_paths.index(gb_xbs_path)
    assert font_paths.index(gb_xbs_path) < font_paths.index(noto_path)
    assert expected is not None
    assert font_path == str(expected)
    assert Path(font_path).exists()
    if not fangzheng_path.exists() and gb_xbs_path.exists():
        assert font_path == str(gb_xbs_path)


def test_henan_city_map_uses_new_standard_breakpoints_by_metric():
    from app.tools.visualization.create_business_chart.domain.henan_city_map import (
        LEVELS,
        NEW_STANDARD_CONCENTRATION_BREAKS,
        _metric_key,
    )

    assert LEVELS == (50, 100, 150, 200, 300)
    assert NEW_STANDARD_CONCENTRATION_BREAKS["PM2_5"] == (35, 60, 115, 150, 250)
    assert NEW_STANDARD_CONCENTRATION_BREAKS["PM10"] == (50, 120, 250, 350, 420)
    assert NEW_STANDARD_CONCENTRATION_BREAKS["O3_8h"] == (100, 160, 215, 265, 800)
    assert _metric_key("PM2.5") == "PM2_5"
    assert _metric_key("O3_8H") == "O3_8h"


def test_label_normalization_converts_ionic_superscripts_and_subscripts_to_mathtext():
    from app.tools.visualization.create_business_chart.text import normalize_matplotlib_label_text

    assert (
        normalize_matplotlib_label_text("各城市PM2.5中SO₄²⁻/NO₃⁻比值对比")
        == "各城市PM$_{2.5}$中SO$_4^{2-}$/NO$_3^-$比值对比"
    )
    assert normalize_matplotlib_label_text("NH₄⁺贡献占比") == "NH$_4^+$贡献占比"
    assert normalize_matplotlib_label_text("O₃_8H日最大") == "O$_3$-8H日最大"
    assert normalize_matplotlib_label_text("PM2.5浓度") == "PM$_{2.5}$浓度"


@pytest.mark.asyncio
async def test_specialized_chart_type_routes_through_unified_tool_metadata():
    result = await CreateBusinessChartTool().execute(
        chart_type="aqi_calendar",
        title="AQI 日历",
        data={"dates": ["2026-01-01"], "aqi": [80]},
        options={"dry_run": True},
    )

    assert result["success"] is True
    assert result["metadata"]["tool_name"] == "create_business_chart"
    assert result["metadata"]["chart_type"] == "aqi_calendar"
    assert result["data"]["render_mode"] == "dry_run"


@pytest.mark.asyncio
async def test_business_chart_returns_resource_refs_and_resume_hints():
    result = await CreateBusinessChartTool().execute(
        chart_id="resource_refs_case",
        chart_type="pollutant_calendar",
        title="资源协议测试图",
        data={"year": 2026, "month": 5, "values": [{"date": "2026-05-01", "value": 18}]},
        file_path="/configured/data/root/sessions/agent_session_test/data/resource-refs.json",
    )

    image_path = Path(result["visuals"][0]["local_path"])

    assert result["success"] is True
    assert image_path.exists()
    assert result["refs"]["data"] == [
        {
            "file_path": "/configured/data/root/sessions/agent_session_test/data/resource-refs.json",
            "usage": "source",
        }
    ]
    assert result["refs"]["files"][0]["path"] == str(image_path)
    assert result["refs"]["files"][0]["type"] == "image"
    assert result["refs"]["files"][0]["usage"] == "business_chart"
    assert result["refs"]["visuals"][0]["tool_path"] == str(image_path)
    assert result["llm_resume"]["source_file_path"] == "/configured/data/root/sessions/agent_session_test/data/resource-refs.json"
    assert result["llm_resume"]["generated_visuals"][0]["tool_path"] == str(image_path)
    assert str(image_path) in result["llm_resume"]["tool_hint"]
    assert "Do not place this server path" in result["llm_resume"]["tool_hint"]


@pytest.mark.asyncio
async def test_aqi_calendar_renders_prepared_city_data_map():
    result = await CreateBusinessChartTool().execute(
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

    result = await CreateBusinessChartTool().execute(
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

    result = await CreateBusinessChartTool().execute(
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

    result = await CreateBusinessChartTool().execute(
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
    result = await CreateBusinessChartTool().execute(
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

    result = await CreateBusinessChartTool().execute(
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
    result = await CreateBusinessChartTool().execute(
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
    assert metadata["pollutant_name"] == "PM$_{2.5}$"
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
    result = await CreateBusinessChartTool().execute(
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
    assert metadata["pollutant_name"] == "O$_3$"
    assert metadata["valid_point_count"] == len(records)
    assert Path(result["visuals"][0]["local_path"]).exists()


def test_wind_timeseries_converts_meteorological_direction_to_components():
    from app.tools.visualization.create_business_chart.domain.wind_timeseries import (
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
    result = await CreateBusinessChartTool().execute(
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
    result = await CreateBusinessChartTool().execute(
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


def test_dual_axis_line_uses_distinct_series_colors_across_axes():
    fig, ax = plt.subplots()
    try:
        _draw_dual_axis_line(
            ax,
            "PM2.5与风速",
            {
                "labels": ["09-22", "09-23"],
                "series": [
                    {"name": "PM2.5", "values": [59, 65], "axis": "left"},
                    {"name": "风速", "values": [1.62, 1.60], "axis": "right"},
                ],
            },
            {"legend": True},
        )
        left_color = ax.lines[0].get_color()
        right_color = fig.axes[1].lines[0].get_color()
        assert (left_color, right_color) == SERIES_COLORS[:2]
        assert left_color != right_color
    finally:
        plt.close(fig)


@pytest.mark.asyncio
async def test_missing_data_and_file_path_returns_input_contract_error():
    result = await CreateBusinessChartTool().execute(
        chart_type="pollutant_calendar",
        title="缺少数据输入",
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "必须提供 data 或 file_path" in result["error"]


@pytest.mark.asyncio
async def test_file_path_without_context_returns_tool_error():
    result = await CreateBusinessChartTool().execute(
        chart_type="pollutant_calendar",
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
    result = await CreateBusinessChartTool().execute(
        context=FakeChartContext({"year": 2026, "month": 5, "values": [{"date": "2026-05-01", "value": 18}]}),
        chart_id="file_path_case",
        chart_type="pollutant_calendar",
        title="file_path 污染物日历",
        file_path="chart_data:v1:abc",
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_runtime_positional_context_call_does_not_conflict_with_chart_type():
    result = await CreateBusinessChartTool().execute(
        FakeChartContext({"year": 2026, "month": 5, "values": [{"date": "2026-05-01", "value": 18}]}),
        chart_id="runtime_context_case",
        chart_type="pollutant_calendar",
        title="runtime context 污染物日历",
        file_path="chart_data:v1:abc",
    )

    assert result["success"] is True
    assert result["metadata"]["source_file_path"] == "chart_data:v1:abc"
    assert Path(result["visuals"][0]["local_path"]).exists()


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
        plt.close(fig)
