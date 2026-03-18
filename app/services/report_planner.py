"""
报告规划器 - 使用ReAct架构规划报告生成流程
"""
from typing import Dict, Any, List, Optional
import structlog

from app.schemas.report_generation import (
    ReportPlan, ReportSection, ReportType, ReportGenerationRequest
)

logger = structlog.get_logger()

class ReportPlanner:
    """报告规划器 - 智能规划报告生成流程"""

    # 预定义的报告结构模板
    REPORT_STRUCTURES = {
        "research_report": {
            "sections": [
                {
                    "id": "abstract",
                    "title": "摘要",
                    "required": True,
                    "order": 1,
                    "use_knowledge_base": True
                },
                {
                    "id": "background",
                    "title": "研究背景",
                    "required": True,
                    "order": 2,
                    "use_knowledge_base": True,
                    "tools": ["search_knowledge_base"]
                },
                {
                    "id": "methodology",
                    "title": "研究方法",
                    "required": True,
                    "order": 3
                },
                {
                    "id": "data_analysis",
                    "title": "数据分析",
                    "required": True,
                    "order": 4,
                    "use_data_tools": True,
                    "tools": ["get_air_quality", "get_weather_data"],
                    "requires_expert": True,
                    "expert_type": "ComponentExpert"
                },
                {
                    "id": "results",
                    "title": "研究结果",
                    "required": True,
                    "order": 5,
                    "use_visualization": True,
                    "tools": ["generate_chart"],
                    "requires_expert": True,
                    "expert_type": "VizExpert"
                },
                {
                    "id": "discussion",
                    "title": "讨论",
                    "required": False,
                    "order": 6
                },
                {
                    "id": "conclusion",
                    "title": "结论与建议",
                    "required": True,
                    "order": 7
                },
                {
                    "id": "references",
                    "title": "参考资料",
                    "required": False,
                    "order": 8,
                    "use_knowledge_base": True
                }
            ]
        },
        "analysis_report": {
            "sections": [
                {
                    "id": "summary",
                    "title": "执行摘要",
                    "required": True,
                    "order": 1
                },
                {
                    "id": "situation",
                    "title": "现状分析",
                    "required": True,
                    "order": 2,
                    "use_data_tools": True,
                    "tools": ["get_air_quality"],
                    "requires_expert": True,
                    "expert_type": "ComponentExpert"
                },
                {
                    "id": "cause_analysis",
                    "title": "原因分析",
                    "required": True,
                    "order": 3,
                    "use_data_tools": True,
                    "tools": ["get_weather_data"],
                    "requires_expert": True,
                    "expert_type": "WeatherExpert"
                },
                {
                    "id": "recommendations",
                    "title": "对策建议",
                    "required": True,
                    "order": 4
                }
            ]
        }
    }

    async def create_plan(
        self,
        topic: str,
        report_type: str,
        requirements: Optional[str] = None
    ) -> ReportPlan:
        """
        创建报告生成计划

        Args:
            topic: 报告主题
            report_type: 报告类型
            requirements: 额外要求

        Returns:
            ReportPlan: 报告生成计划
        """
        logger.info(f"Creating plan for: {topic}")

        # 获取报告结构模板
        structure_template = self.REPORT_STRUCTURES.get(
            report_type,
            self.REPORT_STRUCTURES["research_report"]
        )

        # 创建章节列表
        sections = []
        for section_config in structure_template["sections"]:
            section = ReportSection(
                id=section_config["id"],
                title=section_config["title"],
                required=section_config.get("required", True),
                order=section_config["order"],
                tools=section_config.get("tools"),
                requires_expert=section_config.get("requires_expert", False),
                expert_type=section_config.get("expert_type"),
                use_knowledge_base=section_config.get("use_knowledge_base", False),
                use_data_tools=section_config.get("use_data_tools", False),
                use_visualization=section_config.get("use_visualization", False)
            )
            sections.append(section)

        # 按顺序排序
        sections.sort(key=lambda x: x.order)

        # 创建计划
        plan = ReportPlan(
            topic=topic,
            report_type=ReportType(report_type),
            requirements=requirements,
            sections=sections,
            estimated_duration=len(sections) * 30  # 预估每章节30秒
        )

        logger.info(f"Plan created with {len(sections)} sections")
        return plan

    async def replan(
        self,
        section: ReportSection,
        error: str
    ) -> Optional[ReportSection]:
        """
        重新规划章节（处理错误后的重试）

        Args:
            section: 失败的章节
            error: 错误信息

        Returns:
            Optional[ReportSection]: 新的章节计划或None
        """
        logger.warning(f"Replanning section {section.id}: {error}")

        # 简化为使用默认工具
        new_section = ReportSection(
            id=section.id,
            title=section.title,
            required=section.required,
            order=section.order,
            # 简化工具列表
            tools=["get_air_quality"] if section.use_data_tools else None,
            requires_expert=False,  # 降级：不使用专家
            expert_type=None,
            use_knowledge_base=False,
            use_data_tools=section.use_data_tools,
            use_visualization=False
        )

        return new_section

    def get_required_tools(self, section: ReportSection) -> List[str]:
        """
        获取章节需要的工具列表

        Args:
            section: 报告章节

        Returns:
            List[str]: 工具名称列表
        """
        tools = []

        if section.tools:
            tools.extend(section.tools)

        if section.use_knowledge_base:
            tools.append("search_knowledge_base")

        if section.use_data_tools:
            tools.extend(["get_air_quality", "get_weather_data"])

        if section.use_visualization:
            tools.append("generate_chart")

        return list(set(tools))  # 去重
