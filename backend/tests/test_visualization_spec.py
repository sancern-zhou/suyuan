"""
测试可视化规范 (VisualizationSpec)

验证内容：
1. 规范定义的完整性
2. 数据验证逻辑
3. 转换函数（to_vegalite, to_echarts）
4. 错误处理
"""

import pytest
from datetime import datetime

from app.schemas.visualization_spec import (
    VisualizationSpec,
    DataReference,
    EncodingChannel,
    Transform,
    ChartConfig,
    spec_to_vegalite,
    spec_to_echarts,
    validate_spec,
    create_simple_spec
)


class TestDataReference:
    """测试数据引用"""

    def test_data_reference_creation(self):
        """测试创建数据引用"""
        data_ref = DataReference(
            data_id="vocs:v1:abc123",
            schema="vocs"
        )
        assert data_ref.data_id == "vocs:v1:abc123"
        assert data_ref.schema == "vocs"

    def test_data_reference_dict(self):
        """测试数据引用转字典"""
        data_ref = DataReference(
            data_id="air_quality:v1:test",
            schema="air_quality"
        )
        data_dict = data_ref.dict()
        assert data_dict["data_id"] == "air_quality:v1:test"
        assert data_dict["schema"] == "air_quality"


class TestEncodingChannel:
    """测试编码通道"""

    def test_encoding_channel_basic(self):
        """测试基础编码通道"""
        encoding = EncodingChannel(
            field="PM2.5",
            type="quantitative"
        )
        assert encoding.field == "PM2.5"
        assert encoding.type == "quantitative"
        assert encoding.aggregate is None

    def test_encoding_channel_with_aggregate(self):
        """测试带聚合函数的编码"""
        encoding = EncodingChannel(
            field="concentration",
            type="quantitative",
            aggregate="mean",
            title="平均浓度"
        )
        assert encoding.aggregate == "mean"
        assert encoding.title == "平均浓度"

    def test_encoding_channel_with_scale(self):
        """测试带刻度配置的编码"""
        encoding = EncodingChannel(
            field="AQI",
            type="quantitative",
            scale={"domain": [0, 500]}
        )
        assert encoding.scale["domain"] == [0, 500]


class TestVisualizationSpec:
    """测试可视化规范"""

    def test_bar_chart_spec(self):
        """测试柱状图规范"""
        spec = VisualizationSpec(
            mark="bar",
            data=DataReference(data_id="test:v1:001", schema="vocs"),
            encoding={
                "x": EncodingChannel(field="species_name", type="nominal"),
                "y": EncodingChannel(field="concentration", type="quantitative")
            }
        )
        assert spec.mark == "bar"
        assert "x" in spec.encoding
        assert "y" in spec.encoding

    def test_line_chart_spec(self):
        """测试折线图规范"""
        spec = VisualizationSpec(
            mark="line",
            data={"values": [{"x": 1, "y": 10}, {"x": 2, "y": 20}]},
            encoding={
                "x": EncodingChannel(field="x", type="quantitative"),
                "y": EncodingChannel(field="y", type="quantitative")
            },
            title="测试折线图"
        )
        assert spec.mark == "line"
        assert spec.title == "测试折线图"
        assert isinstance(spec.data, dict)

    def test_pie_chart_spec(self):
        """测试饼图规范"""
        spec = VisualizationSpec(
            mark="pie",
            data=DataReference(data_id="test:v1:002", schema="pmf_result"),
            encoding={
                "theta": EncodingChannel(field="contribution_pct", type="quantitative"),
                "color": EncodingChannel(field="source_name", type="nominal")
            }
        )
        assert spec.mark == "pie"
        assert "theta" in spec.encoding

    def test_timeseries_spec(self):
        """测试时序图规范"""
        spec = VisualizationSpec(
            mark="timeseries",
            data=DataReference(data_id="test:v1:003", schema="air_quality"),
            encoding={
                "x": EncodingChannel(field="timePoint", type="temporal"),
                "y": EncodingChannel(field="PM2.5", type="quantitative"),
                "color": EncodingChannel(field="station_name", type="nominal")
            }
        )
        assert spec.mark == "timeseries"
        assert spec.encoding["x"].type == "temporal"

    def test_spec_validation_bar_missing_y(self):
        """测试柱状图缺少y编码的验证"""
        with pytest.raises(ValueError, match="必须包含x和y编码"):
            VisualizationSpec(
                mark="bar",
                data=DataReference(data_id="test:v1:004", schema="vocs"),
                encoding={
                    "x": EncodingChannel(field="species_name", type="nominal")
                }
            )

    def test_spec_validation_pie_missing_theta(self):
        """测试饼图缺少theta编码的验证"""
        with pytest.raises(ValueError, match="必须包含theta或value编码"):
            VisualizationSpec(
                mark="pie",
                data=DataReference(data_id="test:v1:005", schema="pmf_result"),
                encoding={
                    "color": EncodingChannel(field="source_name", type="nominal")
                }
            )


class TestSpecToVegalite:
    """测试转换为Vega-Lite格式"""

    def test_simple_bar_chart_conversion(self):
        """测试简单柱状图转换"""
        spec = VisualizationSpec(
            mark="bar",
            data=DataReference(data_id="test:v1:001", schema="vocs"),
            encoding={
                "x": EncodingChannel(field="species_name", type="nominal"),
                "y": EncodingChannel(field="concentration", type="quantitative")
            },
            title="VOCs浓度"
        )

        vegalite = spec_to_vegalite(spec)

        assert vegalite["$schema"] == "https://vega.github.io/schema/vega-lite/v5.json"
        assert vegalite["mark"] == "bar"
        assert vegalite["title"] == "VOCs浓度"
        assert vegalite["encoding"]["x"]["field"] == "species_name"
        assert vegalite["encoding"]["y"]["field"] == "concentration"

    def test_with_aggregate_conversion(self):
        """测试带聚合函数的转换"""
        spec = VisualizationSpec(
            mark="bar",
            data=DataReference(data_id="test:v1:002", schema="air_quality"),
            encoding={
                "x": EncodingChannel(field="station_name", type="nominal"),
                "y": EncodingChannel(
                    field="PM2.5",
                    type="quantitative",
                    aggregate="mean",
                    title="平均PM2.5"
                )
            }
        )

        vegalite = spec_to_vegalite(spec)

        assert vegalite["encoding"]["y"]["aggregate"] == "mean"
        assert vegalite["encoding"]["y"]["title"] == "平均PM2.5"


class TestSpecToEcharts:
    """测试转换为ECharts格式"""

    def test_bar_chart_conversion(self):
        """测试柱状图转换"""
        spec = VisualizationSpec(
            mark="bar",
            data=DataReference(data_id="test:v1:001", schema="vocs"),
            encoding={
                "x": EncodingChannel(field="species_name", type="nominal"),
                "y": EncodingChannel(field="concentration", type="quantitative")
            },
            title="VOCs浓度"
        )

        echarts_option = spec_to_echarts(spec)

        assert echarts_option["title"]["text"] == "VOCs浓度"
        assert echarts_option["xAxis"]["type"] == "category"
        assert echarts_option["yAxis"]["type"] == "value"
        assert echarts_option["series"][0]["type"] == "bar"

    def test_line_chart_conversion(self):
        """测试折线图转换"""
        spec = VisualizationSpec(
            mark="line",
            data=DataReference(data_id="test:v1:002", schema="air_quality"),
            encoding={
                "x": EncodingChannel(field="timePoint", type="temporal"),
                "y": EncodingChannel(field="PM2.5", type="quantitative")
            }
        )

        echarts_option = spec_to_echarts(spec)

        assert echarts_option["xAxis"]["type"] == "time"
        assert echarts_option["series"][0]["type"] == "line"

    def test_pie_chart_conversion(self):
        """测试饼图转换"""
        spec = VisualizationSpec(
            mark="pie",
            data=DataReference(data_id="test:v1:003", schema="pmf_result"),
            encoding={
                "theta": EncodingChannel(field="contribution_pct", type="quantitative"),
                "color": EncodingChannel(field="source_name", type="nominal")
            },
            title="源贡献占比"
        )

        echarts_option = spec_to_echarts(spec)

        assert echarts_option["title"]["text"] == "源贡献占比"
        assert echarts_option["series"][0]["type"] == "pie"
        assert echarts_option["series"][0]["radius"] == "50%"


class TestValidateSpec:
    """测试规范验证"""

    def test_valid_spec(self):
        """测试有效规范"""
        spec = VisualizationSpec(
            mark="bar",
            data=DataReference(data_id="test:v1:001", schema="vocs"),
            encoding={
                "x": EncodingChannel(field="species_name", type="nominal"),
                "y": EncodingChannel(field="concentration", type="quantitative")
            }
        )

        result = validate_spec(spec)

        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_temporal_field_warning(self):
        """测试时间字段类型警告"""
        spec = VisualizationSpec(
            mark="line",
            data=DataReference(data_id="test:v1:002", schema="air_quality"),
            encoding={
                "x": EncodingChannel(field="timePoint", type="quantitative"),  # 应该是temporal
                "y": EncodingChannel(field="PM2.5", type="quantitative")
            }
        )

        result = validate_spec(spec)

        assert result["valid"] is True
        assert len(result["warnings"]) > 0
        # 检查警告中包含字段名和时间相关提示
        assert "timePoint" in result["warnings"][0]
        assert "时间字段" in result["warnings"][0]


class TestCreateSimpleSpec:
    """测试快速创建规范"""

    def test_create_bar_chart(self):
        """测试创建柱状图"""
        spec = create_simple_spec(
            mark="bar",
            data_id="vocs:v1:abc123",
            schema="vocs",
            x_field="species_name",
            y_field="concentration",
            title="VOCs浓度分布"
        )

        assert spec.mark == "bar"
        assert spec.title == "VOCs浓度分布"
        assert spec.encoding["x"].field == "species_name"
        assert spec.encoding["y"].field == "concentration"

    def test_create_timeseries_chart(self):
        """测试创建时序图"""
        spec = create_simple_spec(
            mark="line",
            data_id="air_quality:v1:test",
            schema="air_quality",
            x_field="timePoint",
            y_field="PM2.5",
            x_type="temporal",
            title="PM2.5时序变化"
        )

        assert spec.mark == "line"
        assert spec.encoding["x"].type == "temporal"


class TestChartConfig:
    """测试图表配置"""

    def test_chart_config_creation(self):
        """测试创建图表配置"""
        spec = VisualizationSpec(
            mark="bar",
            data=DataReference(data_id="test:v1:001", schema="vocs"),
            encoding={
                "x": EncodingChannel(field="species_name", type="nominal"),
                "y": EncodingChannel(field="concentration", type="quantitative")
            }
        )

        config = ChartConfig(
            chart_id="chart_001",
            specification=spec,
            quality_score=0.85,
            generated_by="template"
        )

        assert config.chart_id == "chart_001"
        assert config.quality_score == 0.85
        assert config.generated_by == "template"
        assert isinstance(config.generated_at, datetime)

    def test_chart_config_with_hints(self):
        """测试带渲染提示的配置"""
        spec = VisualizationSpec(
            mark="line",
            data=DataReference(data_id="test:v1:002", schema="air_quality"),
            encoding={
                "x": EncodingChannel(field="timePoint", type="temporal"),
                "y": EncodingChannel(field="PM2.5", type="quantitative")
            }
        )

        config = ChartConfig(
            chart_id="chart_002",
            specification=spec,
            generated_by="smart_recommend",
            render_hints={
                "preferred_library": "vega-lite",
                "fallback_library": "echarts"
            }
        )

        assert config.render_hints["preferred_library"] == "vega-lite"
        assert config.render_hints["fallback_library"] == "echarts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
