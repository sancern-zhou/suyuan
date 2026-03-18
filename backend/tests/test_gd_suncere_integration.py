"""
广东省 Suncere API 工具链集成测试

测试完整的工具调用链，包括 API 客户端、数据标准化、上下文管理
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta


def test_city_hour_query():
    """测试城市小时数据查询"""
    print("\n" + "=" * 60)
    print("测试: 城市小时数据查询（区域对比）")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        # 创建上下文
        memory_manager = HybridMemoryManager(session_id="test_session_city_hour")
        data_manager = DataContextManager(memory_manager)
        context = ExecutionContext(
            session_id="test_session_city_hour",
            iteration=1,
            data_manager=data_manager
        )

        # 查询昨天的小时数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        print(f"\n查询时间: {yesterday}")
        print(f"城市: 韶关、广州、深圳")

        # 执行查询
        result = execute_query_gd_suncere_station_hour(
            cities=["韶关", "广州", "深圳"],
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        print(f"\n查询状态: {result.get('status')}")
        print(f"查询成功: {result.get('success')}")

        if result.get("success"):
            metadata = result.get("metadata", {})
            print(f"数据ID: {metadata.get('data_id')}")
            print(f"总记录数: {metadata.get('total_records')}")
            print(f"返回记录数: {metadata.get('returned_records')}")

            # 检查数据格式
            data = result.get("data", [])
            if data:
                first_record = data[0]
                print(f"\n第一条记录字段: {list(first_record.keys())[:15]}")

                if "measurements" in first_record:
                    print(f"[PASS] 数据包含 measurements 字段")
                else:
                    print(f"[WARN] 数据不包含 measurements 字段（可能在 top-level）")

            print(f"\n[PASS] 工具链集成测试通过")
            return True
        else:
            print(f"\n[FAIL] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regional_comparison_query():
    """测试区域对比查询"""
    print("\n" + "=" * 60)
    print("测试: 区域对比数据查询")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_regional_comparison
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        # 创建上下文
        memory_manager = HybridMemoryManager(session_id="test_session_regional_comparison")
        data_manager = DataContextManager(memory_manager)
        context = ExecutionContext(
            session_id="test_session_regional_comparison",
            iteration=1,
            data_manager=data_manager
        )

        # 查询昨天的小时数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        print(f"\n查询时间: {yesterday}")
        print(f"目标城市: 韶关")
        print(f"周边城市: 广州、深圳、佛山、东莞")

        # 执行区域对比查询
        result = execute_query_gd_suncere_regional_comparison(
            target_city="韶关",
            nearby_cities=["广州", "深圳", "佛山", "东莞"],
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        print(f"\n查询状态: {result.get('status')}")
        print(f"查询成功: {result.get('success')}")

        if result.get("success"):
            metadata = result.get("metadata", {})
            print(f"数据ID: {metadata.get('data_id')}")
            print(f"总记录数: {metadata.get('total_records')}")
            print(f"查询类型: {metadata.get('query_type')}")
            print(f"目标城市: {metadata.get('target_city')}")
            print(f"周边城市: {metadata.get('nearby_cities')}")

            print(f"\n[PASS] 区域对比查询测试通过")
            return True
        else:
            print(f"\n[FAIL] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API 工具链集成测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("城市小时查询", test_city_hour_query()))
    results.append(("区域对比查询", test_regional_comparison_query()))

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
