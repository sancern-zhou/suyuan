"""
测试广东省综合统计报表查询工具
查看返回数据字段结构
"""
import asyncio
import json
from datetime import datetime, timedelta
from app.tools.query.query_gd_suncere.tool import (
    execute_query_gd_suncere_report,
    execute_query_gd_suncere_report_compare
)
from app.agent.context.execution_context import ExecutionContext
from app.services.image_cache import ImageCache


class MockDataContextManager:
    """模拟数据上下文管理器"""
    def save_data(self, data, schema, metadata=None):
        """模拟保存数据"""
        print(f"\n[MockDataContextManager] 保存数据:")
        print(f"  - schema: {schema}")
        print(f"  - data_count: {len(data) if isinstance(data, list) else 'N/A'}")
        print(f"  - metadata: {metadata}")
        return "mock_data_id"


async def test_report_structure():
    """测试综合统计报表数据结构"""
    print("=" * 80)
    print("测试广东省综合统计报表查询工具")
    print("=" * 80)

    # 创建模拟上下文
    context = ExecutionContext(
        session_id="test_session",
        iteration=1,
        data_manager=MockDataContextManager()
    )

    # 测试参数
    cities = ["广州"]
    start_time = "2026-02-01 00:00:00"
    end_time = "2026-02-10 23:59:59"

    print(f"\n【测试参数】")
    print(f"  - cities: {cities}")
    print(f"  - start_time: {start_time}")
    print(f"  - end_time: {end_time}")

    # 调用综合统计报表查询
    print(f"\n【调用 query_gd_suncere_report】")
    result = execute_query_gd_suncere_report(
        cities=cities,
        start_time=start_time,
        end_time=end_time,
        time_type=8,  # 任意时间报表
        area_type=2,  # 城市级别
        pollutant_codes=None,
        context=context
    )

    # 打印结果结构
    print(f"\n【返回结果结构】")
    print(f"  - status: {result.get('status')}")
    print(f"  - success: {result.get('success')}")
    print(f"  - summary: {result.get('summary')}")

    metadata = result.get('metadata', {})
    print(f"\n【元数据】")
    for key, value in metadata.items():
        print(f"  - {key}: {value}")

    # 打印数据字段结构
    data = result.get('data', [])
    print(f"\n【数据字段结构】")
    if data and len(data) > 0:
        first_record = data[0]
        print(f"  - 总记录数: {len(data)}")
        print(f"  - 第一条记录字段:")

        # 按类别分组显示字段
        basic_fields = []
        pollutant_fields = []
        stat_fields = []
        rank_fields = []
        other_fields = []

        for key in sorted(first_record.keys()):
            value = first_record[key]
            field_type = type(value).__name__

            # 分类字段
            if key in ['cityCode', 'cityName', 'districtCode', 'districtName',
                      'uniqueCode', 'stationCode', 'stationName', 'timePoint']:
                basic_fields.append(f"    {key}: {value} ({field_type})")
            elif any(x in key.upper() for x in ['SO2', 'NO2', 'PM', 'CO', 'O3']):
                pollutant_fields.append(f"    {key}: {value} ({field_type})")
            elif 'Index' in key or 'Level' in key or 'Rate' in key or 'Days' in key:
                stat_fields.append(f"    {key}: {value} ({field_type})")
            elif 'Rank' in key:
                rank_fields.append(f"    {key}: {value} ({field_type})")
            else:
                other_fields.append(f"    {key}: {value} ({field_type})")

        print(f"\n  【基础信息字段】")
        for field in basic_fields:
            print(field)

        print(f"\n  【污染物浓度字段】")
        for field in pollutant_fields:
            print(field)

        print(f"\n  【统计指标字段】")
        for field in stat_fields:
            print(field)

        print(f"\n  【排名字段】")
        for field in rank_fields:
            print(field)

        if other_fields:
            print(f"\n  【其他字段】")
            for field in other_fields:
                print(field)

        # 完整显示第一条记录
        print(f"\n【完整第一条记录（JSON格式）】")
        print(json.dumps(first_record, indent=2, ensure_ascii=False))

    else:
        print(f"  - 无数据返回")
        print(f"  - 完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}")


async def test_report_compare_structure():
    """测试对比分析报表数据结构"""
    print("\n")
    print("=" * 80)
    print("测试广东省对比分析报表查询工具")
    print("=" * 80)

    # 创建模拟上下文
    context = ExecutionContext(
        session_id="test_session_compare",
        iteration=1,
        data_manager=MockDataContextManager()
    )

    # 测试参数
    cities = ["广州"]
    time_point = ["2026-02-01 00:00:00", "2026-02-10 23:59:59"]
    contrast_time = ["2025-02-01 00:00:00", "2025-02-10 23:59:59"]

    print(f"\n【测试参数】")
    print(f"  - cities: {cities}")
    print(f"  - time_point: {time_point}")
    print(f"  - contrast_time: {contrast_time}")

    # 调用对比分析报表查询
    print(f"\n【调用 query_gd_suncere_report_compare】")
    result = execute_query_gd_suncere_report_compare(
        cities=cities,
        time_point=time_point,
        contrast_time=contrast_time,
        time_type=8,  # 任意时间
        area_type=2,  # 城市级别
        pollutant_codes=None,
        context=context
    )

    # 打印结果结构
    print(f"\n【返回结果结构】")
    print(f"  - status: {result.get('status')}")
    print(f"  - success: {result.get('success')}")
    print(f"  - summary: {result.get('summary')}")

    metadata = result.get('metadata', {})
    print(f"\n【元数据】")
    for key, value in metadata.items():
        print(f"  - {key}: {value}")

    # 打印数据字段结构
    data = result.get('data', [])
    print(f"\n【数据字段结构】")
    if data and len(data) > 0:
        first_record = data[0]
        print(f"  - 总记录数: {len(data)}")
        print(f"  - 第一条记录字段:")

        # 按类别分组显示字段
        basic_fields = []
        current_fields = []
        compare_fields = []
        increase_fields = []
        rank_fields = []

        for key in sorted(first_record.keys()):
            value = first_record[key]
            field_type = type(value).__name__
            value_str = str(value)[:50] if len(str(value)) > 50 else str(value)

            # 分类字段
            if key in ['cityCode', 'cityName', 'districtCode', 'districtName',
                      'uniqueCode', 'stationCode', 'stationName', 'timePoint']:
                basic_fields.append(f"    {key}: {value_str} ({field_type})")
            elif key.endswith('_Compare') and not key.endswith('Compare'):
                compare_fields.append(f"    {key}: {value_str} ({field_type})")
            elif key.endswith('_Increase'):
                increase_fields.append(f"    {key}: {value_str} ({field_type})")
            elif 'Rank' in key:
                rank_fields.append(f"    {key}: {value_str} ({field_type})")
            elif not any(x in key for x in ['_Compare', '_Increase', 'Rank']):
                current_fields.append(f"    {key}: {value_str} ({field_type})")

        print(f"\n  【基础信息字段】")
        for field in basic_fields:
            print(field)

        print(f"\n  【当前值字段】")
        for field in current_fields[:20]:  # 限制显示数量
            print(field)
        if len(current_fields) > 20:
            print(f"    ... 还有 {len(current_fields) - 20} 个字段")

        print(f"\n  【对比值字段（_Compare）】")
        for field in compare_fields[:15]:
            print(field)
        if len(compare_fields) > 15:
            print(f"    ... 还有 {len(compare_fields) - 15} 个字段")

        print(f"\n  【增幅字段（_Increase）】")
        for field in increase_fields[:15]:
            print(field)
        if len(increase_fields) > 15:
            print(f"    ... 还有 {len(increase_fields) - 15} 个字段")

        print(f"\n  【排名字段（_Rank）】")
        for field in rank_fields[:15]:
            print(field)
        if len(rank_fields) > 15:
            print(f"    ... 还有 {len(rank_fields) - 15} 个字段")

        # 完整显示第一条记录
        print(f"\n【完整第一条记录（JSON格式，关键字段）】")
        # 只显示关键字段
        key_fields = ['cityName', 'timePoint', 'compositeIndex', 'compositeIndex_Compare',
                     'compositeIndex_Increase', 'pM2_5', 'pM2_5_Compare', 'pM2_5_Increase',
                     'fineDays', 'fineDays_Compare', 'fineDays_Increase']
        filtered_record = {k: first_record.get(k) for k in key_fields if k in first_record}
        print(json.dumps(filtered_record, indent=2, ensure_ascii=False))

    else:
        print(f"  - 无数据返回")
        print(f"  - 完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    print("开始测试广东省综合统计报表查询工具\n")

    # 测试综合统计报表
    asyncio.run(test_report_structure())

    # 测试对比分析报表
    asyncio.run(test_report_compare_structure())

    print("\n测试完成！")
