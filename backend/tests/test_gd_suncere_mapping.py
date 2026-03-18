"""
广东省 Suncere API 编码映射测试

测试城市/站点名称到编码的自动映射功能（LLM驱动架构）
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_city_code_mapping():
    """测试城市名称映射"""
    print("\n" + "=" * 60)
    print("测试1: 城市名称自动映射")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere.tool import GeoMappingResolver

        resolver = GeoMappingResolver()

        # 测试标准名称和别名
        test_cases = [
            ("广州", "440100"),
            ("广州市", "440100"),
            ("深圳", "440300"),
            ("韶关", "440200"),
            ("佛山", "440600"),
        ]

        print("\n直接查找测试:")
        all_pass = True
        for city_name, expected_code in test_cases:
            actual_code = resolver.CITY_CODE_MAP.get(city_name)
            status = "[PASS]" if actual_code == expected_code else "[FAIL]"
            print(f"{status} {city_name} → {actual_code}")
            if actual_code != expected_code:
                all_pass = False

        # 测试批量解析
        print("\n批量解析测试:")
        city_names = ["广州", "深圳市", "佛山", "韶关市"]
        city_codes = resolver.resolve_city_codes(city_names)

        print(f"输入: {city_names}")
        print(f"输出: {city_codes}")

        expected_codes = ["440100", "440300", "440600", "440200"]
        if city_codes == expected_codes:
            print(f"[PASS] 批量解析成功")
        else:
            print(f"[FAIL] 批量解析失败 (期望: {expected_codes})")
            all_pass = False

        return all_pass

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_station_code_mapping():
    """测试站点名称映射"""
    print("\n" + "=" * 60)
    print("测试2: 站点名称自动映射")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere.tool import GeoMappingResolver

        resolver = GeoMappingResolver()

        # 测试站点名称
        test_stations = [
            ("广雅中学", "1001A"),
            ("市监测站", "1008A"),
            ("洪湖", "1018A"),
            ("华侨城", "1019A"),
            ("韶关学院", "1015A")
        ]

        print("\n直接查找测试:")
        all_pass = True
        for station_name, expected_code in test_stations:
            actual_code = resolver.STATION_CODE_MAP.get(station_name)
            if actual_code == expected_code:
                print(f"[PASS] {station_name} → {actual_code}")
            else:
                print(f"[FAIL] {station_name} → {actual_code} (期望: {expected_code})")
                all_pass = False

        # 测试批量解析
        print("\n批量解析测试:")
        station_names = ["广雅中学", "市监测站", "洪湖"]
        station_codes = resolver.resolve_station_codes(station_names)

        print(f"输入: {station_names}")
        print(f"输出: {station_codes}")

        if len(station_codes) == len(station_names):
            print(f"[PASS] 批量解析成功")
        else:
            print(f"[WARN] 部分站点未解析")

        return all_pass

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mixed_input():
    """测试混合输入（名称和编码）"""
    print("\n" + "=" * 60)
    print("测试3: 混合输入（城市名称 + 城市编码）")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool

        # 模拟 LLM 可能的输出：混合名称和编码
        mixed_input = ["广州", "440300", "佛山", "440200"]
        print(f"混合输入: {mixed_input}")

        # 使用工具的智能判断逻辑
        tool = QueryGDSuncereDataTool()
        resolved_codes = []
        for city in mixed_input:
            city = city.strip()
            if city.isdigit() and len(city) == 6:
                resolved_codes.append(city)
                print(f"[检测到编码] {city}")
            else:
                code = tool.get_city_code(city)
                if code:
                    resolved_codes.append(code)
                    print(f"[名称转编码] {city} → {code}")

        expected = ["440100", "440300", "440600", "440200"]
        if resolved_codes == expected:
            print(f"\n[PASS] 混合输入解析成功: {resolved_codes}")
            return True
        else:
            print(f"\n[FAIL] 解析失败 (期望: {expected})")
            return False

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API 编码映射测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("城市名称映射", test_city_code_mapping()))
    results.append(("站点名称映射", test_station_code_mapping()))
    results.append(("混合输入解析", test_mixed_input()))

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n所有测试通过!")
    else:
        print(f"\n{total - passed} 个测试失败")
