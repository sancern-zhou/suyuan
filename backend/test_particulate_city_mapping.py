"""
测试颗粒物组分查询的城市→站点→编码映射流程
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.utils.particulate_city_mapper import get_particulate_city_mapper
from app.utils.geo_matcher import get_geo_matcher


def test_city_to_station_to_code():
    """测试完整的映射流程：城市→站点→编码"""

    print("=" * 60)
    print("测试颗粒物组分查询的城市→站点→编码映射流程")
    print("=" * 60)

    # 测试用例
    test_cases = [
        "深圳",
        "深圳市",
        "广州",
        "东莞",
        "深南中路",  # 直接输入站点名
        "东城",      # 直接输入站点名
        "不存在的城市"
    ]

    city_mapper = get_particulate_city_mapper()
    geo_matcher = get_geo_matcher()

    print(f"\n可用城市列表（前10个）: {city_mapper.get_available_cities()[:10]}")
    print("\n" + "=" * 60)

    for location in test_cases:
        print(f"\n测试输入: '{location}'")
        print("-" * 60)

        # 步骤1：城市→站点映射
        station_name = city_mapper.city_to_station_name(location)
        if station_name:
            print(f"  步骤1 [城市→站点]: '{location}' → '{station_name}' ✓")
        else:
            print(f"  步骤1 [城市→站点]: '{location}' → 映射失败，假设为站点名")
            station_name = location

        # 步骤2：站点→编码映射
        station_codes = geo_matcher.stations_to_codes([station_name])
        if station_codes:
            print(f"  步骤2 [站点→编码]: '{station_name}' → '{station_codes[0]}' ✓")
            print(f"  最终结果: '{location}' → '{station_name}' → '{station_codes[0]}' ✓✓✓")
        else:
            print(f"  步骤2 [站点→编码]: '{station_name}' → 映射失败 ✗")
            print(f"  最终结果: 映射失败 ✗✗✗")


def test_tool_simulation():
    """模拟工具调用流程"""

    print("\n" + "=" * 60)
    print("模拟工具调用流程（locations=['深圳']）")
    print("=" * 60)

    locations = ["深圳"]

    # 步骤1：城市名→站点名映射
    city_mapper = get_particulate_city_mapper()
    station_names = []

    for location in locations:
        station_name = city_mapper.city_to_station_name(location)
        if station_name:
            station_names.append(station_name)
            print(f"\n城市映射成功: '{location}' → '{station_name}'")
        else:
            station_names.append(location)
            print(f"\n假设为站点名: '{location}'")

    # 步骤2：站点名→站点编码映射
    geo_matcher = get_geo_matcher()
    station_codes = geo_matcher.stations_to_codes(station_names)

    if station_codes:
        code = station_codes[0]
        station = station_names[0]
        print(f"站点编码映射成功: '{station}' → '{code}'")
        print(f"\n最终参数:")
        print(f"  station = '{station}'")
        print(f"  code = '{code}'")
        print(f"\nAPI调用参数:")
        print(f"  Station: '{station}'")
        print(f"  Code: '{code}'")
        print("\n映射成功！可以正常调用API ✓✓✓")
    else:
        print(f"\n映射失败: 无法将 {station_names} 映射到站点编码")
        print("映射失败！无法调用API ✗✗✗")


if __name__ == "__main__":
    test_city_to_station_to_code()
    test_tool_simulation()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
