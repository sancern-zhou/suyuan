"""
测试两阶段工具加载流程

测试场景：
1. LLM输出 args: null 触发第二阶段加载
2. 上下文精简功能验证
3. 参数构造prompt生成验证
4. 完整流程集成测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from app.agent.core.planner import LLMPlanner


class TestTwoStageLoading:
    """两阶段工具加载测试"""

    @pytest.fixture
    def planner(self):
        """创建LLMPlanner实例"""
        # Mock初始化以避免需要API key
        with patch('app.agent.core.planner.LLMPlanner._initialize_client'):
            return LLMPlanner()

    @pytest.fixture
    def mock_context(self):
        """模拟历史上下文"""
        return """
## 迭代 1
用户查询: 查询广州昨日空气质量
Thought: 需要调用get_air_quality工具
Action: TOOL_CALL - get_air_quality
Observation: 成功获取数据，data_id: air_quality_001

## 迭代 2
用户查询: 分析PM2.5来源
Thought: 需要调用calculate_pm_pmf工具
Action: TOOL_CALL - calculate_pm_pmf
"""

    def test_extract_relevant_context(self, planner, mock_context):
        """测试上下文精简功能"""
        simplified = planner._extract_relevant_context(
            full_context=mock_context,
            tool_name="calculate_pm_pmf",
            query="分析PM2.5来源"
        )

        # 验证精简后的上下文包含关键信息
        assert "用户查询" in simplified
        assert "分析PM2.5来源" in simplified
        assert "data_id" in simplified or "air_quality_001" in simplified
        assert len(simplified) < len(mock_context)

        print(f"\n原始上下文长度: {len(mock_context)}")
        print(f"精简后长度: {len(simplified)}")
        print(f"压缩比: {len(simplified)/len(mock_context)*100:.1f}%")

    def test_build_param_construction_prompt(self, planner):
        """测试参数构造prompt生成"""
        schema = {
            "name": "get_air_quality",
            "description": "获取空气质量数据",
            "parameters": {
                "question": {"type": "string", "required": True}
            }
        }

        prompt = planner._build_param_construction_prompt(
            tool_name="get_air_quality",
            schema=schema,
            query="查询广州昨日空气质量",
            simplified_context="## 用户查询\n查询广州昨日空气质量",
            thought="需要调用get_air_quality工具",
            reasoning="用户明确要求查询空气质量数据"
        )

        # 验证prompt包含必要信息
        assert "get_air_quality" in prompt
        assert "查询广州昨日空气质量" in prompt
        assert "parameters" in prompt or "参数" in prompt
        assert "JSON" in prompt

        print(f"\n生成的prompt长度: {len(prompt)}")
        print(f"Prompt预览:\n{prompt[:500]}...")

    @pytest.mark.asyncio
    async def test_load_schema_and_construct_params(self, planner, mock_context):
        """测试完整的第二阶段加载流程"""
        # Mock依赖
        with patch('app.agent.tool_adapter.get_detailed_schemas_for_tools') as mock_get_schemas, \
             patch('app.services.llm_service.llm_service.call_llm_with_messages', new_callable=AsyncMock) as mock_llm:

            # 设置mock返回值
            mock_get_schemas.return_value = [{
                "name": "get_air_quality",
                "description": "获取空气质量数据",
                "parameters": {
                    "question": {"type": "string", "required": True}
                }
            }]

            mock_llm.return_value = {
                "data": {
                    "args": {
                        "question": "查询广州昨日空气质量"
                    }
                }
            }

            # 调用方法
            args = await planner._load_schema_and_construct_params(
                tool_name="get_air_quality",
                query="查询广州昨日空气质量",
                context=mock_context,
                thought="需要调用get_air_quality工具",
                reasoning="用户明确要求查询空气质量数据"
            )

            # 验证结果
            assert args is not None
            assert isinstance(args, dict)
            assert "question" in args
            assert args["question"] == "查询广州昨日空气质量"

            # 验证调用
            mock_get_schemas.assert_called_once_with(["get_air_quality"])
            mock_llm.assert_called_once()

            print(f"\n成功构造参数: {args}")

    @pytest.mark.asyncio
    async def test_load_schema_error_handling(self, planner, mock_context):
        """测试schema加载失败的错误处理"""
        with patch('app.agent.tool_adapter.get_detailed_schemas_for_tools') as mock_get_schemas:
            # 模拟找不到schema
            mock_get_schemas.return_value = []

            # 验证抛出异常
            with pytest.raises(ValueError, match="无法找到工具"):
                await planner._load_schema_and_construct_params(
                    tool_name="non_existent_tool",
                    query="测试查询",
                    context=mock_context,
                    thought="测试思考",
                    reasoning="测试推理"
                )

            print("\n错误处理测试通过：正确抛出ValueError")

    def test_context_compression_ratio(self, planner):
        """测试上下文压缩比"""
        # 创建一个较大的上下文
        large_context = "\n".join([
            f"## 迭代 {i}\n用户查询: 测试查询{i}\nObservation: 测试结果{i}\ndata_id: test_{i}"
            for i in range(10)
        ])

        simplified = planner._extract_relevant_context(
            full_context=large_context,
            tool_name="test_tool",
            query="测试查询"
        )

        compression_ratio = len(simplified) / len(large_context) * 100

        print(f"\n上下文压缩测试:")
        print(f"原始长度: {len(large_context)} 字符")
        print(f"精简后长度: {len(simplified)} 字符")
        print(f"压缩比: {compression_ratio:.1f}%")

        # 验证压缩效果（应该小于80%，对于真实长上下文会更低）
        assert compression_ratio < 80, f"压缩比过高: {compression_ratio:.1f}%"


if __name__ == "__main__":
    print("运行两阶段工具加载测试...")
    pytest.main([__file__, "-v", "-s"])

