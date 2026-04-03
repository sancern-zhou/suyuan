"""
办公工具格式化器

处理办公助理工具的结果格式化，完整传递数据给LLM。
"""

from typing import Dict, Any, List
import json
import os

from .base import ObservationFormatter


class ImageFormatter(ObservationFormatter):
    """图片分析工具格式化器（analyze_image）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "analyze_image" and "analysis" in data

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []
        lines.append(f"**完整分析结果**:\n{data['analysis']}")
        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 10  # 高优先级


class FileFormatter(ObservationFormatter):
    """文件读取工具格式化器（read_file）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "read_file"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []
        file_type = data.get("type", "")

        if file_type == "image":
            # 图片文件：显示分析结果
            if "analysis" in data:
                lines.append(f"**图片分析结果**:\n{data['analysis']}")
            elif "analysis_error" in data:
                lines.append(f"**分析失败**: {data['analysis_error']}")
            # 显示图片信息
            lines.append(f"\n**图片信息**:")
            lines.append(f"  路径: `{data.get('path', 'N/A')}`")
            lines.append(f"  格式: {data.get('format', 'N/A')}")
            lines.append(f"  大小: {data.get('size', 0)} bytes")
        elif "content" in data:
            # 文本文件：显示完整的文件内容
            lines.append(f"**文件内容**:\n{data['content']}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 11


class GrepFormatter(ObservationFormatter):
    """文件内容搜索工具格式化器（grep）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "grep"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "results" in data:
            results = data["results"]
            total_matches = data.get("total_matches", 0)
            lines.append(f"**搜索结果** (共 {total_matches} 处匹配):")
            if isinstance(results, list):
                for result in results[:50]:  # 最多显示前50个结果
                    if isinstance(result, dict):
                        file_path = result.get("file", "")
                        line_num = result.get("line", "")
                        content = result.get("content", "")
                        lines.append(f"\n`{file_path}:{line_num}`: {content}")
                    else:
                        lines.append(f"  {result}")
                if len(results) > 50:
                    lines.append(f"\n... 还有 {len(results) - 50} 个结果")
        elif "output_text" in data:
            # 文本输出模式
            lines.append(f"**搜索结果**:\n{data['output_text']}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 12


class GlobFormatter(ObservationFormatter):
    """文件名搜索工具格式化器（glob/search_files）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator in ["glob", "search_files"]

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "files" in data:
            files = data["files"]
            count = data.get("count", len(files))
            lines.append(f"**找到的文件** (共 {count} 个):")
            if isinstance(files, list):
                for file in files[:100]:  # 最多显示前100个文件
                    lines.append(f"  - {file}")
                if len(files) > 100:
                    lines.append(f"\n... 还有 {len(files) - 100} 个文件")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 13


class ListDirectoryFormatter(ObservationFormatter):
    """目录列表工具格式化器（list_directory）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "list_directory"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "entries" in data:
            entries = data["entries"]
            count = data.get("count", len(entries))
            lines.append(f"**目录内容** (共 {count} 项):")
            if isinstance(entries, list):
                for entry in entries[:100]:  # 最多显示前100项
                    if isinstance(entry, dict):
                        name = entry.get("name", "")
                        entry_type = entry.get("type", "")
                        size = entry.get("size", "")
                        type_icon = "📁" if entry_type == "directory" else "📄"
                        size_str = f" ({size} bytes)" if size else ""
                        lines.append(f"  {type_icon} {name}{size_str}")
                    else:
                        lines.append(f"  {entry}")
                if len(entries) > 100:
                    lines.append(f"\n... 还有 {len(entries) - 100} 项")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 14


class BrowserFormatter(ObservationFormatter):
    """浏览器工具格式化器（browser）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "browser"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        # 使用统一的格式化函数处理所有浏览器操作
        from app.agent.core.browser_result_formatter import format_browser_result
        return format_browser_result(data)

    @classmethod
    def get_priority(cls) -> int:
        return 15


class TodoWriteFormatter(ObservationFormatter):
    """任务管理工具格式化器（TodoWrite）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "TodoWrite"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "rendered" in data:
            # Display the formatted todo list
            lines.append(f"**任务清单**:")
            lines.append(data["rendered"])
        elif "task_id" in data:
            # get_task/update_task/create_task 工具：显示单个任务
            task_id = data.get("task_id", "N/A")
            subject = data.get("subject", "无标题")
            status = data.get("status", "unknown")
            description = data.get("description", "")
            progress = data.get("progress", 0)
            depends_on = data.get("depends_on", [])

            lines.append(f"**任务ID**: {task_id}")
            lines.append(f"**标题**: {subject}")
            lines.append(f"**状态**: {status}")
            if progress > 0:
                lines.append(f"**进度**: {progress}%")
            if description:
                lines.append(f"**描述**: {description}")
            if depends_on:
                lines.append(f"**依赖**: {', '.join(depends_on)}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 16


class ExecutePythonFormatter(ObservationFormatter):
    """Python代码执行工具格式化器（execute_python）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "execute_python"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "output" in data and data["output"]:
            lines.append(f"**代码输出**:\n{data['output']}")
        if "files" in data and data["files"]:
            lines.append(f"\n**生成的文件**:")
            for file_path in data["files"]:
                file_name = os.path.basename(file_path)
                lines.append(f"  - {file_name}")
                lines.append(f"    路径: `{file_path}`")

        # ✅ 从 visuals 生成图表 markdown（用于 LLM 阅读）
        # visuals 信息通过 metadata 传递
        visuals = metadata.get("visuals", [])
        if visuals:
            lines.append(f"\n**✅ 图表生成成功** (共 {len(visuals)} 个):")
            for viz in visuals:
                viz_type = viz.get("type", "unknown")
                title = viz.get("title", "图表")

                if viz_type == "image":
                    # matplotlib 图片
                    url = viz["data"].get("url")
                    if url:
                        lines.append(f"- {title}: ![Chart]({url})")
                    elif viz["data"].get("file_path"):
                        lines.append(f"- {title}: `{viz['data']['file_path']}` (缓存失败)")
                elif viz_type in ["line", "bar", "pie", "scatter", "heatmap", "map", "wind_rose", "profile"]:
                    # Chart v3.1 ECharts 配置
                    lines.append(f"- {title} (Chart v3.1 - {viz_type})")
                    lines.append(f"  图表ID: {viz.get('id')}")
                    lines.append(f"  数据字段: {list(viz.get('data', {}).keys())}")
                else:
                    lines.append(f"- {title} ({viz_type})")

            # 明确告诉 LLM 任务已完成
            lines.append(f"\n⚠️ **图表已成功生成，请使用 FINAL_ANSWER 向用户展示结果，不要再次执行 execute_python**")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 17


class WebSearchFormatter(ObservationFormatter):
    """网络搜索工具格式化器（web_search）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "web_search"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "results_text" in data:
            lines.append(f"**搜索结果**:\n{data['results_text']}")
        # 显示其他元数据
        if "provider" in data:
            lines.append(f"\n**搜索来源**: {data['provider']}")
        if "count" in data:
            lines.append(f"**结果数量**: {data['count']}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 18


class WebFetchFormatter(ObservationFormatter):
    """网页抓取工具格式化器（web_fetch）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "web_fetch"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "text" in data:
            lines.append(f"**网页内容**:\n{data['text']}")
        # 显示其他元数据
        if "final_url" in data:
            lines.append(f"\n**最终URL**: {data['final_url']}")
        if "status" in data:
            lines.append(f"**HTTP状态码**: {data['status']}")
        if "length" in data:
            lines.append(f"**内容长度**: {data['length']} 字符")
        if "extractor" in data:
            lines.append(f"**抓取方式**: {data['extractor']}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 19


class SearchHistoryFormatter(ObservationFormatter):
    """搜索历史工具格式化器（search_history）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "search_history"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "results" in data and isinstance(data["results"], list):
            results = data["results"]
            lines.append(f"**搜索结果** (共 {len(results)} 条):")
            for idx, result in enumerate(results[:20], 1):  # 最多显示前20条
                if isinstance(result, dict):
                    match = result.get("match", "")
                    context = result.get("context", "")
                    line_number = result.get("line_number", 0)
                    lines.append(f"\n{idx}. **匹配内容**: {match}")
                    if context:
                        lines.append(f"   **上下文**: {context[:200]}...")  # 限制上下文长度
                    if line_number:
                        lines.append(f"   **行号**: {line_number}")
            if len(results) > 20:
                lines.append(f"\n... 还有 {len(results) - 20} 条结果")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 20
