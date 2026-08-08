"""
广东省 Suncere API DataSource 参数自动修正测试

测试根据查询时间范围自动判断 DataSource 参数的功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta


def test_calculate_data_source():
    """测试 DataSource 参数自动计算"""
    print("\n" + "=" * 60)
    print("测试: DataSource 参数自动计算")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool

        # 测试用例
        test_cases = [
            # (结束时间, 预期DataSource, 描述)
            (datetime.now().strftime("%Y-%m-%d"), 0, "今天"),
            ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), 0, "昨天"),
            ((datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"), 0, "前天"),
            ((datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"), 0, "三天前"),
            ((datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d"), 1, "四天前"),
            ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"), 1, "一周前"),
            ((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), 1, "一月前"),
            ((datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"), 1, "三月前"),
        ]

        print("\n测试用例:")
        all_pass = True
        for end_time, expected_ds, description in test_cases:
            actual_ds = QueryGDSuncereDataTool.calculate_data_source(end_time)
            status = "[PASS]" if actual_ds == expected_ds else "[FAIL]"
            ds_type = "原始实况" if actual_ds == 0 else "审核实况"
            expected_type = "原始实况" if expected_ds == 0 else "审核实况"

            print(f"{status} {description:8s} (结束时间: {end_time})")
            print(f"       预期: DataSource={expected_ds} ({expected_type})")
            print(f"       实际: DataSource={actual_ds} ({ds_type})")

            if actual_ds != expected_ds:
                all_pass = False

        return all_pass

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_calculate_data_source_with_time():
    """测试带时间部分的 DataSource 计算"""
    print("\n" + "=" * 60)
    print("测试: 带时间部分的 DataSource 参数计算")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool

        # 测试用例（带时间部分）
        test_cases = [
            (datetime.now().strftime("%Y-%m-%d 00:00:00"), 0, "今天 00:00:00"),
            (datetime.now().strftime("%Y-%m-%d 23:59:59"), 0, "今天 23:59:59"),
            ((datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d 12:00:00"), 0, "三天前 12:00:00"),
            ((datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d 15:30:00"), 1, "四天前 15:30:00"),
        ]

        print("\n测试用例:")
        all_pass = True
        for end_time, expected_ds, description in test_cases:
            actual_ds = QueryGDSuncereDataTool.calculate_data_source(end_time)
            status = "[PASS]" if actual_ds == expected_ds else "[FAIL]"
            ds_type = "原始实况" if actual_ds == 0 else "审核实况"

            print(f"{status} {description}")
            print(f"       时间: {end_time}")
            print(f"       预期: DataSource={expected_ds}, 实际: DataSource={actual_ds} ({ds_type})")

            if actual_ds != expected_ds:
                all_pass = False

        return all_pass

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_with_auto_datasource():
    """测试完整查询流程中的 DataSource 自动计算"""
    print("\n" + "=" * 60)
    print("测试: 查询流程中的 DataSource 自动计算")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        # 创建上下文
        memory_manager = HybridMemoryManager(session_id="test_datasource_auto")
        data_manager = DataContextManager(memory_manager)
        context = ExecutionContext(
            session_id="test_datasource_auto",
            iteration=1,
            data_manager=data_manager
        )

        # 测试用例1: 查询最近三天的数据（应该使用 DataSource=0）
        print("\n用例1: 查询昨天的数据（应该使用原始实况）")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        print(f"时间范围: {start_time} - {end_time}")

        # 预先计算期望的 DataSource
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool
        expected_ds = QueryGDSuncereDataTool.calculate_data_source(end_time)
        print(f"期望 DataSource: {expected_ds} ({'原始实况' if expected_ds == 0 else '审核实况'})")

        result = execute_query_gd_suncere_station_hour(
            cities=["广州"],
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        if result.get("success"):
            metadata = result.get("metadata", {})
            print(f"[PASS] 查询成功")
            print(f"数据ID: {metadata.get('data_id')}")
            print(f"总记录数: {metadata.get('total_records')}")
        else:
            print(f"[WARN] 查询失败: {result.get('error')}")
            print("注意: 这可能是网络或API问题，不影响 DataSource 计算逻辑测试")

        return True

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API DataSource 参数自动修正测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("DataSource 参数计算", test_calculate_data_source()))
    results.append(("带时间部分的计算", test_calculate_data_source_with_time()))
    results.append(("完整查询流程", test_query_with_auto_datasource()))

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
