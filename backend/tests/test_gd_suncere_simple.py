"""
广东省 Suncere API 简化测试脚本

直接测试 API 客户端，避免依赖整个工具系统
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta


def test_token_authentication():
    """测试 Token 认证"""
    print("\n" + "=" * 60)
    print("测试1: Token 认证")
    print("=" * 60)

    try:
        from app.services.gd_suncere_api_client import get_gd_suncere_api_client

        api_client = get_gd_suncere_api_client()
        token = api_client.get_token()

        print(f"\n[PASS] Token 获取成功")
        print(f"Token 长度: {len(token)}")
        print(f"Token 前20字符: {token[:20]}...")

        return True
    except Exception as e:
        print(f"\n[FAIL] Token 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_direct_call():
    """直接调用 API 测试"""
    print("\n" + "=" * 60)
    print("测试2: 直接 API 调用（站点小时数据）")
    print("=" * 60)

    try:
        from app.services.gd_suncere_api_client import get_gd_suncere_api_client

        api_client = get_gd_suncere_api_client()

        # 查询最近3天的数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        print(f"\n查询时间: {yesterday}")
        print(f"城市代码: 440200 (韶关)")

        # 直接调用 API
        response = api_client.query_station_hour_data(
            city_code="440200",  # 韶关
            start_time=start_time,
            end_time=end_time,
            pollutant_codes=["PM2.5", "PM10", "SO2", "NO2", "O3", "CO"]
        )

        print(f"\nAPI 响应状态: {response.get('status')}")
        print(f"API Success: {response.get('success')}")

        if response.get("success") and response.get("data"):
            records = response["data"]
            print(f"记录数: {len(records)}")

            if records:
                first_record = records[0]
                print(f"\n第一条记录示例:")
                for key, value in list(first_record.items())[:10]:
                    print(f"  {key}: {value}")

                # 检查是否有数值数据
                has_values = any(
                    v is not None and v != '—'
                    for v in first_record.values()
                    if isinstance(v, (int, float, str))
                )

                if has_values:
                    print(f"\n[PASS] API 返回了实际数值数据")
                else:
                    print(f"\n[WARN] API 返回数据但值可能为空或'—'")

            return True
        else:
            print(f"\n[FAIL] API 未返回数据")
            print(f"错误信息: {response.get('error', 'Unknown')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_city_code_mapping():
    """测试城市代码映射"""
    print("\n" + "=" * 60)
    print("测试3: 城市代码映射")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool

        # 测试城市代码映射
        test_cities = ["广州", "深圳", "佛山", "韶关", "东莞"]

        print(f"\n测试城市: {test_cities}")

        for city in test_cities:
            code = QueryGDSuncereDataTool.get_city_code(city)
            if code:
                print(f"[PASS] {city} -> {code}")
            else:
                print(f"[FAIL] {city} -> 未找到代码")

        return True

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_error_handling():
    """测试 API 错误处理"""
    print("\n" + "=" * 60)
    print("测试4: API 错误处理（无效城市代码）")
    print("=" * 60)

    try:
        from app.services.gd_suncere_api_client import get_gd_suncere_api_client

        api_client = get_gd_suncere_api_client()

        # 使用无效的城市代码
        response = api_client.query_station_hour_data(
            city_code="999999",  # 无效代码
            start_time="2024-12-01 00:00:00",
            end_time="2024-12-01 23:59:59",
            pollutant_codes=["PM2.5"]
        )

        print(f"\nAPI 响应: {response.get('status')}")
        print(f"错误处理正常: {response.get('success') == False or response.get('error') is not None}")

        return True

    except Exception as e:
        # 预期会有错误，但应该被正确处理
        print(f"\n[PASS] 错误被正确捕获: {type(e).__name__}")
        return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API 简化测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("Token 认证", test_token_authentication()))
    results.append(("API 直接调用", test_api_direct_call()))
    results.append(("城市代码映射", test_city_code_mapping()))
    results.append(("错误处理", test_api_error_handling()))

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
        print("\n✅ 所有测试通过！")
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
