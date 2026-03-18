"""
测试所有15种图表类型的转换功能和ChartResponse v3.1格式

测试覆盖:
- 基础图表 (4种): pie, bar, line, timeseries
- 气象图表 (2种): wind_rose, profile
- 3D图表 (5种): scatter3d, surface3d, line3d, bar3d, volume3d
- 高级图表 (3种): heatmap, radar, map
- 未实现 (1种): story (标记为未来扩展)

验证点:
1. 返回格式符合ChartResponse v3.1标准
2. 嵌套data.type字段正确
3. 必填字段完整
4. meta字段包含必要信息
"""

import pytest
from typing import Dict, Any, List
from app.utils.chart_data_converter import ChartDataConverter


class TestBasicCharts:
    """测试基础图表类型 (4种)"""

    def test_pie_chart_pmf_result(self):
        """测试饼图 - PMF结果转换"""
        # 构造PMF结果数据
        pmf_data = {
            "pollutant": "PM2.5",
            "station_name": "测试站点",
            "sources": [
                {"source_name": "工业源", "contribution_pct": 35.2, "concentration": 15.8, "confidence": "High"},
                {"source_name": "机动车", "contribution_pct": 28.5, "concentration": 12.8, "confidence": "High"},
                {"source_name": "扬尘", "contribution_pct": 22.3, "concentration": 10.0, "confidence": "Medium"},
                {"source_name": "其他", "contribution_pct": 14.0, "concentration": 6.3, "confidence": "Low"}
            ],
            "timeseries": [],
            "performance": {"R2": 0.85}
        }

        result = ChartDataConverter.convert_pmf_result(pmf_data, chart_type="pie")

        # 验证基础结构
        assert "id" in result
        assert "type" in result
        assert "title" in result
        assert "data" in result
        assert "meta" in result

        # 验证type字段
        assert result["type"] == "pie"

        # 验证嵌套data结构
        assert "type" in result["data"]
        assert result["data"]["type"] == "pie"
        assert "data" in result["data"]

        # 验证饼图数据格式
        pie_data = result["data"]["data"]
        assert isinstance(pie_data, list)
        assert len(pie_data) == 4
        assert all("name" in item and "value" in item for item in pie_data)

        # 验证meta字段
        assert "unit" in result["meta"]
        assert "data_source" in result["meta"]
        assert result["meta"]["data_source"] == "pmf_analysis"

        print(f"✓ 饼图测试通过: {result['id']}")

    def test_bar_chart_obm_result(self):
        """测试柱状图 - OBM结果转换"""
        obm_data = {
            "station_name": "测试站点",
            "total_ofp": 125.6,
            "primary_vocs": ["苯", "甲苯", "乙烯"],
            "category_summary": [
                {"category": "烷烃", "total_ofp": 45.2, "species_count": 10, "contribution_pct": 36.0},
                {"category": "烯烃", "total_ofp": 38.5, "species_count": 8, "contribution_pct": 30.6},
                {"category": "芳香烃", "total_ofp": 28.3, "species_count": 6, "contribution_pct": 22.5},
                {"category": "其他", "total_ofp": 13.6, "species_count": 4, "contribution_pct": 10.9}
            ],
            "species_ofp": [
                {"species": "苯", "ofp": 18.5, "concentration": 5.2},
                {"species": "甲苯", "ofp": 15.3, "concentration": 4.8},
                {"species": "乙烯", "ofp": 12.8, "concentration": 3.5}
            ],
            "sensitivity": {
                "sensitivity_type": "VOCs-limited",
                "vocs_control_effectiveness": 75.0,
                "nox_control_effectiveness": 25.0,
                "recommendation": "建议优先控制VOCs"
            }
        }

        result = ChartDataConverter.convert_obm_result(obm_data, chart_type="bar")

        # 验证基础结构
        assert result["type"] == "bar"
        assert result["data"]["type"] == "bar"

        # 验证柱状图数据格式
        bar_data = result["data"]["data"]
        assert "x" in bar_data
        assert "y" in bar_data
        assert isinstance(bar_data["x"], list)
        assert isinstance(bar_data["y"], list)
        assert len(bar_data["x"]) == len(bar_data["y"])

        print(f"✓ 柱状图测试通过: {result['id']}")

    def test_line_chart_guangdong_stations(self):
        """测试折线图 - 广东站点数据转换"""
        station_data = [
            {
                "station_name": "深圳站",
                "timestamp": "2025-11-01 00:00",
                "measurements": {"pM2_5": 45.2}
            },
            {
                "station_name": "深圳站",
                "timestamp": "2025-11-01 01:00",
                "measurements": {"pM2_5": 48.1}
            },
            {
                "station_name": "深圳站",
                "timestamp": "2025-11-01 02:00",
                "measurements": {"pM2_5": 42.3}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            station_data,
            chart_type="line"
        )

        # line图复用timeseries逻辑，只是type不同
        assert result["type"] == "line"
        assert result["data"]["type"] == "line"

        print(f"✓ 折线图测试通过: {result['id']}")

    def test_timeseries_chart_multi_pollutant(self):
        """测试时序图 - 多污染物时序对比"""
        multi_pollutant_data = [
            {
                "station_name": "深圳站",
                "timestamp": "2025-11-01 00:00",
                "measurements": {"PM2.5": 45.2, "O3": 80.5, "NO2": 35.8}
            },
            {
                "station_name": "深圳站",
                "timestamp": "2025-11-01 01:00",
                "measurements": {"PM2.5": 48.1, "O3": 75.3, "NO2": 38.2}
            },
            {
                "station_name": "深圳站",
                "timestamp": "2025-11-01 02:00",
                "measurements": {"PM2.5": 42.3, "O3": 82.1, "NO2": 32.5}
            }
        ]

        result = ChartDataConverter.convert_guangdong_stations(
            multi_pollutant_data,
            chart_type="timeseries",
            enable_multi_pollutant=True
        )

        # 验证时序图格式
        assert result["type"] == "timeseries"
        assert result["data"]["type"] == "timeseries"

        # 验证series结构
        ts_data = result["data"]["data"]
        assert "x" in ts_data
        assert "series" in ts_data
        assert isinstance(ts_data["series"], list)

        # 验证多污染物（应该检测到3个）
        assert len(ts_data["series"]) >= 2
        for series in ts_data["series"]:
            assert "name" in series
            assert "data" in series
            assert isinstance(series["data"], list)

        print(f"✓ 时序图测试通过: {result['id']}")


class TestMeteorologyCharts:
    """测试气象图表类型 (2种)"""

    def test_wind_rose_chart(self):
        """测试风向玫瑰图"""
        weather_data = []
        # 生成16个风向的模拟数据，每个方向10条记录
        directions = [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5,
                     180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5]
        for direction in directions:
            for i in range(10):
                weather_data.append({
                    "timestamp": f"2025-11-01 {i:02d}:00",
                    "windDirection": direction + (i % 3) * 2,  # 添加一些变化
                    "windSpeed": 3.5 + (i % 5),  # 风速变化范围 3.5-7.5
                    "temperature": 20.0,
                    "humidity": 65.0
                })

        result = ChartDataConverter.convert_meteorology_data(
            weather_data,
            chart_type="wind_rose",
            station_name="测试气象站"
        )

        # 验证基础结构
        assert result["type"] == "wind_rose"
        assert result["data"]["type"] == "wind_rose"

        # 验证风向玫瑰图数据格式
        wind_data = result["data"]["data"]
        assert "sectors" in wind_data
        assert "legend" in wind_data
        assert isinstance(wind_data["sectors"], list)

        # 验证扇区数据
        for sector in wind_data["sectors"]:
            assert "direction" in sector
            assert "angle" in sector
            assert "avg_speed" in sector
            assert "max_speed" in sector
            assert "count" in sector
            assert "speed_distribution" in sector

        print(f"✓ 风向玫瑰图测试通过: {result['id']}")

    def test_profile_chart(self):
        """测试边界层廓线图"""
        profile_data = [
            {"altitude": 0, "temperature": 20.0, "windSpeed": 2.5, "pbl": 500},
            {"altitude": 100, "temperature": 19.5, "windSpeed": 3.0, "pbl": 500},
            {"altitude": 200, "temperature": 19.0, "windSpeed": 3.5, "pbl": 500},
            {"altitude": 500, "temperature": 17.5, "windSpeed": 5.0, "pbl": 500},
            {"altitude": 1000, "temperature": 15.0, "windSpeed": 7.5, "pbl": 500},
            {"altitude": 1500, "temperature": 12.5, "windSpeed": 10.0, "pbl": 500}
        ]

        result = ChartDataConverter.convert_meteorology_data(
            profile_data,
            chart_type="profile",
            station_name="测试气象站"
        )

        # 验证基础结构
        assert result["type"] == "profile"
        assert result["data"]["type"] == "profile"

        # 验证廓线图数据格式
        profile_chart_data = result["data"]["data"]
        assert "altitudes" in profile_chart_data
        assert "elements" in profile_chart_data
        assert isinstance(profile_chart_data["altitudes"], list)
        assert isinstance(profile_chart_data["elements"], list)

        # 验证要素数据
        for element in profile_chart_data["elements"]:
            assert "name" in element
            assert "unit" in element
            assert "data" in element

        print(f"✓ 边界层廓线图测试通过: {result['id']}")


class Test3DCharts:
    """测试3D图表类型 (5种)"""

    def test_scatter3d_chart(self):
        """测试3D散点图"""
        scatter_data = [
            {"x": 1.0, "y": 2.0, "z": 3.0, "color": "red", "size": 10},
            {"x": 2.0, "y": 3.0, "z": 4.0, "color": "blue", "size": 15},
            {"x": 3.0, "y": 4.0, "z": 5.0, "color": "green", "size": 20},
            {"x": 4.0, "y": 5.0, "z": 6.0, "color": "red", "size": 12}
        ]

        result = ChartDataConverter.convert_3d_chart_data(
            scatter_data,
            chart_type="scatter3d",
            title="3D散点分布"
        )

        # 验证基础结构
        assert result["type"] == "scatter3d"
        assert result["data"]["type"] == "scatter3d"

        # 验证3D散点数据
        scatter_chart_data = result["data"]["data"]
        assert "points" in scatter_chart_data
        assert isinstance(scatter_chart_data["points"], list)

        for point in scatter_chart_data["points"]:
            assert "x" in point
            assert "y" in point
            assert "z" in point

        print(f"✓ 3D散点图测试通过: {result['id']}")

    def test_surface3d_chart(self):
        """测试3D曲面图"""
        surface_data = []
        for x in range(5):
            for y in range(5):
                surface_data.append({
                    "x": float(x),
                    "y": float(y),
                    "z": float(x * y)
                })

        result = ChartDataConverter.convert_3d_chart_data(
            surface_data,
            chart_type="surface3d",
            title="3D曲面分布"
        )

        # 验证基础结构
        assert result["type"] == "surface3d"
        assert result["data"]["type"] == "surface3d"

        # 验证3D曲面数据
        surface_chart_data = result["data"]["data"]
        assert "x" in surface_chart_data
        assert "y" in surface_chart_data
        assert "z" in surface_chart_data
        assert isinstance(surface_chart_data["z"], list)

        print(f"✓ 3D曲面图测试通过: {result['id']}")

    def test_line3d_chart(self):
        """测试3D线图"""
        line_data = [
            {"x": 0.0, "y": 0.0, "z": 0.0, "order": 0},
            {"x": 1.0, "y": 1.0, "z": 1.0, "order": 1},
            {"x": 2.0, "y": 2.0, "z": 4.0, "order": 2},
            {"x": 3.0, "y": 3.0, "z": 9.0, "order": 3}
        ]

        result = ChartDataConverter.convert_3d_chart_data(
            line_data,
            chart_type="line3d",
            title="3D轨迹"
        )

        # 验证基础结构
        assert result["type"] == "line3d"
        assert result["data"]["type"] == "line3d"

        # 验证3D线数据
        line_chart_data = result["data"]["data"]
        assert "trajectory" in line_chart_data
        assert isinstance(line_chart_data["trajectory"], list)
        assert len(line_chart_data["trajectory"]) >= 2

        print(f"✓ 3D线图测试通过: {result['id']}")

    def test_bar3d_chart(self):
        """测试3D柱状图"""
        bar_data = [
            {"category_x": "A", "category_y": "1", "z": 10.0},
            {"category_x": "A", "category_y": "2", "z": 15.0},
            {"category_x": "B", "category_y": "1", "z": 12.0},
            {"category_x": "B", "category_y": "2", "z": 18.0}
        ]

        result = ChartDataConverter.convert_3d_chart_data(
            bar_data,
            chart_type="bar3d",
            title="3D柱状对比"
        )

        # 验证基础结构
        assert result["type"] == "bar3d"
        assert result["data"]["type"] == "bar3d"

        # 验证3D柱状数据
        bar_chart_data = result["data"]["data"]
        assert "bars" in bar_chart_data
        assert isinstance(bar_chart_data["bars"], list)

        for bar in bar_chart_data["bars"]:
            assert "x" in bar
            assert "y" in bar
            assert "z" in bar

        print(f"✓ 3D柱状图测试通过: {result['id']}")

    def test_volume3d_chart(self):
        """测试3D体素图"""
        volume_data = []
        for x in range(3):
            for y in range(3):
                for z in range(3):
                    volume_data.append({
                        "x": float(x),
                        "y": float(y),
                        "z": float(z),
                        "value": float(x + y + z)
                    })

        result = ChartDataConverter.convert_3d_chart_data(
            volume_data,
            chart_type="volume3d",
            title="3D体积分布"
        )

        # 验证基础结构
        assert result["type"] == "volume3d"
        assert result["data"]["type"] == "volume3d"

        # 验证3D体素数据
        volume_chart_data = result["data"]["data"]
        assert "voxels" in volume_chart_data
        assert "value_range" in volume_chart_data
        assert isinstance(volume_chart_data["voxels"], list)

        for voxel in volume_chart_data["voxels"]:
            assert "x" in voxel
            assert "y" in voxel
            assert "z" in voxel
            assert "value" in voxel

        print(f"✓ 3D体素图测试通过: {result['id']}")


class TestAdvancedCharts:
    """测试高级图表类型 (3种)"""

    def test_heatmap_chart(self):
        """测试热力图"""
        heatmap_data = [
            {"longitude": 114.0, "latitude": 22.5, "value": 45.2},
            {"longitude": 114.1, "latitude": 22.6, "value": 52.8},
            {"longitude": 114.2, "latitude": 22.7, "value": 38.5},
            {"longitude": 114.3, "latitude": 22.8, "value": 61.3}
        ]

        result = ChartDataConverter.convert_map_data(
            heatmap_data,
            chart_type="heatmap",
            title="污染物浓度热力分布"
        )

        # 验证基础结构
        assert result["type"] == "heatmap"
        assert result["data"]["type"] == "heatmap"

        # 验证热力图数据
        heatmap_chart_data = result["data"]["data"]
        assert "map_center" in heatmap_chart_data
        assert "zoom" in heatmap_chart_data
        assert "layers" in heatmap_chart_data

        # 验证图层数据
        assert len(heatmap_chart_data["layers"]) > 0
        heatmap_layer = heatmap_chart_data["layers"][0]
        assert heatmap_layer["type"] == "heatmap"
        assert "data" in heatmap_layer
        assert isinstance(heatmap_layer["data"], list)

        for point in heatmap_layer["data"]:
            assert "lng" in point
            assert "lat" in point
            assert "value" in point

        print(f"✓ 热力图测试通过: {result['id']}")

    def test_radar_chart(self):
        """测试雷达图 - OBM敏感性分析"""
        obm_data = {
            "station_name": "测试站点",
            "total_ofp": 125.6,
            "primary_vocs": ["苯", "甲苯"],
            "category_summary": [],
            "species_ofp": [],
            "sensitivity": {
                "sensitivity_type": "VOCs-limited",
                "vocs_control_effectiveness": 75.0,
                "nox_control_effectiveness": 25.0,
                "recommendation": "建议优先控制VOCs"
            }
        }

        result = ChartDataConverter.convert_obm_result(
            obm_data,
            chart_type="radar"
        )

        # 验证基础结构
        assert result["type"] == "radar"
        assert result["data"]["type"] == "radar"

        # 验证雷达图数据
        radar_data = result["data"]["data"]
        assert "x" in radar_data
        assert "y" in radar_data

        print(f"✓ 雷达图测试通过: {result['id']}")

    def test_map_chart(self):
        """测试地图"""
        map_data = [
            {
                "longitude": 114.0579,
                "latitude": 22.5431,
                "title": "深圳站点",
                "content": "PM2.5: 45.2 μg/m³",
                "color": "blue"
            },
            {
                "longitude": 114.1579,
                "latitude": 22.6431,
                "title": "广州站点",
                "content": "PM2.5: 52.8 μg/m³",
                "color": "red"
            }
        ]

        result = ChartDataConverter.convert_map_data(
            map_data,
            chart_type="map",
            title="监测站点分布"
        )

        # 验证基础结构
        assert result["type"] == "map"
        assert result["data"]["type"] == "map"

        # 验证地图数据
        map_chart_data = result["data"]["data"]
        assert "map_center" in map_chart_data
        assert "zoom" in map_chart_data
        assert "layers" in map_chart_data

        # 验证图层数据
        assert len(map_chart_data["layers"]) > 0
        marker_layer = map_chart_data["layers"][0]
        assert marker_layer["type"] == "marker"
        assert "data" in marker_layer
        assert isinstance(marker_layer["data"], list)

        for marker in marker_layer["data"]:
            assert "lng" in marker
            assert "lat" in marker
            assert "title" in marker

        print(f"✓ 地图测试通过: {result['id']}")


class TestChartResponseV3Format:
    """验证所有图表都符合ChartResponse v3.1格式规范"""

    @pytest.fixture
    def sample_charts(self):
        """准备各类图表样本数据"""
        # 准备风向玫瑰图数据
        wind_data = []
        for direction in [0, 45, 90, 135, 180, 225, 270, 315]:
            for i in range(5):
                wind_data.append({
                    "windDirection": direction + i,
                    "windSpeed": 3.0 + i,
                    "timestamp": f"2025-11-01 {i:02d}:00"
                })

        return {
            "pie": ChartDataConverter.convert_pmf_result(
                {
                    "pollutant": "PM2.5",
                    "station_name": "测试站",
                    "sources": [
                        {"source_name": "工业", "contribution_pct": 50, "concentration": 25, "confidence": "High"}
                    ],
                    "timeseries": [],
                    "performance": {"R2": 0.85}
                },
                "pie"
            ),
            "wind_rose": ChartDataConverter.convert_meteorology_data(
                wind_data,
                "wind_rose",
                station_name="测试站"
            ),
            "map": ChartDataConverter.convert_map_data(
                [{"longitude": 114.0, "latitude": 22.5, "title": "测试点"}],
                "map"
            )
        }

    def test_required_fields_present(self, sample_charts):
        """验证所有必填字段存在"""
        required_fields = ["id", "type", "title", "data", "meta"]

        for chart_type, chart in sample_charts.items():
            assert not isinstance(chart, dict) or "error" not in chart, f"{chart_type}转换失败"

            for field in required_fields:
                assert field in chart, f"{chart_type}缺少必填字段: {field}"

            print(f"✓ {chart_type}包含所有必填字段")

    def test_nested_data_type_field(self, sample_charts):
        """验证嵌套data.type字段正确"""
        for chart_type, chart in sample_charts.items():
            if "error" in chart:
                continue

            assert "type" in chart["data"], f"{chart_type}缺少data.type字段"
            assert chart["data"]["type"] == chart["type"], f"{chart_type}的data.type与type不一致"

            print(f"✓ {chart_type}的嵌套type字段正确")

    def test_meta_fields(self, sample_charts):
        """验证meta字段包含关键信息"""
        for chart_type, chart in sample_charts.items():
            if "error" in chart:
                continue

            assert "meta" in chart, f"{chart_type}缺少meta字段"
            meta = chart["meta"]

            # 至少应该有unit或data_source
            assert "unit" in meta or "data_source" in meta, f"{chart_type}的meta缺少基础字段"

            print(f"✓ {chart_type}的meta字段完整")


if __name__ == "__main__":
    print("=" * 80)
    print("开始测试所有15种图表类型的转换功能")
    print("=" * 80)
    print()

    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])

    print()
    print("=" * 80)
    print("测试完成")
    print("=" * 80)
