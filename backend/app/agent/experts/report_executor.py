"""
报告专家执行器 (ReportExecutor)

负责综合多个专家的分析结果生成综合报告
注：报告专家不调用工具，纯LLM综合
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import structlog
import json
import re

from app.services.llm_service import llm_service
from app.agent.core.expert_plan_generator import ExpertTask
from .expert_executor import ExpertExecutor, ExpertResult, ExpertAnalysis, ExecutionSummary

logger = structlog.get_logger()


class ReportContent(BaseModel):
    """报告内容"""
    title: str = ""
    summary: str = ""
    background: str = ""
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    upwind_enterprises: List[Dict[str, Any]] = Field(default_factory=list)  # 上风向企业完整清单
    conclusions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReportExecutor(ExpertExecutor):
    """报告专家执行器"""
    
    def __init__(self):
        super().__init__("report")
    
    def _load_tools(self) -> Dict[str, Any]:
        """报告专家不使用工具"""
        return {}
    
    def _get_summary_prompt(self) -> str:
        """报告专家提示词（不使用，重写execute）"""
        return ""
    
    def _extract_summary_stats(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """报告专家不执行工具"""
        return {}
    
    async def execute(self, task: ExpertTask, expert_results: Optional[Dict[str, ExpertResult]] = None) -> ExpertResult:
        """
        执行报告生成
        
        Args:
            task: 专家任务
            expert_results: 其他专家的执行结果
            
        Returns:
            ExpertResult: 包含综合报告的结果
        """
        logger.info(
            "report_executor_started",
            task_id=task.task_id,
            upstream_experts=list(expert_results.keys()) if expert_results else []
        )
        
        result = ExpertResult(
            status="pending",
            expert_type=self.expert_type,
            task_id=task.task_id
        )
        
        try:
            # 生成综合报告
            report = await self._generate_report(
                task.task_description,
                task.context,
                expert_results or {}
            )
            
            result.analysis = ExpertAnalysis(
                summary=report.title,
                key_findings=report.conclusions[:3] if report.conclusions else [],
                data_quality="good" if report.confidence > 0.7 else "fair",
                confidence=report.confidence
            )
            
            # 将完整报告存入tool_results
            report_dict = report.dict()
            result.tool_results = [{
                "tool": "report_generation",
                "status": "success",
                "result": report_dict
            }]
            
            logger.info(
                "report_tool_results_set",
                has_sections=bool(report_dict.get("sections")),
                sections_keys=list(report_dict.get("sections", [{}])[0].keys()) if report_dict.get("sections") else []
            )
            
            result.execution_summary = ExecutionSummary(
                tools_executed=1,
                tools_succeeded=1,
                tools_failed=0
            )
            
            result.status = "success"
            
            logger.info(
                "report_executor_completed",
                task_id=task.task_id,
                confidence=report.confidence
            )
            
        except Exception as e:
            logger.error(
                "report_executor_failed",
                task_id=task.task_id,
                error=str(e),
                exc_info=True
            )
            result.status = "failed"
            result.errors.append({"type": "report_generation_error", "message": str(e)})
        
        return result
    
    async def _generate_report(
        self,
        task_description: str,
        context: Dict[str, Any],
        expert_results: Dict[str, ExpertResult]
    ) -> ReportContent:
        """生成综合报告"""
        
        # 收集各专家的分析结论
        expert_summaries = {}
        upwind_enterprises = []  # 上风向企业完整清单
        chart_info_by_section = {
            "weather": [],
            "component": [],
            "other": []
        }
        
        # 收集各专家的章节内容
        expert_sections = {}
        
        for expert_type, result in expert_results.items():
            logger.info(
                "processing_expert_result_start",
                expert_type=expert_type,
                result_status=result.status,
                has_analysis=result.analysis is not None
            )

            if result.status in ["success", "partial"]:
                expert_summaries[expert_type] = {
                    "summary": result.analysis.summary,
                    "key_findings": result.analysis.key_findings,
                    "confidence": result.analysis.confidence
                }

                # 【详细日志】追踪section_content的获取过程
                logger.info(
                    "expert_analysis_details",
                    expert_type=expert_type,
                    analysis_type=type(result.analysis).__name__,
                    has_summary=hasattr(result.analysis, 'summary'),
                    has_section_content=hasattr(result.analysis, 'section_content'),
                    summary_length=len(result.analysis.summary) if result.analysis.summary else 0
                )

                # 检查section_content是否存在
                section_content = None
                if hasattr(result.analysis, 'section_content'):
                    section_content = result.analysis.section_content
                    logger.info(
                        "section_content_attribute_found",
                        expert_type=expert_type,
                        section_content_type=type(section_content).__name__,
                        section_content_length=len(section_content) if section_content else 0,
                        section_content_is_none=section_content is None,
                        section_content_is_empty=section_content == "" if section_content else False
                    )
                else:
                    logger.warning(
                        "section_content_attribute_missing",
                        expert_type=expert_type,
                        analysis_attributes=list(dir(result.analysis))
                    )

                # 如果section_content不为空，添加到expert_sections
                if section_content and section_content.strip():
                    expert_sections[expert_type] = section_content
                    logger.info(
                        "expert_section_collected_success",
                        expert_type=expert_type,
                        content_length=len(section_content),
                        content_preview=section_content[:200] + "..." if len(section_content) > 200 else section_content,
                        has_markers=any(marker in section_content for marker in [
                            "[WEATHER_SECTION_START]", "[COMPONENT_SECTION_START]"
                        ])
                    )
                else:
                    logger.warning(
                        "expert_section_missing_or_empty",
                        expert_type=expert_type,
                        has_section_content=section_content is not None,
                        section_content_length=len(section_content) if section_content else 0,
                        is_empty=section_content == "" if section_content else False
                    )
        
        logger.info(
            "expert_sections_collection_complete",
            collected_experts=list(expert_sections.keys()),
            total_experts=list(expert_results.keys()),
            has_sections=bool(expert_sections)
        )
        
        # 收集图表信息
        for expert_type, result in expert_results.items():
            if result.status in ["success", "partial"]:
                # 【关键修复】优先从 ExpertResult.visuals 收集图表（由 _aggregate_visuals 聚合）
                visuals = result.visuals if hasattr(result, 'visuals') and result.visuals else []

                # 如果没有聚合的visuals，尝试从tool_results中获取（向后兼容）
                if not visuals and result.tool_results:
                    for tool_result in result.tool_results:
                        result_data = tool_result.get("result")
                        if result_data and isinstance(result_data, dict):
                            tool_visuals = result_data.get("visuals")
                            if tool_visuals and isinstance(tool_visuals, list):
                                visuals.extend(tool_visuals)

                # 获取该专家的data_id（用于图表分类）
                tool_data_id = ""
                if result.data_ids:
                    tool_data_id = result.data_ids[0]  # 取第一个data_id

                # 遍历visuals收集图表信息
                for visual in visuals:
                    if not isinstance(visual, dict):
                        continue

                    # ✅ 提取图片URL信息
                    image_url = ""
                    image_id = ""
                    visual_id = visual.get("id", "")

                    # 【调试】记录visual_id的类型
                    logger.info(
                        "[DEBUG_REPORT_VISUAL]",
                        visual_id_type=type(visual_id).__name__,
                        visual_id_preview=str(visual_id)[:200]
                    )

                    # 处理不同类型的id字段
                    if isinstance(visual_id, str):
                        # id是纯字符串，直接使用
                        image_id = visual_id
                    elif isinstance(visual_id, dict):
                        # ⚠️ id是字典，需要提取真正的image_id
                        logger.info(
                            "[DEBUG_REPORT_VISUAL_ID_IS_DICT]",
                            keys=list(visual_id.keys()),
                            has_image_id="image_id" in visual_id,
                            has_id="id" in visual_id,
                            has_url="url" in visual_id
                        )
                        # 情况1: {'image_id': 'charge_balance_xxx', ...}
                        if "image_id" in visual_id:
                            image_id = visual_id["image_id"]
                        # 情况2: {'id': 'charge_balance_xxx', ...}
                        elif "id" in visual_id and isinstance(visual_id["id"], str):
                            image_id = visual_id["id"]
                        else:
                            # 都没有，记录警告并跳过
                            logger.warning(
                                "chart_id_is_dict_without_valid_id",
                                visual_id_keys=list(visual_id.keys()),
                                visual_preview=str(visual_id)[:200]
                            )
                            continue

                        # ✅ 同时尝试从字典中提取预生成的URL
                        # ⚠️ 检查url字段是否是字符串
                        dict_url = visual_id.get("url", "")
                        if isinstance(dict_url, str) and dict_url.startswith("/api/"):
                            image_url = dict_url
                        elif isinstance(dict_url, dict):
                            # url字段也是字典，尝试提取
                            logger.warning(
                                "url_field_is_dict",
                                url_keys=list(dict_url.keys())
                            )
                            image_url = dict_url.get("url", "") or dict_url.get("image_url", "")

                        logger.info(
                            "[DEBUG_REPORT_EXTRACTED_FROM_DICT]",
                            extracted_image_id=image_id,
                            extracted_image_url=image_url,
                            extracted_image_url_type=type(image_url).__name__
                        )
                    else:
                        # id既不是字符串也不是字典，跳过
                        logger.warning(
                            "chart_id_unexpected_type",
                            id_type=type(visual_id).__name__,
                            visual_preview=str(visual_id)[:200]
                        )
                        continue

                    # 如果没有从字典中获取到URL，尝试从visual顶层获取
                    if not image_url:
                        visual_top_image_url = visual.get("image_url", "")
                        # 检查是否是字符串
                        if isinstance(visual_top_image_url, str):
                            image_url = visual_top_image_url
                        elif isinstance(visual_top_image_url, dict):
                            logger.warning(
                                "visual_top_image_url_is_dict",
                                url_keys=list(visual_top_image_url.keys())
                            )

                    # 如果仍然没有URL但有image_id，构建标准URL
                    if not image_url and image_id:
                        image_url = f"/api/image/{image_id}"

                    chart_info = {
                        "id": image_id,  # ✅ 使用纯字符串ID
                        "image_id": image_id,  # ✅ 明确的image_id字段
                        "image_url": image_url,  # ✅ 完整的URL
                        "title": self._extract_chart_title(visual),
                        "type": visual.get("type", ""),
                        "expert": expert_type
                    }

                    # 【调试】记录chart_info
                    logger.info(
                        "[DEBUG_REPORT_CHART_INFO]",
                        chart_id=chart_info.get("id"),
                        chart_id_type=type(chart_info.get("id")).__name__,
                        chart_image_id=chart_info.get("image_id"),
                        chart_image_url=chart_info.get("image_url"),
                        chart_title=chart_info.get("title")[:50]
                    )

                    # 如果没有ID，跳过
                    if not chart_info["id"]:
                        logger.debug(
                            "chart_skipped_no_id",
                            expert_type=expert_type,
                            visual_keys=list(visual.keys())
                        )
                        continue

                    # 添加data_id到visual中（用于分类判断）
                    visual_for_classification = visual.copy()
                    if tool_data_id:
                        if "payload" not in visual_for_classification:
                            visual_for_classification["payload"] = {}
                        if not isinstance(visual_for_classification["payload"], dict):
                            visual_for_classification["payload"] = {}
                        if "meta" not in visual_for_classification["payload"]:
                            visual_for_classification["payload"]["meta"] = {}
                        if not isinstance(visual_for_classification["payload"]["meta"], dict):
                            visual_for_classification["payload"]["meta"] = {}
                        if not visual_for_classification["payload"]["meta"].get("data_id"):
                            visual_for_classification["payload"]["meta"]["data_id"] = tool_data_id
                        if not visual_for_classification["payload"]["meta"].get("source_data_id"):
                            visual_for_classification["payload"]["meta"]["source_data_id"] = tool_data_id
                        visual_for_classification["data_id"] = tool_data_id

                    # 根据expert_type、meta和data_id分组
                    section = self._determine_chart_section(visual_for_classification, expert_type)
                    chart_info_by_section[section].append(chart_info)

                # 提取上风向企业分析的完整数据（从聚合的visuals中）
                if expert_type == "weather" and visuals:
                    for visual in visuals:
                        if not isinstance(visual, dict):
                            continue
                        payload = visual.get("payload", {})
                        if isinstance(payload, dict):
                            data = payload.get("data", {})
                            if isinstance(data, dict):
                                enterprises = data.get("enterprises", [])
                                if enterprises and isinstance(enterprises, list):
                                    upwind_enterprises = enterprises
                                    logger.info(
                                        "upwind_enterprises_extracted",
                                        count=len(enterprises),
                                        from_visual=visual.get("id", "")
                                    )
                                    break
        
        # 记录收集到的图表信息
        logger.info(
            "chart_info_collected",
            weather_count=len(chart_info_by_section["weather"]),
            component_count=len(chart_info_by_section["component"]),
            other_count=len(chart_info_by_section["other"])
        )
        
        # 构建报告生成提示词
        prompt = self._build_report_prompt(
            task_description,
            context,
            expert_summaries,
            upwind_enterprises=upwind_enterprises,
            chart_info_by_section=chart_info_by_section
        )
        
        # 记录发送给LLM的上下文
        logger.info(
            "report_llm_context",
            prompt_length=len(prompt),
            prompt_preview=prompt[:500] + "..." if len(prompt) > 500 else prompt,
            expert_summaries_keys=list(expert_summaries.keys()),
            upwind_count=len(upwind_enterprises)
        )
        
        try:
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                timeout=180.0,  # 报告生成需要更长超时
                max_tokens=8192  # 确保完整输出，设置较大的token限制
            )
            
            if not response:
                logger.warning("report_llm_empty_response")
                raise ValueError("LLM返回空响应")

            logger.info(
                "report_llm_response",
                response_length=len(response),
                response_preview=response[:1000] + "..." if len(response) > 1000 else response
            )

            # 【Markdown格式处理】处理响应文本
            if response:
                # 解析结论章节（必须有专家章节内容）
                conclusion_content = ""
                
                # 先尝试匹配完整的标识对
                conclusion_match = re.search(
                    r'\[CONCLUSION_SECTION_START\](.*?)\[CONCLUSION_SECTION_END\]',
                    response,
                    re.DOTALL
                )
                
                if conclusion_match:
                    conclusion_content = conclusion_match.group(1).strip()
                    logger.info("conclusion_section_extracted", content_length=len(conclusion_content))
                else:
                    # 如果没有结束标识，提取从开始标识到响应末尾的内容
                    start_match = re.search(
                        r'\[CONCLUSION_SECTION_START\](.*)',
                        response,
                        re.DOTALL
                    )
                    if start_match:
                        conclusion_content = start_match.group(1).strip()
                        logger.warning(
                            "conclusion_section_end_marker_missing",
                            content_length=len(conclusion_content),
                            response_length=len(response)
                        )
                    else:
                        logger.warning("conclusion_section_markers_not_found", response_preview=response[:500])
                
                # 去除标识（如果存在）
                if conclusion_content:
                    conclusion_content = re.sub(r'\[CONCLUSION_SECTION_START\]', '', conclusion_content)
                    conclusion_content = re.sub(r'\[CONCLUSION_SECTION_END\]', '', conclusion_content)
                    conclusion_content = conclusion_content.strip()
                
                # 提取标题（从markdown中提取第一个# 标题）
                title_match = re.search(r'^#\s+(.+)$', response.strip(), re.MULTILINE)
                report_title = title_match.group(1) if title_match else "污染溯源分析报告"

                # 提取置信度（查找markdown中的置信度数值）
                confidence_patterns = [
                    r'置信度[:：]\s*([\d.]+)',
                    r'confidence[:：]\s*([\d.]+)',
                    r'([\d.]+)\s*%?\s*置信度',
                    r'分析置信度[:：]\s*([\d.]+)'
                ]
                confidence = 0.85  # 默认值
                for pattern in confidence_patterns:
                    conf_match = re.search(pattern, response)
                    if conf_match:
                        conf_val = float(conf_match.group(1))
                        if conf_val > 1:
                            conf_val = conf_val / 100
                        confidence = conf_val
                        break

                # 提取关键发现（查找markdown中的要点或列表）
                key_findings = []
                # 查找"关键发现"、"主要发现"等段落
                findings_sections = re.findall(r'(?:关键发现|主要发现|重要发现)[:：]?\s*\n((?:- .+\n?)+)', response, re.MULTILINE)
                if findings_sections:
                    for section in findings_sections:
                        findings = re.findall(r'- (.+)', section)
                        key_findings.extend(findings[:3])

                # 查找执行摘要中的结论
                conclusion_section = re.search(r'### 执行摘要.*?\n((?:.+\n)+)', response, re.MULTILINE | re.DOTALL)
                if conclusion_section:
                    lines = conclusion_section.group(1).strip().split('\n')
                    for line in lines[:3]:
                        line = line.strip()
                        if line and not line.startswith('#') and not line.startswith('**'):
                            key_findings.append(line)

                # 提取建议措施（查找markdown中的措施列表）
                recommendations = []
                measures_sections = re.findall(r'(?:控制建议|应急措施|建议措施)[:：]?\s*\n((?:- .+\n?)+)', response, re.MULTILINE)
                if measures_sections:
                    for section in measures_sections:
                        measures = re.findall(r'- (.+)', section)
                        recommendations.extend(measures[:3])

                # 提取主要结论
                main_conclusion = ""
                conclusion_match = re.search(r'(?:主要结论|结论)[:：]\s*(.+)', response)
                if conclusion_match:
                    main_conclusion = conclusion_match.group(1).strip()

                # 组装章节内容
                sections = []
                
                # 必须有专家生成的章节内容
                if not expert_sections:
                    logger.error(
                        "report_generation_failed",
                        reason="缺少专家章节内容",
                        available_experts=list(expert_results.keys()),
                        expert_statuses={k: v.status for k, v in expert_results.items()}
                    )
                    raise ValueError("报告生成失败：缺少专家章节内容，无法生成报告")
                
                # 按顺序添加：气象分析、组分分析
                # 【修复】直接使用专家生成的章节内容（包含LLM生成的图片URL引用）
                # 图片URL格式：![标题](/api/image/xxx)
                for section_type in ["weather", "component"]:
                    if section_type in expert_sections:
                        section_content = expert_sections[section_type]
                        # 直接使用章节内容（包含LLM生成的图片URL引用）
                        sections.append({
                            "type": section_type,
                            "name": "气象分析" if section_type == "weather" else "组分分析",
                            "markdown_content": section_content
                        })
                        logger.info(
                            "section_added",
                            section_type=section_type,
                            content_length=len(section_content),
                            has_image_url="/api/image/" in section_content
                        )
                    else:
                        logger.warning(
                            "section_missing",
                            section_type=section_type,
                            available_sections=list(expert_sections.keys())
                        )
                
                # 添加结论与建议章节
                if conclusion_content and len(conclusion_content) > 50:
                    sections.append({
                        "type": "conclusion",
                        "name": "结论与建议",
                        "markdown_content": conclusion_content
                    })
                    logger.info("conclusion_section_added", content_length=len(conclusion_content))
                else:
                    logger.warning("conclusion_section_missing", content_length=len(conclusion_content) if conclusion_content else 0)
                
                # 构造报告内容
                report = ReportContent(
                    title=report_title,
                    summary=response[:500] + "..." if len(response) > 500 else response,  # 前500字符作为摘要
                    background="已整合气象、组分等多维度数据分析结果",
                    sections=sections,
                    upwind_enterprises=upwind_enterprises,  # 使用原始企业数据
                    conclusions=key_findings[:3] if key_findings else [main_conclusion] if main_conclusion else [],
                    recommendations=recommendations[:3],
                    limitations=[],
                    confidence=confidence,
                    metadata={
                        "title": report_title,
                        "confidence_level": confidence,
                        "format": "markdown",
                        "expert_summaries": expert_summaries,
                        "has_expert_sections": bool(expert_sections)
                    }
                )

                logger.info(
                    "report_parsed_successfully",
                    title=report.title,
                    confidence=confidence,
                    sections_count=len(report.sections),
                    has_sections=bool(report.sections),
                    key_findings_count=len(report.conclusions),
                    recommendations_count=len(report.recommendations)
                )

                # 如果没有提取到建议，使用默认建议
                if not report.recommendations:
                    report.recommendations = [
                        "加强上风向企业监管",
                        "实施区域联防联控",
                        "持续监测空气质量变化"
                    ]

                return report
                
        except Exception as e:
            logger.error("report_generation_llm_failed", error=str(e))
        
        return ReportContent(
            title="报告生成失败",
            summary="无法生成综合报告",
            confidence=0.0
        )
    
    def _extract_chart_title(self, visual: Dict) -> str:
        """从visual中提取图表标题"""
        # 优先从payload.title获取
        if isinstance(visual, dict):
            payload = visual.get("payload", {})
            if isinstance(payload, dict):
                title = payload.get("title", "")
                if title:
                    return title
            
            # 其次从visual.title获取
            title = visual.get("title", "")
            if title:
                return title
        
        return "分析图表"

    def _insert_charts_into_section(
        self,
        section_content: str,
        charts: List[Dict],
        section_type: str,
        expert_results: Dict[str, ExpertResult] = None
    ) -> str:
        """
        将图表动态插入到章节内容中的关键位置

        Args:
            section_content: 章节markdown内容（包含[WEATHER_SECTION_START]等标记）
            charts: 该章节对应的图表列表
            section_type: 章节类型（weather/component）
            expert_results: 专家结果（用于获取实际图片数据）

        Returns:
            包含插入图表的章节内容
        """
        if not charts:
            logger.debug(
                "no_charts_to_insert",
                section_type=section_type,
                reason="empty_charts_list"
            )
            return section_content

        logger.info(
            "inserting_charts_into_section",
            section_type=section_type,
            chart_count=len(charts),
            section_content_length=len(section_content)
        )

        # 【修复】更灵活的正则表达式匹配章节标题
        # 尝试多种匹配模式
        section_title_match = None
        section_start_marker = f"[{section_type.upper()}_SECTION_START]"

        # 模式1：直接匹配标记后的第一个##标题
        section_title_match = re.search(
            rf'{re.escape(section_start_marker)}\s*\n(##\s+.+?)(?:\n|$)',
            section_content,
            re.MULTILINE
        )

        # 模式2：如果模式1失败，尝试匹配任意位置的最早##标题
        if not section_title_match:
            section_title_match = re.search(
                r'(##\s+.+?)(?:\n|$)',
                section_content,
                re.MULTILINE
            )

        if not section_title_match:
            logger.warning(
                "section_title_not_found",
                section_type=section_type,
                has_start_marker=section_start_marker in section_content,
                content_preview=section_content[:200]
            )
            # 如果没找到标题标记，直接在内容开头插入
            charts_text = self._format_charts_for_section(charts, section_type, 1, expert_results)
            return f"{charts_text}\n\n{section_content}"

        # 找到标题位置，在标题后插入图表
        title_position = section_title_match.end(1)  # 标题结束位置
        charts_text = self._format_charts_for_section(charts, section_type, 1, expert_results)

        # 在标题后插入图表
        enhanced_content = (
            section_content[:title_position] +
            f"\n\n{charts_text}" +
            section_content[title_position:]
        )

        logger.info(
            "charts_inserted_successfully",
            section_type=section_type,
            charts_count=len(charts),
            original_length=len(section_content),
            enhanced_length=len(enhanced_content)
        )

        return enhanced_content

    def _format_charts_for_section(
        self,
        charts: List[Dict],
        section_type: str,
        start_index: int,
        expert_results: Dict[str, ExpertResult] = None
    ) -> str:
        """
        为特定章节格式化图表（生成markdown图片URL引用）

        Args:
            charts: 图表列表
            section_type: 章节类型
            start_index: 起始图表编号
            expert_results: 专家结果（用于获取实际图片数据）

        Returns:
            格式化的图表markdown文本（包含图片URL）
        """
        if not charts:
            return ""

        section_name = "气象分析" if section_type == "weather" else "组分分析"
        lines = [f"### {section_name}相关图表\n"]

        # 构建backend_host（用于生成完整URL）
        from config.settings import settings
        backend_host = getattr(settings, "BACKEND_HOST", "http://localhost:8000")

        for i, chart in enumerate(charts, start=start_index):
            title = chart.get("title", "分析图表")
            chart_type = chart.get("type", "")

            # 【调试】记录chart的详细信息
            logger.info(
                "[DEBUG_FORMAT_CHART]",
                chart_index=i,
                chart_id=chart.get("id"),
                chart_id_type=type(chart.get("id")).__name__,
                chart_image_id=chart.get("image_id"),
                chart_image_url=chart.get("image_url"),
                chart_title=title[:50]
            )

            # 【关键修复】优先使用visual的原始ID，确保与前端图表引用ID一致
            chart_id = chart.get("id", "")

            # ⚠️ 如果chart_id仍然是字典，说明前面的修复没有生效
            if isinstance(chart_id, dict):
                logger.error(
                    "[BUG] chart_id_is_still_dict",
                    chart_index=i,
                    chart_id_keys=list(chart_id.keys()),
                    chart_id_preview=str(chart_id)[:200]
                )
                # 强制提取字符串ID
                if "image_id" in chart_id:
                    chart_id = chart_id["image_id"]
                elif "id" in chart_id and isinstance(chart_id["id"], str):
                    chart_id = chart_id["id"]
                else:
                    chart_id = f"chart_{i}"

            if not chart_id:
                # 只有在真正没有ID时才使用fallback，但仍保持简洁格式避免ID不匹配
                chart_id = f"chart_{i}"
                logger.warning(
                    "chart_id_missing_using_fallback",
                    fallback_id=chart_id,
                    chart_index=i,
                    chart_title=title
                )

            # 尝试从chart中获取预生成的URL
            image_url = chart.get("image_url", "")
            markdown_image = chart.get("markdown_image", "")

            # 【调试】记录URL获取情况
            logger.info(
                "[DEBUG_FORMAT_CHART_URL]",
                chart_index=i,
                has_image_url=bool(image_url),
                has_markdown_image=bool(markdown_image),
                image_url_type=type(image_url).__name__,
                image_url_preview=str(image_url)[:100] if image_url else "",
                markdown_image_preview=str(markdown_image)[:100] if markdown_image else ""
            )

            # 如果没有预生成的URL，构建标准URL
            if not image_url:
                image_id = chart.get("image_id") or chart_id

                # 【调试】记录image_id获取情况
                logger.info(
                    "[DEBUG_FORMAT_CHART_BUILD_URL]",
                    chart_index=i,
                    image_id=image_id,
                    image_id_type=type(image_id).__name__,
                    chart_id=chart_id,
                    chart_id_type=type(chart_id).__name__
                )

                # 【修复】使用相对路径，让前端通过vite代理或同域访问
                image_url = f"/api/image/{image_id}"

            # 【调试】记录最终URL
            logger.info(
                "[DEBUG_FORMAT_CHART_FINAL_URL]",
                chart_index=i,
                final_image_url=image_url[:150]
            )

            # 使用markdown_image（如果有的话），否则构建标准Markdown
            if markdown_image:
                markdown_link = markdown_image
            else:
                markdown_link = f"![{title}]({image_url})"

            lines.append(f"**图{i}：{title}**")
            lines.append(markdown_link)
            lines.append(f"*数据来源：{self._get_chart_data_source(chart)}*")
            lines.append("")

        return "\n".join(lines)

    def _get_chart_data_source(self, chart: Dict) -> str:
        """
        获取图表的数据来源描述

        优先从 chart.meta.generator 获取工具名称，避免关键词匹配
        """
        # 优先从 meta.generator 获取工具名称
        meta = chart.get("meta", {})
        generator = meta.get("generator", "")

        if generator:
            # 根据工具名称直接判断数据来源
            if generator == "analyze_trajectory_sources":
                return "HYSPLIT后向轨迹分析"
            elif generator in ["calculate_pm_pmf", "calculate_vocs_pmf"]:
                return "PMF源解析分析"
            elif generator == "get_jining_regular_stations":
                return "时间序列监测数据"
            elif generator in ["get_vocs_data", "get_pm25_component", "get_pm25_ionic", "get_pm25_carbon"]:
                return "组分数据分析"
            elif generator in ["calculate_reconstruction", "calculate_carbon", "calculate_crustal", "calculate_soluble", "calculate_trace"]:
                return "组分分析结果"
            elif generator == "smart_chart_generator":
                return "智能图表分析"

        # 降级：根据图表类型判断
        chart_type = chart.get("type", "")
        if chart_type == "timeseries":
            return "时间序列监测数据"
        elif chart_type == "pie":
            return "组分占比分析"
        elif chart_type in ["bar", "line"]:
            return "数据分析结果"

        # 默认返回
        return "数据分析结果"

    def _get_chart_image_data(self, chart: Dict, expert_results: Dict[str, ExpertResult]) -> Optional[str]:
        """
        从专家结果中获取图表的实际图片数据（base64）

        Args:
            chart: 图表信息（包含id、title等）
            expert_results: 专家结果字典

        Returns:
            base64编码的图片数据，如果没有找到返回None
        """
        chart_id = chart.get("id", "")
        if not chart_id:
            logger.debug(
                "chart_image_data_search_failed",
                reason="empty_chart_id",
                chart_id=chart_id
            )
            return None

        # 在所有专家结果中查找匹配的图表
        for expert_type, expert_result in expert_results.items():
            if expert_result.status not in ["success", "partial"]:
                continue

            if not expert_result.tool_results:
                continue

            for tool_result in expert_result.tool_results:
                result_data = tool_result.get("result")
                if not result_data or not isinstance(result_data, dict):
                    continue

                # 从visuals中查找匹配的图表
                visuals = result_data.get("visuals", [])
                if not visuals or not isinstance(visuals, list):
                    continue

                for visual in visuals:
                    if not isinstance(visual, dict):
                        continue

                    # 匹配图表ID
                    visual_id = visual.get("id", "")
                    if visual_id != chart_id:
                        continue

                    logger.info(
                        "chart_id_matched",
                        chart_id=chart_id,
                        expert_type=expert_type,
                        tool_name=tool_result.get("tool", ""),
                        visual_id=visual_id
                    )

                    # 【核心修复】优先从visual的data字段获取图片数据
                    visual_data = visual.get("data")
                    if visual_data:
                        logger.info(
                            "visual_data_found",
                            chart_id=chart_id,
                            data_type=type(visual_data).__name__,
                            data_preview=str(visual_data)[:100] if isinstance(visual_data, str) else "not_string"
                        )
                        # 如果是完整的data URL格式（data:image/png;base64,xxx）
                        if isinstance(visual_data, str) and visual_data.startswith("data:image/"):
                            # 提取base64部分
                            base64_part = visual_data.split(",", 1)[1] if "," in visual_data else visual_data
                            logger.info(
                                "image_extracted_from_data_url",
                                chart_id=chart_id,
                                base64_length=len(base64_part)
                            )
                            return base64_part
                        # 如果直接是base64字符串
                        elif isinstance(visual_data, str):
                            logger.info(
                                "image_extracted_from_base64",
                                chart_id=chart_id,
                                base64_length=len(visual_data)
                            )
                            return visual_data
                        # 【新增】如果是字典格式（交互式图表配置），返回None使用占位标记
                        elif isinstance(visual_data, dict):
                            logger.info(
                                "interactive_chart_detected",
                                chart_id=chart_id,
                                data_type="dict",
                                chart_title=visual.get("title", "")
                            )
                            # 返回None，让调用者使用ECHARTS_PLACEHOLDER标记
                            return None

                    # 从visual的payload中提取图片数据
                    payload = visual.get("payload", {})
                    if isinstance(payload, dict):
                        # 检查是否有直接的图片数据
                        if "image" in payload:
                            return payload["image"]
                        if "image_data" in payload:
                            return payload["image_data"]
                        if "base64" in payload:
                            return payload["base64"]

                        # 检查data字段中是否包含图片
                        data = payload.get("data", {})
                        if isinstance(data, dict):
                            if "image" in data:
                                return data["image"]
                            if "image_data" in data:
                                return data["image_data"]
                            if "base64" in data:
                                return data["base64"]
                            # 【新增】如果data是字典格式（交互式图表配置），返回None使用占位标记
                            else:
                                logger.info(
                                    "payload_data_dict_detected",
                                    chart_id=chart_id,
                                    data_type="dict_in_payload",
                                    data_keys=list(data.keys()) if isinstance(data, dict) else []
                                )
                                # 返回None，让调用者使用ECHARTS_PLACEHOLDER标记
                                return None
                        # 检查data字段是否为字符串（可能是完整的data URL）
                        elif isinstance(data, str) and data.startswith("data:image/"):
                            base64_part = data.split(",", 1)[1] if "," in data else data
                            return base64_part

                    # 也检查visual顶层
                    if "image" in visual:
                        return visual["image"]
                    if "image_data" in visual:
                        return visual["image_data"]
                    if "base64" in visual:
                        return visual["base64"]

        logger.debug(
            "chart_image_data_not_found",
            chart_id=chart_id,
            searched_experts=list(expert_results.keys())
        )
        return None

    def _determine_chart_section(self, visual: Dict, expert_type: str) -> str:
        """确定图表所属章节"""
        # 从meta中获取
        payload = visual.get("payload", {}) if isinstance(visual, dict) else {}
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        
        # 也检查visual的meta
        if not meta and isinstance(visual, dict):
            meta = visual.get("meta", {})
        
        # 方法1：从meta中获取expert信息
        expert_tag = str(
            meta.get("expert") or
            meta.get("generator") or
            meta.get("scenario") or
            expert_type or
            ""
        ).lower()
        
        # 方法2：从数据来源（data_id）推断（当expert_type是viz时）
        data_id = ""
        # 优先从我们添加的data_id字段获取（在收集图表信息时添加的）
        if isinstance(visual, dict):
            data_id = visual.get("data_id") or ""
        # 从payload.meta中获取（smart_chart_generator在这里设置source_data_id）
        if not data_id and isinstance(payload, dict):
            payload_meta = payload.get("meta", {})
            if isinstance(payload_meta, dict):
                data_id = payload_meta.get("data_id") or payload_meta.get("source_data_id") or ""
            # 也检查payload.metadata（有些图表可能用metadata）
            payload_metadata = payload.get("metadata", {})
            if not data_id and isinstance(payload_metadata, dict):
                data_id = payload_metadata.get("data_id") or payload_metadata.get("source_data_id") or ""
            # 也检查payload顶层
            if not data_id:
                data_id = payload.get("data_id") or payload.get("source_data_id") or ""
        # 从visual的meta中获取
        if not data_id and isinstance(meta, dict):
            data_id = meta.get("data_id") or meta.get("source_data_id") or ""
        
        data_id_lower = str(data_id).lower()
        
        # 根据数据来源判断分类
        if data_id:
            # 气象相关数据
            if any(keyword in data_id_lower for keyword in [
                "meteorology", "trajectory", "气象", "轨迹", "风速", "风向", "边界层"
            ]):
                logger.debug("chart_classified_by_data_id", data_id=data_id, section="weather")
                return "weather"
            # 组分相关数据
            elif any(keyword in data_id_lower for keyword in [
                "vocs", "pmf", "obm", "component", "组分", "源解析", "贡献", "air_quality", "regional"
            ]):
                logger.debug("chart_classified_by_data_id", data_id=data_id, section="component")
                return "component"
        
        # 根据expert_tag判断
        if "weather" in expert_tag or "气象" in expert_tag:
            return "weather"
        elif "component" in expert_tag or "组分" in expert_tag:
            return "component"
        else:
            # 如果都没有，记录调试信息
            logger.debug(
                "chart_classified_as_other",
                expert_type=expert_type,
                expert_tag=expert_tag,
                data_id=data_id,
                visual_keys=list(visual.keys()) if isinstance(visual, dict) else []
            )
            return "other"
    
    def _format_charts_for_prompt(
        self,
        charts: List[Dict],
        section_name: str,
        start_index: int
    ) -> str:
        """格式化图表列表供LLM使用（使用URL直接引用格式）"""
        if not charts:
            return ""

        lines = [f"{section_name}章节图表列表：\n"]

        # 构建backend_host（用于生成完整URL）
        from config.settings import settings
        backend_host = getattr(settings, "BACKEND_HOST", "http://localhost:8000")

        # 直接输出所有图表，使用Markdown URL格式
        for i, chart in enumerate(charts, start=start_index):
            title = chart.get("title", f"图表{i}")
            chart_type = chart.get("type", "")
            chart_id = chart.get("id", "")

            # 尝试从chart中获取image_url或markdown_image
            image_url = chart.get("image_url", "")
            markdown_image = chart.get("markdown_image", "")

            # 如果没有预生成的URL，构建标准URL
            if not image_url:
                url_id = chart.get("image_id") or chart_id or f"chart_{i}"
                # 【修复】使用相对路径，让前端通过vite代理或同域访问
                image_url = f"/api/image/{url_id}"

            # 使用markdown_image（如果有的话），否则构建标准Markdown
            if markdown_image:
                markdown_link = markdown_image
            else:
                markdown_link = f"![{title}]({image_url})"

            # 输出图表信息（包含ID、标题和Markdown代码）
            lines.append(f"**图{i}**：{title}")
            lines.append(f"   - ID: `{chart_id}`")
            lines.append(f"   - 类型: `{chart_type}`")
            lines.append(f"   - Markdown代码: `{markdown_link}`")
            lines.append("")

        return "\n".join(lines)
    
    def _build_report_prompt(
        self,
        task_description: str,
        context: Dict[str, Any],
        expert_summaries: Dict[str, Dict],
        upwind_enterprises: List[Dict] = None,
        chart_info_by_section: Dict[str, List] = None
    ) -> str:
        """构建专业溯源分析报告提示词"""

        location = context.get("location", "目标区域")
        time_range = ""
        if context.get("start_time") and context.get("end_time"):
            time_range = f"{context['start_time'][:10]}至{context['end_time'][:10]}"
        pollutants = "、".join(context.get("pollutants", [])) or "污染物"

        expert_text = json.dumps(expert_summaries, ensure_ascii=False, indent=2)

        # 构建上风向企业清单文本
        upwind_enterprises_text = ""
        if upwind_enterprises:
            upwind_enterprises_text = self._format_upwind_enterprises(upwind_enterprises)
        
        # 格式化图表信息
        chart_info_by_section = chart_info_by_section or {}
        weather_charts_text = self._format_charts_for_prompt(
            chart_info_by_section.get("weather", []),
            section_name="气象分析",
            start_index=1
        )
        component_charts_text = self._format_charts_for_prompt(
            chart_info_by_section.get("component", []),
            section_name="组分分析",
            start_index=len(chart_info_by_section.get("weather", [])) + 1
        )
        other_charts_text = self._format_charts_for_prompt(
            chart_info_by_section.get("other", []),
            section_name="其他分析",
            start_index=len(chart_info_by_section.get("weather", [])) + 
                        len(chart_info_by_section.get("component", [])) + 1
        )
        
        # 在Prompt中添加图表信息部分
        charts_section = f"""
## 可用图表列表

### 气象分析章节图表
{weather_charts_text if weather_charts_text else "暂无图表"}

### 组分分析章节图表
{component_charts_text if component_charts_text else "暂无图表"}

### 其他分析章节图表
{other_charts_text if other_charts_text else "暂无图表"}

## 图表引用要求（重要）

在生成报告时，请：
1. **直接使用Markdown图片格式**：`![图表标题](/api/image/图表ID)`
2. **为每个图表提供1-2句说明**：说明图表要表达的核心观点
3. **图表编号连续**：按章节顺序编号（气象分析从图1开始，组分分析继续编号）
4. **图表说明要自然流畅**：与章节内容上下文呼应，不要显得机械化

例如：
```markdown
## 气象分析

[概述段落...]

![NOAA HYSPLIT Backward轨迹分析](/api/image/trajectory_xxx)
轨迹分析显示污染物的主要传输路径来自西北方向，有助于识别潜在污染源区域。

![新兴上风向企业分布图](/api/image/upwind_xxx)
企业分布图反映了上风向潜在污染源的空间分布特征，结合距离和风向信息，有助于定位重点监管目标。

[详细分析...]
```
"""

        # 简化提示词模板
        prompt_template = """你是大气污染溯源分析专家。请综合专家分析结果生成Markdown格式的溯源报告。

## 分析任务
TASK_DESCRIPTION_PLACEHOLDER

## 背景信息
- **地点**：LOCATION_PLACEHOLDER
- **时间**：TIME_RANGE_PLACEHOLDER
- **污染物**：POLLUTANTS_PLACEHOLDER

## 专家分析结论
EXPERT_TEXT_PLACEHOLDER

## 上风向企业TOP10
UPWIND_ENTERPRISES_TEXT_PLACEHOLDER

CHARTS_SECTION_PLACEHOLDER

## 报告要求

报告中已经包含专家生成的章节内容（气象分析、组分分析），你只需要生成"结论与建议"章节。

## 语言风格和可读性要求

1. **章节概述**：
   - 每个主要分析章节（气象分析、组分分析等）开头要有2-3段概述
   - 概述要通俗易懂，避免技术术语堆砌
   - 突出核心观点和关键发现
   - 控制在150-200字

2. **图表说明**：
   - 在引用图表时，提供1-2句自然流畅的说明
   - 说明要表达图表的核心观点，与上下文呼应
   - 避免"该图展示了..."、"如图所示"等机械化表述
   - 使用更自然的表达，如"轨迹分析显示..."、"企业分布图反映了..."

3. **整体风格**：
   - 使用自然流畅的中文表达
   - 避免机械化、模板化的表述
   - 符合专业报告但易于理解的风格
   - 每个结论都要有数据支撑，但表达要通俗

4. **结构要求**：
   - 使用清晰的Markdown结构
   - 章节标题使用##，子标题使用###
   - 图表引用使用"图X：标题"格式，紧跟说明文字
   - 避免重复的标题和冗余的过渡段落

【输出格式要求】
- 使用Markdown格式输出
- 包含标题、列表、表格等Markdown语法
- 突出重点内容和关键数据
- 便于前端页面渲染和阅读
- 总篇幅控制在1500-2000字

【数据要求】
- 包含具体的数值、比例、时间等定量信息
- 标注数据来源和置信度
- 区分高/中/低置信度结论

记住：你是在为环境管理部门和应急决策者提供专业分析报告，重点是实用性和可操作性，每个结论都要有数据支撑。

## 输出格式要求（重要）

报告中已经包含专家生成的章节内容（气象分析、组分分析），请只生成"结论与建议"章节，使用以下格式：

[CONCLUSION_SECTION_START]
## 结论与建议

### 主要结论
[3-5条主要结论，每条1-2句，包含具体数据支撑]

### 控制建议
[3-5条控制建议，每条1-2句，具体可操作]

[CONCLUSION_SECTION_END]

**必须包含所有预设标识**：[CONCLUSION_SECTION_START] 和 [CONCLUSION_SECTION_END]"""

        # 使用字符串替换
        prompt = prompt_template.replace("TASK_DESCRIPTION_PLACEHOLDER", task_description)
        prompt = prompt.replace("LOCATION_PLACEHOLDER", location)
        prompt = prompt.replace("TIME_RANGE_PLACEHOLDER", time_range)
        prompt = prompt.replace("POLLUTANTS_PLACEHOLDER", pollutants)
        prompt = prompt.replace("EXPERT_TEXT_PLACEHOLDER", expert_text)
        prompt = prompt.replace("UPWIND_ENTERPRISES_TEXT_PLACEHOLDER",
                               upwind_enterprises_text if upwind_enterprises_text else "暂无上风向企业分析数据")
        prompt = prompt.replace("CHARTS_SECTION_PLACEHOLDER", charts_section)

        return prompt
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """解析JSON响应"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                try:
                    return json.loads(response[start:end].strip())
                except json.JSONDecodeError:
                    pass
        
        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end+1])
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _format_upwind_enterprises(self, enterprises: List[Dict]) -> str:
        """格式化上风向企业清单供LLM分析（仅TOP 10）"""
        if not enterprises:
            return "暂无上风向企业数据"
        
        # 按贡献度排序
        sorted_enterprises = sorted(
            enterprises,
            key=lambda x: (x.get("score_norm", 0) or 0, x.get("hit_ratio", 0) or 0),
            reverse=True
        )
        
        # 只保留TOP 10
        top_enterprises = sorted_enterprises[:10]
        
        lines = [f"共发现 {len(enterprises)} 个上风向企业，以下为TOP 10：\n"]
        
        for i, ent in enumerate(top_enterprises, 1):
            name = ent.get("name", "未知企业")
            industry = ent.get("industry", "未知行业")
            distance = ent.get("distance_km", 0)
            tier = ent.get("tier", "")
            score = ent.get("score_norm", 0) or ent.get("score_sum", 0) or 0
            hit_ratio = ent.get("hit_ratio", 0) or 0
            
            # 风险等级
            tier_label = {"hi": "高风险", "mid": "中风险", "low": "低风险"}.get(tier, "")
            tier_str = f" [{tier_label}]" if tier_label else ""
            
            lines.append(
                f"{i}. {name}{tier_str} | {industry} | {distance:.1f}km | 贡献:{score:.3f}\n"
            )
        
        return "\n".join(lines)
