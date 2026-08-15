"""
验证广东省 Suncere API 工具是否符合 UDF v2.0 数据规范
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta


def test_udf_v2_compliance():
    """测试 UDF v2.0 规范符合性"""
    print("\n" + "=" * 60)
    print("测试: UDF v2.0 规范符合性")
    print("=" * 60)

    try:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        # 创建上下文
        memory_manager = HybridMemoryManager(session_id="test_udf_v2")
        data_manager = DataContextManager(memory_manager)
        context = ExecutionContext(
            session_id="test_udf_v2",
            iteration=1,
            data_manager=data_manager
        )

        # 查询数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:59"

        result = execute_query_gd_suncere_station_hour(
            cities=["广州"],
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        print("\n检查 UDF v2.0 规范要求:")
        all_pass = True

        # 1. 检查顶层字段
        print("\n1. 顶层字段检查:")
        required_fields = {
            "status": "success",
            "success": True,
            "data": list,
            "metadata": dict,
            "summary": str
        }

        for field, expected_value in required_fields.items():
            if field in result:
                if isinstance(expected_value, type):
                    # 检查类型
                    if isinstance(result[field], expected_value):
                        print(f"   [PASS] {field}: {type(result[field]).__name__}")
                    else:
                        print(f"   [FAIL] {field}: 期望 {expected_value.__name__}, 实际 {type(result[field]).__name__}")
                        all_pass = False
                else:
                    # 检查值
                    if result[field] == expected_value:
                        print(f"   [PASS] {field}: {expected_value}")
                    else:
                        print(f"   [FAIL] {field}: 期望 {expected_value}, 实际 {result[field]}")
                        all_pass = False
            else:
                print(f"   [FAIL] {field}: 字段缺失")
                all_pass = False

        # 2. 检查 metadata 字段
        print("\n2. metadata 字段检查:")
        metadata = result.get("metadata", {})
        required_metadata = {
            "tool_name": str,
            "data_id": str,
            "total_records": int,
            "returned_records": int,
            "schema_version": str,  # UDF v2.0 必需
            "source": str
        }

        for field, expected_type in required_metadata.items():
            if field in metadata:
                if isinstance(metadata[field], expected_type):
                    print(f"   [PASS] metadata.{field}: {metadata[field]}")
                else:
                    print(f"   [FAIL] metadata.{field}: 期望 {expected_type.__name__}, 实际 {type(metadata[field]).__name__}")
                    all_pass = False
            else:
                print(f"   [FAIL] metadata.{field}: 字段缺失")
                all_pass = False

        # 3. 检查 schema_version 值
        print("\n3. schema_version 值检查:")
        if metadata.get("schema_version") == "v2.0":
            print(f"   [PASS] schema_version = v2.0")
        else:
            print(f"   [FAIL] schema_version = {metadata.get('schema_version')}, 期望 v2.0")
            all_pass = False

        # 4. 检查 data_id 格式
        print("\n4. data_id 格式检查:")
        data_id = metadata.get("data_id", "")
        if ":" in data_id:
            parts = data_id.split(":")
            if len(parts) >= 3:
                print(f"   [PASS] data_id 格式正确: {data_id}")
                print(f"          schema={parts[0]}, version={parts[1]}, hash={parts[2][:8]}...")
            else:
                print(f"   [WARN] data_id 格式不标准: {data_id}")
        else:
            print(f"   [FAIL] data_id 格式错误: {data_id}")
            all_pass = False

        # 5. 检查数据记录格式
        print("\n5. 数据记录格式检查:")
        data = result.get("data", [])
        if data:
            first_record = data[0]
            print(f"   样本记录字段: {list(first_record.keys())[:15]}")

            # 检查是否有 measurements 字段（UDF v2.0 标准）
            if "measurements" in first_record:
                print(f"   [PASS] 包含 measurements 字段（嵌套数据）")
            else:
                print(f"   [WARN] 不包含 measurements 字段（可能是扁平数据）")

            # 检查是否有标准字段名
            standard_fields = ["station_name", "timestamp", "PM2_5", "PM10", "O3", "NO2", "SO2"]
            found_fields = [f for f in standard_fields if f in first_record or f in first_record.get("measurements", {})]
            print(f"   标准字段: {found_fields}")

        return all_pass

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("广东省 Suncere API UDF v2.0 规范验证")
    print("=" * 60)

    result = test_udf_v2_compliance()

    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)

    if result:
        print("[PASS] 工具完全符合 UDF v2.0 规范")
    else:
        print("[FAIL] 工具不符合 UDF v2.0 规范，请检查上述失败项")
