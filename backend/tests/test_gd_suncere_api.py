"""
广东省 Suncere API 测试脚本

测试 API 认证、数据查询和标准化功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.tools.query.query_gd_suncere import (
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_hour
)
from app.agent.context.execution_context import ExecutionContext
from app.agent.memory.session_memory import SessionMemoryManager


def test_token_authentication():
    """测试 Token 认证"""
    print("\n" + "=" * 60)
    print("测试1: Token 认证")
    print("=" * 60)

    try:
        api_client = get_gd_suncere_api_client()
        token = api_client.get_token()

        print(f"\n[PASS] Token 获取成功")
        print(f"Token 长度: {len(token)}")
        print(f"Token 前20字符: {token[:20]}...")

        return True
    except Exception as e:
        print(f"\n[FAIL] Token 获取失败: {e}")
        return False


def test_city_day_query():
    """测试城市日报数据查询"""
    print("\n" + "=" * 60)
    print("测试2: 城市日报数据查询")
    print("=" * 60)

    # 创建上下文
    session_manager = SessionMemoryManager()
    context = ExecutionContext(session_manager)

    # 查询最近3天的数据
    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    print(f"\n查询时间范围: {start_date} 至 {end_date}")
    print(f"查询城市: 广州、深圳")

    try:
        result = execute_query_gd_suncere_city_day(
            cities=["广州", "深圳"],
            start_date=start_date,
            end_date=end_date,
            context=context
        )

        if result.get("success"):
            print(f"\n[PASS] 查询成功")
            print(f"数据ID: {result['metadata']['data_id']}")
            print(f"总记录数: {result['metadata']['total_records']}")
            print(f"返回记录数: {result['metadata']['returned_records']}")

            # 检查数据格式
            if result.get("data") and len(result["data"]) > 0:
                first_record = result["data"][0]
                print(f"\n第一条记录字段: {list(first_record.keys())[:15]}")

                if "measurements" in first_record:
                    print(f"[PASS] 数据包含 measurements 字段")
                    print(f"measurements 内容: {first_record['measurements']}")
                else:
                    print(f"[WARN] 数据不包含 measurements 字段")

            return True
        else:
            print(f"\n[FAIL] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] 查询异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_station_hour_query():
    """测试站点小时数据查询"""
    print("\n" + "=" * 60)
    print("测试3: 站点小时数据查询")
    print("=" * 60)

    # 创建上下文
    session_manager = SessionMemoryManager()
    context = ExecutionContext(session_manager)

    # 查询昨天的小时数据
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    start_time = f"{yesterday} 00:00:00"
    end_time = f"{yesterday} 23:59:59"

    print(f"\n查询时间: {yesterday}")
    print(f"查询城市: 韶关、广州")

    try:
        result = execute_query_gd_suncere_station_hour(
            cities=["韶关", "广州"],
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        if result.get("success"):
            print(f"\n[PASS] 查询成功")
            print(f"数据ID: {result['metadata']['data_id']}")
            print(f"总记录数: {result['metadata']['total_records']}")

            # 检查数据是否有污染物浓度
            if result.get("data") and len(result["data"]) > 0:
                first_record = result["data"][0]

                if "measurements" in first_record:
                    measurements = first_record["measurements"]
                    has_data = any(v is not None for v in measurements.values())

                    if has_data:
                        print(f"[PASS] 数据包含实际浓度值")
                        print(f"污染物示例: {list(measurements.keys())[:5]}")
                    else:
                        print(f"[WARN] measurements 字段存在但值为空/None")
                else:
                    print(f"[FAIL] 数据不包含 measurements 字段")
                    print(f"实际字段: {list(first_record.keys())}")

            return True
        else:
            print(f"\n[FAIL] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] 查询异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regional_comparison():
    """测试区域对比数据查询"""
    print("\n" + "=" * 60)
    print("测试4: 区域对比数据查询")
    print("=" * 60)

    # 创建上下文
    session_manager = SessionMemoryManager()
    context = ExecutionContext(session_manager)

    # 查询昨天的小时数据
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_time = f"{yesterday} 00:00:00"
    end_time = f"{yesterday} 23:59:59"

    print(f"\n目标城市: 韶关")
    print(f"周边城市: 广州、深圳、佛山、东莞")
    print(f"查询时间: {yesterday}")

    try:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_regional_comparison

        result = execute_query_gd_suncere_regional_comparison(
            target_city="韶关",
            nearby_cities=["广州", "深圳", "佛山", "东莞"],
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        if result.get("success"):
            print(f"\n[PASS] 区域对比查询成功")
            print(f"数据ID: {result['metadata']['data_id']}")
            print(f"总记录数: {result['metadata']['total_records']}")

            # 验证多城市数据
            if result.get("data") and len(result["data"]) > 0:
                cities_in_data = set()
                for record in result["data"][:50]:  # 检查前50条
                    if "city" in record:
                        cities_in_data.add(record["city"])

                print(f"数据中的城市: {cities_in_data}")

                if len(cities_in_data) > 1:
                    print(f"[PASS] 包含多个城市的数据")
                else:
                    print(f"[WARN] 只有一个城市的数据")

            return True
        else:
            print(f"\n[FAIL] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] 查询异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API 测试")
    print("=" * 60)

    results = []

    # 运行所有测试
    results.append(("Token 认证", test_token_authentication()))
    results.append(("城市日报查询", test_city_day_query()))
    results.append(("站点小时查询", test_station_hour_query()))
    results.append(("区域对比查询", test_regional_comparison()))

    # 输出测试总结
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
