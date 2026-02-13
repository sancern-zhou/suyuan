"""
docx -> markdown/text 转换工具
优先使用 mammoth（效果更接近 markdown），若不可用则使用 python-docx 退化为纯文本。
"""
import importlib.util
import importlib
import io
import logging
import re
from typing import Dict, Any
from fastapi import HTTPException


logger = logging.getLogger(__name__)


def convert_docx_to_markdown(raw_bytes: bytes) -> str:
    """
    将 docx 转为 Markdown（完整支持表格+基本格式）

    策略优先级：
    1. python-docx 增强版（推荐）：完整支持表格、标题、加粗、斜体
    2. mammoth 回退方案：格式丰富但表格会丢失
    3. 都不可用则抛出异常
    """
    # 优先方案：python-docx 增强版（支持表格+基本格式）
    docx_spec = importlib.util.find_spec("docx")
    if docx_spec is not None:
        logger.info("docx_convert_use_python_docx_enhanced")
        return _convert_with_python_docx_enhanced(raw_bytes)

    # 回退方案：mammoth（表格会丢失，但至少有内容）
    mammoth_spec = importlib.util.find_spec("mammoth")
    if mammoth_spec is not None:
        logger.warning("docx_convert_fallback_to_mammoth_tables_will_be_lost")
        mammoth = importlib.import_module("mammoth")
        with io.BytesIO(raw_bytes) as b:
            result = mammoth.convert_to_markdown(b)
            preview = (result.value or "")[:1000]
            logger.info("docx_mammoth_markdown_preview: %s", preview)
            return result.value

    # 无依赖
    logger.error("docx_convert_no_supported_library")
    raise HTTPException(
        status_code=500,
        detail="需要安装 python-docx (推荐) 或 mammoth"
    )


def _convert_with_python_docx_enhanced(raw_bytes: bytes) -> str:
    """
    使用 python-docx 按文档结构顺序转换为 Markdown

    支持功能：
    - 段落和表格的顺序保留
    - 标题级别 (Heading 1-6 → # - ######)
    - 内联格式 (加粗、斜体、加粗斜体)
    - 表格转换为标准 Markdown 表格

    参数：
        raw_bytes: docx 文件的字节内容

    返回：
        Markdown 格式的文本
    """
    docx = importlib.import_module("docx")

    with io.BytesIO(raw_bytes) as b:
        document = docx.Document(b)

        markdown_parts = []
        paragraph_count = 0
        table_count = 0

        # 关键：遍历文档 body 的原始 XML 元素，保持段落和表格的顺序
        for element in document.element.body:
            # 获取元素类型（去除 XML 命名空间前缀）
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == 'p':  # 段落
                # 找到对应的 Paragraph 对象
                para = next((p for p in document.paragraphs
                            if p._element == element), None)
                if para:
                    md_para = _paragraph_to_markdown(para)
                    if md_para:
                        markdown_parts.append(md_para)
                        paragraph_count += 1

            elif tag == 'tbl':  # 表格
                # 找到对应的 Table 对象
                table = next((t for t in document.tables
                             if t._element == element), None)
                if table:
                    md_table = _convert_table_to_markdown(table)
                    if md_table:
                        markdown_parts.append(md_table)
                        table_count += 1

        logger.info(
            "docx_convert_complete: paragraphs=%d, tables=%d",
            paragraph_count,
            table_count
        )

        result = "\n\n".join(markdown_parts)

        # 记录转换结果预览
        preview = result[:1000]
        logger.info("docx_python_docx_enhanced_preview: %s", preview)

        return result


def _paragraph_to_markdown(para) -> str:
    """
    将段落转换为 Markdown，支持标题、加粗、斜体等格式

    参数：
        para: python-docx Paragraph 对象

    返回：
        Markdown 格式的段落文本
    """
    # 处理标题样式
    style_name = para.style.name if para.style else ""
    if style_name.startswith('Heading'):
        # 提取标题级别 (Heading 1 → 1, Heading 2 → 2, ...)
        try:
            level_str = style_name.replace('Heading', '').strip()
            level = int(level_str) if level_str else 1
            level = min(max(level, 1), 6)  # 限制在 1-6 范围
        except (ValueError, AttributeError):
            level = 1
        return '#' * level + ' ' + para.text

    # 处理普通段落
    if not para.text.strip():
        return ""

    # 如果段落没有 runs（格式化片段），直接返回纯文本
    if not para.runs:
        return para.text

    # 处理内联格式（加粗、斜体）
    md_parts = []
    for run in para.runs:
        text = run.text
        if not text:
            continue

        # 检测格式属性
        is_bold = run.bold or (run.font.bold if run.font else False)
        is_italic = run.italic or (run.font.italic if run.font else False)

        # 应用 Markdown 格式标记
        if is_bold and is_italic:
            text = f'***{text}***'
        elif is_bold:
            text = f'**{text}**'
        elif is_italic:
            text = f'*{text}*'

        md_parts.append(text)

    return ''.join(md_parts)


def _convert_table_to_markdown(table) -> str:
    """
    将 python-docx Table 对象转换为标准 Markdown 表格

    处理要点：
    1. 每行独立处理，避免跨行的合并单元格检测错误
    2. 空单元格填充
    3. 列数对齐（处理不规则表格）
    4. 第一行作为表头

    参数：
        table: python-docx Table 对象

    返回：
        Markdown 格式的表格文本
    """
    if not table.rows:
        return ""

    # 收集所有行的数据
    rows_data = []

    for row_idx, row in enumerate(table.rows):
        cells_data = []
        seen_cells_in_row = set()  # 每行独立检测合并单元格

        for cell in row.cells:
            # 检测合并单元格（Word 中横向合并的单元格会共享同一个 cell 对象）
            cell_id = id(cell._element)

            # 提取单元格文本（可能包含多个段落）
            cell_text = ' '.join(
                p.text.strip()
                for p in cell.paragraphs
                if p.text.strip()
            )

            # 空单元格用一个空格占位（Markdown 表格要求）
            if not cell_text:
                cell_text = " "

            # 合并单元格特殊处理：同一行内，只在第一次遇到时添加
            # 这样可以避免横向合并的单元格重复出现
            if cell_id not in seen_cells_in_row:
                cells_data.append(cell_text)
                seen_cells_in_row.add(cell_id)

        if cells_data:  # 跳过空行
            rows_data.append(cells_data)

    if not rows_data:
        return ""

    # 计算最大列数（处理不规则表格）
    max_cols = max(len(row) for row in rows_data)

    # 补齐所有行的列数（确保表格对齐）
    for row in rows_data:
        while len(row) < max_cols:
            row.append(" ")
        # 截断多余的列（通常不会出现，但做防御性处理）
        if len(row) > max_cols:
            row[:] = row[:max_cols]

    # 构建 Markdown 表格
    md_lines = []

    # 第一行作为表头
    header_row = rows_data[0]
    md_lines.append("| " + " | ".join(header_row) + " |")

    # 分隔线（表头和数据行之间）
    separator = "| " + " | ".join(["---"] * max_cols) + " |"
    md_lines.append(separator)

    # 数据行
    for row_data in rows_data[1:]:
        md_lines.append("| " + " | ".join(row_data) + " |")

    return "\n".join(md_lines)


def sanitize_template_time_references(template_content: str) -> str:
    """
    模板时间标准化处理：将模板中的具体时间引用替换为占位符，避免LLM被历史时间误导。
    
    处理策略：
    1. 识别并替换各种时间模式（年份、月份、日期范围等）
    2. 保留时间相关的语义（如"同比"、"环比"、"去年同期"等）
    3. 使用占位符替代具体时间，让LLM只能使用目标时间范围
    
    参数:
        template_content: 原始模板内容（Markdown文本）
    
    返回:
        处理后的模板内容，所有具体时间已替换为占位符
    """
    if not template_content:
        return template_content
    
    content = template_content
    
    # 按优先级顺序替换，从最具体到最一般
    
    # 1. 替换完整日期范围（如"2025-01-01至2025-06-30"、"2025年1月1日至6月30日"）
    # 匹配：完整日期范围（最具体，优先处理）
    content = re.sub(
        r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})[日]?[至-](\d{4})[-年]?(\d{1,2})[-月]?(\d{1,2})?[日]?',
        r'【目标时间范围】',
        content
    )
    
    # 2. 替换年份+月份范围（如"2025年1-6月"、"2025年1月至6月"）
    # 匹配：年份 + 月份范围
    content = re.sub(
        r'(\d{4})年(\d{1,2})[-至](\d{1,2})月',
        r'【目标时间段】',
        content
    )
    
    # 3. 替换单个完整日期（如"2025年6月1日"、"2025-06-01"）
    # 匹配：完整日期（避免与日期范围冲突）
    content = re.sub(
        r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})[日]?',
        r'【目标日期】',
        content
    )
    
    # 4. 替换年份+单个月份（如"2025年6月"）
    # 匹配：年份 + 月份（避免与年份+月份范围冲突）
    content = re.sub(
        r'(\d{4})年(\d{1,2})月(?!同期|相比|对比)',
        r'【目标月份】',
        content
    )
    
    # 5. 替换月份范围（如"1-6月"、"1月至6月"、"1-6月份"，没有年份）
    # 匹配：月份范围（避免与年份+月份范围冲突）
    # 使用 ? 匹配可选的"份"，支持"月"和"月份"两种形式
    content = re.sub(
        r'(\d{1,2})[-至](\d{1,2})月份?',
        r'【目标月份范围】',
        content
    )

    # 6. 替换单个月份（如"6月"、"6月份"，没有年份）
    # 匹配：单独的月份（最后处理，避免与其他模式冲突）
    # 使用负向前瞻和负向后顾确保不是月份范围的一部分
    # 明确标记为【目标单月】，与【目标月份范围】区分
    content = re.sub(
        r'(?<!\d-)(\d{1,2})月份?(?!同期|相比|对比|-)',
        r'【目标单月】',
        content
    )
    
    # 7. 替换季度（如"第一季度"、"Q1"、"1季度"）
    content = re.sub(
        r'[第]?([1-4])季度|[Qq]([1-4])',
        r'【目标季度】',
        content
    )
    
    # 8. 替换半年（如"上半年"、"下半年"、"前半年"）
    content = re.sub(
        r'[上下前后]?半年',
        r'【目标半年】',
        content
    )
    
    # 9. 替换独立年份（如"2025年"、"2024年"）
    # 注意：保留"去年同期"、"上一年"、"与X年同比"等语义，只替换独立的年份
    # 策略：使用负向前瞻和负向后顾，避免替换对比关系中的年份
    
    # 先保护"与X年同比"、"和X年同比"等模式（使用临时占位符）
    protected_placeholders = {}
    placeholder_counter = 0
    
    # 匹配"与/和 + 年份 + 同比"模式（中间可能有空格或标点）
    def protect_comparison_year(match):
        nonlocal placeholder_counter
        placeholder = f"__PROTECT_YEAR_COMP_{placeholder_counter}__"
        protected_placeholders[placeholder] = match.group()
        placeholder_counter += 1
        return placeholder
    
    # 保护各种对比模式
    content = re.sub(
        r'[与和及同]\s*(\d{4})年\s*同比',
        protect_comparison_year,
        content
    )
    content = re.sub(
        r'(\d{4})年\s*同期',
        protect_comparison_year,
        content
    )
    
    # 替换其他独立年份（不在对比关系中的）
    content = re.sub(
        r'(\d{4})年(?!同期|相比|对比|度|同比)',
        r'【目标年份】',
        content
    )
    
    # 恢复被保护的模式
    for placeholder, original in protected_placeholders.items():
        content = content.replace(placeholder, original)
    
    # 记录处理情况（仅在有替换时记录）
    if content != template_content:
        # 统计替换次数（简单统计占位符出现次数）
        placeholder_count = len(re.findall(r'【目标[^】]+】', content))
        preview = content[:500]  # 只记录前500字符
        logger.info(
            "template_time_sanitized: placeholder_count=%d, preview=%s",
            placeholder_count,
            preview
        )
    
    return content

