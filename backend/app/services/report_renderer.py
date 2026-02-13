"""
报告渲染器 - LLM生成分析部分，整合数据生成最终报告
场景2核心组件
"""
from typing import Dict, Any, List, Optional
import logging

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

class ReportRenderer:
    """报告渲染器 - 基于模板和数据生成最终报告"""

    # ======================================================================
    # 方案B（结构化拆解）0-regex 支持：Markdown分段工具
    # ======================================================================

    def _split_by_h2(self, md: str) -> tuple[str, List[Dict[str, str]]]:
        """
        按Markdown二级标题（'## '）分段，不使用任何正则。

        Returns:
            (preamble, sections)
            - preamble: 第一个'## '之前的文本
            - sections: [{"title": "...", "content": "..."}]
        """
        if not md:
            return "", []

        lines = md.splitlines()
        preamble_lines: List[str] = []
        sections: List[Dict[str, str]] = []

        current_title: Optional[str] = None
        current_lines: List[str] = []
        in_sections = False

        def flush_section():
            nonlocal current_title, current_lines
            if current_title is None:
                return
            sections.append({
                "title": current_title,
                "content": "\n".join(current_lines).strip()
            })
            current_title = None
            current_lines = []

        for line in lines:
            if line.startswith("## "):
                in_sections = True
                flush_section()
                current_title = line[3:].strip()
                current_lines = []
                continue

            if not in_sections:
                preamble_lines.append(line)
            else:
                current_lines.append(line)

        flush_section()
        return "\n".join(preamble_lines).strip(), sections

    def _join_by_h2(self, preamble: str, sections: List[Dict[str, str]]) -> str:
        """将 _split_by_h2 的结构拼回Markdown，不使用正则。"""
        parts: List[str] = []
        if preamble and preamble.strip():
            parts.append(preamble.strip())

        for section in sections:
            title = (section.get("title") or "").strip()
            content = (section.get("content") or "").strip()
            if not title:
                continue
            parts.append(f"## {title}")
            if content:
                parts.append(content)

        return "\n\n".join(parts).strip() + "\n"

    async def render(
        self,
        template: str,
        structure: Dict[str, Any],
        data: Dict[str, Any],
        target_time_range: Dict[str, Any],
        is_annotated: bool = False
    ) -> str:
        """
        渲染最终报告

        Args:
            template: 模板内容
            structure: 报告结构
            data: 整理后的数据
            target_time_range: 目标时间范围
            is_annotated: 是否为标注模板

        Returns:
            str: 渲染后的Markdown报告
        """
        logger.info("Rendering final report")

        if is_annotated:
            # 方案C：标注模板渲染
            return await self._render_annotated_template(
                template, data, target_time_range
            )
        else:
            # 方案B：结构化拆解渲染
            return await self._render_structured_template(
                template, structure, data, target_time_range
            )

    async def _render_structured_template(
        self,
        template: str,
        structure: Dict[str, Any],
        data: Dict[str, Any],
        time_range: Dict[str, Any]
    ) -> str:
        """
        渲染结构化模板（方案B）

        Args:
            template: 原始模板
            structure: 报告结构
            data: 数据
            time_range: 时间范围

        Returns:
            str: 渲染后的报告
        """
        logger.info("Rendering structured template (方案B, no-regex)")

        rendered = template or ""

        # 1) 时间范围：仅做简单字符串替换（不使用正则）
        time_display = time_range.get("display") or f"{time_range.get('start', '')}至{time_range.get('end', '')}"
        if "1-6月" in rendered and time_display:
            rendered = rendered.replace("1-6月", time_display)
        if "{{time_range.display}}" in rendered and time_display:
            rendered = rendered.replace("{{time_range.display}}", time_display)

        # 2) 按'## '分段后做标题级替换（不使用正则）
        preamble, sections = self._split_by_h2(rendered)
        section_map = {s["title"]: s for s in sections if s.get("title")}

        for section in data.get("sections", []) or []:
            section_title = section.get("title") or ""
            if not section_title:
                continue
            section_data = section.get("data", []) or []
            section_content = await self._generate_section_content(section_title, section_data, time_range)

            if section_title in section_map:
                section_map[section_title]["content"] = section_content
            else:
                sections.append({"title": section_title, "content": section_content})

        rendered = self._join_by_h2(preamble, sections)

        # 3) 排名：仅做显式占位符替换（不使用正则）
        for ranking in data.get("rankings", []) or []:
            ranking_content = self._render_ranking(ranking)
            if ranking_content:
                rendered = rendered.replace("前5市是{{best_5_cities}}", ranking_content)

        return rendered

    async def _render_annotated_template(
        self,
        template: str,
        data: Dict[str, Any],
        time_range: Dict[str, Any]
    ) -> str:
        """
        渲染标注模板（方案C）

        Args:
            template: 标注模板
            data: 数据
            time_range: 时间范围

        Returns:
            str: 渲染后的报告
        """
        logger.info("Rendering annotated template (方案C)")

        # 方案C：本文件中不再使用任何正则。
        # 注意：方案B禁用正则不代表方案C必须禁用，但用户当前要求“0-regex”，这里也保持0-regex。
        rendered = template or ""
        rendered = self._replace_simple_placeholders(rendered, data, time_range)
        rendered = self._replace_each_blocks(rendered, data)
        rendered = self._replace_if_blocks(rendered, data)
        return rendered

    async def _generate_section_content(
        self,
        title: str,
        data_points: List[Dict[str, Any]],
        time_range: Dict[str, Any]
    ) -> str:
        """
        生成章节内容

        Args:
            title: 章节标题
            data_points: 数据点列表
            time_range: 时间范围

        Returns:
            str: 章节内容
        """
        content_lines = []

        # 生成数据描述
        for point in data_points:
            name = point.get("name", "")
            value = point.get("value", "")
            unit = point.get("unit", "")
            comparison = point.get("comparison", "")

            if value != "N/A":
                line = f"- **{name}**：{value}{unit}"
                if comparison:
                    line += f"，{comparison}"
                content_lines.append(line)

        # 生成LLM分析
        if "分析" in title or "讨论" in title:
            analysis = await self._generate_llm_analysis(data_points, time_range)
            content_lines.append("")
            content_lines.append(analysis)

        return "\n".join(content_lines)

    async def _generate_llm_analysis(
        self,
        data_points: List[Dict[str, Any]],
        time_range: Dict[str, Any]
    ) -> str:
        """
        生成LLM分析内容

        Args:
            data_points: 数据点
            time_range: 时间范围

        Returns:
            str: 分析内容
        """
        # 构建分析prompt
        prompt = self._build_analysis_prompt(data_points, time_range)

        try:
            # 调用真实LLM服务
            response = await llm_service.chat([{"role": "user", "content": prompt}])

            # 清理响应中的思维链标记
            clean_response = llm_service.clean_thinking_tags(response)

            logger.info("LLM analysis generated successfully")
            return clean_response.strip()

        except Exception as e:
            logger.error(f"LLM analysis generation failed: {str(e)}, using fallback")
            # 降级到简单分析
            return self._fallback_analysis(data_points, time_range)

    def _build_analysis_prompt(
        self,
        data_points: List[Dict[str, Any]],
        time_range: Dict[str, Any]
    ) -> str:
        """
        构建分析prompt

        Args:
            data_points: 数据点
            time_range: 时间范围

        Returns:
            str: 分析prompt
        """
        time_display = time_range.get('display', '指定时期')
        data_summary = "\n".join([
            f"- {point.get('name', '')}: {point.get('value', '')}{point.get('unit', '')}"
            for point in data_points
        ])

        prompt = f"""请基于以下空气质量数据，生成专业的中文分析内容：

时间范围：{time_display}

数据摘要：
{data_summary}

请从以下角度进行分析：
1. 空气质量总体状况评估
2. 主要污染物浓度变化趋势
3. 存在的问题和风险
4. 防控建议和措施

要求：
- 分析客观专业，数据支撑
- 逻辑清晰，条理分明
- 语言简洁，重点突出
- 建议具体可操作

请直接返回分析内容，不需要markdown格式。
"""
        return prompt

    def _fallback_analysis(
        self,
        data_points: List[Dict[str, Any]],
        time_range: Dict[str, Any]
    ) -> str:
        """
        降级分析（LLM调用失败时使用）

        Args:
            data_points: 数据点
            time_range: 时间范围

        Returns:
            str: 基础分析内容
        """
        return f"""基于{time_range.get('display', '指定时期')}的数据分析：

1. 空气质量总体状况需要持续关注
2. 各项污染物指标存在波动，建议加强监测
3. 建议加强污染防控措施，确保空气质量持续改善
"""

    def _render_table(self, table: Dict[str, Any]) -> str:
        """
        渲染表格

        Args:
            table: 表格数据

        Returns:
            str: Markdown表格
        """
        lines = []

        # 表头
        columns = table.get("columns", [])
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join(["---"] * len(columns)) + " |"

        lines.append(header)
        lines.append(separator)

        # 表格行
        rows = table.get("rows", [])
        for row in rows:
            row_data = []
            for col in columns:
                value = str(row.get(col, ""))
                row_data.append(value)
            lines.append("| " + " | ".join(row_data) + " |")

        return "\n".join(lines)

    def _render_ranking(self, ranking: Dict[str, Any]) -> str:
        """
        渲染排名

        Args:
            ranking: 排名数据

        Returns:
            str: 排名描述
        """
        items = ranking.get("items", [])
        if not items:
            return ""

        names = [item.get("name", "") for item in items]
        return "、".join(names)

    def _replace_simple_placeholders(
        self,
        template: str,
        data: Dict[str, Any],
        time_range: Dict[str, Any]
    ) -> str:
        """
        替换简单占位符 {{placeholder}}

        Args:
            template: 模板
            data: 数据
            time_range: 时间范围

        Returns:
            str: 替换后的模板
        """
        # 0-regex：仅做显式字符串替换
        display = time_range.get("display", "") if isinstance(time_range, dict) else ""
        if "{{time_range.display}}" in template and display:
            template = template.replace("{{time_range.display}}", display)
        return template

    def _replace_each_blocks(
        self,
        template: str,
        data: Dict[str, Any]
    ) -> str:
        """
        替换循环块 {{#each}}

        Args:
            template: 模板
            data: 数据

        Returns:
            str: 替换后的模板
        """
        # 0-regex：方案C循环语法暂不在此实现（建议后续引入成熟模板引擎）
        return template

    def _replace_if_blocks(
        self,
        template: str,
        data: Dict[str, Any]
    ) -> str:
        """
        替换条件块 {{#if}}

        Args:
            template: 模板
            data: 数据

        Returns:
            str: 替换后的模板
        """
        # 0-regex：方案C条件语法暂不在此实现（建议后续引入成熟模板引擎）
        return template
