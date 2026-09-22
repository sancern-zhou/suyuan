"""
测试工作流工具

验证工作流工具的基本功能：
1. 工作流工具基类功能
2. 各个工作流工具的execute方法
3. 返回格式符合UDF v2.0标准
"""

import pytest
import asyncio
from datetime import datetime

from app.tools.workflow.workflow_tool import WorkflowTool, WorkflowStatus
from app.tools.workflow.quick_trace_workflow import QuickTraceWorkflow
from app.tools.workflow.standard_analysis_workflow import StandardAnalysisWorkflow
from app.tools.workflow.deep_trace_workflow import DeepTraceWorkflow
from app.tools.workflow.knowledge_qa_workflow import KnowledgeQAWorkflow


class TestWorkflowToolBase:
    """测试工作流工具基类"""

    def test_workflow_status_enum(self):
        """测试WorkflowStatus枚举"""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.PARTIAL.value == "partial"

    def test_workflow_tool_base_class(self):
        """测试WorkflowTool基类不能直接实例化"""
        with pytest.raises(TypeError):
            WorkflowTool()


class TestQuickTraceWorkflow:
    """测试快速溯源工作流"""

    @pytest.fixture
    def workflow(self):
        return QuickTraceWorkflow()

    def test_workflow_properties(self, workflow):
        """测试工作流属性"""
        assert workflow.name == "quick_trace_workflow"
        assert workflow.version == "1.0.0"
        assert workflow.category == "quick_trace"
        assert workflow.requires_context is False
        assert len(workflow.description) > 0

    def test_get_function_schema(self, workflow):
        """测试get_function_schema方法"""
        schema = workflow.get_function_schema()

        assert schema["name"] == "quick_trace_workflow"
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"
        assert "properties" in schema["parameters"]
        assert "required" in schema["parameters"]

        # 验证必需参数
        required = schema["parameters"]["required"]
        assert "city" in required
        assert "alert_time" in required
        assert "pollutant" in required
        assert "alert_value" in required

    def test_record_step(self, workflow):
        """测试步骤记录"""
        workflow._record_step("test_step", "success", {"test": "data"})

        steps = workflow.get_executed_steps()
        assert len(steps) == 1
        assert steps[0]["step"] == "test_step"
        assert steps[0]["status"] == "success"
        assert steps[0]["data"]["test"] == "data"

    def test_timer(self, workflow):
        """测试计时器"""
        workflow._start_timer()
        assert workflow._start_time is not None

        elapsed = workflow._get_elapsed_ms()
        assert elapsed is not None
        assert elapsed >= 0

    def test_execution_summary(self, workflow):
        """测试执行摘要"""
        workflow._record_step("step1", "success")
        workflow._record_step("step2", "failed")
        workflow._start_timer()

        summary = workflow.get_execution_summary()
        assert summary["workflow"] == "quick_trace_workflow"
        assert summary["total_steps"] == 2
        assert summary["success_steps"] == 1
        assert summary["failed_steps"] == 1
        assert summary["execution_time_ms"] is not None


class TestStandardAnalysisWorkflow:
    """测试标准分析工作流"""

    @pytest.fixture
    def workflow(self):
        return StandardAnalysisWorkflow()

    def test_workflow_properties(self, workflow):
        """测试工作流属性"""
        assert workflow.name == "standard_analysis_workflow"
        assert workflow.version == "1.0.0"
        assert workflow.category == "standard_analysis"
        assert workflow.requires_context is False

    def test_get_function_schema(self, workflow):
        """测试get_function_schema方法"""
        schema = workflow.get_function_schema()

        assert schema["name"] == "standard_analysis_workflow"
        assert "user_query" in schema["parameters"]["required"]
        assert "precision" in schema["parameters"]["properties"]
        assert "session_id" in schema["parameters"]["properties"]


class TestDeepTraceWorkflow:
    """测试深度溯源工作流"""

    @pytest.fixture
    def workflow(self):
        return DeepTraceWorkflow()

    def test_workflow_properties(self, workflow):
        """测试工作流属性"""
        assert workflow.name == "deep_trace_workflow"
        assert workflow.version == "1.0.0"
        assert workflow.category == "deep_trace"
        assert workflow.requires_context is True  # 需要ExecutionContext

    def test_get_function_schema(self, workflow):
        """测试get_function_schema方法"""
        schema = workflow.get_function_schema()

        assert schema["name"] == "deep_trace_workflow"
        required = schema["parameters"]["required"]
        assert "city" in required
        assert "pollutant" in required
        assert "start_time" in required
        assert "end_time" in required


class TestKnowledgeQAWorkflow:
    """测试知识问答工作流"""

    @pytest.fixture
    def workflow(self):
        return KnowledgeQAWorkflow()

    def test_workflow_properties(self, workflow):
        """测试工作流属性"""
        assert workflow.name == "knowledge_qa_workflow"
        assert workflow.version == "1.0.0"
        assert workflow.category == "knowledge_qa"
        assert workflow.requires_context is False

    def test_get_function_schema(self, workflow):
        """测试get_function_schema方法"""
        schema = workflow.get_function_schema()

        assert schema["name"] == "knowledge_qa_workflow"
        assert "query" in schema["parameters"]["required"]
        assert "top_k" in schema["parameters"]["properties"]


class TestWorkflowToolsRegistry:
    """测试工作流工具注册表"""

    def test_workflow_tools_registry(self):
        """测试工作流工具注册表"""
        from app.tools.workflow import WORKFLOW_TOOLS_REGISTRY, list_workflow_tools

        # 验证注册表不为空
        assert len(WORKFLOW_TOOLS_REGISTRY) > 0

        # 验证工具列表
        tool_names = list_workflow_tools()
        assert len(tool_names) > 0

        # 验证必需的工具存在
        expected_tools = [
            "quick_trace_workflow",
            "standard_analysis_workflow",
            "deep_trace_workflow",
            "knowledge_qa_workflow"
        ]

        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Missing tool: {tool_name}"

    def test_get_workflow_tool(self):
        """测试获取工作流工具实例"""
        from app.tools.workflow import get_workflow_tool

        # 测试获取快速溯源工作流
        workflow = get_workflow_tool("quick_trace_workflow")
        assert workflow is not None
        assert workflow.name == "quick_trace_workflow"

        # 测试获取不存在的工作流
        with pytest.raises(ValueError):
            get_workflow_tool("non_existent_workflow")


class TestUDFV2Format:
    """测试UDF v2.0格式"""

    def test_build_udf_v2_result(self):
        """测试构建标准UDF v2.0格式结果"""
        workflow = QuickTraceWorkflow()

        result = workflow._build_udf_v2_result(
            status="success",
            success=True,
            data={"test": "data"},
            visuals=[{"id": "test"}],
            summary="Test summary"
        )

        # 验证必需字段
        assert "status" in result
        assert "success" in result
        assert "data" in result
        assert "visuals" in result
        assert "metadata" in result
        assert "summary" in result

        # 验证metadata格式
        assert result["metadata"]["schema_version"] == "v2.0"
        assert result["metadata"]["generator"] == "quick_trace_workflow"
        assert "execution_steps" in result["metadata"]
        assert "execution_time_ms" in result["metadata"]


@pytest.mark.integration
class TestWorkflowIntegration:
    """集成测试：工作流工具与ReAct Agent集成"""

    def test_workflow_tools_in_global_registry(self):
        """测试工作流工具已注册到全局工具注册表"""
        from app.tools import global_tool_registry

        # 检查快速溯源工作流
        quick_trace_tool = global_tool_registry.get_tool("quick_trace_workflow")
        assert quick_trace_tool is not None

        # 检查深度溯源工作流
        deep_trace_tool = global_tool_registry.get_tool("deep_trace_workflow")
        assert deep_trace_tool is not None

        # 检查知识问答工作流
        knowledge_qa_tool = global_tool_registry.get_tool("knowledge_qa_workflow")
        assert knowledge_qa_tool is not None

    def test_react_agent_initialization(self):
        """测试ReActAgent初始化时正确注册工作流工具"""
        from app.agent.react_agent import create_react_agent

        # 创建ReAct Agent
        agent = create_react_agent()

        # 验证工具列表包含工作流工具
        available_tools = agent.get_available_tools()
        assert "quick_trace_workflow" in available_tools
        assert "deep_trace_workflow" in available_tools
        assert "knowledge_qa_workflow" in available_tools


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
