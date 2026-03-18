"""
测试UnifiedParticulateData.from_raw_data方法
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.schemas.particulate import UnifiedParticulateData


def test_from_raw_data():
    """测试from_raw_data方法"""

    print("=" * 80)
    print("UnifiedParticulateData.from_raw_data 测试")
    print("=" * 80)

    # 测试场景1：扁平结构（API原始数据）
    print("\n场景1：扁平结构（API原始数据，中文字段名）")
    raw_flat = {
        "station_code": "1067b",
        "station_name": "深南中路",
        "timestamp": "2026-02-01 00:00:00",
        "铝": 1.949,
        "硅": 4.123,
        "铁": 0.856,
        "钙": 2.345,
        "PM2_5": 35.5
    }

    print("输入数据:")
    for key, value in raw_flat.items():
        print(f"  {key}: {value}")

    result1 = UnifiedParticulateData.from_raw_data(raw_flat)
    print("\nfrom_raw_data 输出:")
    result1_dict = result1.model_dump()
    for key, value in result1_dict.items():
        if isinstance(value, dict):
            print(f"  {key}: (字典，{len(value)} 项)")
            for sub_key, sub_value in value.items():
                print(f"    {sub_key}: {sub_value}")
        else:
            print(f"  {key}: {value}")

    # 测试场景2：已标准化的数据（components已聚合）
    print("\n" + "=" * 80)
    print("场景2：已标准化的数据（components已聚合，英文字段名）")
    standardized = {
        "station_code": "1067b",
        "station_name": "深南中路",
        "timestamp": "2026-02-01 00:00:00",
        "components": {
            "Al": 1.949,
            "Si": 4.123,
            "Fe": 0.856,
            "Ca": 2.345,
            "Mg": 0.678,
            "K": 1.234,
            "Na": 0.987,
            "Ti": 0.123
        },
        "PM2_5": 35.5
    }

    print("输入数据:")
    for key, value in standardized.items():
        if isinstance(value, dict):
            print(f"  {key}: (字典，{len(value)} 项)")
            for sub_key, sub_value in value.items():
                print(f"    {sub_key}: {sub_value}")
        else:
            print(f"  {key}: {value}")

    result2 = UnifiedParticulateData.from_raw_data(standardized)
    print("\nfrom_raw_data 输出:")
    result2_dict = result2.model_dump()
    for key, value in result2_dict.items():
        if isinstance(value, dict):
            print(f"  {key}: (字典，{len(value)} 项)")
            if value:
                for sub_key, sub_value in value.items():
                    print(f"    {sub_key}: {sub_value}")
            else:
                print(f"    (空字典)")
        else:
            print(f"  {key}: {value}")

    # 检查结果
    print("\n" + "=" * 80)
    print("结果分析:")
    print(f"场景1 components 数量: {len(result1_dict.get('components', {}))}")
    print(f"场景2 components 数量: {len(result2_dict.get('components', {}))}")

    if len(result2_dict.get('components', {})) == 0:
        print("\n问题发现：场景2的components为空！")
        print("原因：from_raw_data 方法将已聚合的 components 字段识别为 known_fields")
        print("      导致 components 被放入 remaining，而不是被保留")

    print("=" * 80)


if __name__ == "__main__":
    test_from_raw_data()
