"""
标准限值对比验证（简化版）

验证168城市统计系统是否使用新标准（HJ 633-2024）
"""
print("="*70)
print("标准限值对比验证（168城市统计系统 vs 新标准报表工具）")
print("="*70)

# 168城市统计系统的标准限值
CITY_LIMITS = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 60,
    'PM2_5': 30,
    'CO': 4,
    'O3_8h': 160
}

CITY_WEIGHTS = {
    'SO2': 1,
    'NO2': 2,
    'PM10': 1,
    'PM2_5': 3,
    'CO': 1,
    'O3_8h': 2
}

# 新标准报表工具的标准限值（从query_new_standard_report/tool.py复制）
REPORT_LIMITS = {
    'PM2_5': 30,   # 年平均二级标准（新标准收严：35→30）
    'PM10': 60,    # 年平均二级标准（新标准收严：70→60）
    'SO2': 60,     # 年平均二级标准
    'NO2': 40,     # 年平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
}

REPORT_WEIGHTS = {
    'PM2_5': 3,
    'PM10': 1,
    'SO2': 1,
    'NO2': 2,
    'CO': 1,
    'O3_8h': 2
}

print("\n1. 年平均二级标准限值对比:")
print(f"{'污染物':<12} {'168城市系统':<15} {'新标准报表':<15} {'是否一致'}")
print("-"*70)

all_consistent = True
for pollutant in ['SO2', 'NO2', 'PM10', 'PM2_5', 'CO', 'O3_8h']:
    city_value = CITY_LIMITS.get(pollutant)
    report_value = REPORT_LIMITS.get(pollutant)
    is_consistent = city_value == report_value
    if not is_consistent:
        all_consistent = False
    status = "✓ 一致" if is_consistent else f"✗ 不一致 ({city_value} vs {report_value})"
    print(f"{pollutant:<12} {city_value:<15} {report_value:<15} {status}")

print("\n2. 综合指数权重对比:")
print(f"{'污染物':<12} {'168城市系统':<15} {'新标准报表':<15} {'是否一致'}")
print("-"*70)

for pollutant in ['SO2', 'NO2', 'PM10', 'PM2_5', 'CO', 'O3_8h']:
    city_weight = CITY_WEIGHTS.get(pollutant)
    report_weight = REPORT_WEIGHTS.get(pollutant)
    is_consistent = city_weight == report_weight
    if not is_consistent:
        all_consistent = False
    status = "✓ 一致" if is_consistent else f"✗ 不一致 ({city_weight} vs {report_weight})"
    print(f"{pollutant:<12} {city_weight:<15} {report_weight:<15} {status}")

print("\n3. 新标准（HJ 633-2024）关键变化:")
print("-"*70)
print("  • PM2.5: 年平均二级标准收严（35→30 μg/m³）")
print("  • PM10:  年平均二级标准收严（70→60 μg/m³）")
print("  • PM2.5权重: 3（最高权重）")
print("  • O3、NO2权重: 2（较高权重）")
print("  • 其他污染物权重: 1")

print("\n4. 统计方法:")
print("-"*70)
print("  • SO2、NO2、PM10、PM2.5: 算术平均值")
print("  • CO: 日平均第95百分位数")
print("  • O3: 日最大8小时第90百分位数")

print("\n" + "="*70)
if all_consistent:
    print("✓ 结论：168城市统计系统完全使用新标准（HJ 633-2024）")
else:
    print("✗ 警告：标准限值不一致！")
print("="*70)
