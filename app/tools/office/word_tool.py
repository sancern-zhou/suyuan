"""
Word Win32 Tool - LLM Tool 包装器

将 WordWin32Tool 包装为符合 LLMTool 接口的工具
支持分页读取，LLM可以指定读取范围
"""

from typing import Dict, Any, List
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

logger = structlog.get_logger()


class WordWin32LLMTool(LLMTool):
    """
    Word 自动化工具（LLM Tool 接口）

    支持：
    - 分页读取 Word 文档内容
    - 替换文本
    - 读取表格
    - 获取文档统计

    分页读取设计：
    - start_index: 起始段落索引（从0开始）
    - end_index: 结束段落索引（不包含）
    - max_chars: 最大读取字符数（用于分页）
    - 返回 has_more 和 next_start，支持连续读取
    """

    # 默认配置
    DEFAULT_MAX_CHARS = 5000  # 默认每次读取5000字符

    def __init__(self):
        super().__init__(
            name="word_processor",
            description="""Word文档编辑工具（Windows）

操作类型：
- read: 读取文档（start_index起始段, end_index结束段, max_chars最大字符数）
- extract_images: 提取图片（提取文档中的所有图片到 backend_data_registry/temp_images）
  返回图片列表：index（索引）、path（文件路径）、width（宽度）、height（高度）
  配合 analyze_image 工具进行图片分析
  示例：{"path": "D:\\\\docs.docx", "operation": "extract_images"}
- insert: 插入文本（position位置: end/start/after/before, target目标文本用于after/before, content插入内容）
- search_and_replace: 搜索替换（search_text查找文本, replace_text替换内容, use_wildcards通配符匹配）
- tables: 读取表格（返回完整数据）
- stats: 统计信息

【extract_images 操作说明】
- 提取文档中的所有 InlineShapes（内嵌图片）
- 图片保存为 PNG 格式到 backend_data_registry/temp_images 目录
- 返回每张图片的 index、path、width、height 信息
- 典型工作流：
  1. word_processor(operation="extract_images") → 获取图片列表
  2. 根据需求选择图片（如 index=0,2 表示第1和第3张）
  3. analyze_image(path="xxx_image_0.png") → 分析选中的图片

【insert操作最佳实践】
1. 优先使用 position="end" 或 "start" 避免匹配失败
2. 使用 after/before 时，target必须精确匹配文档中的文本
3. 建议：先用read操作查看文档，复制准确的目标文本作为target
4. 如需在特定段落插入，考虑使用search_and_replace替换段落内的唯一标识

示例：{"path": "D:\\\\docs.docx", "operation": "insert", "position": "end", "content": "追加内容"}
""",
            category=ToolCategory.QUERY,
            version="2.4.0",
            requires_context=False  # 不需要Context，直接读取文件
        )
        self._word_tool = None

    def _get_tool(self):
        """获取 Word 工具实例（延迟初始化）"""
        if self._word_tool is None:
            self._word_tool = WordWin32Tool(visible=False)
        return self._word_tool

    async def execute(
        self,
        path: str,
        operation: str = "read",
        start_index: int = 0,
        end_index: int = None,
        max_chars: int = None,
        search_text: str = None,
        replace_text: str = None,
        save_as: str = None,
        replacements: dict = None,
        match_case: bool = False,
        match_whole_word: bool = False,
        use_wildcards: bool = False,
        target_type: str = "text",
        target_index: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Word 操作

        Args:
            path: Word 文档路径
            operation: 操作类型（read/insert/search_and_replace/tables/stats/batch_replace）
            start_index: 起始段落索引（用于read）
            end_index: 结束段落索引（用于read）
            max_chars: 最大读取字符数（用于read，默认5000）
            search_text: 查找文本（search_and_replace操作必需）
            replace_text: 替换文本（search_and_replace操作，默认空即删除）
            save_as: 另存为路径（可选）
            replacements: 批量替换字典（batch_replace操作）
            match_case: 是否区分大小写
            match_whole_word: 是否全字匹配
            use_wildcards: 是否使用通配符（*匹配任意字符，[]匹配字符集）

        Returns:
            操作结果字典（UDF v2.0 格式）
        """
        try:
            word = self._get_tool()

            # 特殊处理 read 操作，支持分页
            if operation == "read":
                result = await self._read_with_pagination(
                    word,
                    path,
                    start_index,
                    end_index,
                    max_chars
                )
                # ✅ 每次操作后关闭 Word 实例
                word.close_app()
                return result

            elif operation == "insert":
                # 验证必需参数
                content = kwargs.get("content", "")
                if not content:
                    return {
                        "success": False,
                        "data": {"path": path, "error": "缺少 content 参数"},
                        "summary": "insert 操作需要 content 参数"
                    }

                # 调用底层工具
                insert_kwargs = {
                    "content": content,
                    "position": kwargs.get("position", "end"),
                    "target": kwargs.get("target"),
                    "target_type": target_type,  # 直接使用参数，不从kwargs获取
                    "target_index": target_index  # 直接使用参数，不从kwargs获取
                }
                if save_as:
                    insert_kwargs["save_as"] = save_as

                result = word.process_file(path, operation=operation, **insert_kwargs)
                # ✅ 简化返回格式
                formatted_result = self._simplify_result(result, path)
                # ✅ 每次操作后关闭 Word 实例
                word.close_app()
                return formatted_result

            elif operation == "extract_images":
                # 提取图片操作
                extract_kwargs = {}
                if kwargs.get("output_dir"):
                    extract_kwargs["output_dir"] = kwargs["output_dir"]

                result = word.extract_images(path, **extract_kwargs)
                formatted_result = self._simplify_result(result, path)
                word.close_app()
                return formatted_result

            elif operation == "search_and_replace":
                # 验证必需参数
                if not search_text:
                    return {
                        "success": False,
                        "data": {"path": path, "error": "缺少 search_text 参数"},
                        "summary": "search_and_replace 操作需要 search_text 参数"
                    }

                # 调用底层工具
                search_kwargs = {
                    "search_text": search_text,
                    "replace_text": replace_text or "",
                    "match_case": match_case,
                    "match_whole_word": match_whole_word,
                    "use_wildcards": use_wildcards
                }
                if save_as:
                    search_kwargs["save_as"] = save_as

                result = word.process_file(path, operation=operation, **search_kwargs)
                formatted_result = self._simplify_result(result, path)
                # ✅ 每次操作后关闭 Word 实例
                word.close_app()
                return formatted_result

            else:
                # 其他操作直接调用底层工具
                result = word.process_file(path, operation=operation, **kwargs)
                formatted_result = self._simplify_result(result, path)
                # ✅ 每次操作后关闭 Word 实例
                word.close_app()
                return formatted_result

        except Exception as e:
            logger.error("word_tool_failed", path=path, operation=operation, error=str(e))
            # ✅ 发生错误时也要尝试关闭 Word
            if 'word' in locals() and word:
                try:
                    word.close_app()
                except:
                    pass
            return {
                "success": False,
                "data": {
                    "path": path,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                "summary": f"Word 操作失败: {str(e)[:50]}"
            }

    async def _read_with_pagination(
        self,
        word: WordWin32Tool,
        path: str,
        start_index: int,
        end_index: int,
        max_chars: int
    ) -> Dict[str, Any]:
        """
        分页读取 Word 文档

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "path": "...",
                    "content": "读取的内容",
                    "paragraphs": ["段落1", "段落2", ...],
                    "range": {
                        "start": 0,
                        "end": 10,
                        "total": 117
                    },
                    "has_more": true,
                    "next_start": 10,
                    "stats": {...}
                },
                "metadata": {...},
                "summary": "读取第1-10段（共117段）"
            }
        """
        import time
        start_time = time.time()

        # 先读取整个文档
        full_result = word.read_all_text(path)

        if full_result.get("status") != "success":
            return self._simplify_result(full_result, path)

        all_paragraphs = full_result.get("paragraphs", [])
        total_paragraphs = len(all_paragraphs)
        total_chars = len(full_result.get("text", ""))

        # 确定读取范围
        if end_index is None:
            if max_chars:
                # 按字符数限制计算结束索引
                end_index = self._find_end_index_by_chars(
                    all_paragraphs,
                    start_index,
                    max_chars
                )
            else:
                # 默认读取剩余所有
                end_index = total_paragraphs

        # 边界检查
        start_index = max(0, min(start_index, total_paragraphs))
        end_index = max(start_index, min(end_index, total_paragraphs))

        # 提取指定范围的段落
        selected_paragraphs = all_paragraphs[start_index:end_index]
        selected_text = "\n\n".join(selected_paragraphs)

        # 检查是否还有更多内容
        has_more = end_index < total_paragraphs
        next_start = end_index if has_more else None

        execution_time = time.time() - start_time

        return {
            "success": True,
            "data": {
                "path": path,
                "content": selected_text,
                "paragraphs": selected_paragraphs,
                "range": {
                    "start": start_index,
                    "end": end_index,
                    "total": total_paragraphs
                },
                "has_more": has_more,
                "next_start": next_start,
                "stats": {
                    "paragraphs_read": len(selected_paragraphs),
                    "chars_read": len(selected_text),
                    "total_paragraphs": total_paragraphs,
                    "total_chars": total_chars,
                    "execution_time": execution_time
                }
            },
            "summary": self._generate_read_summary(
                start_index,
                end_index,
                total_paragraphs,
                has_more
            )
        }

    def _find_end_index_by_chars(
        self,
        paragraphs: List[str],
        start: int,
        max_chars: int
    ) -> int:
        """根据字符数限制找到结束索引"""
        char_count = 0
        for i in range(start, len(paragraphs)):
            char_count += len(paragraphs[i]) + 2  # +2 for "\n\n"
            if char_count > max_chars:
                return i
        return len(paragraphs)

    def _generate_read_summary(
        self,
        start: int,
        end: int,
        total: int,
        has_more: bool
    ) -> str:
        """生成读取操作的摘要信息"""
        summary = f"读取第{start+1}-{end}段（共{total}段）"
        if has_more:
            summary += f"，还有{total-end}段未读取"
        return summary

    def _simplify_result(
        self,
        result: Dict[str, Any],
        path: str
    ) -> Dict[str, Any]:
        """
        简化底层工具的返回结果（移除不必要的 UDF v2.0 字段）

        Office 工具不需要复杂的数据格式，只需简单的 {success, data, summary}
        """
        success = result.get("status") == "success"

        # 简化格式
        simplified = {
            "success": success,
            "data": None,
            "summary": result.get("summary", "Word 操作完成")
        }

        # 处理成功情况：保留完整数据
        if success:
            # 排除已处理的字段
            simplified["data"] = {
                k: v for k, v in result.items()
                if k not in ["status", "summary"]
            }
            # 添加路径信息
            if "path" not in simplified["data"]:
                simplified["data"]["path"] = path

        # 处理失败情况：返回错误信息
        else:
            simplified["data"] = {
                "path": path,
                "error": result.get("error", "操作失败")
            }

        return simplified

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "word_processor",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Word文档完整路径"
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["read", "insert", "search_and_replace", "tables", "stats", "batch_replace"],
                        "description": "操作类型：read/insert/search_and_replace/tables/stats/batch_replace"
                    },
                    "content": {
                        "type": "string",
                        "description": "插入内容（insert操作必需）"
                    },
                    "position": {
                        "type": "string",
                        "enum": ["end", "start", "after", "before"],
                        "description": "插入位置：end=末尾, start=开头, after=目标后, before=目标前"
                    },
                    "target": {
                        "type": "string",
                        "description": "目标文本（position=after/before时必需，需精确匹配文档）"
                    },
                    "start_index": {
                        "type": "integer",
                        "description": "起始段落索引（从0开始，用于read操作）"
                    },
                    "end_index": {
                        "type": "integer",
                        "description": "结束段落索引（不包含，用于read操作）"
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最大读取字符数（默认5000，用于read操作）"
                    },
                    "search_text": {
                        "type": "string",
                        "description": "查找文本（search_and_replace操作必需，支持通配符）"
                    },
                    "replace_text": {
                        "type": "string",
                        "description": "替换文本（search_and_replace操作，默认空即删除）"
                    },
                    "save_as": {
                        "type": "string",
                        "description": "另存为路径（可选，默认覆盖原文件）"
                    },
                    "replacements": {
                        "type": "object",
                        "description": "批量替换字典（batch_replace操作，如{\"旧1\":\"新1\", \"旧2\":\"新2\"}）"
                    },
                    "match_case": {
                        "type": "boolean",
                        "description": "是否区分大小写（search_and_replace操作）"
                    },
                    "match_whole_word": {
                        "type": "boolean",
                        "description": "是否全字匹配（用于 search_and_replace 操作）"
                    },
                    "use_wildcards": {
                        "type": "boolean",
                        "description": "是否使用通配符（用于 search_and_replace 操作，如 *臭氧* 匹配包含\"臭氧\"的任意文本）"
                    },
                    "target_type": {
                        "type": "string",
                        "enum": ["text", "table", "image"],
                        "description": "目标类型（用于 insert 操作的 position=after/before）：text=文本目标（默认）, table=表格目标, image=图片目标"
                    },
                    "target_index": {
                        "type": "integer",
                        "description": "目标索引（从0开始，用于 insert 操作且 target_type=table/image 时）"
                    }
                },
                "required": ["path", "operation"]
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用（仅 Windows）"""
        import os
        return os.name == 'nt'  # Windows 系统
