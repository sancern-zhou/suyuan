"""
测试地理位置映射功能
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_geo_matcher():
    """测试GeoMatcher映射功能"""
    print("=" * 80)
    print("GeoMatcher 映射功能测试")
    print("=" * 80)

    from app.utils.geo_matcher import get_geo_matcher

    geo_matcher = get_geo_matcher()

    # 测试站点名称到编码映射
    print("\n【站点名称 → 编码映射】")
    test_stations = ["东莞", "新兴", "从化天湖", "广州塔", "公园前"]
    codes = geo_matcher.stations_to_codes(test_stations)
    for station, code in zip(test_stations, codes):
        print(f"  {station} → {code}")

    # 测试城市名称到编码映射
    print("\n【城市名称 → 编码映射】")
    test_cities = ["广州", "深圳", "东莞", "佛山", "珠海"]
    codes = geo_matcher.cities_to_codes(test_cities)
    for city, code in zip(test_cities, codes):
        print(f"  {city} → {code}")

    # 测试区县名称到编码映射
    print("\n【区县名称 → 编码映射】")
    test_districts = ["天河区", "白云区", "福田区", "南海区"]
    codes = geo_matcher.districts_to_codes(test_districts)
    for district, code in zip(test_districts, codes):
        print(f"  {district} → {code}")

    # 测试模糊匹配
    print("\n【模糊匹配测试】")
    test_fuzzy = ["东城", "从化", "公园", "天湖"]
    for location in test_fuzzy:
        loc_type, code = geo_matcher.resolve_location(location)
        print(f"  {location} → 类型:{loc_type}, 编码:{code}")

    # 测试统计信息
    print("\n【映射统计】")
    print(f"  站点映射数量: {len(geo_matcher.station_codes)}")
    print(f"  城市映射数量: {len(geo_matcher.city_codes)}")
    print(f"  区县映射数量: {len(geo_matcher.district_codes)}")


def test_tool_integration():
    """测试工具集成"""
    print("\n" + "=" * 80)
    print("工具集成测试（locations参数）")
    print("=" * 80)

    from app.tools.query.get_particulate_components.tool import GetParticulateComponentsTool

    tool = GetParticulateComponentsTool()

    print("\n【Schema验证】")
    schema = tool.function_schema
    print(f"  工具名称: {schema['name']}")
    print(f"  必需参数: {schema['parameters']['required']}")
    print(f"  可选参数: {list(schema['parameters']['properties'].keys())}")

    # 检查 locations 参数
    if 'locations' in schema['parameters']['properties']:
        print(f"\n  ✓ locations 参数已添加")
        locations_param = schema['parameters']['properties']['locations']
        print(f"    类型: {locations_param['type']}")
        print(f"    描述: {locations_param['description'][:80]}...")
    else:
        print(f"\n  ✗ locations 参数未找到")

    # 检查 station 和 code 参数是否变为可选
    required = set(schema['parameters']['required'])
    if 'station' not in required and 'code' not in required:
        print(f"  ✓ station 和 code 参数已变为可选（支持 locations 自动映射）")
    else:
        print(f"  ✗ station/code 仍然是必需参数")


if __name__ == "__main__":
    print("地理位置映射功能测试")
    print("=" * 80)

    # 测试1: GeoMatcher 映射
    test_geo_matcher()

    # 测试2: 工具集成
    test_tool_integration()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
