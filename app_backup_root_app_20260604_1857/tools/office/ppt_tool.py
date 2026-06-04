"""
PowerPoint Win32 Tool - LLM Tool 包装器

将 PPTWin32Tool 包装为符合 LLMTool 接口的工具
支持分页读取，LLM可以指定读取范围
"""

from typing import Dict, Any
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.ppt_win32_tool import PPTWin32Tool
import structlog

logger = structlog.get_logger()


class PPTWin32LLMTool(LLMTool):
    """
    PowerPoint 自动化工具（LLM Tool 接口）

    支持：
    - 分页读取幻灯片内容
    - 替换文本
    - 列出幻灯片
    - 获取演示文稿统计

    分页读取设计：
    - start_slide: 起始幻灯片编号（从1开始）
    - end_slide: 结束幻灯片编号（不包含）
    - max_slides: 最大读取幻灯片数（用于分页）
    """

    # 默认配置
    DEFAULT_MAX_SLIDES = 10  # 默认每次读取10张幻灯片

    def __init__(self):
        super().__init__(
            name="ppt_processor",
            description="读取和编辑 PowerPoint 演示文稿（仅 Windows）。支持分页读取、搜索并替换、列出幻灯片、获取统计信息。",
            category=ToolCategory.QUERY,
            version="2.2.0",
            requires_context=False  # 不需要Context，直接读取文件
        )
        self._ppt_tool = None

    def _get_tool(self):
        """获取 PPT 工具实例（延迟初始化）"""
        if self._ppt_tool is None:
            self._ppt_tool = PPTWin32Tool(visible=False)
        return self._ppt_tool

    async def execute(
        self,
        file_path: str,
        operation: str = "list_slides",
        start_slide: int = 1,
        end_slide: int = None,
        max_slides: int = None,
        search_text: str = None,
        replace_text: str = None,
        save_as: str = None,
        match_case: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 PowerPoint 操作

        Args:
            file_path: PowerPoint 文件路径
            operation: 操作类型
                - list_slides: 列出幻灯片
                - read: 读取内容（支持分页）
                - search_and_replace: 搜索并替换
                - stats: 获取统计信息
            start_slide: 起始幻灯片编号（用于分页读取，从1开始）
            end_slide: 结束幻灯片编号（用于分页读取，不包含）
            max_slides: 最大读取幻灯片数（用于分页读取）
            search_text: 要查找的文本（用于 search_and_replace 操作）
            replace_text: 替换的文本（用于 search_and_replace 操作，默认为空即删除）
            save_as: 保存路径（可选）
            match_case: 是否区分大小写（用于 search_and_replace 操作）

        Returns:
            操作结果字典（UDF v2.0 格式）

        分页读取示例：
            读取前10张幻灯片:
                operation="read", start_slide=1, end_slide=11
            从第11张开始读10张:
                operation="read", start_slide=11, max_slides=10

        搜索并替换示例：
            删除文本:
                operation="search_and_replace", search_text="臭氧", replace_text=""
        """
        try:
            ppt = self._get_tool()

            # 特殊处理 read 操作，支持分页
            if operation == "read" and (start_slide > 1 or end_slide is not None or max_slides is not None):
                result = await self._read_with_pagination(
                    ppt,
                    file_path,
                    start_slide,
                    end_slide,
                    max_slides
                )
                # ✅ 每次操作后关闭 PowerPoint 实例
                ppt.close_app()
                return result

            elif operation == "search_and_replace":
                # 验证必需参数
                if not search_text:
                    return {
                        "success": False,
                        "data": {
                            "file_path": file_path,
                            "error": "缺少 search_text 参数"
                        },
                        "summary": "search_and_replace 操作需要 search_text 参数"
                    }

                # 调用底层工具
                search_kwargs = {
                    "search_text": search_text,
                    "replace_text": replace_text or "",
                    "match_case": match_case
                }
                if save_as:
                    search_kwargs["save_as"] = save_as

                result = ppt.process_file(file_path, operation=operation, **search_kwargs)
                formatted_result = self._simplify_result(result, file_path)
                # ✅ 每次操作后关闭 PowerPoint 实例
                ppt.close_app()
                return formatted_result

            else:
                # 其他操作直接调用底层工具
                result = ppt.process_file(file_path, operation=operation, **kwargs)
                formatted_result = self._simplify_result(result, file_path)
                # ✅ 每次操作后关闭 PowerPoint 实例
                ppt.close_app()
                return formatted_result

        except Exception as e:
            logger.error("ppt_tool_failed", path=file_path, operation=operation, error=str(e))
            # ✅ 发生错误时也要尝试关闭 PowerPoint
            if 'ppt' in locals() and ppt:
                try:
                    ppt.close_app()
                except:
                    pass
            return {
                "success": False,
                "data": {
                    "file_path": file_path,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                "summary": f"PowerPoint 操作失败: {str(e)[:50]}"
            }

    async def _read_with_pagination(
        self,
        ppt: PPTWin32Tool,
        file_path: str,
        start_slide: int,
        end_slide: int,
        max_slides: int
    ) -> Dict[str, Any]:
        """
        分页读取 PowerPoint 演示文稿

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "file_path": "...",
                    "slides": [
                        {"slide_number": 1, "text": "..."},
                        {"slide_number": 2, "text": "..."}
                    ],
                    "range": {
                        "start": 1,
                        "end": 10,
                        "total": 50
                    },
                    "has_more": true,
                    "next_start": 11,
                    "stats": {...}
                },
                "metadata": {...},
                "summary": "读取第1-10张幻灯片（共50张）"
            }
        """
        import time
        start_time = time.time()

        # 打开演示文稿
        app = ppt.app
        ppt.ensure_initialized()

        abs_path = ppt.get_absolute_path(file_path)
        if not ppt.check_file_exists(abs_path):
            return {
                "success": False,
                "data": {
                    "file_path": file_path,
                    "error": "文件不存在"
                },
                "summary": "文件不存在"
            }

        presentation = app.Presentations.Open(abs_path, ReadOnly=True, Visible=False)

        try:
            total_slides = presentation.Slides.Count

            # 确定读取范围
            if end_slide is None:
                if max_slides:
                    end_slide = min(start_slide + max_slides, total_slides + 1)
                else:
                    end_slide = total_slides + 1

            # 边界检查（幻灯片编号从1开始）
            start_slide = max(1, min(start_slide, total_slides))
            end_slide = max(start_slide, min(end_slide, total_slides + 1))

            # 读取指定范围的幻灯片
            slides_data = []
            for i in range(start_slide, end_slide):
                slide = presentation.Slides(i)
                text_content = ""

                # 提取所有文本框内容
                for shape in slide.Shapes:
                    if shape.HasTextFrame:
                        text_frame = shape.TextFrame
                        if text_frame.HasText:
                            text_content += text_frame.TextRange.Text + "\n"

                slides_data.append({
                    "slide_number": i,
                    "text": text_content.strip(),
                    "title": self._extract_slide_title(slide)
                })

            # 检查是否还有更多内容
            has_more = end_slide <= total_slides
            next_start = end_slide if has_more else None

            execution_time = time.time() - start_time

            # 关闭演示文稿
            presentation.Close()

            return {
                "success": True,
                "data": {
                    "file_path": file_path,
                    "slides": slides_data,
                    "range": {
                        "start": start_slide,
                        "end": end_slide - 1,  # 转换为包含式
                        "total": total_slides
                    },
                    "has_more": has_more,
                    "next_start": next_start,
                    "stats": {
                        "slides_read": len(slides_data),
                        "total_slides": total_slides,
                        "execution_time": execution_time
                    }
                },
                "summary": self._generate_read_summary(
                    start_slide,
                    end_slide - 1,
                    total_slides,
                    has_more
                )
            }

        except Exception as e:
            presentation.Close()
            raise

    def _extract_slide_title(self, slide) -> str:
        """提取幻灯片标题"""
        try:
            # 通常标题在第一个形状中
            if slide.Shapes.Count > 0:
                first_shape = slide.Shapes(1)
                if first_shape.HasTextFrame and first_shape.TextFrame.HasText:
                    return first_shape.TextFrame.TextRange.Text.strip()
        except:
            pass
        return f"幻灯片 {slide.SlideIndex}"

    def _generate_read_summary(
        self,
        start: int,
        end: int,
        total: int,
        has_more: bool
    ) -> str:
        """生成读取操作的摘要信息"""
        summary = f"读取第{start}-{end}张幻灯片（共{total}张）"
        if has_more:
            summary += f"，还有{total-end}张未读取"
        return summary

    def _simplify_result(
        self,
        result: Dict[str, Any],
        file_path: str
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
            "summary": result.get("summary", "PowerPoint 操作完成")
        }

        # 处理成功情况：保留完整数据
        if success:
            # 排除已处理的字段
            simplified["data"] = {
                k: v for k, v in result.items()
                if k not in ["status", "summary"]
            }
            # 添加路径信息
            if "file_path" not in simplified["data"]:
                simplified["data"]["file_path"] = file_path

        # 处理失败情况：返回错误信息
        else:
            simplified["data"] = {
                "file_path": file_path,
                "error": result.get("error", "操作失败")
            }

        return simplified

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "ppt_processor",
            "description": self.description + "\n\n**常用操作示例**：\n" +
                "- 列出幻灯片：{\"file_path\": \"D:\\\\docs\\\\presentation.pptx\", \"operation\": \"list_slides\"}\n" +
                "- 读取前10张：{\"file_path\": \"D:\\\\docs\\\\presentation.pptx\", \"operation\": \"read\", \"start_slide\": 1, \"max_slides\": 10}\n" +
                "- 删除文本：{\"file_path\": \"D:\\\\docs\\\\presentation.pptx\", \"operation\": \"search_and_replace\", \"search_text\": \"臭氧\", \"replace_text\": \"\"}",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "PowerPoint 文件的完整路径（如 D:\\\\docs\\\\presentation.pptx）"
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["list_slides", "read", "search_and_replace", "stats"],
                        "description": "操作类型：list_slides=列出幻灯片, read=读取内容（支持分页）, search_and_replace=搜索并替换, stats=统计信息"
                    },
                    "start_slide": {
                        "type": "integer",
                        "description": "起始幻灯片编号（从1开始），用于分页读取。例如：start_slide=1 表示从第1张幻灯片开始"
                    },
                    "end_slide": {
                        "type": "integer",
                        "description": "结束幻灯片编号（不包含），用于分页读取。例如：end_slide=11 表示读取到第10张（不含）。如果不指定，读取到演示文稿结尾或达到max_slides限制"
                    },
                    "max_slides": {
                        "type": "integer",
                        "description": "最大读取幻灯片数（用于分页读取），默认10。当指定此参数时，end_slide会被自动计算"
                    },
                    "search_text": {
                        "type": "string",
                        "description": "要查找的文本（用于 search_and_replace 操作）"
                    },
                    "replace_text": {
                        "type": "string",
                        "description": "替换后的文本（用于 search_and_replace 操作，默认为空字符串即删除）"
                    },
                    "save_as": {
                        "type": "string",
                        "description": "保存为新文件的路径（可选）"
                    },
                    "match_case": {
                        "type": "boolean",
                        "description": "是否区分大小写（用于 search_and_replace 操作）"
                    }
                },
                "required": ["file_path", "operation"]
            }
        }

    def is_available(self) -> bool:
        """检查工具工具是否可用（仅 Windows）"""
        import os
        return os.name == 'nt'  # Windows 系统
