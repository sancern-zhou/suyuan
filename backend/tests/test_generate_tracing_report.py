"""
污染溯源报告生成工具测试

测试 GenerateTracingReportTool 的基本功能：
1. 工具注册
2. Schema 验证
3. 图表类型识别
4. qmd 内容生成
"""

import pytest
import json
from pathlib import Path
from app.tools.reporting.generate_tracing_report.tool import GenerateTracingReportTool
from app.tools.base.tool_interface import ToolCategory


class TestGenerateTracingReportTool:
    """测试污染溯源报告生成工具"""

    def test_tool_creation(self):
        """测试工具创建"""
        tool = GenerateTracingReportTool()
        assert tool.name == "generate_tracing_report"
        assert tool.category == ToolCategory.REPORTING
        assert tool.version == "1.0.0"
        assert tool.requires_context is False

    def test_function_schema(self):
        """测试函数 schema"""
        tool = GenerateTracingReportTool()
        schema = tool.get_function_schema()

        assert schema["name"] == "generate_tracing_report"
        assert "污染溯源分析报告" in schema["description"]

        params = schema["parameters"]["properties"]
        assert "query" in params
        assert "precision" in params

        # 验证 query 参数
        assert params["query"]["type"] == "string"
        assert "用户查询" in params["query"]["description"]

        # 验证 precision 参数
        assert params["precision"]["type"] == "string"
        assert params["precision"]["enum"] == ["fast", "standard", "full"]

        # 验证必需参数
        assert schema["parameters"]["required"] == ["query"]

    def test_static_image_detection(self):
        """测试静态图片识别"""
        tool = GenerateTracingReportTool()

        # 静态图片（字典类型ID）
        visual1 = {
            "id": {"image_id": "img_123"},
            "title": "测试图表1",
            "payload": {}
        }
        assert tool._is_static_image(visual1) is True

        # 静态图片（字符串类型ID）
        visual2 = {
            "id": "image_id_abc",
            "title": "测试图表2",
            "payload": {}
        }
        assert tool._is_static_image(visual2) is True

        # ECharts 配置
        visual3 = {
            "id": "echart_123",
            "title": "测试图表3",
            "payload": {
                "data": {
                    "xAxis": {"data": ["Mon", "Tue"]},
                    "yAxis": {},
                    "series": [{"data": [10, 20]}]
                }
            }
        }
        assert tool._is_static_image(visual3) is False

    def test_qmd_content_generation(self):
        """测试 qmd 内容生成"""
        tool = GenerateTracingReportTool()

        # 创建模拟的 pipeline_result
        from app.agent.experts.expert_router_v3 import PipelineResult
        from app.agent.core.structured_query_parser import StructuredQuery

        pipeline_result = PipelineResult()
        pipeline_result.query = "分析广州昨日O3污染"
        pipeline_result.parsed_query = StructuredQuery(
            location="广州",
            pollutant="O3",
            date_range="昨日"
        )
        pipeline_result.selected_experts = ["weather", "component", "viz", "report"]
        pipeline_result.confidence = 0.85
        pipeline_result.conclusions = ["结论1", "结论2"]
        pipeline_result.recommendations = ["建议1", "建议2"]
        pipeline_result.response = "完整的分析响应内容"

        # 添加专家结果
        from app.agent.experts.expert_executor import ExpertResult, ExpertAnalysis

        pipeline_result.expert_results["weather"] = ExpertResult(
            status="success",
            expert_type="weather",
            analysis=ExpertAnalysis(
                summary="气象条件良好",
                key_findings=["发现1", "发现2"],
                confidence=0.9
            )
        )

        # 模拟处理后的图表
        processed_visuals = [
            {
                "id": "chart1",
                "type": "static",
                "title": "风向玫瑰图",
                "image_path": "/path/to/chart1.png",
                "relative_path": "assets/images/chart1.png",
                "expert": "weather"
            }
        ]

        # 生成 qmd 内容
        qmd_content = tool._generate_qmd_content(
            pipeline_result,
            processed_visuals,
            "test_report_001"
        )

        # 验证 qmd 内容
        assert "---" in qmd_content
        assert "title:" in qmd_content
        assert "广州污染溯源分析报告" in qmd_content
        assert "## 执行摘要" in qmd_content
        assert "## 气象条件分析" in qmd_content
        assert "### 主要结论" in qmd_content
        assert "结论1" in qmd_content
        assert "建议1" in qmd_content
        assert "assets/images/chart1.png" in qmd_content
        assert "## 综合分析结论" in qmd_content

    def test_expert_sections_generation(self):
        """测试专家章节生成"""
        tool = GenerateTracingReportTool()

        from app.agent.experts.expert_router_v3 import PipelineResult
        from app.agent.experts.expert_executor import ExpertResult, ExpertAnalysis

        pipeline_result = PipelineResult()
        pipeline_result.response = "最终分析结果"

        pipeline_result.expert_results["weather"] = ExpertResult(
            status="success",
            expert_type="weather",
            analysis=ExpertAnalysis(
                summary="气象分析总结",
                key_findings=["发现A", "发现B"],
                confidence=0.9
            )
        )

        visuals_by_expert = {
            "weather": [
                {
                    "title": "风向玫瑰图",
                    "relative_path": "assets/images/wind_rose.png"
                }
            ]
        }

        content = tool._generate_expert_sections(pipeline_result, visuals_by_expert)

        assert "## 气象条件分析" in content
        assert "气象分析总结" in content
        assert "风向玫瑰图" in content
        assert "assets/images/wind_rose.png" in content
        assert "#### 关键发现" in content
        assert "发现A" in content
        assert "发现B" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
