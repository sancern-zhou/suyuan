"""
验证DataStandardizer修复是否生效
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.data_standardizer import DataStandardizer

# 测试数据：模拟API返回的格式
test_record = {
    "name": "广州",
    "code": 440100,
    "pM2_5": 45.2,
    "pM10": 68.5,
    "o3": 52.3,
    "aqi": 85,
    "timestamp": "2026-02-01 00:00:00",
    "cityOrder": None,
    "co": 0.8,
    "nO2": 12.3
}

print("输入数据:")
for key, value in test_record.items():
    print(f"  {key}: {value}")

# 标准化
standardizer = DataStandardizer()
result = standardizer.standardize(test_record)

print("\n输出数据:")
for key, value in result.items():
    if isinstance(value, dict):
        print(f"  {key}: (dict) {list(value.keys())}")
    else:
        print(f"  {key}: {value}")

# 验证
if "measurements" in result:
    print("\n[SUCCESS] measurements字段存在")
    measurements = result["measurements"]
    if "PM2_5" in measurements and "PM10" in measurements:
        print(f"[SUCCESS] PM2_5: {measurements['PM2_5']}")
        print(f"[SUCCESS] PM10: {measurements['PM10']}")
    else:
        print(f"[FAIL] PM2_5或PM10不在measurements中")
        print(f"measurements内容: {measurements}")
else:
    print("\n[FAIL] measurements字段不存在")
    print(f"结果字段: {list(result.keys())}")
