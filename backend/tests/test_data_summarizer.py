"""
测试数据摘要工具 (DataSummarizer)

验证内容：
1. 字段类型推断（数值、类别、时间）
2. 统计信息生成
3. 图表推荐逻辑
4. 边界情况处理
"""

import pytest
from typing import List, Dict, Any

from app.tools.visualization.data_summarizer import DataSummarizer, summarize_data


class TestFieldTypeInference:
    """测试字段类型推断"""

    def setup_method(self):
        """初始化测试"""
        self.summarizer = DataSummarizer()

    def test_infer_quantitative_field(self):
        """测试推断数值字段"""
        values = [12.5, 15.3, 18.2, 20.1]
        field_type = self.summarizer._infer_field_type("concentration", values)
        assert field_type == "quantitative"

    def test_infer_nominal_field(self):
        """测试推断类别字段"""
        values = ["广州", "深圳", "北京", "上海"]
        field_type = self.summarizer._infer_field_type("station_name", values)
        assert field_type == "nominal"

    def test_infer_temporal_field_by_name(self):
        """测试通过字段名推断时间字段"""
        values = ["2025-01-01 00:00", "2025-01-01 01:00"]
        field_type = self.summarizer._infer_field_type("timePoint", values)
        assert field_type == "temporal"

    def test_infer_temporal_field_by_format(self):
        """测试通过值格式推断时间字段"""
        values = ["2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 02:00"]
        field_type = self.summarizer._infer_field_type("data_time", values)
        assert field_type == "temporal"

    def test_mixed_numeric_strings(self):
        """测试混合数值和字符串"""
        values = ["12.5", "15.3", "invalid", "20.1", "25.8"]
        field_type = self.summarizer._infer_field_type("value", values)
        # 80%以上是数值，应判定为quantitative
        assert field_type == "quantitative"

    def test_empty_values(self):
        """测试空值列表"""
        values = []
        field_type = self.summarizer._infer_field_type("unknown", values)
        assert field_type == "nominal"  # 默认类别


class TestDataSummarization:
    """测试数据摘要生成"""

    def setup_method(self):
        """初始化测试"""
        self.summarizer = DataSummarizer()

    def test_summarize_air_quality_data(self):
        """测试空气质量数据摘要"""
        data = [
            {"timePoint": "2025-01-01 00:00", "PM2.5": 35.2, "O3": 45.8, "station_name": "广州"},
            {"timePoint": "2025-01-01 01:00", "PM2.5": 38.5, "O3": 42.1, "station_name": "广州"},
            {"timePoint": "2025-01-01 00:00", "PM2.5": 28.5, "O3": 52.3, "station_name": "深圳"}
        ]

        summary = self.summarizer.summarize(data, "air_quality")

        assert summary["statistics"]["record_count"] == 3
        assert summary["statistics"]["has_time_series"] is True
        assert "PM2.5" in summary["statistics"]["numeric_fields"]
        assert "O3" in summary["statistics"]["numeric_fields"]
        assert "station_name" in summary["statistics"]["categorical_fields"]
        assert "timePoint" in summary["statistics"]["temporal_fields"]

    def test_summarize_vocs_data(self):
        """测试VOCs数据摘要"""
        data = [
            {"species_name": "乙烯", "concentration": 12.5, "category": "烷烃"},
            {"species_name": "丙烯", "concentration": 8.3, "category": "烯烃"},
            {"species_name": "甲苯", "concentration": 15.7, "category": "芳香烃"}
        ]

        summary = self.summarizer.summarize(data, "vocs")

        assert summary["statistics"]["record_count"] == 3
        assert summary["statistics"]["has_time_series"] is False
        assert "concentration" in summary["statistics"]["numeric_fields"]
        assert "species_name" in summary["statistics"]["categorical_fields"]

    def test_field_statistics(self):
        """测试字段统计信息"""
        data = [
            {"value": 10.0},
            {"value": 20.0},
            {"value": 30.0}
        ]

        summary = self.summarizer.summarize(data)

        field_info = summary["field_info"]["value"]
        assert "statistics" in field_info
        assert field_info["statistics"]["min"] == 10.0
        assert field_info["statistics"]["max"] == 30.0
        assert field_info["statistics"]["mean"] == 20.0

    def test_missing_values(self):
        """测试缺失值处理"""
        data = [
            {"value": 10.0, "name": "A"},
            {"value": None, "name": "B"},
            {"value": 30.0, "name": ""},
            {"value": "-", "name": "C"}
        ]

        summary = self.summarizer.summarize(data)

        assert summary["field_info"]["value"]["missing_count"] == 2  # None and "-"
        assert summary["field_info"]["name"]["missing_count"] == 1   # ""

    def test_distinct_count(self):
        """测试不同值数量"""
        data = [
            {"category": "A"},
            {"category": "B"},
            {"category": "A"},
            {"category": "C"}
        ]

        summary = self.summarizer.summarize(data)

        assert summary["field_info"]["category"]["distinct_count"] == 3  # A, B, C


class TestRecommendations:
    """测试图表推荐"""

    def setup_method(self):
        """初始化测试"""
        self.summarizer = DataSummarizer()

    def test_recommend_timeseries_for_temporal_data(self):
        """测试推荐时序图"""
        data = [
            {"time": "2025-01-01 00:00", "value": 10.0},
            {"time": "2025-01-01 01:00", "value": 15.0}
        ]

        summary = self.summarizer.summarize(data)

        assert "timeseries" in summary["recommendations"]["suitable_chart_types"]
        assert "line" in summary["recommendations"]["suitable_chart_types"]

    def test_recommend_bar_for_categorical_data(self):
        """测试推荐柱状图"""
        data = [
            {"category": "A", "value": 10.0},
            {"category": "B", "value": 15.0},
            {"category": "C", "value": 20.0}
        ]

        summary = self.summarizer.summarize(data)

        assert "bar" in summary["recommendations"]["suitable_chart_types"]

    def test_recommend_pie_for_categories(self):
        """测试推荐饼图"""
        data = [
            {"category": "A", "value": 10.0},
            {"category": "B", "value": 15.0}
        ]

        summary = self.summarizer.summarize(data)

        assert "pie" in summary["recommendations"]["suitable_chart_types"]

    def test_recommend_scatter_for_multiple_numeric(self):
        """测试推荐散点图"""
        data = [
            {"x": 10.0, "y": 20.0, "z": 30.0},
            {"x": 15.0, "y": 25.0, "z": 35.0}
        ]

        summary = self.summarizer.summarize(data)

        assert "scatter" in summary["recommendations"]["suitable_chart_types"]

    def test_primary_dimensions_and_measures(self):
        """测试主要维度和度量推荐"""
        data = [
            {"station": "A", "species": "甲苯", "concentration": 10.0, "ofp": 5.0},
            {"station": "B", "species": "乙烯", "concentration": 15.0, "ofp": 8.0}
        ]

        summary = self.summarizer.summarize(data)

        recommendations = summary["recommendations"]
        assert "station" in recommendations["primary_dimensions"]
        assert "species" in recommendations["primary_dimensions"]
        assert "concentration" in recommendations["primary_measures"]
        assert "ofp" in recommendations["primary_measures"]

    def test_default_recommendation(self):
        """测试默认推荐"""
        data = [
            {"unknown_field": "value1"},
            {"unknown_field": "value2"}
        ]

        summary = self.summarizer.summarize(data)

        # 如果无法推荐，默认柱状图
        assert "bar" in summary["recommendations"]["suitable_chart_types"]


class TestEdgeCases:
    """测试边界情况"""

    def setup_method(self):
        """初始化测试"""
        self.summarizer = DataSummarizer()

    def test_empty_data(self):
        """测试空数据"""
        summary = self.summarizer.summarize([])

        assert "error" in summary
        assert summary["record_count"] == 0

    def test_single_record(self):
        """测试单条记录"""
        data = [{"field": "value"}]

        summary = self.summarizer.summarize(data)

        assert summary["statistics"]["record_count"] == 1

    def test_udf_format(self):
        """测试UDF v1.0格式"""
        data = {
            "data": [
                {"field": "value1"},
                {"field": "value2"}
            ],
            "metadata": {
                "data_type": "test"
            }
        }

        summary = self.summarizer.summarize(data)

        assert summary["statistics"]["record_count"] == 2

    def test_all_missing_values(self):
        """测试所有值都缺失"""
        data = [
            {"field": None},
            {"field": ""},
            {"field": "-"}
        ]

        summary = self.summarizer.summarize(data)

        assert summary["field_info"]["field"]["missing_count"] == 3
        assert summary["field_info"]["field"]["distinct_count"] == 0


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_summarize_data_function(self):
        """测试summarize_data函数"""
        data = [
            {"time": "2025-01-01", "value": 10.0},
            {"time": "2025-01-02", "value": 20.0}
        ]

        summary = summarize_data(data, "test")

        assert "statistics" in summary
        assert "field_info" in summary
        assert "recommendations" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
