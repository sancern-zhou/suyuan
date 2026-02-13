"""
测试 load_data_from_memory 的智能采样功能

验证：
1. 小数据集（<= max_records）不采样
2. 大数据集（> max_records）智能采样
3. 采样策略：首尾30% + 中间40%
4. 元数据正确记录采样信息
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock


class TestLoadDataSampling:
    """测试数据加载的智能采样功能"""

    def test_small_data_no_sampling(self):
        """测试小数据集不采样"""
        # 导入工具适配器
        from app.agent.tool_adapter import get_react_agent_tool_registry

        # 创建工具注册表
        tool_registry = get_react_agent_tool_registry()
        load_data_tool = tool_registry["load_data_from_memory"]

        # 模拟上下文
        mock_context = Mock()
        small_data = [
            {"id": i, "value": f"record_{i}"}
            for i in range(10)  # 10条记录 < max_records(100)
        ]
        mock_context.get_data = Mock(return_value=small_data)

        # 调用工具
        import asyncio
        result = asyncio.run(load_data_tool(
            data_id="test:v1:abc123",
            max_records=100,
            context=mock_context
        ))

        # 验证
        assert result["success"] is True
        assert result["metadata"]["truncated"] is False
        assert len(result["data"]) == 10
        assert result["metadata"]["original_count"] == 10
        assert result["metadata"]["sampling_info"] is None
        print("[PASS] 小数据集测试通过：不采样")

    def test_large_data_with_sampling(self):
        """测试大数据集智能采样"""
        from app.agent.tool_adapter import get_react_agent_tool_registry

        # 创建工具注册表
        tool_registry = get_react_agent_tool_registry()
        load_data_tool = tool_registry["load_data_from_memory"]

        # 模拟上下文
        mock_context = Mock()
        large_data = [
            {"id": i, "value": f"record_{i}", "timestamp": f"2024-01-{i%30+1:02d}"}
            for i in range(1000)  # 1000条记录 > max_records(100)
        ]
        mock_context.get_data = Mock(return_value=large_data)

        # 调用工具
        import asyncio
        result = asyncio.run(load_data_tool(
            data_id="test:v1:abc123",
            max_records=100,
            context=mock_context
        ))

        # 验证
        assert result["success"] is True
        assert result["metadata"]["truncated"] is True
        assert len(result["data"]) == 100  # 最多返回100条
        assert result["metadata"]["original_count"] == 1000

        # 验证采样信息
        sampling_info = result["metadata"]["sampling_info"]
        assert sampling_info is not None
        assert sampling_info["strategy"] == "head_tail_middle_sampling"
        assert sampling_info["original_count"] == 1000
        assert sampling_info["sampled_count"] == 100
        assert sampling_info["retention_ratio"] == 0.1

        # 验证采样比例：首30 + 尾30 + 中40 = 100
        assert sampling_info["head_samples"] == 30
        assert sampling_info["tail_samples"] == 30
        assert sampling_info["middle_samples"] == 40

        # 验证数据连续性：首部应该是前30条
        assert result["data"][0]["id"] == 0
        assert result["data"][29]["id"] == 29

        # 验证数据连续性：尾部应该是最后30条
        assert result["data"][-1]["id"] == 999
        assert result["data"][-30]["id"] == 970

        print("[PASS] 大数据集测试通过：智能采样")

    def test_custom_max_records(self):
        """测试自定义max_records"""
        from app.agent.tool_adapter import get_react_agent_tool_registry

        # 创建工具注册表
        tool_registry = get_react_agent_tool_registry()
        load_data_tool = tool_registry["load_data_from_memory"]

        # 模拟上下文
        mock_context = Mock()
        large_data = [
            {"id": i, "value": f"record_{i}"}
            for i in range(500)
        ]
        mock_context.get_data = Mock(return_value=large_data)

        # 调用工具，使用自定义max_records=50
        import asyncio
        result = asyncio.run(load_data_tool(
            data_id="test:v1:abc123",
            max_records=50,
            context=mock_context
        ))

        # 验证
        assert result["success"] is True
        assert len(result["data"]) == 50
        assert result["metadata"]["truncated"] is True
        assert result["metadata"]["sampling_info"]["sampled_count"] == 50

        print("[PASS] 自定义max_records测试通过")

    def test_sampling_distribution(self):
        """测试采样分布的合理性"""
        from app.agent.tool_adapter import get_react_agent_tool_registry

        # 创建工具注册表
        tool_registry = get_react_agent_tool_registry()
        load_data_tool = tool_registry["load_data_from_memory"]

        # 模拟上下文（带时间戳的数据）
        mock_context = Mock()
        time_series_data = [
            {
                "id": i,
                "timestamp": f"2024-01-{i//24 + 1:02d} {i%24:02d}:00:00",
                "value": i * 10
            }
            for i in range(720)  # 30天的每小时数据
        ]
        mock_context.get_data = Mock(return_value=time_series_data)

        # 调用工具
        import asyncio
        result = asyncio.run(load_data_tool(
            data_id="timeseries:v1:abc123",
            max_records=100,
            context=mock_context
        ))

        # 验证时间覆盖：应该覆盖整个时间范围
        first_timestamp = result["data"][0]["timestamp"]
        last_timestamp = result["data"][-1]["timestamp"]

        assert "2024-01-01" in first_timestamp
        assert "2024-01-30" in last_timestamp

        print(f"[PASS] 时间覆盖测试通过：{first_timestamp} → {last_timestamp}")

    def test_edge_case_empty_data(self):
        """测试空数据边界情况"""
        from app.agent.tool_adapter import get_react_agent_tool_registry

        # 创建工具注册表
        tool_registry = get_react_agent_tool_registry()
        load_data_tool = tool_registry["load_data_from_memory"]

        # 模拟上下文（空数据）
        mock_context = Mock()
        mock_context.get_data = Mock(return_value=[])

        # 调用工具
        import asyncio
        result = asyncio.run(load_data_tool(
            data_id="empty:v1:abc123",
            max_records=100,
            context=mock_context
        ))

        # 验证
        assert result["success"] is True
        assert len(result["data"]) == 0
        assert result["metadata"]["truncated"] is False

        print("[PASS] 空数据测试通过")

    def test_single_record_data(self):
        """测试单条记录数据"""
        from app.agent.tool_adapter import get_react_agent_tool_registry

        # 创建工具注册表
        tool_registry = get_react_agent_tool_registry()
        load_data_tool = tool_registry["load_data_from_memory"]

        # 模拟上下文（单条记录）
        mock_context = Mock()
        single_data = [{"id": 1, "value": "single_record"}]
        mock_context.get_data = Mock(return_value=single_data)

        # 调用工具
        import asyncio
        result = asyncio.run(load_data_tool(
            data_id="single:v1:abc123",
            max_records=100,
            context=mock_context
        ))

        # 验证
        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["metadata"]["truncated"] is False
        assert result["metadata"]["original_count"] == 1

        print("[PASS] 单条记录测试通过")


if __name__ == "__main__":
    """运行测试"""
    test = TestLoadDataSampling()

    print("=" * 60)
    print("开始测试 load_data_from_memory 智能采样功能")
    print("=" * 60)

    test.test_small_data_no_sampling()
    test.test_large_data_with_sampling()
    test.test_custom_max_records()
    test.test_sampling_distribution()
    test.test_edge_case_empty_data()
    test.test_single_record_data()

    print("=" * 60)
    print("[PASS] 所有测试通过！")
    print("=" * 60)
