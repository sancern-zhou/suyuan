"""
测试图表数据目录 (ChartDataCatalog)

验证内容：
1. 数据目录的完整性
2. 推荐模板查询
3. 字段验证
4. 条件检查
"""

import pytest

from app.tools.visualization.chart_data_catalog import (
    ChartTemplate,
    DataCatalogEntry,
    CHART_DATA_CATALOG,
    get_catalog_entry,
    get_recommended_templates,
    validate_data_fields,
    get_all_schemas,
    get_catalog_summary
)


class TestChartTemplate:
    """测试图表模板"""

    def test_template_creation(self):
        """测试创建图表模板"""
        template = ChartTemplate(
            chart_type="bar",
            scenario="组分对比",
            priority=1,
            encoding_template={
                "x": {"field": "species_name", "type": "nominal"},
                "y": {"field": "concentration", "type": "quantitative"}
            }
        )

        assert template.chart_type == "bar"
        assert template.scenario == "组分对比"
        assert template.priority == 1
        assert template.special is False

    def test_special_template(self):
        """测试特殊模板（需要专门组件）"""
        template = ChartTemplate(
            chart_type="wind_rose",
            scenario="风向玫瑰",
            priority=1,
            special=True,
            requires_map=False,
            encoding_template={
                "theta": {"field": "windDirection", "type": "quantitative"},
                "radius": {"field": "windSpeed", "type": "quantitative"}
            }
        )

        assert template.special is True
        assert template.requires_map is False


class TestDataCatalogEntry:
    """测试数据目录条目"""

    def test_entry_creation(self):
        """测试创建数据目录条目"""
        entry = DataCatalogEntry(
            schema="test_data",
            description="测试数据类型",
            required_fields=["field1", "field2"],
            optional_fields=["field3"],
            time_granularity=["hourly"],
            recommended_templates=[
                ChartTemplate(
                    chart_type="bar",
                    scenario="测试场景",
                    priority=1,
                    encoding_template={}
                )
            ],
            sample_config={"key": "value"}
        )

        assert entry.schema == "test_data"
        assert len(entry.required_fields) == 2
        assert len(entry.recommended_templates) == 1


class TestChartDataCatalog:
    """测试图表数据目录"""

    def test_catalog_exists(self):
        """测试目录存在"""
        assert CHART_DATA_CATALOG is not None
        assert isinstance(CHART_DATA_CATALOG, dict)

    def test_catalog_has_vocs(self):
        """测试目录包含VOCs"""
        assert "vocs" in CHART_DATA_CATALOG
        vocs_entry = CHART_DATA_CATALOG["vocs"]
        assert vocs_entry.schema == "vocs"

    def test_catalog_has_air_quality(self):
        """测试目录包含空气质量"""
        assert "air_quality" in CHART_DATA_CATALOG
        entry = CHART_DATA_CATALOG["air_quality"]
        assert entry.schema == "air_quality"
        assert "timePoint" in entry.required_fields
        assert "AQI" in entry.required_fields

    def test_catalog_has_guangdong_stations(self):
        """测试目录包含广东站点"""
        assert "guangdong_stations" in CHART_DATA_CATALOG
        entry = CHART_DATA_CATALOG["guangdong_stations"]
        assert entry.schema == "guangdong_stations"
        assert len(entry.recommended_templates) >= 3

    def test_catalog_has_pmf_result(self):
        """测试目录包含PMF结果"""
        assert "pmf_result" in CHART_DATA_CATALOG
        entry = CHART_DATA_CATALOG["pmf_result"]
        assert "source_name" in entry.required_fields
        assert "contribution_pct" in entry.required_fields

    def test_catalog_has_obm_result(self):
        """测试目录包含OBM结果"""
        assert "obm_ofp_result" in CHART_DATA_CATALOG
        entry = CHART_DATA_CATALOG["obm_ofp_result"]
        assert "species_name" in entry.required_fields
        assert "ofp" in entry.required_fields

    def test_catalog_coverage(self):
        """测试目录覆盖率"""
        # 至少应该包含这些核心数据类型
        required_schemas = [
            "vocs",
            "air_quality",
            "guangdong_stations",
            "meteorology",
            "pmf_result",
            "obm_ofp_result"
        ]

        for schema in required_schemas:
            assert schema in CHART_DATA_CATALOG, f"Missing schema: {schema}"


class TestGetCatalogEntry:
    """测试获取目录条目"""

    def test_get_existing_entry(self):
        """测试获取存在的条目"""
        entry = get_catalog_entry("vocs")
        assert entry is not None
        assert entry.schema == "vocs"

    def test_get_nonexistent_entry(self):
        """测试获取不存在的条目"""
        entry = get_catalog_entry("nonexistent_type")
        assert entry is None


class TestGetRecommendedTemplates:
    """测试获取推荐模板"""

    def test_get_vocs_templates(self):
        """测试获取VOCs推荐模板"""
        templates = get_recommended_templates("vocs")

        assert len(templates) >= 3
        # 验证按优先级排序
        for i in range(len(templates) - 1):
            assert templates[i].priority <= templates[i + 1].priority

    def test_get_guangdong_templates(self):
        """测试获取广东站点推荐模板"""
        templates = get_recommended_templates("guangdong_stations")

        assert len(templates) >= 3
        # 应该包含timeseries, bar, pie
        chart_types = [t.chart_type for t in templates]
        assert "timeseries" in chart_types
        assert "bar" in chart_types

    def test_get_templates_with_scenario_filter(self):
        """测试根据场景过滤模板"""
        templates = get_recommended_templates("vocs", scenario="占比")

        # 应该只返回场景包含"占比"的模板
        for template in templates:
            assert "占比" in template.scenario

    def test_get_templates_for_nonexistent_schema(self):
        """测试获取不存在schema的模板"""
        templates = get_recommended_templates("nonexistent")
        assert len(templates) == 0

    def test_pmf_templates_priority(self):
        """测试PMF模板优先级"""
        templates = get_recommended_templates("pmf_result")

        # pie应该是最高优先级
        assert templates[0].chart_type == "pie"
        assert templates[0].scenario == "源贡献占比"


class TestValidateDataFields:
    """测试数据字段验证"""

    def test_valid_vocs_fields(self):
        """测试有效的VOCs字段"""
        result = validate_data_fields(
            "vocs",
            ["species_name", "concentration", "timestamp", "station_name"]
        )

        assert result["valid"] is True
        assert len(result["missing_fields"]) == 0
        assert len(result["available_templates"]) > 0

    def test_missing_required_fields(self):
        """测试缺少必需字段"""
        result = validate_data_fields(
            "vocs",
            ["species_name"]  # 缺少concentration和timestamp
        )

        assert result["valid"] is False
        assert "concentration" in result["missing_fields"]
        assert "timestamp" in result["missing_fields"]

    def test_air_quality_validation(self):
        """测试空气质量数据验证"""
        result = validate_data_fields(
            "air_quality",
            ["timePoint", "AQI", "PM2.5", "station_name"]
        )

        assert result["valid"] is True

    def test_guangdong_stations_validation(self):
        """测试广东站点数据验证"""
        result = validate_data_fields(
            "guangdong_stations",
            ["station_name", "time_point", "PM2.5"]
        )

        assert result["valid"] is True

    def test_conditional_template_filtering(self):
        """测试条件模板过滤"""
        # PMF结果没有timeseries字段
        result = validate_data_fields(
            "pmf_result",
            ["source_name", "contribution_pct"]
        )

        assert result["valid"] is True
        # 应该过滤掉需要timeseries的模板
        available_chart_types = [t.chart_type for t in result["available_templates"]]

        # 基础模板应该可用
        assert "pie" in available_chart_types
        assert "bar" in available_chart_types

    def test_unknown_schema(self):
        """测试未知schema"""
        result = validate_data_fields(
            "unknown_schema",
            ["field1", "field2"]
        )

        assert result["valid"] is False
        assert "error" in result


class TestGetAllSchemas:
    """测试获取所有schema"""

    def test_get_all_schemas(self):
        """测试获取所有支持的schema"""
        schemas = get_all_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) >= 6  # 至少6种数据类型
        assert "vocs" in schemas
        assert "air_quality" in schemas
        assert "guangdong_stations" in schemas


class TestGetCatalogSummary:
    """测试获取目录摘要"""

    def test_catalog_summary(self):
        """测试获取目录摘要"""
        summary = get_catalog_summary()

        assert "total_schemas" in summary
        assert "schemas" in summary
        assert summary["total_schemas"] >= 6

    def test_summary_details(self):
        """测试摘要详细信息"""
        summary = get_catalog_summary()

        # 检查VOCs的摘要信息
        assert "vocs" in summary["schemas"]
        vocs_info = summary["schemas"]["vocs"]

        assert "description" in vocs_info
        assert "template_count" in vocs_info
        assert "required_fields_count" in vocs_info
        assert vocs_info["template_count"] >= 3


class TestTemplateEncodingStructure:
    """测试模板编码结构"""

    def test_vocs_pie_template_encoding(self):
        """测试VOCs饼图模板编码"""
        templates = get_recommended_templates("vocs", scenario="占比")

        assert len(templates) > 0
        pie_template = templates[0]

        assert pie_template.chart_type == "pie"
        assert "theta" in pie_template.encoding_template
        assert "color" in pie_template.encoding_template

    def test_air_quality_timeseries_encoding(self):
        """测试空气质量时序图编码"""
        templates = get_recommended_templates("air_quality", scenario="时序")

        assert len(templates) > 0
        ts_template = templates[0]

        assert ts_template.chart_type == "timeseries"
        assert "x" in ts_template.encoding_template
        assert "y" in ts_template.encoding_template
        assert ts_template.encoding_template["x"]["type"] == "temporal"

    def test_meteorology_wind_rose_encoding(self):
        """测试气象风向玫瑰图编码"""
        entry = get_catalog_entry("meteorology")

        wind_rose_templates = [t for t in entry.recommended_templates if t.chart_type == "wind_rose"]
        assert len(wind_rose_templates) > 0

        wind_rose = wind_rose_templates[0]
        assert wind_rose.special is True
        assert "theta" in wind_rose.encoding_template
        assert "radius" in wind_rose.encoding_template


class TestSpecialChartTypes:
    """测试特殊图表类型"""

    def test_special_charts_marked(self):
        """测试特殊图表已标记"""
        # 风向玫瑰图应该标记为special
        meteorology = get_catalog_entry("meteorology")
        wind_rose_template = [t for t in meteorology.recommended_templates if t.chart_type == "wind_rose"][0]
        assert wind_rose_template.special is True

    def test_map_requirements(self):
        """测试地图需求标记"""
        # 轨迹图应该需要地图
        if "dust_trajectory" in CHART_DATA_CATALOG:
            trajectory = get_catalog_entry("dust_trajectory")
            map_templates = [t for t in trajectory.recommended_templates if t.requires_map]
            assert len(map_templates) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
