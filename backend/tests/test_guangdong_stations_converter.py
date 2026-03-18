"""
测试广东站点图表数据转换器

验证内容：
1. 广东站点支持timeseries图表
2. 广东站点支持pie图表
3. 广东站点支持line图表
4. 数据格式处理正确性
"""

import pytest
from typing import List, Dict, Any

from app.utils.chart_data_converter import ChartDataConverter


class TestGuangdongStationsBarChart:
    """测试广东站点柱状图"""

    def test_bar_chart_with_dict_data(self):
        """测试字典格式数据生成柱状图"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "38.5"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "28.5"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "30.2"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="bar"
        )

        assert "error" not in result
        assert result["type"] == "bar"
        assert result["id"] == "guangdong_stations_pm25_comparison"
        assert "data" in result
        assert result["data"]["type"] == "bar"

        # 验证数据结构
        option = result["data"]["data"]
        assert "x" in option
        assert "y" in option
        assert len(option["x"]) == 2  # 两个站点
        assert "广州" in option["x"]
        assert "深圳" in option["x"]

    def test_bar_chart_averages_correctly(self):
        """测试柱状图正确计算平均值"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "30.0"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "40.0"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="bar"
        )

        # 广州的平均值应该是35.0
        option = result["data"]["data"]
        gz_index = option["x"].index("广州")
        assert option["y"][gz_index] == 35.0


class TestGuangdongStationsTimeseriesChart:
    """测试广东站点时序图"""

    def test_timeseries_chart_basic(self):
        """测试基础时序图生成"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "38.5"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "28.5"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "30.2"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="timeseries",
            pollutant="PM2.5"
        )

        assert "error" not in result
        assert result["type"] == "timeseries"
        assert result["title"] == "广东各站点PM2.5浓度时序对比"

        # 验证数据结构
        assert "data" in result
        assert result["data"]["type"] == "timeseries"
        option = result["data"]["data"]
        assert "x" in option
        assert "series" in option

        # 时间点应该排序
        assert option["x"] == ["2025-01-01 00:00", "2025-01-01 01:00"]

        # 应该有两个站点的series
        assert len(option["series"]) == 2
        station_names = [s["name"] for s in option["series"]]
        assert "广州" in station_names
        assert "深圳" in station_names

    def test_timeseries_handles_missing_values(self):
        """测试时序图处理缺失值"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-01 02:00",
                "measurements": {"pM2_5": "38.5"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "28.5"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="timeseries"
        )

        assert "error" not in result
        option = result["data"]["data"]

        # 应该包含所有时间点
        assert len(option["x"]) == 3

        # 每个series应该有3个值（包含None）
        for series in option["series"]:
            assert len(series["data"]) == 3

    def test_timeseries_custom_pollutant(self):
        """测试时序图自定义污染物"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM10": "50.0"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="timeseries",
            pollutant="PM10"
        )

        assert "error" not in result
        assert result["id"] == "guangdong_stations_PM10_timeseries"
        assert result["meta"]["pollutant"] == "PM10"

    def test_timeseries_limits_to_top_10_stations(self):
        """测试时序图限制为前10个站点"""
        # 创建15个站点的数据
        test_data = []
        for i in range(15):
            for hour in range(24):  # 每个站点24小时数据
                test_data.append({
                    "station_name": f"站点{i}",
                    "time_point": f"2025-01-01 {hour:02d}:00",
                    "measurements": {"pM2_5": str(30.0 + i)}
                })

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="timeseries"
        )

        assert "error" not in result
        option = result["data"]["data"]

        # 应该只保留10个站点
        assert len(option["series"]) == 10

    def test_timeseries_meta_includes_time_range(self):
        """测试时序图元数据包含时间范围"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-02 00:00",
                "measurements": {"pM2_5": "38.5"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="timeseries"
        )

        assert "time_range" in result["meta"]
        assert result["meta"]["time_range"][0] == "2025-01-01 00:00"
        assert result["meta"]["time_range"][1] == "2025-01-02 00:00"


class TestGuangdongStationsPieChart:
    """测试广东站点饼图"""

    def test_pie_chart_basic(self):
        """测试基础饼图生成"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.0"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "28.0"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="pie",
            pollutant="PM2.5"
        )

        assert "error" not in result
        assert result["type"] == "pie"
        assert result["title"] == "广东各站点PM2.5平均浓度占比"

        # 验证数据结构
        assert result["data"]["type"] == "pie"
        pie_data = result["data"]["data"]
        assert len(pie_data) == 2

        # 验证饼图数据包含name和value
        for item in pie_data:
            assert "name" in item
            assert "value" in item

    def test_pie_chart_calculates_averages(self):
        """测试饼图计算平均值"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "30.0"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "40.0"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="pie"
        )

        pie_data = result["data"]["data"]
        gz_item = next(item for item in pie_data if item["name"] == "广州")

        # 平均值应该是35.0
        assert gz_item["value"] == 35.0

    def test_pie_chart_limits_to_top_15(self):
        """测试饼图限制为前15个站点"""
        test_data = []
        for i in range(20):
            test_data.append({
                "station_name": f"站点{i}",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": str(30.0 + i)}
            })

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="pie"
        )

        pie_data = result["data"]["data"]
        assert len(pie_data) == 15

    def test_pie_chart_sorts_by_value(self):
        """测试饼图按值排序"""
        test_data = [
            {
                "station_name": "低浓度",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "10.0"}
            },
            {
                "station_name": "高浓度",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "50.0"}
            },
            {
                "station_name": "中浓度",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "30.0"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="pie"
        )

        pie_data = result["data"]["data"]
        # 第一个应该是最高浓度
        assert pie_data[0]["name"] == "高浓度"
        assert pie_data[0]["value"] == 50.0


class TestGuangdongStationsLineChart:
    """测试广东站点折线图"""

    def test_line_chart_converts_to_line_type(self):
        """测试折线图转换为line类型"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            },
            {
                "station_name": "广州",
                "time_point": "2025-01-01 01:00",
                "measurements": {"pM2_5": "38.5"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="line",
            pollutant="PM2.5"
        )

        assert "error" not in result
        assert result["type"] == "line"
        assert result["data"]["type"] == "line"
        assert result["id"] == "guangdong_stations_PM2.5_line"
        assert "趋势" in result["title"]


class TestGuangdongStationsDataHandling:
    """测试广东站点数据处理"""

    def test_handles_empty_data(self):
        """测试处理空数据"""
        result = ChartDataConverter.convert_guangdong_stations(
            [],
            chart_type="bar"
        )

        assert "error" in result
        assert "为空" in result["error"]

    def test_handles_invalid_chart_type(self):
        """测试处理无效图表类型"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="invalid_type"
        )

        assert "error" in result
        assert "不支持" in result["error"]

    def test_handles_missing_time_point(self):
        """测试处理缺少时间点"""
        test_data = [
            {
                "station_name": "广州",
                "measurements": {"pM2_5": "35.2"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="timeseries"
        )

        # 应该返回错误或跳过该记录
        assert "error" in result or result["meta"]["record_count"] == 1

    def test_handles_dash_values(self):
        """测试处理"-"值"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "-"}
            },
            {
                "station_name": "深圳",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "30.0"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="bar"
        )

        # 应该只包含有效值的站点
        assert "error" not in result

    def test_normalizes_chart_type(self):
        """测试图表类型标准化"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            }
        ]

        # 使用time_series（应该被标准化为timeseries）
        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="time_series",
            pollutant="PM2.5"
        )

        assert "error" not in result
        assert result["type"] == "timeseries"


class TestGuangdongStationsMetadata:
    """测试广东站点元数据"""

    def test_metadata_includes_all_required_fields(self):
        """测试元数据包含所有必需字段"""
        test_data = [
            {
                "station_name": "广州",
                "time_point": "2025-01-01 00:00",
                "measurements": {"pM2_5": "35.2"}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            test_data,
            chart_type="bar"
        )

        meta = result["meta"]
        assert "unit" in meta
        assert "data_source" in meta
        assert "record_count" in meta
        assert "station_count" in meta
        assert "pollutant" in meta

        assert meta["unit"] == "μg/m³"
        assert meta["data_source"] == "guangdong_stations"
        assert meta["record_count"] == 1
        assert meta["pollutant"] == "PM2.5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
