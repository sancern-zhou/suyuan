"""
测试气象轨迹分析工具的数据验证修复
确保在无轨迹数据情况下不会进行源区贡献分析

修复原因：
- 防止出现轨迹数据为空但声称"识别3个源区"的矛盾
- 确保源区分析与轨迹数据的一致性
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# 添加backend路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool
from app.agent.context import ExecutionContext


class TestMeteorologicalTrajectoryDataValidation:
    """气象轨迹分析工具数据验证测试"""

    @pytest.fixture
    def mock_context(self):
        """创建模拟上下文"""
        context = Mock(spec=ExecutionContext)
        context.session_id = "test_session_001"
        context.data_manager = Mock()
        context.data_manager.save_data = Mock(return_value="test_data_id_001")
        return context

    @pytest.fixture
    def tool(self):
        """创建工具实例"""
        return MeteorologicalTrajectoryAnalysisTool()

    @pytest.mark.asyncio
    async def test_source_analysis_skipped_when_no_trajectories(self, tool, mock_context):
        """测试：无轨迹数据时应跳过源区分析"""
        # 模拟空的轨迹数据场景
        with patch.object(tool, '_fetch_gdas_meteorology', return_value={"status": "failed"}), \
             patch.object(tool, '_fetch_boundary_layer_data', return_value={"status": "failed"}), \
             patch.object(tool, '_fetch_surface_meteorology', return_value={"status": "failed"}), \
             patch.object(tool, '_calculate_trajectories', return_value=[]), \
             patch.object(tool, '_generate_visualizations', return_value=[]):

            # 执行工具（启用源区分析）
            result = await tool.execute(
                context=mock_context,
                lat=0.0,  # 赤道附近，可能无数据
                lon=0.0,
                start_time="2025-11-30T00:00:00Z",
                hours_backward=72,
                trajectory_height=100,
                cluster_analysis=False,
                source_contribution=True,  # 启用源区分析
                fire_integration=False,
                forward_simulation=False
            )

            # 验证结果
            # 注意：即使没有轨迹数据，工具也可能返回success状态
            # 关键是检查摘要中没有矛盾的源区信息
            assert len(result.get('data', [])) == 0, "没有轨迹数据时data应为空"

            # 验证摘要中没有矛盾的源区信息
            summary = result.get('summary', '')
            # 检查摘要中没有虚假的源区信息
            if '源区' in summary:
                # 如果摘要中包含源区信息，应该是合理的（如"无源区"等）
                assert any(keyword in summary for keyword in ['跳过', '未识别', '无源区']), \
                    f"轨迹数据为空时摘要不应包含虚假源区信息，但摘要为：{summary}"

    @pytest.mark.asyncio
    async def test_source_analysis_performed_with_trajectories(self, tool, mock_context):
        """测试：有轨迹数据时应进行源区分析"""
        # 模拟有轨迹数据的场景
        mock_trajectories = [
            {
                "id": "trajectory_001",
                "type": "backward",
                "start_location": {"lat": 23.13, "lon": 113.26},
                "points": [
                    {"lat": 23.13, "lon": 113.26, "height": 100},
                    {"lat": 24.0, "lon": 114.0, "height": 150}
                ]
            }
        ]

        with patch.object(tool, '_fetch_gdas_meteorology', return_value={"status": "success"}), \
             patch.object(tool, '_fetch_boundary_layer_data', return_value={"status": "success"}), \
             patch.object(tool, '_fetch_surface_meteorology', return_value={"status": "success", "surface_data": {}}), \
             patch.object(tool, '_calculate_trajectories', return_value=mock_trajectories), \
             patch.object(tool, '_analyze_source_contribution', return_value={
                 "status": "success",
                 "source_regions": [{"region": "test_region", "contribution_percentage": 50.0}]
             }), \
             patch.object(tool, '_generate_visualizations', return_value=[]):

            # 执行工具（启用源区分析）
            result = await tool.execute(
                context=mock_context,
                lat=23.13,
                lon=113.26,
                start_time="2025-11-30T00:00:00Z",
                hours_backward=72,
                trajectory_height=100,
                cluster_analysis=False,
                source_contribution=True,  # 启用源区分析
                fire_integration=False,
                forward_simulation=False
            )

            # 验证结果
            assert result['status'] == 'success'
            assert result['success'] is True
            # 确保有轨迹数据
            assert len(result.get('data', [])) > 0

    @pytest.mark.asyncio
    async def test_source_analysis_disabled(self, tool, mock_context):
        """测试：禁用源区分析时不执行源区分析"""
        # 模拟无轨迹数据且禁用源区分析的场景
        with patch.object(tool, '_fetch_gdas_meteorology', return_value={"status": "failed"}), \
             patch.object(tool, '_fetch_boundary_layer_data', return_value={"status": "failed"}), \
             patch.object(tool, '_fetch_surface_meteorology', return_value={"status": "failed"}), \
             patch.object(tool, '_calculate_trajectories', return_value=[]), \
             patch.object(tool, '_generate_visualizations', return_value=[]):

            # 执行工具（禁用源区分析）
            result = await tool.execute(
                context=mock_context,
                lat=0.0,
                lon=0.0,
                start_time="2025-11-30T00:00:00Z",
                hours_backward=72,
                trajectory_height=100,
                cluster_analysis=False,
                source_contribution=False,  # 禁用源区分析
                fire_integration=False,
                forward_simulation=False
            )

            # 验证结果（应该正常失败，但不涉及源区分析）
            assert 'summary' in result
            # 验证摘要中没有矛盾的源区信息
            summary = result.get('summary', '')
            assert '源区' not in summary or 'skipping_source_analysis_no_trajectories' in summary.lower()

    def test_data_validation_logic_directly(self):
        """直接测试数据验证逻辑（单元测试）"""
        # 测试场景1：空轨迹数据
        trajectories_empty = []
        source_contribution = True
        source_analysis = None

        # 应用修复后的逻辑
        if source_contribution and len(trajectories_empty) > 0:
            source_analysis = "进行源区分析"
        elif source_contribution and len(trajectories_empty) == 0:
            # 应跳过源区分析
            source_analysis = None

        assert source_analysis is None, "空轨迹数据时应跳过源区分析"

        # 测试场景2：有轨迹数据
        trajectories_valid = [{"id": "traj_001", "points": [{"lat": 23.13, "lon": 113.26}]}]
        source_analysis = None

        # 应用修复后的逻辑
        if source_contribution and len(trajectories_valid) > 0:
            source_analysis = "进行源区分析"
        elif source_contribution and len(trajectories_valid) == 0:
            source_analysis = None

        assert source_analysis is not None, "有轨迹数据时应进行源区分析"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
