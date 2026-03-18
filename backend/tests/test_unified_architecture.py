"""
Test Unified Architecture: Input Adapter + Context-Aware V2

验证统一架构实现:
1. Input Adapter 正确映射参数
2. Context-Aware V2 工具通过 ExecutionContext 加载数据
3. 旧包装器不再拦截 V2 工具
4. PMF/OBM 工具成功执行
5. 结果正确序列化 (无 Pydantic 对象)
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.agent.input_adapter import InputAdapterEngine, InputValidationError
from app.agent.core.memory_tools_handler import MemoryToolsHandler
from app.agent.context.execution_context import ExecutionContext
from app.schemas.vocs import UnifiedVOCsData


class TestInputAdapterRules:
    """测试 Input Adapter 规则配置"""

    def setup_method(self):
        self.adapter = InputAdapterEngine()

    def test_pmf_tool_has_rules(self):
        """验证 PMF 工具有 Input Adapter 规则"""
        assert "calculate_pmf" in self.adapter.tool_rules

        pmf_rule = self.adapter.tool_rules["calculate_pmf"]
        assert "station_name" in pmf_rule["required_fields"]
        assert "data_id" in pmf_rule["required_fields"]
        assert "pollutant_type" in pmf_rule["required_fields"]

    def test_obm_tool_has_rules(self):
        """验证 OBM 工具有 Input Adapter 规则"""
        assert "calculate_obm_ofp" in self.adapter.tool_rules

        obm_rule = self.adapter.tool_rules["calculate_obm_ofp"]
        assert "station_name" in obm_rule["required_fields"]
        assert "vocs_data_id" in obm_rule["required_fields"]

    def test_pmf_field_mapping(self):
        """测试 PMF 参数映射: component_data -> data_id"""
        raw_args = {
            "station_name": "深圳南山",
            "component_data": "vocs:v1:abc123",  # 旧参数名
            "pollutant_type": "VOCs"
        }

        normalized_args, report = self.adapter.normalize("calculate_pmf", raw_args)

        # 验证参数被映射
        assert "data_id" in normalized_args
        assert normalized_args["data_id"] == "vocs:v1:abc123"
        assert "component_data" not in normalized_args  # 旧参数被移除

        # 验证报告记录映射
        assert any(
            correction["type"] == "field_mapping" and correction["to"] == "data_id"
            for correction in report["corrections"]
        )

    def test_pmf_data_ref_mapping(self):
        """测试 PMF 参数映射: data_ref -> data_id"""
        raw_args = {
            "station_name": "广州天河",
            "data_ref": "particulate:v1:def456",
            "pollutant_type": "PM2.5"
        }

        normalized_args, report = self.adapter.normalize("calculate_pmf", raw_args)

        assert "data_id" in normalized_args
        assert normalized_args["data_id"] == "particulate:v1:def456"

    def test_obm_field_mapping(self):
        """测试 OBM 参数映射: data_id -> vocs_data_id"""
        raw_args = {
            "station_name": "深圳莲花山",
            "data_id": "vocs_unified:v1:xyz789"  # LLM 可能用 data_id
        }

        normalized_args, report = self.adapter.normalize("calculate_obm_ofp", raw_args)

        # 验证参数被映射到正确字段
        assert "vocs_data_id" in normalized_args
        assert normalized_args["vocs_data_id"] == "vocs_unified:v1:xyz789"
        assert "data_id" not in normalized_args

    def test_obm_component_data_mapping(self):
        """测试 OBM 参数映射: component_data -> vocs_data_id"""
        raw_args = {
            "station_name": "深圳莲花山",
            "component_data": "vocs_unified:v1:aaa111"
        }

        normalized_args, report = self.adapter.normalize("calculate_obm_ofp", raw_args)

        assert "vocs_data_id" in normalized_args
        assert normalized_args["vocs_data_id"] == "vocs_unified:v1:aaa111"

    def test_pmf_missing_required_fields(self):
        """测试 PMF 必需字段验证"""
        raw_args = {
            "station_name": "深圳南山"
            # 缺少 data_id 和 pollutant_type
        }

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize("calculate_pmf", raw_args)

        error = exc_info.value
        assert "data_id" in error.missing_fields
        assert "pollutant_type" in error.missing_fields

    def test_obm_missing_required_fields(self):
        """测试 OBM 必需字段验证"""
        raw_args = {
            "station_name": "深圳莲花山"
            # 缺少 vocs_data_id
        }

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize("calculate_obm_ofp", raw_args)

        error = exc_info.value
        assert "vocs_data_id" in error.missing_fields


class TestMemoryToolsHandlerUnified:
    """测试旧包装器不再拦截 Context-Aware V2 工具"""

    def setup_method(self):
        self.mock_memory = Mock()
        self.mock_executor = Mock()
        self.mock_executor.tool_registry = {}

        # Mock register_tool 方法
        def mock_register_tool(name, func):
            self.mock_executor.tool_registry[name] = func

        self.mock_executor.register_tool = Mock(side_effect=mock_register_tool)

        self.handler = MemoryToolsHandler(self.mock_memory, self.mock_executor)

    def test_no_wrapper_calls_for_v2_tools(self):
        """验证旧包装器不再包装 V2 工具"""
        # 调用 register_memory_tools（不再注册任何工具）
        self.handler.register_memory_tools()

        # 验证 tool_registry 中没有旧的工具
        assert "load_data_from_memory" not in self.mock_executor.tool_registry

        # PMF 和 OBM 不应该被包装
        # (它们由 global_tool_registry 单独注册)

    def test_wrap_analysis_tool_removed(self):
        """✅ 验证 wrap_analysis_tool 方法已完全移除 - 统一架构完成"""
        # 验证 wrap_analysis_tool 方法不再存在
        assert not hasattr(self.handler, "wrap_analysis_tool")
        assert not hasattr(self.handler, "resolve_component_dataset")
        assert not hasattr(self.handler, "_latest_data_ref")
        assert not hasattr(self.handler, "_extract_data_ref")
        assert not hasattr(self.handler, "_extract_registry_id")

        # 验证只有必要的方法存在
        assert hasattr(self.handler, "register_memory_tools")
        assert hasattr(self.handler, "__init__")

        # ✅ 统一架构已完全实施，不再需要旧包装器


class TestContextAwareV2ToolExecution:
    """测试 Context-Aware V2 工具执行流程"""

    @pytest.fixture
    def mock_context(self):
        """创建 mock ExecutionContext"""
        context = Mock(spec=ExecutionContext)
        context.session_id = "test_session_123"
        return context

    @pytest.fixture
    def sample_vocs_data(self):
        """创建示例 VOCs 数据"""
        return [
            UnifiedVOCsData(
                station_code="SZ001",
                station_name="深圳南山",
                timestamp="2025-11-04 00:00:00",
                unit="ppb",
                species_data={
                    "乙烯": 12.5,
                    "丙烯": 8.3,
                    "苯": 5.2,
                    "甲苯": 3.8
                }
            ),
            UnifiedVOCsData(
                station_code="SZ001",
                station_name="深圳南山",
                timestamp="2025-11-04 01:00:00",
                unit="ppb",
                species_data={
                    "乙烯": 11.2,
                    "丙烯": 7.9,
                    "苯": 4.8,
                    "甲苯": 3.5
                }
            )
        ]

    @pytest.mark.asyncio
    async def test_pmf_tool_loads_data_via_context(self, mock_context):
        """测试 PMF 工具通过 ExecutionContext 加载数据"""
        from app.tools.analysis.calculate_pmf.tool import CalculatePMFTool

        # 生成足够的数据样本 (25条记录) - PMF需要至少20个样本
        sample_vocs_data = []
        for i in range(25):
            sample_vocs_data.append(
                UnifiedVOCsData(
                    station_code="SZ001",
                    station_name="深圳南山",
                    timestamp=f"2025-11-04 {i % 24:02d}:00:00",
                    unit="ppb",
                    species_data={
                        "乙烯": 12.5 + i * 0.1,
                        "丙烯": 8.3 + i * 0.05,
                        "苯": 5.2 + i * 0.02,
                        "甲苯": 3.8 + i * 0.01
                    }
                )
            )

        # 创建 mock handle
        mock_handle = Mock()
        mock_handle.is_compatible_with.return_value = True
        mock_handle.record_count = len(sample_vocs_data)
        mock_handle.schema = "vocs_unified"
        mock_handle.validate_for_pmf.return_value = (True, None)
        mock_handle.has_required_fields.return_value = (True, [])
        mock_handle.get_available_fields.return_value = ["乙烯", "丙烯", "苯", "甲苯"]

        # 配置 mock context
        mock_context.get_handle.return_value = mock_handle
        mock_context.get_data.return_value = sample_vocs_data
        mock_context.save_data.return_value = "pmf_result:v1:test123"

        # 执行 PMF 工具
        tool = CalculatePMFTool()
        result = await tool.execute(
            context=mock_context,
            station_name="深圳南山",
            data_id="vocs_unified:v1:abc123",
            pollutant_type="VOCs"
        )

        # 验证调用
        mock_context.get_handle.assert_called_once_with("vocs_unified:v1:abc123")
        mock_context.get_data.assert_called_once_with("vocs_unified:v1:abc123", expected_schema="vocs_unified")

        # 验证结果格式
        assert result["success"] is True
        assert "data" in result
        assert "sources" in result["data"]
        assert "source_contributions" in result["data"]

        # 验证 UDF v1.0 合规性: sources 必须是字典列表
        assert isinstance(result["data"]["sources"], list)
        if result["data"]["sources"]:
            first_source = result["data"]["sources"][0]
            assert isinstance(first_source, dict)
            assert not hasattr(first_source, "model_dump")  # 不是 Pydantic 对象

    @pytest.mark.asyncio
    async def test_obm_tool_loads_data_via_context(self, mock_context, sample_vocs_data):
        """测试 OBM 工具通过 ExecutionContext 加载数据"""
        from app.tools.analysis.calculate_obm_ofp.tool_v2_context import CalculateOBMOFPTool

        # 创建 mock handle
        mock_vocs_handle = Mock()
        mock_vocs_handle.is_compatible_with.return_value = True
        mock_vocs_handle.record_count = len(sample_vocs_data)
        mock_vocs_handle.schema = "vocs_unified"
        mock_vocs_handle.get_available_fields.return_value = ["乙烯", "丙烯", "苯", "甲苯"]

        # 配置 mock context
        mock_context.get_handle.return_value = mock_vocs_handle
        mock_context.get_data.return_value = sample_vocs_data
        mock_context.save_data.return_value = "obm_result:v1:test456"

        # 执行 OBM 工具
        tool = CalculateOBMOFPTool()
        result = await tool.execute(
            context=mock_context,
            station_name="深圳莲花山",
            vocs_data_id="vocs_unified:v1:xyz789"
        )

        # 验证调用
        mock_context.get_handle.assert_called_with("vocs_unified:v1:xyz789")
        mock_context.get_data.assert_called()

        # 验证结果格式
        assert result["success"] is True
        assert "data" in result
        assert "species_ofp" in result["data"]
        assert "sensitivity" in result["data"]


class TestEndToEndUnifiedArchitecture:
    """端到端测试: Input Adapter + Context-Aware V2"""

    @pytest.mark.asyncio
    async def test_pmf_with_wrong_param_name(self):
        """测试 LLM 使用错误参数名, Input Adapter 自动修正"""
        # Step 1: Input Adapter 规范化参数
        adapter = InputAdapterEngine()
        raw_args = {
            "station_name": "深圳南山",
            "component_data": "vocs:v1:abc123",  # 错误参数名
            "pollutant_type": "VOCs"
        }

        normalized_args, report = adapter.normalize("calculate_pmf", raw_args)

        # 验证参数被修正
        assert "data_id" in normalized_args
        assert normalized_args["data_id"] == "vocs:v1:abc123"

        # Step 2: Context-Aware V2 工具接收修正后的参数
        from app.tools.analysis.calculate_pmf.tool import CalculatePMFTool

        mock_context = Mock(spec=ExecutionContext)
        mock_handle = Mock()
        mock_handle.is_compatible_with.return_value = True
        mock_handle.schema = "vocs"
        mock_handle.record_count = 25
        mock_handle.validate_for_pmf.return_value = (True, None)
        mock_handle.has_required_fields.return_value = (True, [])
        mock_handle.get_available_fields.return_value = ["乙烯", "丙烯"]

        mock_context.get_handle.return_value = mock_handle
        mock_context.get_data.return_value = []  # 简化测试
        mock_context.save_data.return_value = "pmf_result:v1:test"
        mock_context.session_id = "test_session"

        tool = CalculatePMFTool()

        # 使用修正后的参数执行
        result = await tool.execute(
            context=mock_context,
            **normalized_args  # 使用 Input Adapter 输出
        )

        # 验证工具接收到正确参数
        assert mock_context.get_handle.called
        assert mock_context.get_handle.call_args[0][0] == "vocs:v1:abc123"

    @pytest.mark.asyncio
    async def test_obm_with_wrong_param_name(self):
        """测试 OBM 工具参数映射"""
        # Step 1: Input Adapter 规范化参数
        adapter = InputAdapterEngine()
        raw_args = {
            "station_name": "深圳莲花山",
            "data_id": "vocs_unified:v1:xyz789"  # LLM 使用 data_id
        }

        normalized_args, report = adapter.normalize("calculate_obm_ofp", raw_args)

        # 验证映射到正确字段
        assert "vocs_data_id" in normalized_args
        assert normalized_args["vocs_data_id"] == "vocs_unified:v1:xyz789"

        # Step 2: 工具执行
        from app.tools.analysis.calculate_obm_ofp.tool_v2_context import CalculateOBMOFPTool

        mock_context = Mock(spec=ExecutionContext)
        mock_handle = Mock()
        mock_handle.is_compatible_with.return_value = True
        mock_handle.schema = "vocs_unified"
        mock_handle.record_count = 30
        mock_handle.get_available_fields.return_value = ["乙烯", "丙烯"]

        mock_context.get_handle.return_value = mock_handle
        mock_context.get_data.return_value = []
        mock_context.save_data.return_value = "obm_result:v1:test"
        mock_context.session_id = "test_session"

        tool = CalculateOBMOFPTool()
        result = await tool.execute(
            context=mock_context,
            **normalized_args
        )

        # 验证正确的参数传递
        assert mock_context.get_handle.called


class TestResultSerialization:
    """测试结果序列化 (UDF v1.0 合规性)"""

    @pytest.mark.asyncio
    async def test_pmf_result_is_json_serializable(self):
        """验证 PMF 结果可以 JSON 序列化"""
        from app.tools.analysis.calculate_pmf.calculator import PMFCalculator

        # 创建足够的测试数据 (25条记录) - PMF需要至少20个样本
        component_data = []
        for i in range(25):
            component_data.append({
                "time": f"2025-11-04 {i % 24:02d}:00:00",
                "乙烯": 12.5 + i * 0.1,
                "丙烯": 8.3 + i * 0.05,
                "苯": 5.2 + i * 0.02,
                "甲苯": 3.8 + i * 0.01
            })

        calculator = PMFCalculator(pollutant_type="VOCs")
        result = calculator.calculate(component_data, pollutant="VOCs")

        # 验证可以 JSON 序列化
        try:
            json_str = json.dumps(result, ensure_ascii=False)
            assert isinstance(json_str, str)
        except TypeError as e:
            pytest.fail(f"PMF result is not JSON serializable: {e}")

        # 验证 sources 是字典列表
        if "sources" in result:
            assert isinstance(result["sources"], list)
            if result["sources"]:
                assert isinstance(result["sources"][0], dict)

        # 验证 timeseries 是字典列表
        if "timeseries" in result:
            assert isinstance(result["timeseries"], list)
            if result["timeseries"]:
                assert isinstance(result["timeseries"][0], dict)


def test_architecture_documentation_exists():
    """验证架构文档存在于代码中"""
    with open("D:/溯源/backend/app/agent/core/memory_tools_handler.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 验证统一架构文档
    assert "统一架构" in content
    assert "Context-Aware V2" in content
    assert "不再需要旧包装器" in content
    assert "已完全移除" in content
