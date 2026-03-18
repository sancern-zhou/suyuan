"""
模板报告引擎 - 场景2核心引擎
支持方案B（临时报告）和方案C（固定报告）
"""
from typing import Dict, Any, List, Optional, AsyncGenerator
import structlog
import asyncio
import re

from app.schemas.report_generation import (
    ReportEvent, EventType, ReportStructure, TemplateReportRequest,
    ReportOptions
)
from app.services.report_parser import ReportParser
from app.services.template_data_fetcher import TemplateDataFetcher
from app.services.data_organizer import DataOrganizer
from app.services.report_renderer import ReportRenderer
from app.services.report_formatter import ReportFormatter
from app.services.tool_executor import ToolExecutor
from app.db.models.report_template import ReportTemplate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4

# Context-related imports
from app.agent.context.execution_context import ExecutionContext
from app.agent.context.data_context_manager import DataContextManager
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.services.data_registry import data_registry

logger = structlog.get_logger()

class TemplateReportEngine:
    """模板化报告引擎"""

    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor
        self.parser = ReportParser()
        # Note: data_fetcher is now created per-request with context
        self.organizer = DataOrganizer()
        self.renderer = ReportRenderer()
        self.formatter = ReportFormatter()

    async def generate_from_template(
        self,
        template_content: str,
        target_time_range: Dict[str, str],
        options: Optional[ReportOptions] = None
    ) -> AsyncGenerator[ReportEvent, None]:
        """
        基于历史报告模板生成新报告

        支持两种模式：
        1. 方案B：临时报告（结构化拆解）
        2. 方案C：固定报告（模板标注）

        Args:
            template_content: 历史报告内容（Markdown）
            target_time_range: 目标时间范围
            options: 生成选项

        Yields:
            ReportEvent: 生成过程事件
        """
        logger.info("Starting template-based report generation")

        try:
            # 阶段1: 报告解析
            yield ReportEvent(
                type=EventType.PHASE_STARTED,
                data={"phase": "parsing", "description": "解析报告结构"}
            )

            # 检查是否为标注模板
            is_annotated = self._is_annotated_template(template_content)

            if is_annotated:
                # 方案C：固定报告（模板标注）
                logger.info("Using annotated template (方案C)")
                structure = await self._parse_annotated_template(template_content)
            else:
                # 方案B：临时报告（结构化拆解）
                logger.info("Using structural parsing (方案B)")
                structure = await self.parser.parse(template_content)

            yield ReportEvent(
                type=EventType.STRUCTURE_PARSED,
                data={
                    "sections_count": len(structure.sections),
                    "tables_count": len(structure.tables),
                    "rankings_count": len(structure.rankings)
                }
            )

            # 阶段2: 数据查询
            # 为此次请求创建独立的ExecutionContext
            session_id = f"template_report_{uuid4().hex[:8]}"
            iteration = 0  # 单次请求，迭代号为0
            memory_manager = HybridMemoryManager(session_id=session_id, iteration=iteration)
            data_manager = DataContextManager(memory_manager)
            execution_context = ExecutionContext(
                session_id=session_id,
                iteration=iteration,
                data_manager=data_manager
            )

            yield ReportEvent(
                type=EventType.PHASE_STARTED,
                data={"phase": "data_fetching", "description": "获取数据"}
            )

            # 使用带context的data_fetcher
            data_fetcher = TemplateDataFetcher(self.tool_executor, execution_context)
            data_requirements = self.parser.get_data_requirements(structure)
            raw_data = await data_fetcher.fetch_all(
                requirements=data_requirements,
                time_range=target_time_range
            )

            yield ReportEvent(
                type=EventType.DATA_FETCHED,
                data={
                    "record_count": len(raw_data),
                    "requirements_count": len(data_requirements)
                }
            )

            # 阶段3: 数据整理
            yield ReportEvent(
                type=EventType.PHASE_STARTED,
                data={"phase": "processing", "description": "整理数据"}
            )

            processed_data = await self.organizer.organize(
                raw_data=raw_data,
                data_points=structure.sections,
                tables=structure.tables,
                rankings=structure.rankings
            )

            yield ReportEvent(
                type=EventType.DATA_ORGANIZED,
                data={
                    "processed_count": len(processed_data),
                    "summary": processed_data.get("summary", "")
                }
            )

            # 阶段4: 报告生成
            yield ReportEvent(
                type=EventType.PHASE_STARTED,
                data={"phase": "rendering", "description": "生成报告"}
            )

            # 使用渲染器生成最终报告
            final_report = await self.renderer.render(
                template=template_content,
                structure=structure,
                data=processed_data,
                target_time_range=target_time_range,
                is_annotated=is_annotated
            )

            yield ReportEvent(
                type=EventType.REPORT_COMPLETED,
                data={"report_content": final_report}
            )

            logger.info("Template-based report generation completed")

        except Exception as e:
            error_msg = f"Template report generation failed: {str(e)}"
            logger.error(error_msg)

            yield ReportEvent(
                type=EventType.REPORT_COMPLETED,
                data={
                    "error": error_msg,
                    "report_content": f"# 报告生成失败\n\n错误：{error_msg}"
                }
            )

    def _is_annotated_template(self, content: str) -> bool:
        """
        检查是否为标注模板

        Args:
            content: 模板内容

        Returns:
            bool: 是否为标注模板
        """
        # 检查是否包含占位符语法
        placeholder_patterns = [
            r'\{\{.*?\}\}',  # {{placeholder}}
            r'\{\{#.*?\}\}',  # {{#if}} {{#each}}
            r'\{\{/.*?\}\}',  # {{/if}} {{/each}}
        ]

        for pattern in placeholder_patterns:
            if re.search(pattern, content):
                return True

        return False

    async def _parse_annotated_template(
        self,
        content: str
    ) -> ReportStructure:
        """
        解析标注模板（方案C）

        Args:
            content: 标注模板内容

        Returns:
            ReportStructure: 模板结构
        """
        # TODO: 实现标注模板解析逻辑
        # 需要解析占位符，提取数据需求

        # 临时实现：使用结构化拆解
        return await self.parser.parse(content)

    async def generate_quick(
        self,
        template_id: str,
        time_range: Dict[str, str],
        db_session: AsyncSession
    ) -> AsyncGenerator[ReportEvent, None]:
        """
        从已保存模板快速生成（方案C）

        Args:
            template_id: 模板ID
            time_range: 时间范围
            db_session: 数据库会话

        Yields:
            ReportEvent: 生成事件
        """
        logger.info(f"Quick generation from template: {template_id}")

        try:
            # 从数据库加载模板
            yield ReportEvent(
                type=EventType.PHASE_STARTED,
                data={"phase": "loading", "description": "加载模板"}
            )

            result = await db_session.execute(
                select(ReportTemplate).where(ReportTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()

            if not template:
                error_msg = f"Template not found: {template_id}"
                logger.error(error_msg)
                yield ReportEvent(
                    type=EventType.REPORT_COMPLETED,
                    data={
                        "error": error_msg,
                        "report_content": f"# 报告生成失败\n\n错误：{error_msg}"
                    }
                )
                return

            logger.info(f"Template loaded: {template.name}")
            template_content = template.content

            # 使用标准生成流程
            async for event in self.generate_from_template(
                template_content=template_content,
                target_time_range=time_range
            ):
                yield event

        except Exception as e:
            error_msg = f"Quick generation failed: {str(e)}"
            logger.error(error_msg)

            yield ReportEvent(
                type=EventType.REPORT_COMPLETED,
                data={
                    "error": error_msg,
                    "report_content": f"# 报告生成失败\n\n错误：{error_msg}"
                }
            )

class TimeRange:
    """时间范围模型"""

    def __init__(self, start: str, end: str):
        self.start = start
        self.end = end
        self.display = f"{start}至{end}"

    @property
    def start_date(self):
        return self.start

    @property
    def end_date(self):
        return self.end
