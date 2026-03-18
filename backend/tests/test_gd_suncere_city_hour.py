"""
广东省 Suncere API 城市小时数据测试

测试城市小时数据查询（适合区域对比分析）
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


def test_city_hour_query():
    """测试城市小时数据查询"""
    print("\n" + "=" * 60)
    print("测试2: 城市小时数据查询（区域对比）")
    print("=" * 60)

    try:
        from app.services.gd_suncere_api_client import get_gd_suncere_api_client

        api_client = get_gd_suncere_api_client()

        # 查询昨天的小时数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        print(f"\n查询时间: {yesterday}")
        print(f"城市代码: 440200 (韶关)")

        # 查询单个城市
        response = api_client.query_city_hour_data(
            city_codes=["440200"],  # 韶关
            start_time=start_time,
            end_time=end_time,
            data_type=0
        )

        print(f"\nAPI 响应状态: {response.get('state')}")
        print(f"API Success: {response.get('success')}")

        if response.get("success") and response.get("result"):
            records = response["result"]
            print(f"记录数: {len(records)}")

            if records:
                first_record = records[0]
                print(f"\n第一条记录示例:")
                for key, value in list(first_record.items())[:15]:
                    print(f"  {key}: {value}")

                # 检查是否有污染物数据
                has_pollutants = any(
                    key.lower() in ['pm2_5', 'pm10', 'so2', 'no2', 'o3', 'co']
                    for key in first_record.keys()
                )

                if has_pollutants:
                    print(f"\n[PASS] API 返回了污染物数据")
                else:
                    print(f"\n[WARN] API 可能缺少污染物字段")

            return True
        else:
            print(f"\n[FAIL] API 未返回数据")
            print(f"错误信息: {response.get('msg', 'Unknown')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_city_hour_query():
    """测试多城市小时数据查询"""
    print("\n" + "=" * 60)
    print("测试3: 多城市小时数据查询")
    print("=" * 60)

    try:
        from app.services.gd_suncere_api_client import get_gd_suncere_api_client

        api_client = get_gd_suncere_api_client()

        # 查询昨天的小时数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        print(f"\n查询时间: {yesterday}")
        print(f"城市代码: 440200, 440100, 440300 (韶关、广州、深圳)")

        # 查询多个城市
        response = api_client.query_city_hour_data(
            city_codes=["440200", "440100", "440300"],  # 韶关、广州、深圳
            start_time=start_time,
            end_time=end_time,
            data_type=0
        )

        print(f"\nAPI 响应状态: {response.get('state')}")

        if response.get("success") and response.get("result"):
            records = response["result"]
            print(f"总记录数: {len(records)}")

            # 统计每个城市的记录数
            city_counts = {}
            for record in records:
                city_name = record.get("name", "Unknown")
                city_counts[city_name] = city_counts.get(city_name, 0) + 1

            print(f"\n各城市记录数:")
            for city, count in city_counts.items():
                print(f"  {city}: {count} 条")

            if len(city_counts) > 1:
                print(f"\n[PASS] 成功查询多个城市")
            else:
                print(f"\n[WARN] 只返回了一个城市的数据")

            return True
        else:
            print(f"\n[FAIL] API 未返回数据")
            print(f"错误信息: {response.get('msg', 'Unknown')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API 城市小时数据测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("Token 认证", test_token_authentication()))
    results.append(("城市小时查询", test_city_hour_query()))
    results.append(("多城市查询", test_multi_city_hour_query()))

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
