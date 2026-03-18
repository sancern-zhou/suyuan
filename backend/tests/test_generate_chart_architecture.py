"""
测试 generate_chart 工具的架构重新设计

验证三个核心功能：
1. 模板兼容性验证 - 缺少必需字段时回退到LLM
2. 模板输出验证 - 空数据/占位符数据时回退到LLM
3. Agent驱动 - 使用Agent LLM显式指定的chart_type_hint

禁止包含emoji表情。
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# 导入被测试的工具
from app.tools.visualization.generate_chart.tool import GenerateChartTool


class TestTemplateCompatibilityValidation:
    """测试模板兼容性验证功能"""

    def setup_method(self):
        """测试前准备"""
        self.tool = GenerateChartTool()
        self.mock_context = Mock()
        self.mock_context.save_data = Mock(return_value="chart_config:test_123")

    def test_wind_rose_missing_required_fields(self):
        """测试1.1: wind_rose缺少wind_speed字段 - 应返回不兼容"""
        data = [
            {"wind_direction": 45, "temperature": 25},
            {"wind_direction": 90, "temperature": 26}
        ]

        result = self.tool._validate_template_compatibility("wind_rose", data)

        print(f"[DEBUG] 返回结果: {result}")
        assert result["compatible"] == False
        assert "wind_speed" in result["reason"]
        assert result["fallback"] == "llm"
        print("[PASS] 测试1.1: wind_rose缺少必需字段正确返回不兼容")

    def test_wind_rose_has_required_fields(self):
        """测试1.2: wind_rose包含所有必需字段 - 应返回兼容"""
        data = [
            {"wind_speed": 3.5, "wind_direction": 45},
            {"wind_speed": 4.2, "wind_direction": 90}
        ]

        result = self.tool._validate_template_compatibility("wind_rose", data)

        assert result["compatible"] == True
        assert "符合模板要求" in result["reason"]
        print("[PASS] 测试1.2: wind_rose包含必需字段正确返回兼容")

    def test_map_missing_latitude(self):
        """测试1.3: map缺少latitude字段 - 应返回不兼容"""
        data = [
            {"longitude": 114.05, "name": "站点A"},
            {"longitude": 114.06, "name": "站点B"}
        ]

        result = self.tool._validate_template_compatibility("map", data)

        assert result["compatible"] == False
        assert "latitude" in result["reason"]
        print("[PASS] 测试1.3: map缺少latitude字段正确返回不兼容")

    def test_profile_altitude_or_height(self):
        """测试1.4: profile字段 - altitude或height任一存在即可"""
        # 测试仅有altitude
        data_altitude = [
            {"altitude": 100, "temperature": 25},
            {"altitude": 200, "temperature": 24}
        ]
        result_altitude = self.tool._validate_template_compatibility("profile", data_altitude)
        assert result_altitude["compatible"] == True

        # 测试仅有height
        data_height = [
            {"height": 100, "temperature": 25},
            {"height": 200, "temperature": 24}
        ]
        result_height = self.tool._validate_template_compatibility("profile", data_height)
        assert result_height["compatible"] == True

        # 测试两者都没有
        data_none = [
            {"temperature": 25},
            {"temperature": 24}
        ]
        result_none = self.tool._validate_template_compatibility("profile", data_none)
        assert result_none["compatible"] == False

        print("[PASS] 测试1.4: profile字段altitude/height任一存在即可")

    def test_pm_analysis_missing_components(self):
        """测试1.5: pm_analysis缺少颗粒物组分 - 应返回不兼容"""
        data = [
            {"PM2.5": 35, "PM10": 50},
            {"PM2.5": 40, "PM10": 55}
        ]

        result = self.tool._validate_template_compatibility("pm_analysis", data)

        assert result["compatible"] == False
        assert "SO4/NO3/NH4/OC/EC" in result["reason"]
        print("[PASS] 测试1.5: pm_analysis缺少颗粒物组分正确返回不兼容")


class TestTemplateOutputValidation:
    """测试模板输出验证功能"""

    def setup_method(self):
        """测试前准备"""
        self.tool = GenerateChartTool()

    def test_pie_chart_empty_data(self):
        """测试2.1: 饼图空数据 - 应返回无效"""
        chart_dict = {
            "id": "test_pie_001",
            "type": "pie",
            "title": "测试饼图",
            "data": []
        }

        result = self.tool._is_valid_chart_output(chart_dict)

        assert result == False
        print("[PASS] 测试2.1: 饼图空数据正确返回无效")

    def test_pie_chart_placeholder_data(self):
        """测试2.2: 饼图占位符数据 - 应返回无效"""
        chart_dict = {
            "id": "test_pie_002",
            "type": "pie",
            "title": "测试饼图",
            "data": [
                {"name": "Unknown", "value": 0},
                {"name": "Unknown", "value": 0}
            ]
        }

        result = self.tool._is_valid_chart_output(chart_dict)

        assert result == False
        print("[PASS] 测试2.2: 饼图占位符数据正确返回无效")

    def test_pie_chart_valid_data(self):
        """测试2.3: 饼图有效数据 - 应返回有效"""
        chart_dict = {
            "id": "test_pie_003",
            "type": "pie",
            "title": "测试饼图",
            "data": [
                {"name": "类别A", "value": 30},
                {"name": "类别B", "value": 70}
            ]
        }

        result = self.tool._is_valid_chart_output(chart_dict)

        assert result == True
        print("[PASS] 测试2.3: 饼图有效数据正确返回有效")

    def test_bar_chart_empty_data(self):
        """测试2.4: 柱状图空数据 - 应返回无效"""
        chart_dict = {
            "id": "test_bar_001",
            "type": "bar",
            "title": "测试柱状图",
            "data": {"x": [], "y": []}
        }

        result = self.tool._is_valid_chart_output(chart_dict)

        assert result == False
        print("[PASS] 测试2.4: 柱状图空数据正确返回无效")

    def test_timeseries_empty_series(self):
        """测试2.5: 时序图空series - 应返回无效"""
        chart_dict = {
            "id": "test_ts_001",
            "type": "timeseries",
            "title": "测试时序图",
            "data": {"x": ["2024-01-01", "2024-01-02"], "series": []}
        }

        result = self.tool._is_valid_chart_output(chart_dict)

        assert result == False
        print("[PASS] 测试2.5: 时序图空series正确返回无效")

    def test_missing_required_fields(self):
        """测试2.6: 缺少必需字段 - 应返回无效"""
        # 缺少data字段
        chart_dict_no_data = {
            "id": "test_001",
            "type": "pie",
            "title": "测试图表"
        }

        result = self.tool._is_valid_chart_output(chart_dict_no_data)
        assert result == False

        # 缺少type字段
        chart_dict_no_type = {
            "id": "test_002",
            "title": "测试图表",
            "data": []
        }

        result = self.tool._is_valid_chart_output(chart_dict_no_type)
        assert result == False

        print("[PASS] 测试2.6: 缺少必需字段正确返回无效")


class TestAgentDrivenChartSelection:
    """测试Agent驱动的图表选择功能"""

    def setup_method(self):
        """测试前准备"""
        self.tool = GenerateChartTool()
        self.mock_context = Mock()
        self.mock_context.save_data = Mock(return_value="chart_config:test_456")

    @pytest.mark.asyncio
    async def test_agent_explicit_chart_type_pie(self):
        """测试3.1: Agent明确指定pie类型 - 应使用pie"""
        with patch.object(self.tool, '_generate_with_llm_v3', new_callable=AsyncMock) as mock_llm:
            # 模拟LLM返回饼图
            mock_llm.return_value = {
                "id": "chart_pie_001",
                "type": "pie",
                "title": "测试饼图",
                "data": [{"name": "A", "value": 50}, {"name": "B", "value": 50}],
                "meta": {"schema_version": "3.1"}
            }

            data = [
                {"category": "A", "value": 50},
                {"category": "B", "value": 50}
            ]

            result = await self.tool.execute(
                context=self.mock_context,
                data=data,
                scenario="custom",
                chart_type_hint="pie",  # Agent明确指定
                title="测试Agent指定pie"
            )

            # 验证返回成功
            assert result["success"] == True
            assert result["status"] == "success"

            # 验证使用了visuals字段（UDF v2.0）
            assert "visuals" in result
            assert len(result["visuals"]) == 1

            # 验证图表类型
            visual_payload = result["visuals"][0]["payload"]
            assert visual_payload["type"] == "pie"

            print("[PASS] 测试3.1: Agent明确指定pie类型正确使用")

    @pytest.mark.asyncio
    async def test_agent_explicit_chart_type_wind_rose(self):
        """测试3.2: Agent明确指定wind_rose - 应验证兼容性"""
        # 准备wind_rose数据
        data = [
            {"wind_speed": 3.5, "wind_direction": 45},
            {"wind_speed": 4.2, "wind_direction": 90}
        ]

        with patch.object(self.tool.template_registry, 'generate') as mock_template:
            # 模拟模板返回wind_rose图表
            mock_template.return_value = {
                "id": "chart_wind_rose_001",
                "type": "wind_rose",
                "title": "风向玫瑰图",
                "data": {
                    "sectors": [
                        {"direction": "NE", "avg_speed": 3.5, "count": 1},
                        {"direction": "E", "avg_speed": 4.2, "count": 1}
                    ]
                },
                "meta": {"schema_version": "3.1"}
            }

            result = await self.tool.execute(
                context=self.mock_context,
                data=data,
                scenario="custom",
                chart_type_hint="wind_rose",  # Agent明确指定
                title="测试wind_rose"
            )

            # 验证兼容性检查通过，使用了模板
            assert result["success"] == True
            assert result["metadata"]["method"] == "template"
            assert result["metadata"]["template_used"] == "wind_rose"

            print("[PASS] 测试3.2: Agent指定wind_rose正确验证兼容性并使用模板")

    @pytest.mark.asyncio
    async def test_agent_chart_type_auto_fallback_llm(self):
        """测试3.3: Agent指定auto - 应跳过模板直接用LLM"""
        with patch.object(self.tool, '_generate_with_llm_v3', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "id": "chart_auto_001",
                "type": "bar",
                "title": "自动生成柱状图",
                "data": {"x": ["A", "B"], "y": [10, 20]},
                "meta": {"schema_version": "3.1"}
            }

            data = [{"category": "A", "value": 10}]

            result = await self.tool.execute(
                context=self.mock_context,
                data=data,
                scenario="custom",
                chart_type_hint="auto",  # Agent指定auto
                title="测试auto回退"
            )

            # 验证使用了LLM生成
            assert result["success"] == True
            assert result["metadata"]["method"] == "llm_generated"

            # 验证LLM被调用
            mock_llm.assert_called_once()

            print("[PASS] 测试3.3: Agent指定auto正确跳过模板使用LLM")

    @pytest.mark.asyncio
    async def test_template_incompatible_fallback_llm(self):
        """测试3.4: 模板不兼容 - 应自动回退到LLM"""
        # 准备缺少必需字段的数据（wind_rose需要wind_speed+wind_direction）
        data = [
            {"wind_direction": 45, "temperature": 25}  # 缺少wind_speed
        ]

        with patch.object(self.tool, '_generate_with_llm_v3', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "id": "chart_fallback_001",
                "type": "bar",
                "title": "回退柱状图",
                "data": {"x": ["A"], "y": [25]},
                "meta": {"schema_version": "3.1"}
            }

            result = await self.tool.execute(
                context=self.mock_context,
                data=data,
                scenario="custom",
                chart_type_hint="wind_rose",  # Agent指定wind_rose
                title="测试不兼容回退"
            )

            # 验证成功但使用了LLM（因为模板不兼容）
            assert result["success"] == True
            assert result["metadata"]["method"] == "llm_generated"

            # 验证LLM被调用
            mock_llm.assert_called_once()

            print("[PASS] 测试3.4: 模板不兼容正确回退到LLM")


class TestIntegrationMultiLevelFallback:
    """测试完整的多级回退机制"""

    def setup_method(self):
        """测试前准备"""
        self.tool = GenerateChartTool()
        self.mock_context = Mock()
        self.mock_context.save_data = Mock(return_value="chart_config:test_789")

    @pytest.mark.asyncio
    async def test_full_fallback_chain(self):
        """测试4.1: 完整回退链 - 兼容性检查失败 -> LLM"""
        # 准备数据：缺少map的必需字段latitude
        data = [
            {"longitude": 114.05, "name": "站点A"},
            {"longitude": 114.06, "name": "站点B"}
        ]

        with patch.object(self.tool, '_generate_with_llm_v3', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "id": "chart_fallback_chain_001",
                "type": "bar",
                "title": "回退柱状图",
                "data": {"x": ["站点A", "站点B"], "y": [1, 1]},
                "meta": {"schema_version": "3.1"}
            }

            result = await self.tool.execute(
                context=self.mock_context,
                data=data,
                scenario="custom",
                chart_type_hint="map",  # Agent指定map
                title="测试完整回退链"
            )

            # 验证：
            # 1. 成功返回
            assert result["success"] == True
            # 2. 使用了LLM（因为兼容性验证失败）
            assert result["metadata"]["method"] == "llm_generated"
            # 3. 返回UDF v2.0格式
            assert result["metadata"]["schema_version"] == "v2.0"
            assert "visuals" in result

            print("[PASS] 测试4.1: 完整回退链验证成功")

    @pytest.mark.asyncio
    async def test_template_output_validation_fallback(self):
        """测试4.2: 模板输出验证失败 -> LLM回退"""
        # 准备有效的pie数据
        data = [
            {"name": "A", "value": 50},
            {"name": "B", "value": 50}
        ]

        with patch.object(self.tool.template_registry, 'generate') as mock_template, \
             patch.object(self.tool, '_generate_with_llm_v3', new_callable=AsyncMock) as mock_llm:

            # 模拟模板返回无效数据（空数据）
            mock_template.return_value = {
                "id": "chart_invalid_001",
                "type": "pie",
                "title": "无效饼图",
                "data": []  # 空数据
            }

            # 模拟LLM返回有效数据
            mock_llm.return_value = {
                "id": "chart_llm_002",
                "type": "pie",
                "title": "LLM生成饼图",
                "data": [{"name": "A", "value": 50}, {"name": "B", "value": 50}],
                "meta": {"schema_version": "3.1"}
            }

            result = await self.tool.execute(
                context=self.mock_context,
                data=data,
                scenario="custom",
                chart_type_hint="pie",
                title="测试输出验证回退"
            )

            # 验证：
            # 1. 模板被调用了
            mock_template.assert_called_once()
            # 2. 但因为输出无效，LLM也被调用了
            mock_llm.assert_called_once()
            # 3. 最终使用LLM结果
            assert result["metadata"]["method"] == "llm_generated"

            print("[PASS] 测试4.2: 模板输出验证失败正确回退到LLM")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始测试 generate_chart 架构重新设计")
    print("="*60 + "\n")

    # 测试1: 模板兼容性验证
    print("\n[测试组1] 模板兼容性验证")
    print("-" * 60)
    test1 = TestTemplateCompatibilityValidation()
    test1.setup_method()
    test1.test_wind_rose_missing_required_fields()
    test1.test_wind_rose_has_required_fields()
    test1.test_map_missing_latitude()
    test1.test_profile_altitude_or_height()
    test1.test_pm_analysis_missing_components()

    # 测试2: 模板输出验证
    print("\n[测试组2] 模板输出验证")
    print("-" * 60)
    test2 = TestTemplateOutputValidation()
    test2.setup_method()
    test2.test_pie_chart_empty_data()
    test2.test_pie_chart_placeholder_data()
    test2.test_pie_chart_valid_data()
    test2.test_bar_chart_empty_data()
    test2.test_timeseries_empty_series()
    test2.test_missing_required_fields()

    # 测试3: Agent驱动
    print("\n[测试组3] Agent驱动图表选择")
    print("-" * 60)
    test3 = TestAgentDrivenChartSelection()
    test3.setup_method()
    asyncio.run(test3.test_agent_explicit_chart_type_pie())
    test3.setup_method()
    asyncio.run(test3.test_agent_explicit_chart_type_wind_rose())
    test3.setup_method()
    asyncio.run(test3.test_agent_chart_type_auto_fallback_llm())
    test3.setup_method()
    asyncio.run(test3.test_template_incompatible_fallback_llm())

    # 测试4: 多级回退集成
    print("\n[测试组4] 多级回退机制集成")
    print("-" * 60)
    test4 = TestIntegrationMultiLevelFallback()
    test4.setup_method()
    asyncio.run(test4.test_full_fallback_chain())
    test4.setup_method()
    asyncio.run(test4.test_template_output_validation_fallback())

    print("\n" + "="*60)
    print("所有测试完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
