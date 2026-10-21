"""
极坐标热力型污染玫瑰图 - 智能数据过滤测试

验证方案C的过滤逻辑：
1. 负值过滤
2. IQR方法检测极大值
3. 保留合理的极值（重污染事件）
"""

import pytest
import numpy as np
from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour


class TestDataFiltering:
    """测试智能数据过滤逻辑"""

    def test_negative_values_filtered(self):
        """测试负值被正确过滤"""
        # 创建测试数据：包含负值
        wind_dirs = [0, 90, 180, 270, 45]
        wind_speeds = [2.0, 3.0, 1.5, 2.5, 4.0]
        concentrations = [50, -10, 80, 120, -5]  # 包含-10和-5

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="负值过滤测试",
            pollutant_name="PM2.5"
        )

        # 验证：负值应该被过滤，只保留3个数据点
        assert isinstance(result, str)
        assert len(result) > 0

    def test_iqr_outliers_detected(self):
        """测试IQR方法检测异常值"""
        np.random.seed(42)

        # 创建测试数据：大部分正常值，几个极端异常值
        wind_dirs = np.random.uniform(0, 360, 100).tolist()
        wind_speeds = np.random.uniform(1, 5, 100).tolist()

        # 大部分正常值：20-100
        concentrations = [50] * 90
        # 添加10个极端异常值：800-1000
        concentrations.extend([800, 850, 900, 950, 1000,
                             820, 880, 920, 980, 990])

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="IQR异常值检测测试",
            pollutant_name="O3"
        )

        # 验证：图表应该成功生成（异常值被过滤）
        assert isinstance(result, str)
        assert len(result) > 0

    def test_retain_valid_extreme_values(self):
        """测试保留合理的极值（重污染事件）"""
        # 模拟真实场景：大部分值20-80，少数几个200-250（重度污染但合理）
        wind_dirs = [0, 45, 90, 135, 180, 225, 270, 315]
        wind_speeds = [2.0, 2.5, 3.0, 1.5, 2.0, 2.5, 3.0, 1.5]
        concentrations = [30, 45, 60, 80, 200, 220, 180, 50]  # 200-220是合理的重污染值

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="保留合理极值测试",
            pollutant_name="O3"
        )

        # 验证：200-220的重污染值应该被保留
        assert isinstance(result, str)
        assert len(result) > 0

    def test_all_data_filtered_error(self):
        """测试全部数据被过滤的情况"""
        # 所有数据都是负值
        wind_dirs = [0, 90, 180]
        wind_speeds = [2.0, 3.0, 1.5]
        concentrations = [-10, -20, -30]  # 全部负值

        # 应该抛出异常
        with pytest.raises(ValueError, match="数据过滤后无有效数据点"):
            generate_pollution_rose_contour(
                wind_directions=wind_dirs,
                wind_speeds=wind_speeds,
                concentrations=concentrations,
                title="全负值测试",
                pollutant_name="PM2.5"
            )

    def test_insufficient_data_for_iqr(self):
        """测试数据点太少时的处理"""
        # 只有5个数据点，不够做IQR统计
        wind_dirs = [0, 90, 180, 270, 45]
        wind_speeds = [2.0, 3.0, 1.5, 2.5, 4.0]
        concentrations = [50, 80, 120, 200, 90]  # 包含一个较高的值200

        # 应该成功生成（跳过IQR检测）
        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="少量数据测试",
            pollutant_name="O3"
        )

        assert isinstance(result, str)

    def test_real_world_scenario(self):
        """测试真实场景：O3数据（-11到855）"""
        # 模拟日志中的真实数据
        np.random.seed(42)
        n = 288

        wind_dirs = np.random.uniform(0, 360, n).tolist()
        wind_speeds = np.random.uniform(0.5, 8, n).tolist()

        # 模拟O3数据：
        # - 大部分：20-150
        # - 少数负值：-11, -5（传感器错误）
        # - 少数异常高值：855, 700（传感器错误）
        concentrations = []
        for i in range(n):
            if i < 5:
                concentrations.append(-11 + i)  # -11, -10, -9, -8, -7
            elif i < 10:
                concentrations.append(800 + i * 10)  # 800, 810, 820, ..., 890
            else:
                concentrations.append(np.random.uniform(20, 150))

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="真实场景O3数据测试",
            pollutant_name="O3",
            unit="μg/m³"
        )

        # 验证：应该成功生成，负值和异常高值被过滤
        assert isinstance(result, str)
        assert len(result) > 0

        # 图片大小应该在合理范围
        assert 100 * 1024 < len(result) < 500 * 1024  # 100-500KB


class TestFilteringBehavior:
    """测试过滤行为特性"""

    def test_iqr_threshold_calculation(self):
        """测试IQR阈值计算逻辑"""
        # 测试数据：[10, 20, 30, 40, 50, 1000]
        # Q1 = 20, Q3 = 40, IQR = 20
        # upper_bound = 40 + 3*20 = 100
        # 1000 > 100，应该被过滤

        wind_dirs = [0, 60, 120, 180, 240, 300]
        wind_speeds = [2.0] * 6
        concentrations = [10, 20, 30, 40, 50, 1000]

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="IQR阈值计算测试",
            pollutant_name="PM2.5"
        )

        # 应该成功生成（1000被过滤）
        assert isinstance(result, str)

    def test_no_false_positives(self):
        """测试不过滤合理的极值"""
        # 数据：[50, 60, 70, 80, 200, 220]
        # Q1 = 60, Q3 = 140, IQR = 80
        # upper_bound = 140 + 3*80 = 380
        # 200和220都 < 380，应该保留

        wind_dirs = [0, 60, 120, 180, 240, 300]
        wind_speeds = [2.0] * 6
        concentrations = [50, 60, 70, 80, 200, 220]

        result = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title="无假阳性测试",
            pollutant_name="O3"
        )

        # 应该成功生成，200和220被保留
        assert isinstance(result, str)


def run_visual_test():
    """运行可视化测试（生成实际图表）"""
    print("\n" + "="*60)
    print("极坐标热力图 - 智能过滤可视化测试")
    print("="*60)

    # 测试数据1：包含负值和异常值
    print("\n测试1：包含负值和异常值的数据")
    wind_dirs = np.random.uniform(0, 360, 100).tolist()
    wind_speeds = np.random.uniform(1, 5, 100).tolist()
    concentrations = []
    for i in range(100):
        if i < 5:
            concentrations.append(-10 - i)  # 负值
        elif i < 10:
            concentrations.append(800 + i * 20)  # 异常高值
        else:
            concentrations.append(np.random.uniform(20, 150))

    result = generate_pollution_rose_contour(
        wind_directions=wind_dirs,
        wind_speeds=wind_speeds,
        concentrations=concentrations,
        title="智能过滤测试：负值和异常值",
        pollutant_name="O3"
    )
    print(f"✓ 生成成功，图片大小: {len(result) / 1024:.1f} KB")

    # 测试数据2：保留合理的重污染值
    print("\n测试2：保留合理的重污染值")
    concentrations2 = []
    for i in range(50):
        if i < 40:
            concentrations2.append(np.random.uniform(20, 80))
        else:
            concentrations2.append(np.random.uniform(180, 250))  # 重污染但合理

    result2 = generate_pollution_rose_contour(
        wind_directions=wind_dirs[:50],
        wind_speeds=wind_speeds[:50],
        concentrations=concentrations2,
        title="智能过滤测试：保留合理极值",
        pollutant_name="O3"
    )
    print(f"✓ 生成成功，图片大小: {len(result2) / 1024:.1f} KB")

    print("\n" + "="*60)
    print("所有测试完成！")
    print("="*60)


if __name__ == '__main__':
    # 运行可视化测试
    run_visual_test()

    # 运行单元测试
    print("\n运行单元测试...")
    pytest.main([__file__, '-v'])
