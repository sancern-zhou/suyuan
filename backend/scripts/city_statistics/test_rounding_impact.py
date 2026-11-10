"""
测试修约规则对计算结果的影响

对比CO保留1位小数 vs 2位小数的差异
"""
from decimal import Decimal, ROUND_HALF_EVEN


def safe_round_old(value: float, decimals: int) -> float:
    """
    旧版本修约（使用Python内置round，可能有浮点数精度问题）
    """
    if value is None:
        return None
    return round(value, decimals)


def safe_round_new(value: float, decimals: int) -> float:
    """
    新版本修约（使用Decimal进行精确修约）
    """
    if value is None:
        return None

    # 转换为Decimal进行精确修约
    decimal_value = Decimal(str(value))
    rounded = decimal_value.quantize(
        Decimal(f'1e-{decimals}'),
        rounding=ROUND_HALF_EVEN
    )
    return float(rounded)


def calculate_impact_example():
    """测试一个具体例子"""
    print("="*80)
    print("修约规则对计算结果的影响测试")
    print("="*80)

    # 模拟CO第95百分位数的计算结果
    test_values = [
        0.835,  # 经典例子：0.835在float中可能被存储为0.834999...
        0.6667,
        1.2345,
        0.9999,
        1.0005,
        0.7001,
    ]

    print(f"\n{'原始值':<15} {'1位小数(旧)':<15} {'2位小数(旧)':<15} {'1位小数(新)':<15} {'2位小数(新)':<15}")
    print("-"*80)

    for value in test_values:
        old_1 = safe_round_old(value, 1)
        old_2 = safe_round_old(value, 2)
        new_1 = safe_round_new(value, 1)
        new_2 = safe_round_new(value, 2)

        print(f"{value:<15.6f} {old_1:<15.6f} {old_2:<15.6f} {new_1:<15.6f} {new_2:<15.6f}")

    # 测试对单项指数的影响
    print("\n" + "="*80)
    print("对单项指数的影响（CO标准限值=4 mg/m³）")
    print("="*80)

    print(f"\n{'CO浓度':<15} {'1位小数指数':<15} {'2位小数指数':<15} {'差异':<15}")
    print("-"*80)

    for value in test_values:
        co_1_decimal = safe_round_new(value, 1)
        co_2_decimal = safe_round_new(value, 2)

        index_1 = safe_round_new(co_1_decimal / 4.0, 3)
        index_2 = safe_round_new(co_2_decimal / 4.0, 3)

        diff = abs(index_2 - index_1)

        print(f"{value:<15.6f} {index_1:<15.6f} {index_2:<15.6f} {diff:<15.6f}")

    # 测试对综合指数的影响
    print("\n" + "="*80)
    print("对综合指数的影响（模拟一个城市的完整计算）")
    print("="*80)

    # 模拟一个城市的污染物浓度
    city_example = {
        'so2': 12.3,
        'no2': 24.5,
        'pm10': 45.6,
        'pm2_5': 23.4,
        'co': 0.835,  # 关键测试值
        'o3_8h': 123.4
    }

    standard_limits = {
        'so2': 60,
        'no2': 40,
        'pm10': 60,
        'pm2_5': 30,
        'co': 4,
        'o3_8h': 160
    }

    weights = {
        'so2': 1,
        'no2': 2,
        'pm10': 1,
        'pm2_5': 3,
        'co': 1,
        'o3_8h': 2
    }

    print(f"\n测试CO浓度: {city_example['co']} mg/m³")
    print("-"*80)

    # 方案1：CO保留1位小数
    co_1 = safe_round_new(city_example['co'], 1)
    index_1 = safe_round_new(co_1 / standard_limits['co'], 3)

    comprehensive_1 = 0.0
    for pollutant, weight in weights.items():
        if pollutant == 'co':
            concentration = co_1
            single_index = index_1
        else:
            concentration = city_example[pollutant]
            single_index = safe_round_new(concentration / standard_limits[pollutant], 3)
        comprehensive_1 += single_index * weight

    comprehensive_1 = safe_round_new(comprehensive_1, 3)

    # 方案2：CO保留2位小数
    co_2 = safe_round_new(city_example['co'], 2)
    index_2 = safe_round_new(co_2 / standard_limits['co'], 3)

    comprehensive_2 = 0.0
    for pollutant, weight in weights.items():
        if pollutant == 'co':
            concentration = co_2
            single_index = index_2
        else:
            concentration = city_example[pollutant]
            single_index = safe_round_new(concentration / standard_limits[pollutant], 3)
        comprehensive_2 += single_index * weight

    comprehensive_2 = safe_round_new(comprehensive_2, 3)

    print(f"{'方案':<20} {'CO浓度':<15} {'CO指数':<15} {'综合指数':<15}")
    print("-"*80)
    print(f"{'CO保留1位小数':<20} {co_1:<15.6f} {index_1:<15.6f} {comprehensive_1:<15.6f}")
    print(f"{'CO保留2位小数':<20} {co_2:<15.6f} {index_2:<15.6f} {comprehensive_2:<15.6f}")
    print(f"{'差异':<20} {'':<15} {abs(index_2-index_1):<15.6f} {abs(comprehensive_2-comprehensive_1):<15.6f}")

    print("\n" + "="*80)
    print("结论")
    print("="*80)
    print("1. CO修约精度会影响单项指数的计算结果")
    print("2. 单项指数的差异会影响综合指数的计算结果")
    print("3. 虽然差异很小（通常在0.001级别），但在排名密集时可能影响排名")
    print("4. 必须确保所有数据使用统一的修约规则（CO保留2位小数）")
    print("="*80)


if __name__ == "__main__":
    calculate_impact_example()
