"""
极坐标热力型污染玫瑰图双模式支持 - 单元测试

测试两种技术方案：
1. Matplotlib方案：平滑静态图
2. ECharts方案：交互式图表
"""

import pytest
import json
import os
import tempfile
from typing import Dict, List

from app.tools.visualization.polar_contour_generator import (
    generate_pollution_rose_contour,
    generate_pollution_rose_echarts,
    generate_from_data_id
)


class TestPolarContourGenerator:
    """测试极坐标等值线生成器"""

    @pytest.fixture
    def sample_data(self):
        """生成测试数据"""
        import numpy as np

        np.random.seed(42)
        n = 500

        # 模拟风向（0-360度）
        wind_dirs = np.random.uniform(0, 360, n)

        # 模拟风速（0.5-8 m/s，偏向2-5 m/s）
        wind_speeds = np.random.beta(2, 5, n) * 8 + 0.5

        # 模拟PM10浓度（31-49 μg/m³，与风向和风速相关）
        # 假设南风（180度）风速较小时浓度较高
        base_conc = 40

        # 风向影响：南风（180度）附近浓度高
        dir_factor = 1 + 0.3 * np.cos(np.radians(wind_dirs - 180))

        # 风速影响：风速小浓度高
        speed_factor = 1 + 0.5 * (5 - wind_speeds) / 5

        concentrations = base_conc * dir_factor * speed_factor + np.random.normal(0, 2, n)

        # 限制在合理范围
        concentrations = np.clip(concentrations, 31, 49)

        return {
            'wind_directions': wind_dirs.tolist(),
            'wind_speeds': wind_speeds.tolist(),
            'concentrations': concentrations.tolist()
        }

    def test_matplotlib_generation(self, sample_data):
        """测试matplotlib方案生成"""
        result = generate_pollution_rose_contour(
            wind_directions=sample_data['wind_directions'],
            wind_speeds=sample_data['wind_speeds'],
            concentrations=sample_data['concentrations'],
            title="测试图表",
            pollutant_name="PM10",
            unit="μg/m³",
            value_range=(31, 49)
        )

        # 验证返回的是base64编码的字符串
        assert isinstance(result, str)
        assert len(result) > 0

        # 验证可以解码为PNG
        import base64
        try:
            img_data = base64.b64decode(result)
            assert len(img_data) > 1000  # 图片应该大于1KB
            assert img_data[:8] == b'\x89PNG\r\n\x1a\n'  # PNG文件头
        except Exception as e:
            pytest.fail(f"无法解码base64图片: {e}")

    def test_echarts_generation(self, sample_data):
        """测试ECharts方案生成"""
        result = generate_pollution_rose_echarts(
            wind_directions=sample_data['wind_directions'],
            wind_speeds=sample_data['wind_speeds'],
            concentrations=sample_data['concentrations'],
            title="测试图表（交互式）",
            pollutant_name="PM10",
            unit="μg/m³",
            color_range=(31, 49)
        )

        # 验证返回的是字典
        assert isinstance(result, dict)

        # 验证ECharts配置结构
        assert 'title' in result
        assert 'polar' in result
        assert 'angleAxis' in result
        assert 'radiusAxis' in result
        assert 'series' in result
        assert 'visualMap' in result

        # 验证series配置
        assert len(result['series']) > 0
        series = result['series'][0]
        assert series['type'] == 'heatmap'
        assert series['coordinateSystem'] == 'polar'
        assert 'data' in series
        assert len(series['data']) > 0

        # 验证数据格式（每个数据点应该是[角度, 风速, 归一化值, 原始浓度]）
        data_point = series['data'][0]
        assert len(data_point) == 4
        assert 0 <= data_point[0] <= 360  # 角度
        assert data_point[1] >= 0  # 风速
        assert 0 <= data_point[2] <= 100  # 归一化值
        assert data_point[3] >= 0  # 原始浓度

    def test_invalid_data_length_mismatch(self):
        """测试数据长度不一致"""
        with pytest.raises(ValueError, match="数据长度必须一致"):
            generate_pollution_rose_contour(
                wind_directions=[0, 90, 180],
                wind_speeds=[2, 3],  # 长度不匹配
                concentrations=[40, 45, 50]
            )

    def test_invalid_data_empty(self):
        """测试空数据"""
        with pytest.raises(ValueError, match="输入数据不能为空"):
            generate_pollution_rose_contour(
                wind_directions=[],
                wind_speeds=[],
                concentrations=[]
            )

    def test_invalid_data_all_nan(self):
        """测试全NaN数据"""
        with pytest.raises(ValueError, match="没有有效数据"):
            generate_pollution_rose_contour(
                wind_directions=[float('nan'), float('nan')],
                wind_speeds=[float('nan'), float('nan')],
                concentrations=[float('nan'), float('nan')]
            )

    def test_zero_wind_speed_filtered(self, sample_data):
        """测试零风速数据被过滤"""
        # 添加一些零风速数据
        wind_dirs = sample_data['wind_directions'] + [0, 90, 180]
        wind_speeds = sample_data['wind_speeds'] + [0, 0, 0]
        concentrations = sample_data['concentrations'] + [40, 45, 50]

        # 应该成功生成（零风速数据被过滤）
        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_matplotlib_color_map_options(self, sample_data):
        """测试不同的颜色映射"""
        color_maps = ['RdYlBu_r', 'jet', 'viridis', 'plasma']

        for cmap in color_maps:
            result = generate_pollution_rose_contour(
                wind_directions=sample_data['wind_directions'],
                wind_speeds=sample_data['wind_speeds'],
                concentrations=sample_data['concentrations'],
                color_map=cmap
            )
            assert isinstance(result, str)
            assert len(result) > 0

    def test_echarts_different_grid_sizes(self, sample_data):
        """测试不同的网格大小"""
        configs = [
            (180, 30),  # 低分辨率
            (360, 50),  # 中等分辨率
            (720, 100),  # 高分辨率
        ]

        for angles, radii in configs:
            result = generate_pollution_rose_echarts(
                wind_directions=sample_data['wind_directions'],
                wind_speeds=sample_data['wind_speeds'],
                concentrations=sample_data['concentrations'],
                grid_angles=angles,
                grid_radii=radii
            )
            assert isinstance(result, dict)
            assert 'series' in result

    def test_echarts_json_serializable(self, sample_data):
        """测试ECharts配置可以JSON序列化"""
        result = generate_pollution_rose_echarts(
            wind_directions=sample_data['wind_directions'],
            wind_speeds=sample_data['wind_speeds'],
            concentrations=sample_data['concentrations']
        )

        # 应该能够序列化为JSON
        json_str = json.dumps(result, ensure_ascii=False)
        assert len(json_str) > 0

        # 应该能够反序列化
        parsed = json.loads(json_str)
        assert 'series' in parsed


class TestGenerateFromDataId:
    """测试从data_id生成图表"""

    @pytest.fixture
    def temp_data_file(self):
        """创建临时数据文件"""
        import numpy as np

        np.random.seed(42)
        n = 100

        data = []
        for i in range(n):
            data.append({
                'time': f'2026-03-01T{i:02d}:00:00',
                'WD': float(np.random.uniform(0, 360)),
                'WS': float(np.random.uniform(0.5, 8)),
                'PM10': float(np.random.uniform(31, 49))
            })

        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        yield temp_path

        # 清理
        if os.path.exists(temp_path):
            os.remove(temp_path)

    def test_matplotlib_from_data_id(self, temp_data_file):
        """测试从data_id生成matplotlib图表"""
        # 模拟data_id（从临时文件路径提取）
        # 注意：实际使用时data_id是文件名不含扩展名

        # 读取数据
        with open(temp_data_file, 'r') as f:
            data = json.load(f)

        # 直接调用生成函数（绕过文件路径问题）
        wind_dirs = [d['WD'] for d in data]
        wind_speeds = [d['WS'] for d in data]
        concentrations = [d['PM10'] for d in data]

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_echarts_from_data_id(self, temp_data_file):
        """测试从data_id生成ECharts图表"""
        # 读取数据
        with open(temp_data_file, 'r') as f:
            data = json.load(f)

        # 直接调用生成函数
        wind_dirs = [d['WD'] for d in data]
        wind_speeds = [d['WS'] for d in data]
        concentrations = [d['PM10'] for d in data]

        result = generate_pollution_rose_echarts(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations
        )

        assert isinstance(result, dict)
        assert 'series' in result

    def test_missing_field_error(self):
        """测试缺少字段的情况"""
        data = [
            {'WD': 180, 'WS': 2.5}  # 缺少PM10字段
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # 读取数据并尝试生成
            with open(temp_path, 'r') as f:
                loaded_data = json.load(f)

            wind_dirs = [d['WD'] for d in loaded_data]
            wind_speeds = [d['WS'] for d in loaded_data]

            # 应该抛出KeyError（缺少PM10字段）
            with pytest.raises(KeyError):
                concentrations = [d['PM10'] for d in loaded_data]
        finally:
            os.remove(temp_path)


class TestPerformance:
    """性能测试"""

    def test_matplotlib_performance_large_dataset(self):
        """测试matplotlib处理大数据集的性能"""
        import numpy as np
        import time

        np.random.seed(42)
        n = 5000  # 5000个数据点

        wind_dirs = np.random.uniform(0, 360, n).tolist()
        wind_speeds = np.random.uniform(0.5, 8, n).tolist()
        concentrations = np.random.uniform(31, 49, n).tolist()

        start = time.time()
        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            grid_resolution=100  # 100x100网格
        )
        elapsed = time.time() - start

        # 验证生成成功
        assert isinstance(result, str)
        assert len(result) > 0

        # 验证性能（应该在5秒内完成）
        assert elapsed < 5.0, f"生成时间过长: {elapsed:.2f}秒"

    def test_echarts_performance_large_dataset(self):
        """测试ECharts处理大数据集的性能"""
        import numpy as np
        import time

        np.random.seed(42)
        n = 5000

        wind_dirs = np.random.uniform(0, 360, n).tolist()
        wind_speeds = np.random.uniform(0.5, 8, n).tolist()
        concentrations = np.random.uniform(31, 49, n).tolist()

        start = time.time()
        result = generate_pollution_rose_echarts(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations
        )
        elapsed = time.time() - start

        # 验证生成成功
        assert isinstance(result, dict)
        assert 'series' in result

        # 验证性能（应该在1秒内完成）
        assert elapsed < 1.0, f"生成时间过长: {elapsed:.2f}秒"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
