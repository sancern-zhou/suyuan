"""
简单测试 load_data_from_memory 的智能采样功能

运行方式：cd backend && python tests/test_load_data_simple.py
"""
import sys
sys.path.insert(0, '.')

# 设置测试模式，避免加载过多依赖
import os
os.environ['TESTING'] = 'true'

from unittest.mock import Mock
import asyncio


def test_smart_sampling_algorithm():
    """直接测试智能采样算法"""
    print("\n" + "="*60)
    print("测试智能采样算法")
    print("="*60)

    # 导入采样函数
    from app.agent.tool_adapter import get_react_agent_tool_registry

    # 获取工具注册表
    tool_registry = get_react_agent_tool_registry()
    load_data_tool = tool_registry["load_data_from_memory"]

    # 测试1：小数据集（不采样）
    print("\n[测试1] 小数据集（10条 < max_records=100）")
    mock_context = Mock()
    small_data = [{"id": i, "value": f"record_{i}"} for i in range(10)]
    mock_context.get_data = Mock(return_value=small_data)

    result = asyncio.run(load_data_tool(
        data_id="test:v1:small",
        max_records=100,
        context=mock_context
    ))

    print(f"  原始记录数: {result['metadata']['original_count']}")
    print(f"  返回记录数: {len(result['data'])}")
    print(f"  是否截断: {result['metadata']['truncated']}")
    assert result['metadata']['truncated'] == False, "小数据集不应被截断"
    assert len(result['data']) == 10, "应返回全部数据"
    print("  [PASS] 测试通过")

    # 测试2：大数据集（采样）
    print("\n[测试2] 大数据集（1000条 > max_records=100）")
    large_data = [{"id": i, "value": f"record_{i}"} for i in range(1000)]
    mock_context.get_data = Mock(return_value=large_data)

    result = asyncio.run(load_data_tool(
        data_id="test:v1:large",
        max_records=100,
        context=mock_context
    ))

    # 检查结果
    if not result.get('success'):
        print(f"  [FAIL] 工具调用失败: {result.get('error')}")
        raise Exception(f"工具调用失败: {result.get('error')}")

    print(f"  原始记录数: {result['metadata']['original_count']}")
    print(f"  返回记录数: {len(result['data'])}")
    print(f"  是否截断: {result['metadata']['truncated']}")

    sampling_info = result['metadata']['sampling_info']
    if sampling_info:
        print(f"  采样策略: {sampling_info['strategy']}")
        print(f"  首部样本: {sampling_info['head_samples']}")
        print(f"  中部样本: {sampling_info['middle_samples']}")
        print(f"  尾部样本: {sampling_info['tail_samples']}")
        print(f"  保留比例: {sampling_info['retention_ratio']:.1%}")

    assert result['metadata']['truncated'] == True, "大数据集应被截断"
    assert len(result['data']) == 100, "应返回100条"
    assert sampling_info['head_samples'] == 30, "首部应为30条"
    assert sampling_info['tail_samples'] == 30, "尾部应为30条"
    assert sampling_info['middle_samples'] == 40, "中部应为40条"
    print("  [PASS] 测试通过")

    # 测试3：自定义max_records
    print("\n[测试3] 自定义max_records=50")
    medium_data = [{"id": i, "value": f"record_{i}"} for i in range(500)]
    mock_context.get_data = Mock(return_value=medium_data)

    result = asyncio.run(load_data_tool(
        data_id="test:v1:medium",
        max_records=50,
        context=mock_context
    ))

    print(f"  原始记录数: {result['metadata']['original_count']}")
    print(f"  返回记录数: {len(result['data'])}")
    assert len(result['data']) == 50, "应返回50条"

    sampling_info = result['metadata']['sampling_info']
    if sampling_info:
        print(f"  首部: {sampling_info['head_samples']}, 中部: {sampling_info['middle_samples']}, 尾部: {sampling_info['tail_samples']}")
    print("  [PASS] 测试通过")

    # 测试4：数据连续性验证
    print("\n[测试4] 验证采样数据的连续性")
    large_data = [{"id": i, "timestamp": f"2024-01-{i%30+1:02d}"} for i in range(1000)]
    mock_context.get_data = Mock(return_value=large_data)

    result = asyncio.run(load_data_tool(
        data_id="test:v1:continuous",
        max_records=100,
        context=mock_context
    ))

    # 验证首部数据
    first_id = result['data'][0]['id']
    print(f"  首部数据ID: {first_id}")
    assert first_id == 0, "首部数据ID应为0"

    # 验证尾部数据
    last_id = result['data'][-1]['id']
    print(f"  尾部数据ID: {last_id}")
    assert last_id == 999, "尾部数据ID应为999"
    print("  [PASS] 测试通过")

    print("\n" + "="*60)
    print("[PASS] 所有测试通过！")
    print("="*60)


if __name__ == "__main__":
    try:
        test_smart_sampling_algorithm()
    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
