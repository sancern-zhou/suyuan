"""
浏览器工具结果格式化器

统一处理浏览器工具的所有操作结果，确保完整数据传递给LLM。

遵循办公工具原则：显示完整结果，不截断数据。
"""

import json
from typing import Dict, Any, List
import structlog

logger = structlog.get_logger()


def format_browser_result(data: Dict[str, Any]) -> List[str]:
    """
    格式化浏览器工具的执行结果

    Args:
        data: 浏览器工具返回的data字段

    Returns:
        格式化后的字符串列表
    """
    lines = []

    # 如果data为空，返回空列表
    if not data:
        return lines

    # ========== 1. execute_js 操作结果 ==========
    if "result" in data:
        result = data["result"]
        result_type = data.get("type", "unknown")

        if isinstance(result, list) and result:
            lines.append(f"**执行结果** (共 {len(result)} 项，类型: {result_type}):")
            # 显示完整结果，不截断（办公工具原则）
            for idx, item in enumerate(result, 1):
                if isinstance(item, dict):
                    # 格式化字典项
                    lines.append(f"\n  **结果 {idx}**:")
                    for key, value in item.items():
                        lines.append(f"    {key}: {value}")
                else:
                    # 其他类型直接显示
                    lines.append(f"  **结果 {idx}**: {item}")
        elif isinstance(result, str):
            lines.append(f"**执行结果**:\n{result}")
        elif isinstance(result, (int, float, bool)):
            lines.append(f"**执行结果**: {result}")
        elif result is not None:
            # 其他类型，转换为JSON显示
            lines.append(f"**执行结果**:\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```")

    # ========== 2. 执行代码（execute_js操作） ==========
    if "code" in data:
        code = data["code"]
        code_preview = code[:200] + "..." if len(code) > 200 else code
        lines.append(f"\n**执行的代码** (长度: {len(code)} 字符):\n```javascript\n{code_preview}\n```")

    # ========== 3. 页面快照（snapshot操作） ==========
    if "snapshot" in data:
        snapshot = data["snapshot"]
        lines.append(f"\n**页面快照**:")
        lines.append(f"```\n{snapshot}\n```")

    # ========== 4. 元素引用（refs） ==========
    if "refs" in data:
        refs = data["refs"]
        if isinstance(refs, dict) and refs:
            lines.append(f"\n**元素引用** (共 {len(refs)} 个):")
            # 按顺序显示所有元素引用
            for ref_id in sorted(refs.keys()):
                ref_data = refs[ref_id]
                if isinstance(ref_data, dict):
                    role = ref_data.get("role", "unknown")
                    name = ref_data.get("name", "")
                    selector = ref_data.get("selector", "")

                    # 构建元素描述
                    lines.append(f"\n  [{ref_id}] {role}: {name}")
                    if selector:
                        lines.append(f"    选择器: {selector}")

                    # 显示重要属性
                    html_attrs = ref_data.get("html_attrs", {})
                    if html_attrs:
                        important_attrs = {}
                        # 只显示重要属性
                        for attr in ["href", "type", "id", "name", "class", "placeholder", "aria-label", "value"]:
                            if attr in html_attrs:
                                important_attrs[attr] = html_attrs[attr]

                        if important_attrs:
                            lines.append(f"    属性: {json.dumps(important_attrs, ensure_ascii=False)}")

    # ========== 5. 统计信息（stats） ==========
    if "stats" in data:
        stats = data["stats"]
        if isinstance(stats, dict):
            lines.append(f"\n**统计信息**:")
            lines.append(f"  总元素数: {stats.get('total_refs', 0)}")
            lines.append(f"  交互元素数: {stats.get('interactive_refs', 0)}")
            lines.append(f"  行数: {stats.get('lines', 0)}")
            lines.append(f"  字符数: {stats.get('chars', 0)}")

    # ========== 6. 页面信息（page_info） ==========
    if "page_info" in data:
        page_info = data["page_info"]
        lines.append(f"\n**页面信息**:")
        if "current_url" in page_info:
            lines.append(f"  URL: {page_info['current_url']}")
        if "page_title" in page_info:
            lines.append(f"  标题: {page_info['page_title']}")
        if "total_tabs" in page_info:
            lines.append(f"  标签数: {page_info['total_tabs']}")

    # ========== 7. 导航操作（navigate） ==========
    if "url" in data and "title" in data:
        # 这是navigate操作的返回结果
        url = data["url"]
        title = data["title"]
        lines.append(f"\n**导航结果**:")
        lines.append(f"  URL: {url}")
        lines.append(f"  页面标题: {title}")

    # ========== 8. 交互操作（act: click, type, scroll等） ==========
    if "action" in data and "ref" in data and "result" in data:
        # 这是act操作的返回结果
        action = data["action"]
        ref = data["ref"]
        result_msg = data["result"]
        lines.append(f"\n**交互操作**:")
        lines.append(f"  操作: {action}")
        lines.append(f"  元素: {ref}")
        lines.append(f"  结果: {result_msg}")

    # ========== 9. 等待操作（wait） ==========
    if "conditions_applied" in data:
        # 这是wait操作的返回结果
        conditions = data["conditions_applied"]
        result_msg = data.get("result", "")
        lines.append(f"\n**等待条件**:")
        if isinstance(conditions, list):
            for condition in conditions:
                lines.append(f"  - {condition}")
        if result_msg:
            lines.append(f"**结果**: {result_msg}")

    # ========== 10. 页面文本内容（text操作） ==========
    if "text" in data:
        # 页面文本内容
        text = data.get("text", "")
        length = data.get("length", 0)
        truncated = data.get("truncated", False)
        lines.append(f"\n**页面文本内容** ({length} 字符{' [已截断]' if truncated else ''}):")
        lines.append(f"```\n{text}\n```")

    # ========== 11. 交互元素（inputs操作） ==========
    if "inputs" in data:
        # 交互元素的原始 DOM 信息
        inputs = data["inputs"]
        if isinstance(inputs, list) and inputs:
            lines.append(f"\n**交互元素** (共 {len(inputs)} 个):")
            for idx, inp in enumerate(inputs[:20], 1):  # 最多显示20个
                # 构建元素描述 - 展示所有可用属性
                parts = [f"<{inp.get('tag', '')}>"]

                if inp.get("type"):
                    parts.append(f"type={inp['type']}")
                if inp.get("id"):
                    parts.append(f"id={inp['id']}")
                if inp.get("name"):
                    parts.append(f"name={inp['name']}")
                if inp.get("placeholder"):
                    parts.append(f"placeholder={inp['placeholder']}")
                if inp.get("className"):
                    parts.append(f"class={inp['className']}")
                if inp.get("text"):
                    parts.append(f"text={inp['text']}")

                lines.append(f"  **元素 {idx}**: {' '.join(parts)}")

            if len(inputs) > 20:
                lines.append(f"\n... 还有 {len(inputs) - 20} 个元素")

    # ========== 12. 表单信息（forms操作） ==========
    if "forms" in data:
        # 表单信息
        forms = data["forms"]
        if isinstance(forms, list) and forms:
            lines.append(f"\n**表单信息** (共 {len(forms)} 个):")
            for idx, form in enumerate(forms, 1):
                action = form.get("action", "")
                method = form.get("method", "")
                field_count = form.get("field_count", 0)
                lines.append(f"  **表单 {idx}**: action={action}, method={method}, 字段数={field_count}")

    # ========== 13. 截图（markdown_image/image_url） ==========
    if "markdown_image" in data:
        lines.append(f"\n**截图**: {data['markdown_image']}")
    elif "image_url" in data:
        # 备选：如果没有 markdown_image，使用 image_url
        lines.append(f"\n**截图链接**: {data['image_url']}")

    # ========== 14. 其他字段（兜底处理） ==========
    # 处理尚未明确处理的字段，确保所有数据都能传递给LLM
    handled_fields = {
        "result", "code", "snapshot", "refs", "stats", "page_info",
        "url", "title", "action", "ref", "conditions_applied",
        "text", "length", "truncated", "inputs", "forms",
        "markdown_image", "image_url", "type", "refs_provided", "ok", "format"
    }

    unhandled_fields = set(data.keys()) - handled_fields
    if unhandled_fields:
        lines.append(f"\n**其他信息**:")
        for field in sorted(unhandled_fields):
            value = data[field]
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"  {field}: {value}")
            elif isinstance(value, list):
                lines.append(f"  {field}: (列表，{len(value)}项)")
            elif isinstance(value, dict):
                lines.append(f"  {field}: (字典，{len(value)}个键)")
            else:
                lines.append(f"  {field}: {type(value).__name__}")

    return lines
