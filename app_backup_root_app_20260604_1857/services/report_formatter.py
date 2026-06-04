"""
报告格式化器 - 统一输出格式为UDF v2.0
"""
from typing import Dict, Any, List, Optional
import json
import time

from app.schemas.report_generation import (
    ReportOutput, SectionContent, ReportType, ReportPlan
)

class ReportFormatter:
    """报告格式化器 - 输出符合UDF v2.0标准"""

    def __init__(self):
        self.schema_version = "v2.0"
        self.chart_schema_version = "3.1"

    def format_research_report(
        self,
        sections: List[SectionContent],
        plan: ReportPlan,
        source_data_ids: Optional[List[str]] = None,
        charts: Optional[List[Dict[str, Any]]] = None
    ) -> ReportOutput:
        """
        格式化研究报告为UDF v2.0格式

        Args:
            sections: 章节内容列表
            plan: 报告计划
            source_data_ids: 源数据ID列表
            charts: 嵌入的图表列表

        Returns:
            ReportOutput: 符合UDF v2.0的报告输出
        """
        # 构建Markdown内容
        markdown_content = self._build_markdown_content(sections)

        # 构建visuals列表
        visuals = []

        # 主要报告（markdown类型）
        report_visual = {
            "id": f"report_{int(time.time())}",
            "type": "markdown",
            "schema": "chart_config",
            "payload": {
                "content": markdown_content,
                "sections": [
                    {
                        "id": section.section_id,
                        "title": section.title,
                        "content": section.content,
                        "order": idx + 1
                    }
                    for idx, section in enumerate(sections)
                ],
                "charts": charts or []
            },
            "meta": {
                "schema_version": self.chart_schema_version,
                "generator": "ReportGenerationAgent",
                "source_data_ids": source_data_ids or [],
                "scenario": plan.report_type.value,
                "layout_hint": "wide",
                "data_flow": ["report_generation", "markdown"]
            }
        }
        visuals.append(report_visual)

        # 添加嵌入的图表
        if charts:
            for idx, chart in enumerate(charts):
                chart_visual = {
                    "id": chart.get("id", f"chart_{idx}"),
                    "type": chart.get("type", "unknown"),
                    "schema": "chart_config",
                    "payload": chart.get("data", {}),
                    "meta": {
                        "schema_version": self.chart_schema_version,
                        "generator": "ReportGenerationAgent",
                        "source_data_ids": source_data_ids or [],
                        "scenario": plan.report_type.value,
                        "layout_hint": chart.get("layout_hint", "inline")
                    }
                }
                visuals.append(chart_visual)

        # 构建元数据
        metadata = {
            "schema_version": self.schema_version,
            "field_mapping_applied": True,
            "field_mapping_info": {
                "standardization_applied": True,
                "field_mappings_count": 0,
                "unified_fields": []
            },
            "generator": "ReportGenerationAgent",
            "scenario": plan.report_type.value,
            "record_count": len(visuals),
            "generator_version": "1.0.0"
        }

        # 构建摘要
        summary = f"已完成{plan.topic}研究报告生成，包含{len(sections)}个章节"

        return ReportOutput(
            status="success",
            success=True,
            data=None,
            visuals=visuals,
            metadata=metadata,
            summary=summary
        )

    def format_template_report(
        self,
        content: str,
        template_name: str,
        time_range: Dict[str, str],
        source_data_ids: Optional[List[str]] = None
    ) -> ReportOutput:
        """
        格式化模板报告为UDF v2.0格式

        Args:
            content: 报告内容（Markdown）
            template_name: 模板名称
            time_range: 时间范围
            source_data_ids: 源数据ID列表

        Returns:
            ReportOutput: 符合UDF v2.0的报告输出
        """
        # 构建visuals
        visuals = [{
            "id": f"template_report_{int(time.time())}",
            "type": "markdown",
            "schema": "chart_config",
            "payload": {
                "content": content,
                "template_name": template_name,
                "time_range": time_range
            },
            "meta": {
                "schema_version": self.chart_schema_version,
                "generator": "TemplateReportEngine",
                "source_data_ids": source_data_ids or [],
                "scenario": "template_report",
                "layout_hint": "wide"
            }
        }]

        # 构建元数据
        metadata = {
            "schema_version": self.schema_version,
            "field_mapping_applied": True,
            "field_mapping_info": {
                "standardization_applied": True,
                "field_mappings_count": 0,
                "unified_fields": []
            },
            "generator": "TemplateReportEngine",
            "scenario": "template_report",
            "record_count": 1,
            "generator_version": "1.0.0"
        }

        # 构建摘要
        summary = f"已完成基于模板'{template_name}'的报告生成，时间范围：{time_range.get('start', '')}至{time_range.get('end', '')}"

        return ReportOutput(
            status="success",
            success=True,
            data=None,
            visuals=visuals,
            metadata=metadata,
            summary=summary
        )

    def _build_markdown_content(self, sections: List[SectionContent]) -> str:
        """
        构建完整的Markdown内容

        Args:
            sections: 章节内容列表

        Returns:
            str: Markdown格式的报告内容
        """
        content_lines = []

        for section in sections:
            # 添加章节标题
            content_lines.append(f"## {section.title}")
            content_lines.append("")

            # 添加章节内容
            content_lines.append(section.content)
            content_lines.append("")

            # 如果有图表引用，添加占位符
            if section.charts:
                content_lines.append("**图表**")
                for chart in section.charts:
                    chart_id = chart.get("id", "chart")
                    content_lines.append(f"![图表]({chart_id})")
                content_lines.append("")

        return "\n".join(content_lines)

    def format_error_report(
        self,
        error_message: str,
        plan: Optional[ReportPlan] = None
    ) -> ReportOutput:
        """
        格式化错误报告

        Args:
            error_message: 错误信息
            plan: 报告计划（可选）

        Returns:
            ReportOutput: 错误报告输出
        """
        content = f"# 报告生成失败\n\n错误信息：{error_message}"

        if plan:
            content += f"\n\n报告主题：{plan.topic}"

        visuals = [{
            "id": f"error_report_{int(time.time())}",
            "type": "markdown",
            "schema": "chart_config",
            "payload": {
                "content": content,
                "error": error_message
            },
            "meta": {
                "schema_version": self.chart_schema_version,
                "generator": "ReportGenerationAgent",
                "scenario": plan.report_type.value if plan else "unknown"
            }
        }]

        metadata = {
            "schema_version": self.schema_version,
            "field_mapping_applied": True,
            "field_mapping_info": {
                "standardization_applied": True,
                "field_mappings_count": 0,
                "unified_fields": []
            },
            "generator": "ReportGenerationAgent",
            "scenario": plan.report_type.value if plan else "error",
            "record_count": 1,
            "generator_version": "1.0.0"
        }

        return ReportOutput(
            status="failed",
            success=False,
            data=None,
            visuals=visuals,
            metadata=metadata,
            summary=f"报告生成失败：{error_message}"
        )
