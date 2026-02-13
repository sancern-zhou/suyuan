"""
测试所有颗粒物工具的 locations 参数映射功能
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_all_tools_schema():
    """测试所有工具的 Schema 是否正确支持 locations 参数"""
    print("=" * 80)
    print("颗粒物工具 locations 参数支持测试")
    print("=" * 80)

    tools_to_test = [
        ("get_particulate_components", "app.tools.query.get_particulate_components.tool", "GetParticulateComponentsTool"),
        ("get_pm25_ionic", "app.tools.query.get_pm25_ionic.tool", "GetPM25IonicTool"),
        ("get_pm25_carbon", "app.tools.query.get_pm25_carbon.tool", "GetPM25CarbonTool"),
        ("get_pm25_crustal", "app.tools.query.get_pm25_crustal.tool", "GetPM25CrustalTool"),
    ]

    results = []

    for tool_name, module_path, class_name in tools_to_test:
        print(f"\n【{tool_name}】")
        print("-" * 60)

        try:
            # 动态导入
            module = __import__(module_path, fromlist=[class_name])
            tool_class = getattr(module, class_name)
            tool = tool_class()

            schema = tool.function_schema

            # 检查 locations 参数
            has_locations = "locations" in schema["parameters"]["properties"]
            locations_param = schema["parameters"]["properties"].get("locations", {})

            # 检查必需参数
            required = set(schema["parameters"]["required"])

            # 验证结果
            checks = {
                "has_locations_param": has_locations,
                "locations_is_array": locations_param.get("type") == "array",
                "station_optional": "station" not in required,
                "code_optional": "code" not in required,
                "only_time_required": required == {"start_time", "end_time"}
            }

            all_passed = all(checks.values())

            # 输出结果
            print(f"  locations 参数: {'✓' if has_locations else '✗'}")
            print(f"  locations 类型: {'✓ array' if locations_param.get('type') == 'array' else '✗ ' + locations_param.get('type', 'N/A')}")
            print(f"  station 可选: {'✓' if checks['station_optional'] else '✗'}")
            print(f"  code 可选: {'✓' if checks['code_optional'] else '✗'}")
            print(f"  必需参数正确: {'✓' if checks['only_time_required'] else '✗ (' + ', '.join(required) + ')'}")
            print(f"  状态: {'✓ 通过' if all_passed else '✗ 失败'}")

            results.append({
                "tool": tool_name,
                "passed": all_passed,
                "checks": checks
            })

        except Exception as e:
            print(f"  ✗ 加载失败: {e}")
            results.append({
                "tool": tool_name,
                "passed": False,
                "error": str(e)
            })

    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)

    print(f"\n通过: {passed_count}/{total_count}")

    for result in results:
        status = "✓" if result["passed"] else "✗"
        print(f"  {status} {result['tool']}")

    if passed_count == total_count:
        print("\n✓ 所有工具的 locations 参数支持测试通过！")
    else:
        print(f"\n✗ {total_count - passed_count} 个工具测试失败")

    return passed_count == total_count


def test_geo_matcher_mappings():
    """测试 GeoMatcher 的映射功能"""
    print("\n" + "=" * 80)
    print("GeoMatcher 映射功能测试")
    print("=" * 80)

    from app.utils.geo_matcher import get_geo_matcher

    geo_matcher = get_geo_matcher()

    # 测试用例
    test_cases = [
        {
            "name": "站点名称映射",
            "input": ["东城", "新兴", "从化天湖"],
            "method": "stations_to_codes"
        },
        {
            "name": "城市名称映射",
            "input": ["广州", "深圳", "东莞"],
            "method": "cities_to_codes"
        },
        {
            "name": "区县名称映射",
            "input": ["天河区", "白云区", "福田区"],
            "method": "districts_to_codes"
        }
    ]

    for test_case in test_cases:
        print(f"\n【{test_case['name']}】")
        method = getattr(geo_matcher, test_case["method"])
        result = method(test_case["input"])

        for inp, code in zip(test_case["input"], result):
            match = "✓" if code else "✗"
            print(f"  {match} {inp} → {code if code else '未映射'}")


if __name__ == "__main__":
    print("颗粒物工具 locations 参数完整测试")
    print("=" * 80)

    # 测试1: 工具 Schema 验证
    schema_passed = test_all_tools_schema()

    # 测试2: GeoMatcher 映射验证
    test_geo_matcher_mappings()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    if schema_passed:
        print("\n✓ 所有测试通过！4个颗粒物工具已全部支持 locations 参数。")
        print("\n使用示例：")
        print('  {"locations": ["东莞"], "start_time": "2024-12-01 00:00:00", "end_time": "2024-12-31 23:59:59"}')
        print('  {"locations": ["东城", "新兴"], "start_time": "2024-12-01 00:00:00", "end_time": "2024-12-31 23:59:59"}')
    else:
        print("\n✗ 部分测试失败，请检查工具实现")
