"""
测试PM2.5数据标准化器
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.utils.data_standardizer import get_data_standardizer


def test_pm25_standardization():
    """测试PM2.5数据标准化"""

    print("=" * 80)
    print("PM2.5数据标准化测试")
    print("=" * 80)

    # 模拟API返回的原始数据（扁平结构，中文字段名）
    raw_data = [
        {
            "station_code": "1067b",
            "station_name": "深南中路",
            "timestamp": "2026-02-01 00:00:00",
            "铝": 1.949,
            "硅": 4.123,
            "铁": 0.856,
            "钙": 2.345,
            "镁": 0.678,
            "钾": 1.234,
            "钠": 0.987,
            "钛": 0.123,
            "PM2_5": 35.5
        }
    ]

    print("\n原始数据 (扁平结构，中文字段名):")
    for key, value in raw_data[0].items():
        print(f"  {key}: {value}")

    # 获取标准化器
    standardizer = get_data_standardizer()

    # 标准化数据
    print("\n开始标准化...")
    standardized_data = standardizer.standardize(raw_data)

    print(f"\n标准化后记录数: {len(standardized_data)}")

    if standardized_data:
        first_record = standardized_data[0]
        print(f"\n标准化后的字段:")
        for key in sorted(first_record.keys()):
            value = first_record[key]
            if isinstance(value, dict):
                print(f"  {key}: (字典，{len(value)} 项)")
                for sub_key, sub_value in value.items():
                    print(f"    {sub_key}: {sub_value}")
            else:
                print(f"  {key}: {value}")

        # 检查 components 字段
        if "components" in first_record:
            components = first_record["components"]
            print(f"\n✓ components 字段存在")
            print(f"  组分数量: {len(components)}")
            if components:
                print(f"  组分内容:")
                for key, value in components.items():
                    print(f"    {key}: {value}")
            else:
                print(f"  ✗ components 字典为空！")
        else:
            print(f"\n✗ components 字段不存在！")

            # 检查是否有数值型字段（可能是组分）
            numeric_fields = {k: v for k, v in first_record.items()
                            if isinstance(v, (int, float))}
            if numeric_fields:
                print(f"\n数值型字段 (可能是组分):")
                for key, value in numeric_fields.items():
                    print(f"  {key}: {value}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_pm25_standardization()
