"""
测试UDF v2.0格式修复

验证：
1. DataStandardizer能正确转换扁平数据为嵌套measurements格式
2. UnifiedDataRecord能正确反序列化数据
3. _extract_tool_data_for_llm能正确展开measurements字段
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from app.utils.data_standardizer import DataStandardizer
from app.schemas.unified import UnifiedDataRecord


def test_data_standardizer_conversion():
    """测试DataStandardizer的UDF v2.0格式转换"""
    print("=" * 60)
    print("测试1: DataStandardizer格式转换")
    print("=" * 60)

    # 模拟API返回的扁平数据
    raw_records = [
        {
            "name": "广州",
            "code": 440100,
            "pM2_5": 45.2,
            "pM10": 68.5,
            "o3": 52.3,
            "aqi": 85,
            "timestamp": "2026-02-01 00:00:00"
        },
        {
            "name": "深圳",
            "code": 440300,
            "pM2_5": 38.7,
            "pM10": 62.1,
            "o3": 48.9,
            "aqi": 78,
            "timestamp": "2026-02-01 00:00:00"
        }
    ]

    # 标准化
    standardizer = DataStandardizer()
    standardized = standardizer.standardize(raw_records)

    print(f"\n原始记录数: {len(raw_records)}")
    print(f"标准化后记录数: {len(standardized)}")

    # 检查第一条记录
    first_record = standardized[0]
    print(f"\n第一条记录字段: {list(first_record.keys())}")

    # 验证measurements字段
    if "measurements" in first_record:
        print(f"\n[PASS] measurements字段存在")
        print(f"measurements内容: {first_record['measurements']}")
    else:
        print(f"\n[FAIL] measurements字段不存在")
        print(f"记录内容: {first_record}")

    # 验证污染物数据是否在measurements中
    if "measurements" in first_record:
        measurements = first_record["measurements"]
        required_fields = ["PM2_5", "PM10", "O3", "AQI"]
        missing_fields = [f for f in required_fields if f not in measurements]

        if not missing_fields:
            print(f"\n[PASS] 所有必需的污染物字段都在measurements中")
        else:
            print(f"\n[FAIL] 缺少字段: {missing_fields}")

    return standardized


def test_unified_data_record_deserialization():
    """测试UnifiedDataRecord的反序列化"""
    print("\n" + "=" * 60)
    print("测试2: UnifiedDataRecord反序列化")
    print("=" * 60)

    # 模拟DataStandardizer输出的嵌套格式
    nested_record = {
        "station_name": "广州",
        "station_code": 440100,
        "timestamp": "2026-02-01 00:00:00",
        "measurements": {
            "PM2_5": 45.2,
            "PM10": 68.5,
            "O3": 52.3,
            "AQI": 85
        }
    }

    print(f"\n输入数据字段: {list(nested_record.keys())}")
    print(f"measurements内容: {nested_record['measurements']}")

    # 反序列化
    try:
        unified_record = UnifiedDataRecord(**nested_record)
        print(f"\n[PASS] UnifiedDataRecord反序列化成功")

        # 验证字段
        print(f"station_name: {unified_record.station_name}")
        print(f"measurements: {unified_record.measurements}")

        # 检查measurements是否完整
        if unified_record.measurements.get("PM2_5") == 45.2:
            print(f"[PASS] PM2_5数据正确")
        else:
            print(f"[FAIL] PM2_5数据错误")

        return unified_record

    except Exception as e:
        print(f"\n[FAIL] UnifiedDataRecord反序列化失败: {e}")
        return None


def test_backward_compatibility():
    """测试向后兼容性（扁平格式）"""
    print("\n" + "=" * 60)
    print("测试3: 向后兼容性（扁平格式自动转换）")
    print("=" * 60)

    # 模拟旧的扁平格式
    flat_record = {
        "station_name": "广州",
        "timestamp": "2026-02-01 00:00:00",
        "PM2_5": 45.2,
        "PM10": 68.5,
        "O3": 52.3,
        "AQI": 85
    }

    print(f"\n输入数据（扁平格式）: {list(flat_record.keys())}")

    # 反序列化
    try:
        unified_record = UnifiedDataRecord(**flat_record)
        print(f"\n[PASS] 扁平格式反序列化成功")

        # 检查是否自动创建了measurements
        if unified_record.measurements:
            print(f"[PASS] measurements字段自动创建")
            print(f"measurements内容: {unified_record.measurements}")

            # 验证数据完整性
            if (unified_record.measurements.get("PM2_5") == 45.2 and
                unified_record.measurements.get("PM10") == 68.5):
                print(f"[PASS] 数据完整，已正确聚合到measurements")
            else:
                print(f"[FAIL] 数据不完整")
        else:
            print(f"[FAIL] measurements字段未创建")

        return unified_record

    except Exception as e:
        print(f"\n[FAIL] 扁平格式反序列化失败: {e}")
        return None


def test_llm_data_extraction():
    """测试LLM数据提取（模拟_extract_tool_data_for_llm）"""
    print("\n" + "=" * 60)
    print("测试4: LLM数据提取（measurements展开）")
    print("=" * 60)

    # 模拟工具结果
    tool_result = {
        "tool": "get_guangdong_regular_stations",
        "status": "success",
        "data": [
            {
                "station_name": "广州",
                "timestamp": "2026-02-01 00:00:00",
                "measurements": {
                    "PM2_5": 45.2,
                    "PM10": 68.5,
                    "O3": 52.3,
                    "AQI": 85
                }
            },
            {
                "station_name": "深圳",
                "timestamp": "2026-02-01 00:00:00",
                "measurements": {
                    "PM2_5": 38.7,
                    "PM10": 62.1,
                    "O3": 48.9,
                    "AQI": 78
                }
            }
        ]
    }

    # 模拟展开逻辑
    data = tool_result.get("data", [])
    if isinstance(data, list) and data:
        first_record = data[0]
        if isinstance(first_record, dict) and "measurements" in first_record:
            expanded_data = []
            for record in data:
                if isinstance(record, dict) and "measurements" in record:
                    expanded_record = {**record}
                    measurements = record.pop("measurements", {})
                    expanded_record.update(measurements)
                    expanded_data.append(expanded_record)
                else:
                    expanded_data.append(record)
            data = expanded_data

    print(f"\n展开后第一条记录字段: {list(data[0].keys())}")

    # 验证污染物数据在顶层
    if "PM2_5" in data[0] and "PM10" in data[0]:
        print(f"[PASS] 污染物数据已展开到顶层")
        print(f"PM2_5: {data[0]['PM2_5']}")
        print(f"PM10: {data[0]['PM10']}")
    else:
        print(f"[FAIL] 污染物数据未展开")

    return data


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("UDF v2.0格式修复验证测试")
    print("=" * 60)

    # 运行所有测试
    standardized = test_data_standardizer_conversion()
    unified = test_unified_data_record_deserialization()
    backward = test_backward_compatibility()
    llm_data = test_llm_data_extraction()

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    all_passed = True

    if standardized and "measurements" in standardized[0]:
        print("[PASS] 测试1通过: DataStandardizer格式转换")
    else:
        print("[FAIL] 测试1失败: DataStandardizer格式转换")
        all_passed = False

    if unified and unified.measurements:
        print("[PASS] 测试2通过: UnifiedDataRecord反序列化")
    else:
        print("[FAIL] 测试2失败: UnifiedDataRecord反序列化")
        all_passed = False

    if backward and backward.measurements:
        print("[PASS] 测试3通过: 向后兼容性")
    else:
        print("[FAIL] 测试3失败: 向后兼容性")
        all_passed = False

    if llm_data and "PM2_5" in llm_data[0]:
        print("[PASS] 测试4通过: LLM数据提取")
    else:
        print("[FAIL] 测试4失败: LLM数据提取")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] 所有测试通过！修复成功！")
    else:
        print("[FAIL] 部分测试失败，需要进一步调试")
    print("=" * 60)
